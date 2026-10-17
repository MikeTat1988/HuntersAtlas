"""Stable entry point for the independently installed, in-game Atlas runtime."""
import importlib.util
import json
import os
from pathlib import Path
import runpy
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
WINDOWED = sys.stdout is None


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def environment(contract):
    state = contract['state_root']
    port_state = state / 'port'
    port_state.mkdir(parents=True, exist_ok=True)
    profile = state / 'profile'
    if os.environ.get('BB_ATLAS_QA') == '1' and os.environ.get('BB_ATLAS_PROFILE_ROOT'):
        profile = Path(os.environ['BB_ATLAS_PROFILE_ROOT']).resolve()
    profile.mkdir(parents=True, exist_ok=True)
    settings_path = profile / 'settings.json'
    if not settings_path.exists():
        settings_path.write_text(json.dumps({'atlas_enabled': True, 'atlas_dir': str(ROOT)}, indent=2), encoding='utf-8')
    else:
        settings = json.loads(settings_path.read_text(encoding='utf-8'))
        # Package moves and transactional updates retain the user's enable preference.
        if settings.get('atlas_dir') != str(ROOT):
            settings['atlas_dir'] = str(ROOT)
            settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding='utf-8')
    for name in ('PYTHONHOME', 'PYTHONPATH', 'BB_LITE_PACKAGE', 'BB_PROBE'):
        os.environ.pop(name, None)
    os.environ.update(BB_OWNED_ATLAS_ROOT=str(ROOT), BB_OWNED_PORT_ROOT=str(contract['base_root']),
                      BB_LAUNCHER_SETTINGS_ROOT=str(profile), BB_DATA_DIR=str(port_state),
                      BB_CONFIG=str(port_state / 'bbport.ini'), BB_INPUT_CONFIG=str(port_state / 'input.ini'),
                      BB_FSR4_DIR=str(port_state / 'fsr4_shaders'), BB_FSR411_DIR=str(port_state / 'fsr4_411'),
                      PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8',
                      BB_ATLAS_PYTHON=str(contract['python']))
    windows = Path(os.environ.get('SystemRoot', r'C:\Windows'))
    os.environ['PATH'] = os.pathsep.join(map(str, (ROOT / 'bin', contract['base_root'] / 'bin', windows / 'System32', windows)))
    return settings_path


def main():
    core = load('atlas_owned_core', ROOT / 'bootstrap/entry.py')
    contract = core.load_contract(ROOT)
    args = sys.argv[1:]
    if args[:1] == ['--verify']:
        print(json.dumps({'valid': True, 'installation_model': 'owned-runtime-v1',
                          'runtime': str(contract['paths']['probe']), 'profile': str(contract['state_root'] / 'profile/settings.json')}))
        return 0
    maintenance = ROOT.parent / ('.' + ROOT.name + '.owned-maintenance.lock')
    if maintenance.exists():
        raise ValueError('Atlas installation or recovery is in progress. Finish it before starting the game.')
    if args[:1] == ['--install-update']:
        raise ValueError('Install Atlas updates using Update.cmd from the new Atlas package.')
    sys.path.insert(0, str(contract['ui'].parent))
    sys.argv = [str(contract['ui']), *args]
    with core.SessionLock(contract['state_root'] / 'ui.lock'):
        if maintenance.exists():
            raise ValueError('Atlas installation or recovery is in progress.')
        environment(contract)
        runpy.run_path(str(contract['ui']), run_name='__main__')
    return 0


if __name__ == '__main__':
    try:
        if sys.stdout is None or sys.stderr is None:
            logs = ROOT / 'state'
            logs.mkdir(parents=True, exist_ok=True)
            stream = (logs / 'launcher.log').open('a', encoding='utf-8', buffering=1)
            sys.stdout = sys.stdout or stream
            sys.stderr = sys.stderr or stream
        raise SystemExit(main())
    except Exception as error:
        import traceback
        traceback.print_exc()
        try:
            import ctypes
            if WINDOWED:
                ctypes.windll.user32.MessageBoxW(None, str(error), "Hunter's Atlas", 0x10)
        except Exception:
            pass
        raise SystemExit(2)
