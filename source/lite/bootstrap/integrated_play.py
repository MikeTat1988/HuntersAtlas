"""Run Atlas from the ordinary launcher's current settings and selected save folder."""
from pathlib import Path
import importlib.util
import json
import os
import subprocess
import sys

def core_module():
    path=Path(__file__).with_name('entry.py')
    spec=importlib.util.spec_from_file_location('atlas_lite_integrated_core',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def environment(core, contract, paths, inherited):
    env=dict(inherited)
    # All ordinary launcher choices, including its live saves, DLC and patch definitions,
    # remain as selected. Only preparation/cache and Atlas resources belong to Atlas.
    for key in list(env):
        if key.upper().startswith(('BB_MAP_','BB_LITE_','BB_ATLAS')) or key.upper()=='BB_PROBE':
            env.pop(key,None)
    base=contract['base_root'];state=contract['state_root']
    env.update(BB_ATLAS_ENABLED='1',BB_ATLAS_QA='0',BB_MAP_QA='0',
        BB_PROBE=str(paths['probe']),BB_MAP_DIR=str(paths['maps']),
        BB_MAP_ART_DIR=str(paths['art']),BB_MAP_CATALOG=str(paths['catalog']),
        BB_MAP_FONT=str(paths['font']),BB_MAP_CONFIG=str(contract['paths']['config']),
        BB_DATA_DIR=str(state),BB_LITE_PORT_DIR=str(base),
        BB_LITE_ENTRY=str(Path(__file__).resolve()),BB_LITE_BOOTSTRAP_PID=str(os.getpid()),
        BB_LITE_MINIMUM_DISK='1')
    # Preserve ordinary locations even though compilation intermediates use Atlas state.
    for key,default in {'BB_USER_DIR':base/'user','BB_CONFIG':base/'bbport.ini',
                        'BB_INPUT_CONFIG':base/'input.ini','BB_PATCHES_DIR':base/'patches',
                        'BB_PATCHES_CONFIG':base/'patches.json','BB_MODS_DIR':base/'mods',
                        'BB_MODS_CONFIG':base/'mods.json'}.items():
        env.setdefault(key,str(default))
    env.setdefault('BB_GPU_USER_DIR',env['BB_USER_DIR'])
    system_root=Path(env.get('SystemRoot',r'C:\Windows'))
    env['PATH']=os.pathsep.join(map(str,(contract['root']/'bin',base/'bin',system_root/'System32',system_root)))
    return env

def main():
    core=core_module();root=Path(__file__).resolve().parents[1]
    try:
        contract=core.load_contract(root)
        args=sys.argv[1:]
        if args[:1]==['--after']:
            core.wait_for_pid(int(args[1]));args=args[2:]
        # Restarts inherit the authoritative launcher's settings/environment.
        core.validate_game_source(contract,{'game_dir':os.environ.get('BB_GAME_DIR','')})
        core.ensure_no_game_processes()
        state=contract['state_root'];state.mkdir(parents=True,exist_ok=True)
        with core.SessionLock(state/'session.lock'):
            with core._materialized_asset_paths(contract) as staged:
                paths={**contract['paths'],**core._validated_materialized_paths(contract,staged)}
                env=environment(core,contract,paths,os.environ)
                if '--integration-dry-run' in args:
                    print(json.dumps(core._redacted_env(env),indent=2));return 0
                return subprocess.call([str(contract['launcher']),'--script',str(contract['runner']),*args],
                    cwd=str(contract['base_root']),env=env,stdin=subprocess.DEVNULL,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except Exception as error:
        print('Hunter\'s Atlas: '+str(error),file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
