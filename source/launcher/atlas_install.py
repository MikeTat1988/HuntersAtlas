"""Reversible, receipt-owned installation of the Atlas launcher adapter.

This tool only edits a separate launcher installation folder. It never edits the
game's AppData settings or save tree, and it deliberately keeps the stock
``_internal`` tree in place. The adapter's frozen dependencies live in the
separate ``_atlas_internal`` directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
from typing import Any

STOCK_LAUNCHER_SHA256 = '4a8e67ce5c2a5e4d8f8add8b0e606caecd5a3389756aef683f3ded793d4f6a59'
ADAPTER_ROOT_NAME = 'Bloodborne'
EXE_NAME = 'Bloodborne.exe'
RUN_NAME = 'run.py'
DEPENDENCIES_NAME = '_atlas_internal'
RECEIPT_NAME = 'atlas-install-receipt.json'
ROLLBACK_DIR_NAME = 'atlas-launcher-rollback'
ATLAS_MANIFEST_NAME = 'manifest.json'


class InstallError(RuntimeError):
    """Input is unsafe, incompatible, or no longer matches its receipt."""


def _generated_asset_path(value: str) -> bool:
    canonical = value.casefold()
    return (canonical in {'maps/atlas.json', 'maps/catalog.json', 'art/native-font.ttf'} or
            re.fullmatch(r'maps/m[0-9]{2}_[0-9]{2}_[0-9]{2}_[0-9]{2}\.json', canonical) is not None)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _resolved(path: str | Path, label: str, *, must_exist: bool = True) -> Path:
    candidate = Path(path).expanduser()
    try:
        return candidate.resolve(strict=must_exist)
    except (OSError, RuntimeError) as error:
        raise InstallError(f'{label} does not resolve: {candidate}') from error


def _inside(path: Path, root: Path, label: str) -> Path:
    resolved = _resolved(path, label)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise InstallError(f'{label} resolves outside its owned root.') from error
    return resolved


def _contained_setting(value: Any, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or '\x00' in value:
        raise InstallError(f'{label} must be a non-empty relative package path.')
    normalized = value.replace('\\', '/')
    parts = normalized.split('/')
    if normalized.startswith('/') or (len(normalized) > 1 and normalized[1] == ':') or any(
            part in ('', '.', '..') or ':' in part for part in parts):
        raise InstallError(f'{label} must stay inside the selected Atlas folder.')
    return PurePosixPath(*parts)


def _validate_addon(folder: Path) -> dict[str, Any]:
    """Validate all package file hashes and package containment before installing."""
    root = _resolved(folder, 'Atlas folder')
    if not root.is_dir():
        raise InstallError('Atlas folder must be an extracted package directory.')
    manifest_path = root / ATLAS_MANIFEST_NAME
    try:
        manifest = json.loads(_inside(manifest_path, root, 'Atlas manifest').read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise InstallError(f'Could not read Atlas manifest: {error}') from error
    if not isinstance(manifest, dict) or manifest.get('id') != 'hunters-atlas':
        raise InstallError('Selected folder does not contain a Hunter\'s Atlas manifest.')
    if ('windows-v1.7.2-atlas1' not in manifest.get('launcher_builds', []) or
            manifest.get('runtime_build') != 'hunters-atlas-runtime-1.4.0-beta1'):
        raise InstallError('Atlas manifest does not support this launcher/runtime build.')
    files = manifest.get('files')
    mutable = manifest.get('mutable_files')
    paths = manifest.get('paths')
    generated = manifest.get('generated')
    if (not isinstance(files, dict) or not isinstance(mutable, list) or len(mutable) != 1 or
            not isinstance(paths, dict) or not isinstance(generated, dict)):
        raise InstallError('Atlas manifest is missing its file hashes, paths, or mutable settings declaration.')
    mutable_path = _contained_setting(mutable[0], 'mutable_files[0]').as_posix().casefold()
    config_path = _contained_setting(paths.get('config'), 'paths.config').as_posix().casefold()
    if mutable_path != config_path:
        raise InstallError('Only paths.config may be mutable in the Atlas package.')
    generated_manifest = _contained_setting(generated.get('manifest'), 'generated.manifest').as_posix().casefold()
    generated_generator = _contained_setting(generated.get('generator'), 'generated.generator').as_posix().casefold()
    required = generated.get('required')
    if (generated_manifest != 'maps/generated-assets.json' or
            not isinstance(required, list) or len(required) != 2 or
            {_contained_setting(value, 'generated.required').as_posix().casefold()
             for value in required} != {'maps/atlas.json', 'maps/catalog.json'}):
        raise InstallError('Atlas manifest has an invalid generated-output contract.')
    listed: dict[str, str] = {}
    for name, digest in files.items():
        rel = _contained_setting(name, f'files[{name!r}]').as_posix().casefold()
        if rel in (mutable_path, generated_manifest) or not isinstance(digest, str) or len(digest) != 64:
            raise InstallError(f'Invalid immutable file record for {name!r}.')
        target = _inside(root.joinpath(*PurePosixPath(rel).parts), root, f'files[{name!r}]')
        if not target.is_file():
            raise InstallError(f'Package file is missing: {name}.')
        actual = sha256_file(target)
        if actual.casefold() != digest.casefold():
            raise InstallError(f'Package file failed SHA-256 verification: {name}.')
        if rel in listed:
            raise InstallError(f'Duplicate package file entry: {name}.')
        listed[rel] = actual
    if any(_generated_asset_path(name) for name in listed):
        raise InstallError('Generated map/font outputs must not be immutable package file entries.')
    discovered: set[str] = set()
    for node in root.rglob('*'):
        if node.is_symlink() or getattr(node, 'is_junction', lambda: False)():
            raise InstallError('Atlas package must not contain symlinks or junctions.')
        if node.is_file():
            rel = node.relative_to(root).as_posix().casefold()
            if rel != ATLAS_MANIFEST_NAME:
                discovered.add(rel)
    generated_allowed = {'maps/atlas.json', 'maps/catalog.json', 'art/native-font.ttf'}
    generated_manifest_path = root.joinpath(*PurePosixPath(generated_manifest).parts)
    for node in root.rglob('*'):
        if node.is_file():
            rel = node.relative_to(root).as_posix().casefold()
            if _generated_asset_path(rel) or rel == generated_manifest:
                discovered.add(rel)
            if _generated_asset_path(rel):generated_allowed.add(rel)
    if any(rel not in set(listed) | {mutable_path, generated_manifest} and
           not _generated_asset_path(rel) for rel in discovered):
        raise InstallError('Atlas package has unlisted files.')
    if not (set(listed) | {mutable_path, generated_manifest} | generated_allowed).issuperset(discovered):
        raise InstallError('Atlas package has unlisted files or files missing from its manifest.')
    for key in ('probe', 'maps', 'config', 'art', 'font'):
        if not isinstance(paths.get(key), str):
            raise InstallError(f'Atlas manifest is missing paths.{key}.')
        relative = _contained_setting(paths[key], f'paths.{key}')
        target = _inside(root.joinpath(*relative.parts), root, f'paths.{key}')
        if key in ('maps', 'art'):
            if not target.is_dir():
                raise InstallError(f'Atlas paths.{key} must be a package folder.')
        elif not target.is_file():
            raise InstallError(f'Atlas paths.{key} must be a package file.')
    catalog_rel = _contained_setting(paths.get('catalog'), 'paths.catalog').as_posix().casefold()
    if catalog_rel != 'maps/catalog.json':
        raise InstallError('Atlas catalog must be a generated map asset.')
    if generated_generator not in listed:
        raise InstallError('The Atlas local generator must be listed in immutable package hashes.')
    hashed_names = set(listed)
    for key in ('probe', 'font'):
        relative = _contained_setting(paths[key], f'paths.{key}').as_posix().casefold()
        if relative not in hashed_names:
            raise InstallError(f'Atlas paths.{key} must have an immutable SHA-256 record.')
    for key in ('art',):
        prefix = _contained_setting(paths[key], f'paths.{key}').as_posix().casefold().rstrip('/') + '/'
        if not any(name.startswith(prefix) for name in hashed_names):
            raise InstallError(f'Atlas paths.{key} must contain immutable files.')
    return manifest


def _inventory(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
            raise InstallError(f'Unexpected link in dependency folder: {path}')
        if path.is_file():
            result[path.relative_to(root).as_posix()] = sha256_file(path)
    return result


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def _validate_uninstalled_receipt(receipt: Path, launcher_root: Path, *,
                                  stock_sha256: str, run_sha256: str) -> dict[str, Any]:
    """Allow reuse only when a retained receipt proves a completed safe uninstall."""
    try:
        record = json.loads(receipt.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise InstallError(f'Could not read existing install receipt: {error}') from error
    if not isinstance(record, dict) or record.get('schema') != 1 or record.get('state') != 'uninstalled':
        raise InstallError(f'{RECEIPT_NAME} exists but does not record a completed uninstall.')
    prior_root = _resolved(record.get('launcher_root', ''), 'Prior receipt launcher root')
    if prior_root != launcher_root or receipt != launcher_root / RECEIPT_NAME:
        raise InstallError('Existing receipt belongs to a different launcher folder.')
    recorded_stock_hash = record.get('stock_exe_sha256')
    if not isinstance(recorded_stock_hash, str) or recorded_stock_hash.casefold() != stock_sha256.casefold():
        raise InstallError('Existing receipt stock executable hash does not match this launcher.')
    if record.get('run_py_sha256') != run_sha256:
        raise InstallError('Existing receipt run.py hash does not match this launcher.')
    prior_rollback = _resolved(record.get('rollback_root', ''), 'Prior receipt rollback folder')
    if (prior_rollback == launcher_root or launcher_root in prior_rollback.parents or
            prior_rollback in launcher_root.parents):
        raise InstallError('Prior receipt rollback folder overlaps the launcher folder.')
    backup = prior_rollback / EXE_NAME
    if not backup.is_file() or sha256_file(backup).casefold() != recorded_stock_hash.casefold():
        raise InstallError('Existing receipt stock backup is missing or changed.')
    if (launcher_root / DEPENDENCIES_NAME).exists():
        raise InstallError('An adapter dependency folder remains after the recorded uninstall.')
    return record


def install(launcher_root: str | Path, adapter_root: str | Path, atlas_folder: str | Path,
            rollback_root: str | Path, *, expected_stock_sha256: str = STOCK_LAUNCHER_SHA256) -> Path:
    """Install only into a separate launcher folder and return its durable receipt."""
    root = _resolved(launcher_root, 'Launcher root')
    adapter = _resolved(adapter_root, 'Adapter build')
    atlas = _resolved(atlas_folder, 'Atlas folder')
    rollback = _resolved(rollback_root, 'Rollback folder', must_exist=False)
    if not root.is_dir() or not adapter.is_dir():
        raise InstallError('Launcher root and adapter build must be existing folders.')
    if (rollback == root or root in rollback.parents or rollback in root.parents or
            rollback == atlas or atlas in rollback.parents or rollback in atlas.parents):
        raise InstallError('Rollback folder must be outside both launcher and public Atlas folders.')
    if root == atlas or root in atlas.parents or atlas in root.parents:
        raise InstallError('Launcher root and public Atlas folder must be separate.')
    _validate_addon(atlas)

    exe = root / EXE_NAME
    run_script = root / RUN_NAME
    original_hash = sha256_file(exe) if exe.is_file() else ''
    if original_hash.casefold() != expected_stock_sha256.casefold():
        raise InstallError(f'Stock launcher SHA-256 mismatch; refusing replacement (found {original_hash or "missing"}).')
    if not run_script.is_file() or sha256_file(run_script) != sha256_file(adapter / RUN_NAME):
        raise InstallError('Installed run.py is not the exact matching launcher source; refusing replacement.')
    current_run_hash = sha256_file(run_script)
    if (root / DEPENDENCIES_NAME).exists():
        raise InstallError(f'{DEPENDENCIES_NAME} already exists; refusing to overwrite unknown files.')
    receipt = root / RECEIPT_NAME
    prior_record = None
    if receipt.exists():
        prior_record = _validate_uninstalled_receipt(
            receipt, root, stock_sha256=original_hash, run_sha256=current_run_hash)
    adapter_exe = adapter / EXE_NAME
    adapter_deps = adapter / DEPENDENCIES_NAME
    build_receipts = (adapter.parent / 'source-receipt.json', adapter.parent.parent / 'source-receipt.json')
    build_receipt = next((candidate for candidate in build_receipts if candidate.is_file()), build_receipts[0])
    if not adapter_exe.is_file() or not adapter_deps.is_dir() or not build_receipt.is_file():
        raise InstallError('Adapter build must contain Bloodborne.exe, _atlas_internal, and source-receipt.json.')
    try:
        build = json.loads(build_receipt.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise InstallError(f'Could not read adapter build receipt: {error}') from error
    adapter_hash = sha256_file(adapter_exe)
    if build.get('frozen_sha256', '').casefold() != adapter_hash.casefold():
        raise InstallError('Adapter executable does not match its frozen-source build receipt.')
    if build.get('launcher_build') != 'windows-v1.7.2-atlas1':
        raise InstallError('Adapter build receipt has an incompatible launcher build id.')
    dependency_inventory = _inventory(adapter_deps)
    if not dependency_inventory:
        raise InstallError('Adapter dependency folder is empty.')
    if build.get('frozen_dependency_sha256') != dependency_inventory:
        raise InstallError('Adapter dependencies do not match the frozen-source build receipt.')
    if rollback.exists() and any(rollback.iterdir()):
        raise InstallError('Rollback folder must be new or empty.')

    # All compatibility and hash checks finish before the first target mutation.
    rollback.mkdir(parents=True, exist_ok=True)
    original_backup = rollback / EXE_NAME
    shutil.copy2(exe, original_backup)
    if sha256_file(original_backup) != original_hash:
        raise InstallError('Rollback copy verification failed; launcher was not changed.')
    temp_deps = root / (DEPENDENCIES_NAME + '.installing')
    temp_exe = root / (EXE_NAME + '.installing')
    archived_receipt = rollback / 'previous-atlas-install-receipt.json'
    try:
        if prior_record is not None:
            shutil.copy2(receipt, archived_receipt)
            if sha256_file(archived_receipt) != sha256_file(receipt):
                raise InstallError('Previous install receipt archival verification failed.')
            receipt.unlink()
        shutil.copytree(adapter_deps, temp_deps)
        shutil.copy2(adapter_exe, temp_exe)
        staged_inventory = _inventory(temp_deps)
        if staged_inventory != _inventory(adapter_deps) or sha256_file(temp_exe) != adapter_hash:
            raise InstallError('Staged adapter files failed verification.')
        os.replace(temp_deps, root / DEPENDENCIES_NAME)
        os.replace(temp_exe, exe)
        if sha256_file(exe) != adapter_hash:
            raise InstallError('Installed launcher failed post-copy verification.')
        record = {
            'schema': 1,
            'state': 'installed',
            'launcher_build': build['launcher_build'],
            'runtime_build': build.get('runtime_build'),
            'launcher_root': str(root),
            'atlas_folder': str(atlas),
            'rollback_root': str(rollback),
            'stock_exe_sha256': original_hash,
            'installed_exe_sha256': adapter_hash,
            'run_py_sha256': sha256_file(run_script),
            'dependencies': _inventory(root / DEPENDENCIES_NAME),
            'adapter_build_receipt_sha256': sha256_file(build_receipt),
            'atlas_manifest_sha256': sha256_file(atlas / ATLAS_MANIFEST_NAME),
        }
        _atomic_json(receipt, record)
    except Exception:
        # Roll back only the exact transient artifacts created by this invocation.
        if exe.is_file() and sha256_file(exe) == adapter_hash:
            restore = root / (EXE_NAME + '.restore')
            shutil.copy2(original_backup, restore)
            os.replace(restore, exe)
        installed_deps = root / DEPENDENCIES_NAME
        if installed_deps.is_dir() and _inventory(installed_deps) == staged_inventory:
            shutil.rmtree(installed_deps)
        for transient in (temp_exe, temp_deps):
            if transient.is_file():
                transient.unlink()
            elif transient.is_dir():
                shutil.rmtree(transient)
        if prior_record is not None and archived_receipt.is_file() and not receipt.exists():
            restore_receipt = root / (RECEIPT_NAME + '.restore')
            shutil.copy2(archived_receipt, restore_receipt)
            os.replace(restore_receipt, receipt)
        raise
    return receipt


def uninstall(receipt_path: str | Path) -> Path:
    """Restore the stock launcher only if every installed byte still matches receipt."""
    receipt_file = _resolved(receipt_path, 'Install receipt')
    try:
        record = json.loads(receipt_file.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise InstallError(f'Could not read install receipt: {error}') from error
    if not isinstance(record, dict) or record.get('schema') != 1 or record.get('state') != 'installed':
        raise InstallError('Receipt is invalid or does not describe an installed adapter.')
    root = _resolved(record.get('launcher_root', ''), 'Receipt launcher root')
    if receipt_file != root / RECEIPT_NAME:
        raise InstallError('Receipt is not at the launcher root recorded during installation.')
    exe = root / EXE_NAME
    deps = root / DEPENDENCIES_NAME
    if sha256_file(exe).casefold() != str(record.get('installed_exe_sha256', '')).casefold():
        raise InstallError('Installed Bloodborne.exe changed since installation; refusing to overwrite it.')
    expected_deps = record.get('dependencies')
    if not isinstance(expected_deps, dict) or _inventory(deps) != expected_deps:
        raise InstallError('Adapter dependency files changed since installation; refusing to remove them.')
    rollback = _resolved(record.get('rollback_root', ''), 'Receipt rollback folder')
    backup = rollback / EXE_NAME
    if not backup.is_file() or sha256_file(backup).casefold() != str(record.get('stock_exe_sha256', '')).casefold():
        raise InstallError('Verified stock launcher backup is missing or changed; refusing uninstall.')
    if sha256_file(root / RUN_NAME).casefold() != str(record.get('run_py_sha256', '')).casefold():
        raise InstallError('run.py changed since installation; refusing partial rollback.')

    restore = root / (EXE_NAME + '.restore')
    shutil.copy2(backup, restore)
    if sha256_file(restore) != record['stock_exe_sha256']:
        restore.unlink(missing_ok=True)
        raise InstallError('Staged stock launcher failed verification.')
    os.replace(restore, exe)
    shutil.rmtree(deps)
    record['state'] = 'uninstalled'
    _atomic_json(receipt_file, record)
    return receipt_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    install_parser = commands.add_parser('install', help='install into a separate launcher folder')
    install_parser.add_argument('--launcher-root', required=True)
    install_parser.add_argument('--adapter-root', required=True)
    install_parser.add_argument('--atlas-folder', required=True)
    install_parser.add_argument('--rollback-root', required=True)
    uninstall_parser = commands.add_parser('uninstall', help='restore files owned by an install receipt')
    uninstall_parser.add_argument('--receipt', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'install':
            result = install(args.launcher_root, args.adapter_root, args.atlas_folder, args.rollback_root)
        else:
            result = uninstall(args.receipt)
    except (InstallError, OSError, shutil.Error) as error:
        parser.exit(2, f'Atlas launcher {args.command} failed: {error}\n')
    print(result)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
