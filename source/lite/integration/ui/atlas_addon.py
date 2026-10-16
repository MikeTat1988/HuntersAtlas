"""Resolve and launch the independently installed Hunter's Atlas package."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import zipfile


MANIFEST_NAME = 'manifest.json'
MANIFEST_ID = 'hunters-atlas-lite'
REQUIRED_PATHS = ('probe', 'maps', 'config', 'art', 'catalog', 'font')
ENV_KEYS = ('BB_PROBE', 'BB_ATLAS_ENABLED', 'BB_ATLAS_QA', 'BB_ENTER_BUTTON')
SHA256_RE = re.compile(r'^[0-9a-fA-F]{64}$')
METADATA_NAME = 'maps/generated-assets.json'
REQUIRED_MAPS = frozenset({'maps/atlas.json', 'maps/catalog.json'})


class AtlasManifestError(ValueError):
    """The Atlas package is incomplete, altered, or incompatible."""


def installed_folder(port_dir: str | os.PathLike[str]) -> str:
    """Offer the receipt-owned Atlas package when no folder is selected."""
    try:
        receipt = json.loads((Path(port_dir) / 'atlas-lite-install.json').read_text(encoding='utf-8'))
        if receipt.get('state') != 'installed':
            return ''
        folder = Path(receipt['atlas_folder'])
        if folder.is_dir() and (folder / MANIFEST_NAME).is_file():
            return str(folder.resolve())
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return ''


@dataclass(frozen=True)
class AtlasPackage:
    root: Path
    manifest: dict
    paths: dict[str, Path]
    generated_ready: bool
    generated_message: str
    lite_contract: dict

    @property
    def display_version(self) -> str:
        return str(self.manifest.get('version', 'unknown'))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def stock_probe(port_dir: str | os.PathLike[str]) -> Path | None:
    """Find the ordinary launcher's probe for the disabled Atlas path."""
    root = Path(port_dir)
    for candidate in (root / 'bin' / 'bb-probe.exe', root / 'out' / 'bb-probe.exe'):
        if candidate.is_file():
            return candidate.resolve()
    return None


def inspect_package(folder: str | os.PathLike[str], *, game_sha256: str | None = None,
                    allow_unprepared: bool = False) -> AtlasPackage:
    """Verify Atlas's pinned files and inspect its small embedded map receipt."""
    del allow_unprepared  # Atlas reports missing or mismatched maps as a readiness state.
    if not str(folder).strip():
        raise AtlasManifestError('Choose the extracted Hunter\'s Atlas folder.')
    root = Path(folder).expanduser()
    if not root.is_dir():
        raise AtlasManifestError('Select the extracted Hunter\'s Atlas folder.')
    root = root.resolve(strict=True)
    try:
        manifest = json.loads((root / MANIFEST_NAME).read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AtlasManifestError(f'Could not read {MANIFEST_NAME}: {error}') from error
    if not isinstance(manifest, dict) or manifest.get('id') != MANIFEST_ID:
        identity = manifest.get('id', 'missing') if isinstance(manifest, dict) else 'missing'
        raise AtlasManifestError(f'Expected the verified Hunter\'s Atlas package (found {identity}).')
    if not isinstance(manifest.get('version'), str) or not manifest['version'].strip():
        raise AtlasManifestError('Atlas manifest is missing its version.')

    try:
        from importlib.util import module_from_spec, spec_from_file_location
        entry_path = root / 'bootstrap' / 'entry.py'
        declared_files = manifest.get('files')
        declared_entry = declared_files.get('bootstrap/entry.py') if isinstance(declared_files, dict) else None
        if not isinstance(declared_entry, str) or not SHA256_RE.fullmatch(declared_entry):
            raise AtlasManifestError('Atlas manifest does not pin bootstrap/entry.py.')
        if sha256_file(entry_path).casefold() != declared_entry.casefold():
            raise AtlasManifestError('Atlas bootstrap entry failed its SHA-256 check.')
        spec = spec_from_file_location('_hunters_atlas_lite_entry', entry_path)
        if spec is None or spec.loader is None:
            raise AtlasManifestError('Could not load the Atlas bootstrap validator.')
        module = module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(spec.name, None)

        contract = module.load_contract(root)
        supported_games = contract.get('manifest', {}).get('game_executables')
        if not isinstance(supported_games, list) or not supported_games or not all(
                isinstance(value, str) and SHA256_RE.fullmatch(value) for value in supported_games):
            raise AtlasManifestError('Atlas package has no valid supported game fingerprints.')
        if not game_sha256:
            raise AtlasManifestError('Could not fingerprint the selected game executable (eboot.bin).')
        if game_sha256.casefold() not in {value.casefold() for value in supported_games}:
            raise AtlasManifestError('This Atlas package does not support the selected Bloodborne game build.')
        paths = {key: contract['paths'][key] for key in REQUIRED_PATHS}
        if contract.get('generator') is None:
            raise AtlasManifestError('Atlas package is missing its map preparation tool.')
        paths['generator'] = contract['generator']
        generated_ready, generated_message = _asset_readiness(contract, game_sha256)
        return AtlasPackage(root=root, manifest=manifest, paths=paths,
                            generated_ready=generated_ready, generated_message=generated_message,
                            lite_contract=contract)
    except AtlasManifestError:
        raise
    except Exception as error:
        raise AtlasManifestError(f'Could not verify the Hunter\'s Atlas package: {error}') from error


def _asset_readiness(contract: dict, game_sha256: str) -> tuple[bool, str]:
    """Read a bounded receipt from the hash-verified archive without expanding it."""
    pack = contract.get('asset_pack')
    if not isinstance(pack, dict) or not isinstance(pack.get('path'), (str, os.PathLike)):
        return False, 'Atlas map assets are not prepared. Prepare maps for the selected game.'
    try:
        with zipfile.ZipFile(pack['path']) as archive:
            try:
                info = archive.getinfo(METADATA_NAME)
            except KeyError:
                return False, 'Atlas map pack has no generated asset metadata. Prepare maps again.'
            if info.file_size > 256 * 1024:
                raise AtlasManifestError('Atlas generated asset metadata exceeds the allowed size.')
            with archive.open(info) as stream:
                metadata = json.loads(stream.read(256 * 1024 + 1).decode('utf-8'))
    except (OSError, zipfile.BadZipFile, RuntimeError, UnicodeError, json.JSONDecodeError) as error:
        raise AtlasManifestError(f'Could not read Atlas generated asset metadata: {error}') from error
    if not isinstance(metadata, dict) or metadata.get('schema') != 1 or metadata.get('version') != 1:
        raise AtlasManifestError('Atlas generated asset metadata has an unsupported schema/version.')
    packed_game = metadata.get('game_eboot_sha256')
    if not isinstance(packed_game, str) or not SHA256_RE.fullmatch(packed_game):
        raise AtlasManifestError('Atlas generated asset metadata has no valid game fingerprint.')
    outputs = metadata.get('files')
    if not isinstance(outputs, dict) or not REQUIRED_MAPS.issubset(outputs):
        return False, 'Atlas map pack is incomplete. Prepare maps for the selected game.'
    if contract.get('manifest', {}).get('feature_schema') == 1 and (
            metadata.get('feature_schema') != 1 or 'maps/features.json' not in outputs):
        return False, 'Prepare Atlas maps to add lamp, pickup, NPC and boss metadata.'
    if packed_game.casefold() != game_sha256.casefold():
        return False, 'Atlas maps were prepared for a different game build. Prepare maps for this game.'
    if contract.get('manifest',{}).get('asset_key_schema')==1 and not isinstance(metadata.get('asset_key'),dict):
        return False, 'Prepare Atlas maps to record their reusable input identity.'
    return True, 'Atlas map assets are prepared for the selected game and hash-verified.'


def atlas_environment(base_environment: dict[str, str], *, enabled: bool,
                      package: AtlasPackage | None = None, enter_button: str = '1',
                      features: dict | None = None) -> dict[str, str]:
    """Build the child environment for Atlas while removing inherited map hooks."""
    env = dict(base_environment)
    reserved = {value.upper() for value in ENV_KEYS} | {'BB_LITE_PACKAGE', 'BB_PAD_FILE', 'BB_DUMP_DIR'}
    for key in list(env):
        normalized = key.upper()
        if normalized in reserved or normalized.startswith('BB_MAP_') or normalized == 'BB_ATLAS_FEATURES':
            env.pop(key, None)
    env['BB_ATLAS_ENABLED'] = '1' if enabled else '0'
    if not enabled:
        return env
    if package is None:
        raise AtlasManifestError('Hunter\'s Atlas is enabled but its package is not valid.')
    if not package.generated_ready:
        raise AtlasManifestError(package.generated_message)
    if package.lite_contract is None:
        raise AtlasManifestError('Selected package is not Hunter\'s Atlas.')
    if enter_button not in ('0', '1'):
        raise AtlasManifestError('Choose Cross (A) or Circle (B) as the confirm button.')
    env['BB_LITE_PACKAGE'] = str(package.root)
    env['BB_ENTER_BUTTON'] = enter_button
    import importlib.util
    feature_path = Path(__file__).with_name('atlas_feature_config.py')
    spec = importlib.util.spec_from_file_location('atlas_feature_config', feature_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    env.update(module.environment(features or {}))
    return env


def rebuild_pending(folder):
    try:return bool(json.loads((Path(folder)/'manifest.json').read_text(encoding='utf-8')).get('runtime_pending'))
    except (OSError,ValueError):return False


def package_status(folder: str | os.PathLike[str], *, game_executable: str | os.PathLike[str]) -> tuple[AtlasPackage | None, str]:
    """Return readiness text for the launcher without exposing resolver exceptions."""
    try:
        package = inspect_package(folder, game_sha256=sha256_file(Path(game_executable)),
                                  allow_unprepared=True)
        if not package.generated_ready:
            return package, package.generated_message
        return package, f'Ready — Hunter\'s Atlas {package.display_version} verified.'
    except (OSError, AtlasManifestError) as error:
        return None, str(error)
