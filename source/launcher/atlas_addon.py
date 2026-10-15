"""Resolve and verify an independently installed Hunter's Atlas add-on."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re


MANIFEST_NAME = 'manifest.json'
MANIFEST_ID = 'hunters-atlas'
LAUNCHER_BUILD = 'windows-v1.7.2-atlas1'
RUNTIME_BUILD = 'hunters-atlas-runtime-1.4.0-beta1'
REQUIRED_PATHS = ('probe', 'maps', 'config', 'art', 'catalog', 'font')
ENV_KEYS = ('BB_PROBE', 'BB_ATLAS_ENABLED', 'BB_ATLAS_QA', 'BB_ENTER_BUTTON')
SHA256_RE = re.compile(r'^[0-9a-fA-F]{64}$')
GENERATED_ASSET_FILES = frozenset({'maps/atlas.json', 'maps/catalog.json', 'art/native-font.ttf'})
GENERATED_OUTPUT_FILES = GENERATED_ASSET_FILES | frozenset({'maps/generated-assets.json'})


class AtlasManifestError(ValueError):
    """An add-on package is incomplete, altered, or incompatible."""


@dataclass(frozen=True)
class AtlasPackage:
    root: Path
    manifest: dict
    paths: dict[str, Path]
    generated_ready: bool = True
    generated_message: str = ''
    generated_font: Path | None = None

    @property
    def display_version(self) -> str:
        return str(self.manifest.get('version', 'unknown'))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def package_file_inventory(folder: str | os.PathLike[str]) -> dict[str, str]:
    """Hash all package files to constrain the generator's final write set."""
    root = Path(folder).resolve(strict=True)
    inventory = {}
    for path in root.rglob('*'):
        if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
            raise AtlasManifestError('Atlas package folders must not contain symlinks or junctions.')
        if path.is_file():
            inventory[path.relative_to(root).as_posix().casefold()] = sha256_file(path)
    return inventory


def validate_generated_output_delta(folder: str | os.PathLike[str], before: dict[str, str]) -> None:
    """Reject generator writes outside the exact generated manifest/output allowlist."""
    after = package_file_inventory(folder)
    changed = {name for name in set(before) | set(after) if before.get(name) != after.get(name)}
    unexpected = sorted(name for name in changed if not _is_generated_output(name))
    if unexpected:
        raise AtlasManifestError(f'Atlas generator changed an unapproved package file: {unexpected[0]}.')


def _is_generated_output(name: str) -> bool:
    canonical = name.casefold()
    return (canonical in GENERATED_OUTPUT_FILES or
            re.fullmatch(r'maps/m[0-9]{2}_[0-9]{2}_[0-9]{2}_[0-9]{2}\.json', canonical) is not None)


def _is_generated_asset(name: str) -> bool:
    canonical = name.casefold()
    return (canonical in GENERATED_ASSET_FILES or
            re.fullmatch(r'maps/m[0-9]{2}_[0-9]{2}_[0-9]{2}_[0-9]{2}\.json', canonical) is not None)


def stock_probe(port_dir: str | os.PathLike[str]) -> Path | None:
    """Locate the launcher's ordinary packaged probe, preferring the release bin folder."""
    root = Path(port_dir)
    for candidate in (root / 'bin' / 'bb-probe.exe', root / 'out' / 'bb-probe.exe'):
        if candidate.is_file():
            return candidate.resolve()
    return None


def _relative_path(value: object, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or '\x00' in value:
        raise AtlasManifestError(f'{label} must be a non-empty relative path.')
    # Accept package manifests written with either separator, but reject Windows drives,
    # UNC roots, POSIX roots, and traversal before touching the filesystem.
    normalized = value.replace('\\', '/')
    if normalized.startswith('/') or re.match(r'^[A-Za-z]:', normalized):
        raise AtlasManifestError(f'{label} must stay inside the selected Atlas folder.')
    parts = normalized.split('/')
    if any(part in ('', '.', '..') or ':' in part for part in parts):
        raise AtlasManifestError(f'{label} contains an unsafe path component.')
    return PurePosixPath(*parts)


def _inside(root: Path, value: object, label: str, *, directory: bool | None = None) -> Path:
    relative = _relative_path(value, label)
    base = root.resolve(strict=True)
    candidate = base.joinpath(*relative.parts)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(base)
    except (OSError, RuntimeError, ValueError) as error:
        raise AtlasManifestError(f'{label} is missing or resolves outside the selected Atlas folder.') from error
    if directory is True and not resolved.is_dir():
        raise AtlasManifestError(f'{label} must name a folder in the Atlas package.')
    if directory is False and not resolved.is_file():
        raise AtlasManifestError(f'{label} must name a file in the Atlas package.')
    return resolved


def _manifest(root: Path) -> dict:
    manifest_path = _inside(root, MANIFEST_NAME, 'Atlas manifest', directory=False)
    try:
        value = json.loads(manifest_path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AtlasManifestError(f'Could not read {MANIFEST_NAME}: {error}') from error
    if not isinstance(value, dict):
        raise AtlasManifestError('Atlas manifest must contain a JSON object.')
    if value.get('id') != MANIFEST_ID:
        raise AtlasManifestError(f'Unsupported add-on id: {value.get("id", "missing")}.')
    if not isinstance(value.get('version'), str) or not value['version'].strip():
        raise AtlasManifestError('Atlas manifest is missing its version.')
    return value


def inspect_package(folder: str | os.PathLike[str], *, launcher_build: str = LAUNCHER_BUILD,
                    runtime_build: str = RUNTIME_BUILD, game_sha256: str | None = None,
                    allow_unprepared: bool = False) -> AtlasPackage:
    """Validate package hashes and generated local assets against the selected game."""
    root = Path(folder).expanduser()
    if not root.is_dir():
        raise AtlasManifestError('Select the extracted Hunter\'s Atlas folder.')
    root = root.resolve(strict=True)
    manifest = _manifest(root)

    launcher_builds = manifest.get('launcher_builds')
    if not isinstance(launcher_builds, list) or not all(isinstance(v, str) for v in launcher_builds):
        raise AtlasManifestError('Atlas manifest has no valid launcher_builds list.')
    if launcher_build not in launcher_builds:
        raise AtlasManifestError(f'This Atlas package does not support launcher build {launcher_build}.')
    if manifest.get('runtime_build') != runtime_build:
        raise AtlasManifestError('Atlas runtime build is incompatible with this launcher.')
    capabilities = manifest.get('capabilities')
    if not isinstance(capabilities, list) or not all(isinstance(value, str) for value in capabilities):
        raise AtlasManifestError('Atlas manifest has no valid capabilities list.')

    game_hashes = manifest.get('game_executables')
    if not isinstance(game_hashes, list) or not game_hashes or not all(
            isinstance(v, str) and SHA256_RE.fullmatch(v) for v in game_hashes):
        raise AtlasManifestError('Atlas manifest has no valid supported game executable fingerprints.')
    if not game_sha256:
        raise AtlasManifestError('Could not fingerprint the selected game executable (Image0/eboot.bin).')
    if game_sha256.lower() not in {value.lower() for value in game_hashes}:
        raise AtlasManifestError('This Atlas package does not support the selected Bloodborne game build.')

    raw_paths = manifest.get('paths')
    if not isinstance(raw_paths, dict) or any(not isinstance(raw_paths.get(key), str) for key in REQUIRED_PATHS):
        raise AtlasManifestError('Atlas manifest must define probe, maps, config, art, catalog, and font paths.')
    path_kinds = {'probe': False, 'maps': True, 'config': False, 'art': True, 'font': False}
    resolved_paths = {key: _inside(root, raw_paths[key], f'paths.{key}', directory=path_kinds[key])
                      for key in REQUIRED_PATHS if key != 'catalog'}
    catalog_relative = _relative_path(raw_paths['catalog'], 'paths.catalog')
    if catalog_relative.as_posix().casefold() != 'maps/catalog.json':
        raise AtlasManifestError('paths.catalog must point to generated maps/catalog.json.')
    resolved_paths['catalog'] = root.joinpath(*catalog_relative.parts)

    mutable_files = manifest.get('mutable_files')
    if not isinstance(mutable_files, list) or not all(isinstance(value, str) for value in mutable_files):
        raise AtlasManifestError('Atlas manifest must list its mutable shortcut settings file.')
    mutable_names = {_relative_path(name, 'mutable file path').as_posix().casefold() for name in mutable_files}
    config_relative = _relative_path(raw_paths['config'], 'paths.config').as_posix().casefold()
    if mutable_names != {config_relative}:
        raise AtlasManifestError('Only the package shortcut settings file may be mutable.')

    files = manifest.get('files')
    if not isinstance(files, dict) or not files:
        raise AtlasManifestError('Atlas manifest has no file hash list.')
    hashed: dict[str, str] = {}
    for raw_name, expected_hash in files.items():
        path = _inside(root, raw_name, f'files[{raw_name!r}]', directory=False)
        if not isinstance(expected_hash, str) or not SHA256_RE.fullmatch(expected_hash):
            raise AtlasManifestError(f'Invalid SHA-256 value for {raw_name}.')
        canonical = _relative_path(raw_name, 'file hash path').as_posix().casefold()
        if canonical in hashed:
            raise AtlasManifestError(f'Duplicate package file entry: {raw_name}.')
        if canonical in mutable_names:
            raise AtlasManifestError('The mutable shortcut settings file must not have an immutable hash entry.')
        actual = sha256_file(path)
        if actual.lower() != expected_hash.lower():
            raise AtlasManifestError(f'Atlas file failed its SHA-256 check: {raw_name}.')
        hashed[canonical] = actual

    probe_relative = _relative_path(raw_paths['probe'], 'paths.probe').as_posix().casefold()
    if probe_relative not in hashed:
        raise AtlasManifestError('The runtime probe is missing from the manifest file hash list.')
    for key in ('font',):
        relative = _relative_path(raw_paths[key], f'paths.{key}').as_posix().casefold()
        if relative not in hashed:
            raise AtlasManifestError(f'The {key} file is missing from the manifest file hash list.')
    for key in ('art',):
        prefix = _relative_path(raw_paths[key], f'paths.{key}').as_posix().casefold().rstrip('/') + '/'
        if not any(name.startswith(prefix) for name in hashed):
            raise AtlasManifestError(f'The {key} folder has no files listed in the manifest.')

    generated = manifest.get('generated')
    if not isinstance(generated, dict):
        raise AtlasManifestError('Atlas manifest must declare its local generated assets.')
    generated_manifest = generated.get('manifest')
    generated_manifest_rel = _relative_path(generated_manifest, 'generated.manifest')
    if generated_manifest_rel.as_posix().casefold() != 'maps/generated-assets.json':
        raise AtlasManifestError('Generated asset manifest must be maps/generated-assets.json.')
    required_generated = generated.get('required')
    if not isinstance(required_generated, list) or {
            _relative_path(value, 'generated.required path').as_posix().casefold()
            for value in required_generated if isinstance(value, str)
    } != {'maps/atlas.json', 'maps/catalog.json'} or len(required_generated) != 2:
        raise AtlasManifestError('Generated asset manifest must require maps/atlas.json and maps/catalog.json.')
    generator_relative = _relative_path(generated.get('generator'), 'generated.generator')
    generator_path = _inside(root, generated_relative := generator_relative.as_posix(),
                             'generated.generator', directory=False)
    generator_name = generator_relative.as_posix().casefold()
    if generator_name not in hashed:
        raise AtlasManifestError('The local asset generator must be listed in immutable package hashes.')
    allowed_generated = set(GENERATED_ASSET_FILES)
    generated_manifest_path = root.joinpath(*generated_manifest_rel.parts)
    if generated_manifest_rel.as_posix().casefold() in hashed or any(
            _is_generated_asset(name) for name in hashed):
        raise AtlasManifestError('Generated map/font outputs must use generated-assets.json, not package file hashes.')
    generated_files: dict[str, str] = {}
    generated_ready = False
    generated_message = 'Local Atlas maps have not been prepared for this game folder.'
    native_font = None
    if generated_manifest_path.exists():
        try:
            _inside(root, generated_manifest, 'generated manifest', directory=False)
            output = json.loads(generated_manifest_path.read_text(encoding='utf-8'))
            if not isinstance(output, dict) or output.get('schema') != 1 or output.get('version') != 1:
                raise AtlasManifestError('Generated asset manifest has an unsupported schema/version.')
            output_hash = output.get('game_eboot_sha256')
            if not isinstance(output_hash, str) or not SHA256_RE.fullmatch(output_hash):
                raise AtlasManifestError('Generated asset manifest has no valid game fingerprint.')
            if not isinstance(output.get('game_version'), str) or not output['game_version'].strip():
                raise AtlasManifestError('Generated asset manifest has no game-version label.')
            output_files = output.get('files')
            if not isinstance(output_files, dict) or not output_files:
                raise AtlasManifestError('Generated asset manifest has no output file hash list.')
            for name, expected_hash in output_files.items():
                relative = _relative_path(name, f'generated.files[{name!r}]').as_posix().casefold()
                if not _is_generated_asset(relative):
                    raise AtlasManifestError(f'Generated asset is outside the allowed output list: {name}.')
                if not isinstance(expected_hash, str) or not SHA256_RE.fullmatch(expected_hash):
                    raise AtlasManifestError(f'Invalid generated SHA-256 value for {name}.')
                output_path = _inside(root, name, f'generated.files[{name!r}]', directory=False)
                actual_hash = sha256_file(output_path)
                if actual_hash.casefold() != expected_hash.casefold():
                    raise AtlasManifestError(f'Generated asset failed its SHA-256 check: {name}.')
                if relative in generated_files:
                    raise AtlasManifestError(f'Duplicate generated asset path: {name}.')
                generated_files[relative] = actual_hash
            required_names = {'maps/atlas.json', 'maps/catalog.json'}
            if not required_names.issubset(generated_files):
                raise AtlasManifestError('Generated asset manifest is missing required map outputs.')
            if output_hash.casefold() != game_sha256.casefold():
                generated_message = ('Local Atlas maps were generated from a different game folder. '
                                     'Prepare them again for the selected game.')
            else:
                generated_ready = True
                generated_message = 'Local Atlas maps are ready for this game folder.'
                if 'art/native-font.ttf' in generated_files:
                    native_font = _inside(root, 'art/native-font.ttf', 'generated native font', directory=False)
        except (OSError, UnicodeError, json.JSONDecodeError, AtlasManifestError) as error:
            if not allow_unprepared:
                if isinstance(error, AtlasManifestError):
                    raise
                raise AtlasManifestError(f'Could not verify generated local assets: {error}') from error
            generated_message = f'Local Atlas maps need preparation: {error}'
    else:
        # Interrupted generator runs can leave only these exact outputs. They remain
        # untrusted until a complete generated-assets.json validates them.
        stray = [name for name in allowed_generated
                 if root.joinpath(*PurePosixPath(name).parts).exists()]
        if stray:
            generated_message = 'An earlier Atlas map preparation was incomplete; prepare maps again.'
    if not generated_ready and not allow_unprepared:
        raise AtlasManifestError(generated_message)

    # The main manifest is self-referential and omitted. Generated outputs have a
    # separate game-bound manifest and are never trusted as package immutables.
    expected_names = set(hashed) | mutable_names
    discovered_names = set()
    for candidate in root.rglob('*'):
        if candidate.is_symlink() or getattr(candidate, 'is_junction', lambda: False)():
            raise AtlasManifestError('Atlas package folders must not contain symlinks or junctions.')
        if candidate.is_file():
            canonical = candidate.relative_to(root).as_posix().casefold()
            if canonical not in (MANIFEST_NAME.casefold(), generated_manifest_rel.as_posix().casefold()) \
                    and not _is_generated_output(canonical):
                discovered_names.add(canonical)
    if discovered_names != expected_names:
        unhashed = sorted(discovered_names - expected_names)
        missing = sorted(expected_names - discovered_names)
        detail = f' Unhashed file: {unhashed[0]}.' if unhashed else f' Missing file: {missing[0]}.'
        raise AtlasManifestError('Atlas package contents do not match the manifest.' + detail)
    resolved_paths['font'] = native_font or resolved_paths['font']
    resolved_paths['generator'] = generator_path
    if generated_ready:
        resolved_paths['catalog'] = _inside(root, 'maps/catalog.json', 'generated map catalog', directory=False)
    return AtlasPackage(root=root, manifest=manifest, paths=resolved_paths,
                        generated_ready=generated_ready, generated_message=generated_message,
                        generated_font=native_font)


def atlas_environment(base_environment: dict[str, str], *, enabled: bool,
                      package: AtlasPackage | None = None, enter_button: str = '1') -> dict[str, str]:
    """Return a child-only environment with stale Atlas wrapper values removed."""
    env = dict(base_environment)
    qa_enabled = enabled and any(key.upper() == 'BB_ATLAS_QA' and value == '1'
                                 for key, value in env.items())
    qa_overrides = {key.upper(): value for key, value in env.items()
                    if key.upper().startswith('BB_MAP_TEST') or key.upper() in (
                        'BB_MAP_UI_DUMP', 'BB_MAP_UI_DUMP_TRIGGER', 'BB_PAD_FILE')}
    for key in list(env):
        normalized = key.upper()
        if normalized in {value.upper() for value in ENV_KEYS} or normalized.startswith('BB_MAP_') \
                or normalized == 'BB_PAD_FILE':
            env.pop(key, None)
    if not qa_enabled:
        for key in list(env):
            normalized = key.upper()
            if normalized.startswith('BB_MAP_TEST') or normalized in ('BB_MAP_UI_DUMP', 'BB_PAD_FILE'):
                env.pop(key, None)
    else:
        env['BB_ATLAS_QA'] = '1'
        env.update(qa_overrides)
    env['BB_ATLAS_ENABLED'] = '1' if enabled else '0'
    if enabled:
        if package is None:
            raise AtlasManifestError('Hunter\'s Atlas is enabled but its package is not valid.')
        if not package.generated_ready:
            raise AtlasManifestError(package.generated_message)
        if enter_button not in ('0', '1'):
            raise AtlasManifestError('Choose Cross (A) or Circle (B) as the Atlas confirm button.')
        values = {
            'BB_PROBE': package.paths['probe'],
            'BB_MAP_DIR': package.paths['maps'],
            'BB_MAP_CONFIG': package.paths['config'],
            'BB_MAP_ART_DIR': package.paths['art'],
            'BB_MAP_CATALOG': package.paths['catalog'],
            'BB_MAP_FONT': package.paths['font'],
            'BB_ENTER_BUTTON': enter_button,
        }
        env.update({key: str(value) for key, value in values.items()})
    return env


def package_status(folder: str | os.PathLike[str], *, game_executable: str | os.PathLike[str],
                   launcher_build: str = LAUNCHER_BUILD, runtime_build: str = RUNTIME_BUILD) -> tuple[AtlasPackage | None, str]:
    """UI helper that returns readable readiness text and never leaks a resolver exception."""
    try:
        game_hash = sha256_file(Path(game_executable))
        package = inspect_package(folder, launcher_build=launcher_build, runtime_build=runtime_build,
                                  game_sha256=game_hash, allow_unprepared=True)
        if not package.generated_ready:
            return package, package.generated_message
        return package, f'Ready — Hunter\'s Atlas {package.display_version} verified.'
    except (OSError, AtlasManifestError) as error:
        return None, str(error)
