"""Install/update the owned in-game runtime while retaining maps and preferences."""
import argparse
import contextlib
import ctypes
from ctypes import wintypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def ordinary_profile():
    return Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming')) / 'bbport-launcher/settings.json'


def generated_cache(name):
    return name in ('compiled', 'out') or name.startswith('session-assets-')


def safe_tree(root, *, package=False, state=False):
    """Reject redirects while pruning reproducible package caches before descent.

    A normal game run creates linked overlays inside these caches. They are not
    installation inputs and must never be followed, validated, or copied.
    Generic content directories retain strict redirect rejection.
    """
    def check(path):
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError(f'Linked installation paths are unsupported: {path}')
    check(root)

    def walk_error(error):
        raise error

    for directory, directories, files in os.walk(root, topdown=True, followlinks=False, onerror=walk_error):
        directory = Path(directory)
        cache_parent = (state and directory == root) or (package and directory == root / 'state')
        if cache_parent:
            directories[:] = [name for name in directories if not generated_cache(name)]
            files = [name for name in files if not generated_cache(name)]
        for name in (*directories, *files):
            check(directory / name)


def copy_state(source, target):
    safe_tree(source, state=True)

    def ignore(directory, names):
        return [name for name in names if generated_cache(name)] if Path(directory) == source else []

    shutil.copytree(source, target, ignore=ignore)


def regular_path(path):
    raw = Path(path).absolute()
    if raw == Path(raw.anchor):
        raise ValueError('A drive root cannot be an Atlas installation.')
    for part in (raw, *raw.parents):
        if part.exists() or part.is_symlink():
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise ValueError(f'Linked installation path refused: {part}')
    return raw.resolve()


def pid_alive(pid):
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        raise ValueError('The maintenance owner PID is invalid; manual inspection is required.')
    if os.name != 'nt':
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x00100000, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:  # ERROR_INVALID_PARAMETER: PID no longer exists.
            return False
        return True  # Access denied and unknown errors are not proof of death.
    try:
        return kernel.WaitForSingleObject(handle, 0) != 0
    finally:
        kernel.CloseHandle(handle)


@contextlib.contextmanager
def maintenance(target, *, recovery=False):
    path = target.parent / ('.' + target.name + '.owned-maintenance.lock')
    path.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    ownership = {'pid': os.getpid(), 'token': token}
    if path.exists() and recovery:
        # Reassign the existing lock under an OS lock rather than unlinking it.
        # Two recovery processes cannot both observe a dead owner and then
        # accidentally remove the other's newly created maintenance lock.
        with path.open('r+', encoding='utf-8') as stream:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                owner = json.load(stream)
                if pid_alive(owner.get('pid')):
                    raise RuntimeError('Atlas maintenance is still owned by a live process.')
                stream.seek(0)
                stream.truncate()
                json.dump(ownership, stream)
                stream.flush()
                os.fsync(stream.fileno())
            finally:
                stream.seek(0)
                if os.name == 'nt':
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    else:
        with path.open('x', encoding='utf-8') as stream:
            json.dump(ownership, stream)
    try:
        yield
    finally:
        if path.exists() and read(path).get('token') == token:
            path.unlink()


def core(root):
    spec = importlib.util.spec_from_file_location('atlas_install_core', root / 'bootstrap/entry.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def associated_atlas(profile_source):
    """Find an earlier Atlas through the ordinary profile without changing it."""
    if profile_source is None or not profile_source.is_file():
        return None
    raw = read(profile_source).get('atlas_dir')
    if not isinstance(raw, str) or not raw.strip():
        return None
    root = regular_path(Path(raw))
    if not (root / 'manifest.json').is_file():
        return None
    manifest = read(root / 'manifest.json')
    if manifest.get('schema') != 1 or manifest.get('id') != 'hunters-atlas-lite':
        return None
    safe_tree(root, package=True)
    return root


def retain_pack(previous, staged):
    """Import only a fully verified pack prepared with the same extraction inputs."""
    if previous is None or not (previous / 'manifest.json').is_file():
        return False
    old = read(previous / 'manifest.json')
    spec = old.get('asset_pack', {})
    if spec.get('path') != 'assets.atlaslite':
        return False
    pack = previous / 'assets.atlaslite'
    if not pack.is_file() or sha(pack) != spec.get('sha256'):
        raise ValueError('The previous Atlas map pack failed its integrity check.')
    new = read(staged / 'manifest.json')
    # Runtime/launcher versions are intentionally absent from this identity.
    identity = ('tools/generator.atlaslite', 'tools/extract_atlas_features.py')
    if any(old.get('files', {}).get(key) != new.get('files', {}).get(key) for key in identity):
        return False
    for key in ('feature_schema', 'asset_key_schema'):
        if old.get(key) != new.get(key):
            return False
    if old.get('compatibility', {}).get('map_schema') != new.get('compatibility', {}).get('map_schema'):
        return False
    module = core(staged)
    contract = module.load_contract(staged)
    assets_spec = importlib.util.spec_from_file_location('atlas_install_assets', staged / 'bootstrap/assets.py')
    assets = importlib.util.module_from_spec(assets_spec)
    assets_spec.loader.exec_module(assets)
    with tempfile.TemporaryDirectory(prefix='atlas-pack-check-') as directory:
        verified = assets.unpack(pack, Path(directory))
        if not verified.get('prepared'):
            return False
        metadata_file = Path(directory) / 'maps/generated-assets.json'
        settings_file = staged / 'state/profile/settings.json'
        if metadata_file.is_file() and settings_file.is_file():
            metadata = read(metadata_file)
            game = Path(read(settings_file).get('game_dir', ''))
            if (game / 'eboot.bin').is_file() and metadata.get('asset_key'):
                module.validate_game_source(contract, {'game_dir': str(game)})
                identity_spec = importlib.util.spec_from_file_location('atlas_install_identity', staged / 'tools/asset_identity.py')
                identity = importlib.util.module_from_spec(identity_spec)
                identity_spec.loader.exec_module(identity)
                if identity.key(game, new) != metadata['asset_key']:
                    return False
    shutil.copyfile(pack, staged / 'assets.atlaslite')
    new['asset_pack'] = {'path': 'assets.atlaslite', 'sha256': sha(staged / 'assets.atlaslite')}
    new['files']['assets.atlaslite'] = new['asset_pack']['sha256']
    write(staged / 'manifest.json', new)
    return True


def initialize(staged, target, profile_source, launcher, previous):
    state = staged / 'state'
    profile = state / 'profile/settings.json'
    if not profile.exists():
        settings = read(profile_source) if profile_source and profile_source.is_file() else {}
        settings['atlas_enabled'] = settings.get('atlas_enabled', True) if previous else True
        settings['atlas_dir'] = str(target)
    else:
        settings = read(profile)
        settings['atlas_dir'] = str(target)
    if not str(settings.get('user_dir') or '').strip():
        if launcher is None:
            raise ValueError('Select the original launcher folder so Atlas can retain its existing user/save folder.')
        settings['user_dir'] = str(launcher / 'user')
    write(profile, settings)
    port = state / 'port'
    port.mkdir(parents=True, exist_ok=True)
    if launcher:
        for name in ('bbport.ini', 'input.ini', 'mods.json', 'patches.json'):
            source = launcher / name
            if source.is_file() and not (port / name).exists():
                shutil.copyfile(source, port / name)
        for name, setting in (('mods', 'mods_dir'), ('patches', 'patches_dir')):
            source = launcher / name
            if settings.get(setting) and Path(settings[setting]).resolve() == source.resolve():
                # An explicitly selected old default has the same meaning as
                # the default. Migrate it with its contents instead of retaining
                # a dependency on the replaceable launcher directory.
                settings[setting] = ''
            if not settings.get(setting) and source.is_dir() and not (port / name).exists():
                safe_tree(source)
                builtin = staged / 'runtime/port/patches/Bloodborne.xml'
                def ignore_builtin(directory, names):
                    if name != 'patches' or not builtin.is_file():
                        return []
                    return [filename for filename in names
                            if filename.casefold() == 'bloodborne.xml'
                            and (Path(directory) / filename).is_file()
                            and sha(Path(directory) / filename) == sha(builtin)]
                shutil.copytree(source, port / name, ignore=ignore_builtin)
        for name in ('fsr4_shaders', 'fsr4_411'):
            source = launcher / name
            if source.is_dir() and not (port / name).exists():
                safe_tree(source)
                shutil.copytree(source, port / name)
        # Explicit user-selected content directories are retained in settings.
        write(profile, settings)
    # Older local candidates copied this builtin into the external-patch list.
    # Its enabled metadata would reapply every default patch from a different
    # path. Only remove a byte-identical owned duplicate; custom XML is kept.
    duplicate = port / 'patches/Bloodborne.xml'
    builtin = staged / 'runtime/port/patches/Bloodborne.xml'
    if duplicate.is_file() and builtin.is_file() and sha(duplicate) == sha(builtin):
        duplicate.unlink()
    old_options = None
    if previous:
        old_manifest = read(previous / 'manifest.json')
        relative = old_manifest.get('paths', {}).get('config', 'settings/settings.ini')
        if Path(relative).is_absolute() or '..' in Path(relative).parts:
            raise ValueError('Previous Atlas settings path is unsafe.')
        old_options = previous / relative
    new_manifest = read(staged / 'manifest.json')
    new_options = staged / new_manifest.get('paths', {}).get('config', 'settings/settings.ini')
    if old_options and old_options.is_file():
        new_options.parent.mkdir(parents=True, exist_ok=True)
        if old_options.resolve() != new_options.resolve():
            shutil.copyfile(old_options, new_options)
    elif not new_options.exists():
        new_options.parent.mkdir(parents=True, exist_ok=True)
        new_options.write_text('[map]\nkeyboard=0\ncontroller=0\n', encoding='utf-8')


def shortcut(path, target, backup):
    if path is None:
        return
    path = shortcut_location(path)
    if path.exists() and not backup.exists():
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, backup)
    # Paths are single-quoted PowerShell literals, never executable command text.
    literal = lambda value: "'" + str(value).replace("'", "''") + "'"
    script = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut(" + literal(path) + ");"
              "$s.TargetPath=" + literal(target / 'HuntersAtlas.exe') + ";"
              "$s.WorkingDirectory=" + literal(target) + ";$s.Arguments='';"
              "$s.IconLocation=" + literal(str(target / 'HuntersAtlas.exe') + ',0') + ";$s.Save()")
    powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-Command', script], check=True)


def install(source, target, *, profile_source=None, launcher=None, shortcut_path=None):
    source = regular_path(source)
    target = regular_path(target)
    with maintenance(target):
        return _install(source, target, profile_source=profile_source,
                        launcher=launcher, shortcut_path=shortcut_path)


def local_file(root, relative):
    relative = str(relative).replace('\\', '/')
    if (not relative or relative.startswith('/') or ':' in relative or
            any(part in ('', '.', '..') for part in relative.split('/'))):
        raise ValueError('Unsafe installation metadata path.')
    path = regular_path(root / relative)
    path.relative_to(root)
    return path


def shortcut_location(value):
    """Validate a caller-selected shortcut without forbidding Desktop redirection.

    Desktop parents may be redirected or supplied by OneDrive. Cloud files
    themselves are read/copied normally (which hydrates them if necessary).
    Name-surrogate links and unknown file reparse tags remain unsupported.
    This exception is solely for external .lnk destinations, never packages.
    """
    path = Path(value).absolute()
    if path.suffix.lower() != '.lnk':
        raise ValueError('The shortcut must name a .lnk file.')

    def check_file(candidate):
        try:
            details = candidate.lstat()
        except FileNotFoundError:
            return
        reparse = getattr(details, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        tag = getattr(details, 'st_reparse_tag', 0)
        cloud = tag == 0x80000021 or (tag & 0xFFFF0FFF) == 0x9000001A
        if stat.S_ISLNK(details.st_mode) or (reparse and (not cloud or tag & 0x20000000)):
            raise ValueError('The shortcut file must not be a symlink, junction, or unknown reparse point.')
        if not stat.S_ISREG(details.st_mode):
            raise ValueError('The shortcut destination must name a regular file.')

    check_file(path)
    parent = path.parent.resolve(strict=True)
    if not parent.is_dir():
        raise ValueError('The shortcut parent folder is unavailable.')
    resolved = parent / path.name
    check_file(resolved)
    return resolved


def save_shortcut(record, journal):
    if not record.get('shortcut'):
        return
    path = shortcut_location(record['shortcut'])
    record['shortcut'] = str(path)
    saved = journal.with_suffix('.shortcut.lnk')
    record['shortcut_existed'] = path.is_file()
    record['shortcut_snapshot'] = str(saved)
    if path.is_file():
        shutil.copyfile(path, saved)
        record['shortcut_sha256'] = sha(saved)


def restore_shortcut(record):
    if not record.get('shortcut'):
        return
    path = shortcut_location(record['shortcut'])
    if record.get('shortcut_existed'):
        saved = regular_path(record['shortcut_snapshot'])
        if not saved.is_file() or sha(saved) != record.get('shortcut_sha256'):
            raise ValueError('The original shortcut snapshot is missing or changed.')
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(saved, path)
    elif path.exists():
        path.unlink()


def portable_snapshot(target, backup, launcher):
    """Record only metadata initialization can change; save data is excluded."""
    manifest = read(target / 'manifest.json')
    names = {'manifest.json', 'assets.atlaslite',
             'state/profile/settings.json', 'state/installation/receipt.json',
             'state/installation/previous-shortcut.lnk',
             manifest.get('paths', {}).get('config', 'settings/settings.ini')}
    for name in ('bbport.ini', 'input.ini', 'mods.json', 'patches.json'):
        names.add('state/port/' + name)
    if launcher:
        for folder in ('mods', 'patches', 'fsr4_shaders', 'fsr4_411'):
            source = launcher / folder
            if source.is_dir() and not (target / 'state/port' / folder).exists():
                safe_tree(source)
                for path in source.rglob('*'):
                    if path.is_file():
                        names.add('state/port/' + folder + '/' + path.relative_to(source).as_posix())
    backup.mkdir()
    shutil.copyfile(target / 'manifest.json', backup / 'manifest.json')
    entries = []
    for index, name in enumerate(sorted(names)):
        path = local_file(target, name)
        entry = {'path': name, 'existed': path.is_file()}
        if path.is_file():
            saved = backup / ('metadata-' + str(index))
            shutil.copyfile(path, saved)
            entry.update(snapshot=saved.name, sha256=sha(saved))
        entries.append(entry)
    write(backup / 'metadata.json', {'schema': 1, 'files': entries})
    return sha(backup / 'metadata.json')


def restore_portable(record, target, backup):
    if not target.is_dir() or not (target / 'manifest.json').is_file():
        raise ValueError('Portable installation is missing or changed; metadata recovery was not applied.')
    if not (backup / 'manifest.json').is_file() or sha(backup / 'manifest.json') != record['original_manifest_sha256']:
        raise ValueError('The portable manifest snapshot is missing or changed.')
    if sha(target / 'manifest.json') != record['original_manifest_sha256']:
        # Importing the legacy map pack intentionally changes these two pins.
        # A crash can happen before new_manifest_sha256 reaches the journal.
        # All other immutable declarations must still match the snapshot.
        def without_pack(value):
            value = dict(value)
            value.pop('asset_pack', None)
            value['files'] = {name: digest for name, digest in value.get('files', {}).items()
                              if name != 'assets.atlaslite'}
            return value
        if without_pack(read(target / 'manifest.json')) != without_pack(read(backup / 'manifest.json')):
            raise ValueError('Portable immutable metadata changed beyond map import; recovery was not applied.')
    metadata = backup / 'metadata.json'
    if not metadata.is_file() or sha(metadata) != record.get('metadata_snapshot_sha256'):
        raise ValueError('Portable metadata snapshot is missing or changed.')
    entries = read(metadata)['files']
    # Validate every snapshot before making the first restoration write.
    for entry in entries:
        local_file(target, entry['path'])
        if entry['existed']:
            saved = local_file(backup, entry['snapshot'])
            if not saved.is_file() or sha(saved) != entry['sha256']:
                raise ValueError('Portable metadata snapshot failed its integrity check.')
    for entry in entries:
        path = local_file(target, entry['path'])
        if entry['existed']:
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(local_file(backup, entry['snapshot']), path)
        elif path.is_file():
            path.unlink()


def _install(source, target, *, profile_source=None, launcher=None, shortcut_path=None):
    safe_tree(source, package=True)
    module = core(source)
    module.load_contract(source)
    module.ensure_no_game_processes()
    ui_lock = target / 'state/ui.lock'
    if ui_lock.exists() and module._pid_alive(read(ui_lock).get('pid', -1)):
        raise RuntimeError('Close the Atlas launcher before installing or updating.')
    if source != target and (source in target.parents or target in source.parents):
        raise ValueError('Source and installation directories must be separate.')
    previous = target if (target / 'manifest.json').is_file() else None
    owned_profile = target / 'state/profile/settings.json'
    migration_source = associated_atlas(profile_source) if not owned_profile.is_file() else None
    if migration_source in (source, target):
        migration_source = None
    if target.exists() and source != target and previous is None:
        raise ValueError('Refusing to replace a directory that is not an Atlas installation.')
    if previous:
        safe_tree(previous, package=True)
        if read(previous / 'manifest.json').get('id') != 'hunters-atlas-lite':
            raise ValueError('The destination is not a recognized Atlas installation.')
    stamp = uuid.uuid4().hex
    journal = target.parent / ('.atlas-owned-install-' + stamp + '.json')
    stage = target.parent / ('.atlas-owned-stage-' + stamp)
    backup = target.parent / (target.name + '.before-owned-' + stamp)
    record = {'schema': 1, 'source': str(source), 'target': str(target),
              'stage': str(stage), 'backup': str(backup), 'phase': 'preparing',
              'same_target': source == target,
              'shortcut': str(shortcut_path) if shortcut_path else None,
              'original_manifest_sha256': sha(target / 'manifest.json') if previous else None}
    save_shortcut(record, journal)
    write(journal, record)
    same = source == target
    if not same:
        shutil.copytree(source, stage, ignore=shutil.ignore_patterns('state', '__pycache__', '*.pyc'))
        if previous and read(previous / 'manifest.json').get('installation_model') == 'owned-runtime-v1':
            if (previous / 'state').is_dir():
                copy_state(previous / 'state', stage / 'state')
        reused = False
    else:
        stage = source
        reused = False
        record['metadata_snapshot_sha256'] = portable_snapshot(target, backup, launcher)
        record['phase'] = 'portable-snapshotted'
        write(journal, record)
    initialize(stage, target, profile_source, launcher, previous)
    if not same:
        reused = retain_pack(previous, stage)
    if not reused and migration_source is not None:
        reused = retain_pack(migration_source, stage)
        if reused:
            record['maps_imported_from'] = str(migration_source)
    module = core(stage)
    module.load_contract(stage)
    record['new_manifest_sha256'] = sha(stage / 'manifest.json')
    if not same:
        record['phase'] = 'activating'
        write(journal, record)
        if target.exists():
            target.rename(backup)
            record['phase'] = 'backup-moved'
            write(journal, record)
        try:
            record['phase'] = 'stage-activation-intent'
            write(journal, record)
            stage.rename(target)
        except Exception:
            if backup.exists() and not target.exists():
                backup.rename(target)
            raise
    record['phase'] = 'active'
    record['maps_reused'] = reused
    record['generator_invocations'] = 0
    write(journal, record)
    shortcut_backup = target / 'state/installation/previous-shortcut.lnk'
    shortcut(shortcut_path, target, shortcut_backup)
    record['phase'] = 'complete'
    write(target / 'state/installation/receipt.json', record)
    write(journal, record)
    return record


def recover(journal_path, *, rollback=False):
    journal_path = regular_path(journal_path)
    record = read(journal_path)
    target, stage, backup = (regular_path(record[key]) for key in ('target', 'stage', 'backup'))
    stamp = journal_path.stem.removeprefix('.atlas-owned-install-')
    if (record.get('schema') != 1 or len(stamp) != 32 or
            any(character not in '0123456789abcdef' for character in stamp) or
            journal_path.parent != target.parent or stage.parent != target.parent or
            stage.name != '.atlas-owned-stage-' + stamp or backup.parent != target.parent or
            backup.name != target.name + '.before-owned-' + stamp):
        raise ValueError('Unsafe or unsupported Atlas recovery journal.')
    for key, expected in (('restoration', '.atlas-owned-restore-' + stamp),
                          ('retained_new_installation', target.name + '.retained-' + stamp)):
        if record.get(key):
            value = regular_path(record[key])
            if value.parent != target.parent or value.name != expected:
                raise ValueError('Unsafe Atlas recovery working directory.')
    with maintenance(target, recovery=True):
        available = target if target.is_dir() else backup if backup.is_dir() else stage
        if not available.is_dir():
            raise ValueError('No installation is available for recovery verification.')
        verifier = available if (available / 'bootstrap/entry.py').is_file() else Path(record['source'])
        module = core(verifier)
        module.ensure_no_game_processes()
        for tree in (target, Path(record.get('retained_new_installation', target))):
            ui_lock = tree / 'state/ui.lock'
            if ui_lock.exists() and pid_alive(read(ui_lock).get('pid')):
                raise ValueError('Close Atlas before recovery or rollback.')
        if record.get('phase') in ('rolled-back', 'recovered'):
            if not target.is_dir():
                raise ValueError('The recovered installation is missing.')
            module.load_contract(target)
            return record
        if record.get('same_target'):
            if not backup.is_dir():
                raise ValueError('Portable initialization snapshot is missing; recovery did not succeed.')
            restore_portable(record, target, backup)
            restore_shortcut(record)
            module.load_contract(target)
        elif backup.is_dir():
            safe_tree(backup, package=True)
            if sha(backup / 'manifest.json') != record['original_manifest_sha256']:
                raise ValueError('The rollback package manifest changed; both installations were preserved.')
            core(backup).load_contract(backup)
            restoration = target.parent / ('.atlas-owned-restore-' + stamp)
            retained = target.parent / (target.name + '.retained-' + stamp)
            # A previous attempt may have activated restoration immediately
            # before its final journal write. Do not retain/replace it twice.
            already_active = (not restoration.exists() and target.is_dir() and
                              record.get('restore_manifest_sha256') == sha(target / 'manifest.json') and
                              record.get('phase') == 'restore-activation-intent')
            if not already_active:
                if target.exists() and not rollback:
                    raise ValueError('Both installations exist. Use --rollback to restore the old runtime.')
                current = target if target.is_dir() else retained if retained.is_dir() else None
                if restoration.exists():
                    safe_tree(restoration, package=True)
                    incomplete = target.parent / ('.atlas-owned-incomplete-' + uuid.uuid4().hex)
                    restoration.rename(incomplete)
                record.update(restoration=str(restoration), retained_new_installation=str(retained),
                              phase='restoration-preparation-intent')
                write(journal_path, record)
                shutil.copytree(backup, restoration, ignore=shutil.ignore_patterns('state', '__pycache__', '*.pyc'))
                owned = read(backup / 'manifest.json').get('installation_model') == 'owned-runtime-v1'
                mutable = current if owned and current is not None else backup
                if (mutable / 'state').is_dir():
                    copy_state(mutable / 'state', restoration / 'state')
                if current is not None and owned:
                    old_config = read(current / 'manifest.json').get('paths', {}).get('config', 'settings/settings.ini')
                    new_config = read(restoration / 'manifest.json').get('paths', {}).get('config', 'settings/settings.ini')
                    original = local_file(current, old_config)
                    destination = local_file(restoration, new_config)
                    if original.is_file():
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(original, destination)
                    retain_pack(current, restoration)
                core(restoration).load_contract(restoration)
                record['restore_manifest_sha256'] = sha(restoration / 'manifest.json')
                record['phase'] = 'restoration-ready'
                write(journal_path, record)
                if target.exists():
                    if retained.exists():
                        raise ValueError('Both current and retained installations exist; neither was replaced.')
                    record['phase'] = 'retain-new-intent'
                    write(journal_path, record)
                    target.rename(retained)
                record['phase'] = 'restore-activation-intent'
                write(journal_path, record)
                restoration.rename(target)
            core(target).load_contract(target)
            restore_shortcut(record)
        elif target.is_dir() and record.get('original_manifest_sha256') == sha(target / 'manifest.json'):
            module.load_contract(target)
            restore_shortcut(record)
        else:
            raise ValueError('No verified rollback snapshot is available; recovery did not succeed.')
        record['phase'] = 'rolled-back' if rollback else 'recovered'
        write(journal_path, record)
        return record


def locator_path():
    return ordinary_profile().parent.parent / 'HuntersAtlas/installation.json'


def pick_folder(title):
    import tkinter as tk
    from tkinter import filedialog
    window = tk.Tk()
    window.withdraw()
    try:
        selected = filedialog.askdirectory(parent=window, title=title, mustexist=True)
    finally:
        window.destroy()
    if not selected:
        raise ValueError('Folder selection was canceled; no installation was changed.')
    return regular_path(Path(selected))


def find_update_target(explicit=None):
    if explicit is not None:
        return regular_path(explicit)
    locator = locator_path()
    if locator.is_file():
        record = read(locator)
        if record.get('schema') != 1 or record.get('installation_model') != 'owned-runtime-v1':
            raise ValueError('Unsupported Atlas installation locator.')
        target = regular_path(Path(record['target']))
        if (target / 'manifest.json').is_file():
            manifest = read(target / 'manifest.json')
            if manifest.get('id') == 'hunters-atlas-lite' and manifest.get('installation_model') == 'owned-runtime-v1':
                return target
    target = pick_folder('Select your installed Hunter\'s Atlas folder to update')
    manifest = read(target / 'manifest.json')
    if manifest.get('id') != 'hunters-atlas-lite' or manifest.get('installation_model') != 'owned-runtime-v1':
        raise ValueError('The selected folder is not an owned Atlas installation.')
    return target


def find_launcher(source, target, explicit=None, *, profile_source=None):
    if explicit is not None:
        result = regular_path(explicit)
        if not result.is_dir():
            raise ValueError('The original launcher folder does not exist.')
        return result
    association = associated_atlas(profile_source)
    for root in (target, source, association):
        if root is None:
            continue
        for name in ('.install/receipt.json', 'atlas-lite-install.json'):
            path = root / name
            if not path.is_file():
                continue
            receipt = read(path)
            raw = receipt.get('launcher_root')
            if raw:
                launcher = regular_path(Path(raw))
                if launcher.is_dir():
                    return launcher
    existing = target / 'state/profile/settings.json'
    if existing.is_file() and str(read(existing).get('user_dir') or '').strip():
        return None
    return pick_folder('Select your original Bloodborne launcher folder (existing saves and settings)')


def desktop_folder():
    """Resolve the user's real Desktop, including Windows folder redirection."""
    try:
        shell = ctypes.WinDLL('shell32', use_last_error=True)
        get_folder = shell.SHGetFolderPathW
    except (AttributeError, OSError) as error:
        raise ValueError('Windows Desktop lookup is unavailable. Supply --shortcut PATH or --no-shortcut; no installation was changed.') from error
    get_folder.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.HANDLE,
                           wintypes.DWORD, wintypes.LPWSTR]
    get_folder.restype = ctypes.c_long
    path_buffer = ctypes.create_unicode_buffer(32768)
    # CSIDL_DESKTOPDIRECTORY, SHGFP_TYPE_CURRENT: the physical per-user Desktop,
    # not the virtual Desktop shell namespace or an assumed USERPROFILE child.
    result = get_folder(None, 0x0010, None, 0, path_buffer)
    if result != 0 or not path_buffer.value:
        raise ValueError('Windows could not resolve your Desktop. Supply --shortcut PATH or --no-shortcut; no installation was changed.')
    desktop = Path(path_buffer.value)
    if not desktop.is_absolute() or not desktop.is_dir():
        raise ValueError('The Windows Desktop folder is missing or unavailable. Supply --shortcut PATH or --no-shortcut; no installation was changed.')
    # The Windows-known Desktop may itself be redirected or a OneDrive cloud
    # reparse directory. This does not relax package/root path validation.
    return desktop.resolve(strict=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=Path)
    parser.add_argument('--profile-source', type=Path, default=ordinary_profile())
    parser.add_argument('--launcher', type=Path)
    parser.add_argument('--shortcut', type=Path)
    parser.add_argument('--no-shortcut', action='store_true')
    parser.add_argument('--update', action='store_true')
    parser.add_argument('--uninstall', action='store_true')
    parser.add_argument('--recover', type=Path)
    parser.add_argument('--rollback', type=Path)
    args = parser.parse_args(argv)
    if args.recover or args.rollback:
        print(json.dumps(recover(args.recover or args.rollback, rollback=bool(args.rollback)), indent=2))
        return
    if args.uninstall:
        args.target = args.target or ROOT
        receipt = read(args.target / 'state/installation/receipt.json')
        saved = args.target / 'state/installation/previous-shortcut.lnk'
        if receipt.get('shortcut') and saved.is_file():
            shutil.copyfile(regular_path(saved), shortcut_location(receipt['shortcut']))
        receipt['uninstalled'] = True
        write(args.target / 'state/installation/receipt.json', receipt)
        print('Shortcut restored. Atlas files, maps and settings have been retained.')
        return
    target = find_update_target(args.target) if args.update else regular_path(args.target or ROOT)
    launcher = find_launcher(ROOT, target, args.launcher, profile_source=args.profile_source)
    if args.shortcut is None and not args.no_shortcut:
        args.shortcut = desktop_folder() / 'Bloodborne.lnk'
    result = install(ROOT, target, profile_source=args.profile_source,
                     launcher=launcher, shortcut_path=None if args.no_shortcut else args.shortcut)
    # This independent locator is written only after a complete transaction.
    # Upstream launchers neither own nor rewrite it.
    write(locator_path(), {'schema': 1, 'installation_model': 'owned-runtime-v1',
                          'target': str(target)})
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
