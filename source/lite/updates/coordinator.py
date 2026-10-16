"""Stage, activate, recover and roll back an authenticated Atlas + launcher pair.

Only this module's fixed operations execute. Catalog records supply identities
and HTTPS artifact locations, never commands. An immutable helper interpreter
lives beside the transaction while launcher/package directories are exchanged.
"""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,os,shutil,stat,subprocess,sys,time,urllib.request, zipfile
from pathlib import Path,PurePosixPath

sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
import catalog
from transaction import Journal,regular_path,write_json,lock,alive

MUTABLE=('user','out','mods','bbport.ini','input.ini','mods.json','patches.json','last_run.log')
ATLAS_FILES=('Bloodborne.stock.exe','atlas-lite-launcher.py','atlas-lite-install.json')
MAX_EXPANDED=2*1024*1024*1024
NO_WINDOW=getattr(subprocess,'CREATE_NO_WINDOW',0)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        while b:=stream.read(1024*1024):h.update(b)
    return h.hexdigest()

def inside(root,name):
    if not isinstance(name,str) or not name or '\\' in name or ':' in name or any(p in ('','.','..') for p in name.split('/')):raise ValueError('Unsafe artifact path')
    p=PurePosixPath(name)
    if p.is_absolute():raise ValueError('Absolute artifact path')
    return regular_path(Path(root).joinpath(*p.parts),root)

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def release_identity(manifest):
    return manifest.get('compatibility') or manifest.get('legacy_runtime') or {}

def bundled_archive(package,entry):
    """A bundled archive is trusted only through the signed catalog digest."""
    path=inside(package,'.distribution/'+entry['upstream_release']+'.zip')
    if not path.is_file():return None
    if not entry.get('atlas_sha256') or sha(path)!=entry['atlas_sha256']:
        raise ValueError('Bundled Atlas archive failed its integrity check')
    return path

def copy_bundled(current,staged,catalog_path,*,fresh=None):
    data=catalog.load(catalog_path,allow_expired=True)
    for entry in data['targets']:
        archive=bundled_archive(fresh,entry) if fresh else None
        if archive is None:
            candidate=inside(current,'.distribution/'+entry['upstream_release']+'.zip')
            # A freshly signed catalog can supersede an older bundled adapter.
            if candidate.is_file() and sha(candidate)==entry.get('atlas_sha256'):archive=candidate
        if archive:
            destination=staged/'.distribution'/archive.name;destination.parent.mkdir(exist_ok=True)
            shutil.copyfile(archive,destination)
    shutil.copyfile(catalog_path,staged/'updates/catalog.json')

def materialize(package,entry,directory):
    archive=bundled_archive(package,entry)
    if archive is None:
        if not entry.get('atlas_artifact_url'):raise ValueError('No authenticated Atlas adapter is available for this launcher')
        archive=download(entry['atlas_artifact_url'],directory/'atlas.zip',entry['atlas_sha256'])
    fresh=safe_unpack(archive,directory/'package',strip_root=archive_root(archive,'manifest.json'))
    shutil.copyfile(Path(package)/'updates/catalog.json',fresh/'updates/catalog.json')
    fresh_package(fresh,entry)
    return fresh

def select_initial(package,launcher):
    """Select an embedded adapter before touching a stock launcher."""
    package=regular_path(package);launcher=regular_path(launcher)
    if (package/'.install').exists() or (launcher/'atlas-lite-install.json').exists():raise ValueError('Initial adapter selection requires a fresh package and stock launcher')
    directory=package.parent/('.atlas-select-'+os.urandom(16).hex());directory.mkdir()
    import rebuild
    fresh,entry,_=rebuild.matching_package(package,launcher,directory,need_archive=False)
    if fresh==package:return entry
    # Keep the previous extracted adapter for diagnosis; no player data exists yet.
    old=directory/'previous-package'
    os.replace(package,old)
    try:
        shutil.copytree(fresh,package)
        copy_bundled(old,package,old/'updates/catalog.json')
    except BaseException:
        if package.exists():shutil.rmtree(regular_path(package,directory.parent))
        os.replace(old,package)
        raise
    return entry

def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def verify_files(root,manifest):
    root=regular_path(root)
    if manifest.get('id')!='hunters-atlas-lite' or manifest.get('schema')!=1:raise ValueError('Invalid Atlas package')
    for name,digest in manifest['files'].items():
        if not isinstance(digest,str) or len(digest)!=64 or sha(inside(root,name))!=digest:raise ValueError('Atlas artifact hash mismatch: '+name)
    return manifest

def fresh_package(root,entry):
    root=regular_path(root)
    if sha(root/'manifest.json')!=entry['atlas_manifest_sha256']:raise ValueError('Atlas artifact does not match the signed compatibility catalog')
    manifest=verify_files(root,read(root/'manifest.json'))
    permitted=set(manifest['files'])|set(manifest.get('mutable_files',[]))|{'manifest.json'}
    if (root/'.distribution').exists():
        data=catalog.load(root/'updates/catalog.json')
        for target in data['targets']:
            archive=bundled_archive(root,target)
            if archive:permitted.add(archive.relative_to(root).as_posix())
    for p in root.rglob('*'):
        regular_path(p,root)
        if p.is_file() and p.relative_to(root).as_posix() not in permitted:raise ValueError('Unlisted file in fresh Atlas artifact: '+str(p))
    profile=release_identity(manifest)
    for key in ('upstream_release','upstream_commit','adapter_protocol'):
        if profile.get(key)!=entry.get(key):raise ValueError('Atlas adapter does not match catalog: '+key)
    if profile.get('feature_schema')!=entry.get('feature_schema') or manifest.get('asset_key_schema')!=entry.get('asset_key_schema'):
        raise ValueError('Atlas map schema does not match catalog')
    return manifest

def safe_unpack(archive,destination,*,strip_root=None):
    destination=regular_path(destination);destination.mkdir(parents=True,exist_ok=True)
    total=0;seen=set()
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            name=info.filename.rstrip('/')
            if not name:continue
            # Validate before removing the archive's root prefix.
            if '\\' in name or ':' in name or name.startswith('/') or any(p in ('','.','..') for p in name.split('/')):
                raise ValueError('Archive traversal')
            if stat.S_ISLNK(info.external_attr>>16):raise ValueError('Linked archive member')
            if strip_root:
                if name==strip_root:continue
                if not name.startswith(strip_root+'/'):raise ValueError('Mixed archive roots')
                name=name[len(strip_root)+1:]
            if name.casefold() in seen:raise ValueError('Duplicate archive path')
            seen.add(name.casefold());total+=info.file_size
            if total>MAX_EXPANDED or info.file_size>512*1024*1024:raise ValueError('Archive size limit')
            out=inside(destination,name)
            if not info.is_dir():
                out.parent.mkdir(parents=True,exist_ok=True)
                with z.open(info) as source,out.open('wb') as target:shutil.copyfileobj(source,target,1024*1024)
    return destination

def archive_root(path,filename):
    with zipfile.ZipFile(path) as z:
        roots={str(PurePosixPath(i.filename).parent) for i in z.infolist() if PurePosixPath(i.filename).name==filename}
    if len(roots)!=1 or '.' in roots:raise ValueError('Artifact must have exactly one named root')
    return next(iter(roots))

def download(url,destination,digest):
    if not url.startswith('https://'):raise ValueError('Update downloads require HTTPS')
    destination=Path(destination);temporary=destination.with_suffix('.partial')
    try:
        request=urllib.request.Request(url,headers={'User-Agent':'HuntersAtlas-update/1'})
        size=0;h=hashlib.sha256()
        with urllib.request.urlopen(request,timeout=60) as source,temporary.open('xb') as target:
            while b:=source.read(1024*1024):
                size+=len(b)
                if size>512*1024*1024:raise ValueError('Update download exceeds size limit')
                h.update(b);target.write(b)
        if h.hexdigest()!=digest:raise ValueError('Downloaded artifact digest mismatch')
        os.replace(temporary,destination)
    finally:temporary.unlink(missing_ok=True)
    return destination

def refresh_catalog(package):
    """An unavailable or rejected remote catalog never replaces the working copy."""
    package=Path(package);path=package/'updates/catalog.json'
    config=read(package/'updates/catalog-source.json')
    url=config.get('url');notice=''
    if url:
        temporary=path.with_name('catalog-refresh-'+os.urandom(16).hex()+'.json')
        try:
            if not url.startswith('https://'):raise ValueError('Catalog refresh requires HTTPS')
            request=urllib.request.Request(url,headers={'User-Agent':'HuntersAtlas-update/1'})
            with urllib.request.urlopen(request,timeout=20) as response:
                raw=response.read(1024*1024+1)
            if len(raw)>1024*1024:raise ValueError('Catalog exceeds size limit')
            temporary.write_bytes(raw);catalog.load(temporary)
            os.replace(temporary,path)
        except Exception as error:notice='Catalog refresh unavailable: '+str(error)
        finally:temporary.unlink(missing_ok=True)
    return catalog.load(path),notice

def is_current(package,entry):
    """Include adapter/UI changes when the native executable is unchanged.

    Installation records the signed artifact identity separately from the
    installed manifest, whose paths and generated-map hashes are local.
    """
    package=Path(package)
    try:
        profile=release_identity(read(package/'manifest.json'))
        return (all(profile.get(key)==entry.get(key) for key in ('upstream_release','upstream_commit','adapter_protocol'))
                and sha(package/'bin/bb-probe.exe')==entry['runtime_sha256']
                and read(package/'.install/receipt.json').get('artifact_manifest_sha256')==entry['atlas_manifest_sha256'])
    except (OSError,ValueError,KeyError):return False

def active_receipt(launcher,package):
    launcher=regular_path(launcher);package=regular_path(package)
    receipt=read(launcher/'atlas-lite-install.json')
    if receipt.get('schema') not in (1,2) or receipt.get('state')!='installed':raise ValueError('Atlas is not installed or its receipt needs recovery')
    if regular_path(receipt['launcher_root'])!=launcher or regular_path(receipt['atlas_folder'])!=package:raise ValueError('Receipt belongs to another installation')
    own=read(package/'.install/receipt.json')
    if own!=receipt:raise ValueError('Launcher and Atlas installation receipts disagree')
    for name,digest in receipt['owned_files'].items():
        if sha(inside(launcher,name))!=digest:raise ValueError('Installed launcher file changed: '+name)
    dependencies=read(package/'.install/dependencies.json')
    if receipt['stock_sha256'] not in dependencies['ordinary_port']['launcher_variants'] or sha(package/'.install/stock.exe')!=receipt['stock_sha256']:
        raise ValueError('The recoverable original launcher identity is invalid')
    verify_files(package,read(package/'manifest.json'))
    return receipt

def running_under(roots):
    if os.name!='nt':return []
    import ctypes
    from ctypes import wintypes
    class Process(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('usage',wintypes.DWORD),('pid',wintypes.DWORD),('heap',ctypes.c_size_t),
                  ('module',wintypes.DWORD),('threads',wintypes.DWORD),('parent',wintypes.DWORD),
                  ('priority',wintypes.LONG),('flags',wintypes.DWORD),('exe',wintypes.WCHAR*260)]
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.CreateToolhelp32Snapshot.argtypes=(wintypes.DWORD,wintypes.DWORD);api.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
    api.Process32FirstW.argtypes=(wintypes.HANDLE,ctypes.POINTER(Process));api.Process32NextW.argtypes=api.Process32FirstW.argtypes
    api.OpenProcess.argtypes=(wintypes.DWORD,wintypes.BOOL,wintypes.DWORD);api.OpenProcess.restype=wintypes.HANDLE
    api.QueryFullProcessImageNameW.argtypes=(wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD))
    api.CloseHandle.argtypes=(wintypes.HANDLE,)
    snapshot=api.CreateToolhelp32Snapshot(2,0)
    if snapshot==wintypes.HANDLE(-1).value:raise OSError('Cannot inspect running installation processes')
    found=[];entry=Process();entry.size=ctypes.sizeof(entry)
    try:
        ok=api.Process32FirstW(snapshot,ctypes.byref(entry))
        while ok:
            if entry.pid:
                handle=api.OpenProcess(0x1000,False,entry.pid)
                if handle:
                    try:
                        buffer=ctypes.create_unicode_buffer(32768);length=wintypes.DWORD(len(buffer))
                        if api.QueryFullProcessImageNameW(handle,0,buffer,ctypes.byref(length)):
                            path=Path(buffer.value).resolve()
                            if any(path==r or r in path.parents for r in roots):found.append(entry.pid)
                    finally:api.CloseHandle(handle)
            ok=api.Process32NextW(snapshot,ctypes.byref(entry))
    finally:api.CloseHandle(snapshot)
    return found

def wait_idle(roots,seconds=60):
    deadline=time.monotonic()+seconds
    while running_under(roots):
        if time.monotonic()>deadline:raise RuntimeError('Close the game and launcher before activating or rolling back Atlas')
        time.sleep(.25)

def native_preflight(package,launcher):
    core=load_module('atlas_update_preflight',package/'bootstrap/entry.py');contract=core.load_contract(package)
    manifest=read(package/'manifest.json')
    if manifest.get('legacy_runtime'):
        legacy=manifest['legacy_runtime']
        if legacy.get('upstream_release')!='windows-v1.7.2' or legacy.get('runtime_sha256')!=sha(package/'bin/bb-probe.exe'):
            raise ValueError('Legacy native runtime identity mismatch')
        return contract
    environment=dict(os.environ)
    environment['PATH']=os.pathsep.join(map(str,(package/'bin',launcher/'bin',Path(environment.get('SystemRoot','C:/Windows'))/'System32')))
    result=subprocess.run([str(package/'bin/bb-probe.exe'),'--atlas-build-info'],env=environment,capture_output=True,check=True,creationflags=NO_WINDOW,timeout=30)
    actual=json.loads(result.stdout);expected=read(package/'native-build.json')
    for key in ('adapter_protocol','upstream_release','upstream_commit','feature_schema'):
        if actual.get(key)!=expected.get(key):raise ValueError('Loaded native runtime preflight failed: '+key)
    return contract

def reuse_assets(current,staged,game):
    target_manifest=read(staged/'manifest.json');old_manifest=read(current/'manifest.json')
    old_pack=current/old_manifest['asset_pack']['path']
    if sha(old_pack)!=old_manifest['asset_pack']['sha256']:raise ValueError('Installed maps failed their integrity check')
    identity=load_module('atlas_update_asset_identity',staged/'tools/asset_identity.py')
    expected=identity.key(game,target_manifest)
    with zipfile.ZipFile(old_pack) as archive:
        if 'maps/generated-assets.json' not in archive.namelist():return False
        metadata=json.loads(archive.read('maps/generated-assets.json'))
    if metadata.get('asset_key')!=expected:return False
    destination=staged/target_manifest['asset_pack']['path'];shutil.copyfile(old_pack,destination)
    target_manifest['asset_pack']['sha256']=sha(destination);target_manifest['files'][target_manifest['asset_pack']['path']]=sha(destination)
    write_json(staged/'manifest.json',target_manifest)
    return True

def stage_update(launcher,current_package,new_package,upstream_archive,catalog_path,profile_path,*,allow_candidate=False,local_build=None,seed_package=None):
    launcher=regular_path(launcher);current_package=regular_path(current_package);new_package=regular_path(new_package)
    profile_path=regular_path(profile_path);profile=read(profile_path)
    if any(a==b or a in b.parents or b in a.parents for a,b in ((launcher,current_package),(launcher,new_package),(current_package,new_package))):
        raise ValueError('The current launcher, current Atlas and fresh candidate must be separate directories')
    manifest=read(new_package/'manifest.json');tag=release_identity(manifest)['upstream_release']
    if local_build is not None:
        import rebuild
        if seed_package is not None:
            seed_manifest=read(Path(seed_package)/'manifest.json')
            seed_entry=catalog.resolve(catalog.load(catalog_path),release_identity(seed_manifest)['upstream_release'],allow_candidate=allow_candidate)
            fresh_package(seed_package,seed_entry)
        entry=rebuild.validate_result(seed_package or current_package,new_package,upstream_archive,local_build)
    else:
        entry=catalog.resolve(catalog.load(catalog_path),tag,allow_candidate=allow_candidate)
        fresh_package(new_package,entry)
    upstream_archive=Path(upstream_archive)
    if sha(upstream_archive)!=entry['upstream_sha256']:raise ValueError('Official launcher download digest mismatch')
    if str(launcher.anchor).casefold()!=str(current_package.anchor).casefold():raise ValueError('Atomic updates require the launcher and Atlas on the same volume')
    with lock(launcher):
        receipt=active_receipt(launcher,current_package)
        # The old launcher may remain open during staging; game/session locks may not.
        session=current_package/'state/session.lock'
        if session.exists() and alive(read(session).get('pid')):raise RuntimeError('Close the running Atlas session before staging an update')
        if shutil.disk_usage(launcher.parent).free<1024*1024*1024:raise OSError('At least 1 GiB of free space is required to stage a recoverable Atlas update')
        transaction=launcher.parent/('.atlas-update-'+os.urandom(16).hex());transaction.mkdir()
        target_launcher=transaction/'launcher';target_atlas=transaction/'atlas';helper=transaction/'helper'
        old_launcher=transaction/'previous-launcher';old_atlas=transaction/'previous-atlas'
        journal_path=transaction/'journal.json'
        write_json(journal_path,dict(schema=1,state='staging',transaction_root=str(transaction),
            allowed_roots=[str(transaction),str(launcher),str(current_package)],launcher=str(launcher),atlas=str(current_package),
            staged_launcher=str(target_launcher),staged_atlas=str(target_atlas),previous_launcher=str(old_launcher),previous_atlas=str(old_atlas),
            profile_path=str(profile_path),previous_atlas_fields=receipt.get('previous_atlas_fields',{}),
            atlas_enabled=profile.get('atlas_enabled',True),old_atlas_fields={k:profile[k] for k in ('atlas_dir','atlas_enabled') if k in profile},
            target=entry,cancel_path=str(transaction/'cancel.request'),actions=[]))
        journal=Journal(journal_path)
        print('Atlas update staging and recovery: '+str(transaction),flush=True)
        try:
            def ignore(directory,names):
                if Path(directory)==launcher:return [n for n in names if n in MUTABLE or n in ATLAS_FILES]
                return [n for n in names if n=='__pycache__']
            shutil.copytree(launcher,target_launcher,ignore=ignore)
            prior=read(current_package/'dependencies.json')['ordinary_port']
            for name in prior['files']:
                path=inside(target_launcher,name)
                if path.is_file():path.unlink()
            private=target_launcher/'_internal'
            if private.exists():regular_path(private,transaction);shutil.rmtree(private)
            safe_unpack(upstream_archive,target_launcher,strip_root=archive_root(upstream_archive,'run.py'))
            shutil.copytree(new_package,target_atlas)
            copy_bundled(current_package,target_atlas,catalog_path,fresh=new_package)
            helper.mkdir();shutil.copyfile(target_launcher/'Bloodborne.exe',helper/'Bloodborne.exe')
            shutil.copytree(target_launcher/'_internal',helper/'_internal')
            for name in ('coordinator.py','transaction.py','catalog.py','trusted-key.json'):
                shutil.copyfile(Path(__file__).with_name(name),transaction/name)
            for filename,action in (('Recover.cmd','--recover'),('Rollback.cmd','--rollback')):
                command='@echo off\r\n"'+str(helper/'Bloodborne.exe')+'" --script "'+str(transaction/'coordinator.py')+'" '+action+' "'+str(journal_path)+'"\r\n'
                (transaction/filename).write_text(command,encoding='utf-8',newline='')
            (transaction/'Cancel.cmd').write_text('@echo off\r\necho cancel>"'+journal.data['cancel_path']+'"\r\n',encoding='utf-8',newline='')
            for name in MUTABLE:
                source=launcher/name
                if source.is_file():shutil.copyfile(source,target_launcher/name)
            profile_stage=transaction/'profile';profile_stage.mkdir();write_json(profile_stage/'settings.json',profile)
            reused=reuse_assets(current_package,target_atlas,Path(profile['game_dir']))
            journal.data['assets_reused']=reused;journal.save()
            environment=dict(os.environ,BB_LAUNCHER_SETTINGS_ROOT=str(profile_stage))
            environment['PSModulePath']=str(Path(environment.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/Modules')
            powershell=Path(environment.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
            command=[str(powershell),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(target_atlas/'installer/Manage-Atlas.ps1'),
                     '-Mode','Install','-LauncherRoot',str(target_launcher),'-PackageRoot',str(target_atlas),'-CancellationFile',journal.data['cancel_path'],'-NoDialog']
            with (transaction/'preparation.log').open('wb') as log:
                process=subprocess.Popen(command,env=environment,stdout=log,stderr=subprocess.STDOUT,creationflags=NO_WINDOW)
                journal.data['preparation_pid']=process.pid;journal.save();result=process.wait()
            if result:raise RuntimeError('Staged installation failed or was cancelled; see '+str(transaction/'preparation.log'))
            native_preflight(target_atlas,target_launcher)
            # A separate verified host survives activation directory renames.
            journal.state('preflight_passed')
            return journal_path
        except BaseException as error:
            journal.data['error']=str(error);journal.state('staging_failed');raise


def stage_pending(launcher,current_package,upstream_archive,entry,profile_path,reason):
    """Install the official launcher while retaining Atlas for a later rebuild.

    The owned wrapper remains available for status/retry, but Play uses only the
    new stock runtime until a rebuilt adapter has passed preflight.
    """
    launcher=regular_path(launcher);atlas=regular_path(current_package);profile_path=regular_path(profile_path)
    if sha(upstream_archive)!=entry['upstream_sha256']:raise ValueError('Official launcher archive changed')
    if launcher.anchor.casefold()!=atlas.anchor.casefold():raise ValueError('Updates require Atlas and launcher on the same volume')
    with lock(launcher):
        receipt=active_receipt(launcher,atlas);profile=read(profile_path)
        session=atlas/'state/session.lock'
        if session.exists() and alive(read(session).get('pid')):raise RuntimeError('Close the game before updating')
        root=launcher.parent/('.atlas-update-'+os.urandom(16).hex());root.mkdir()
        target=root/'launcher';package=root/'atlas';helper=root/'helper'
        path=root/'journal.json'
        write_json(path,dict(schema=1,state='staging',transaction_root=str(root),allowed_roots=[str(root),str(launcher),str(atlas)],
            launcher=str(launcher),atlas=str(atlas),staged_launcher=str(target),staged_atlas=str(package),
            previous_launcher=str(root/'previous-launcher'),previous_atlas=str(root/'previous-atlas'),profile_path=str(profile_path),
            previous_atlas_fields=receipt.get('previous_atlas_fields',{}),old_atlas_fields={k:profile[k] for k in ('atlas_dir','atlas_enabled') if k in profile},
            atlas_enabled=profile.get('atlas_enabled',True),target=entry,pending=True,assets_reused=True,
            cancel_path=str(root/'cancel.request'),actions=[]))
        journal=Journal(path)
        try:
            pristine=safe_unpack(upstream_archive,root/'official',strip_root=archive_root(upstream_archive,'run.py'))
            deps_builder=load_module('pending_dependencies',atlas/'updates/build_dependencies.py')
            deps=deps_builder.build_template(pristine,Path(upstream_archive),pristine,asset_url=entry['upstream_url'],
                release_page='https://github.com/Supermedo/bloodborne_pc/releases/tag/'+entry['upstream_release'])
            def ignore(directory,names):
                if Path(directory)==launcher:return [n for n in names if n in (*MUTABLE,*ATLAS_FILES,'_internal')]
                return [n for n in names if n=='__pycache__']
            shutil.copytree(launcher,target,ignore=ignore)
            for name in read(atlas/'dependencies.json')['ordinary_port']['files']:
                old=inside(target,name)
                if old.is_file():old.unlink()
            shutil.copytree(pristine,target,dirs_exist_ok=True)
            stock_hash=sha(target/'Bloodborne.exe');entry=dict(entry,stock_launcher_sha256=stock_hash)
            journal.data['target']=entry
            manifest=read(atlas/'manifest.json');package.mkdir()
            for name in manifest['files']:
                source=inside(atlas,name);destination=inside(package,name);destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,destination)
            for name in ('settings/settings.ini','updates/catalog.json'):
                destination=package/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(atlas/name,destination)
            copy_bundled(atlas,package,atlas/'updates/catalog.json')
            install=package/'.install';install.mkdir()
            shutil.copyfile(target/'Bloodborne.exe',install/'stock.exe')
            shutil.copyfile(target/'Bloodborne.exe',target/'Bloodborne.stock.exe')
            write_json(install/'dependencies.json',deps)
            for name in ('manifest.json','assets.atlaslite'):shutil.copyfile(atlas/name,install/name)
            shutil.copyfile(profile_path,install/'settings-before.json')
            helper.mkdir();shutil.copyfile(target/'Bloodborne.exe',helper/'Bloodborne.exe');shutil.copytree(target/'_internal',helper/'_internal')
            for name in ('coordinator.py','transaction.py','catalog.py','trusted-key.json'):shutil.copyfile(Path(__file__).with_name(name),root/name)
            for filename,action in (('Recover.cmd','--recover'),('Rollback.cmd','--rollback')):
                (root/filename).write_text('@echo off\n"'+str(helper/'Bloodborne.exe')+'" --script "'+str(root/'coordinator.py')+'" '+action+' "'+str(path)+'"\n')
            (root/'Cancel.cmd').write_text('@echo off\necho cancel>"'+str(root/'cancel.request')+'"\n')
            deps['ordinary_port']['root']=str(target);deps['ordinary_port']['launcher_path']='Bloodborne.stock.exe'
            deps['ordinary_port']['launcher_variants'][stock_hash]['path']='Bloodborne.stock.exe'
            write_json(package/'dependencies.json',deps)
            write_json(package/'adapter-release.json',dict(upstream_release=entry['upstream_release']))
            write_json(package/'updates/pending.json',dict(reason=str(reason),target=entry['upstream_release'],last_attempt=time.time()))
            manifest['runtime_pending']=True
            manifest['files']={n:sha(package/n) for n in manifest['files']}
            for name in ('adapter-release.json','dependencies.json'):manifest['files'][name]=sha(package/name)
            manifest['mutable_files']=list(set(manifest.get('mutable_files',[]))|{'updates/pending.json'})
            write_json(package/'manifest.json',manifest)
            bridge=target/'atlas-lite-launcher.py'
            bridge.write_text("import runpy\nrunpy.run_path("+json.dumps(str(package/'integration/ui/bbport_launcher_win.py'))+", run_name='__main__')\n")
            shutil.copyfile(package/'integration/AtlasLauncher.exe',target/'Bloodborne.exe')
            pending_receipt=dict(receipt,stock_sha256=stock_hash,launcher_root=str(target),atlas_folder=str(package),
                owned_files={n:sha(target/n) for n in ('Bloodborne.exe','Bloodborne.stock.exe','atlas-lite-launcher.py')})
            write_json(package/'.install/receipt.json',pending_receipt);write_json(target/'atlas-lite-install.json',pending_receipt)
            journal.data['target']['atlas_manifest_sha256']=sha(package/'manifest.json')
            journal.state('preflight_passed');return path
        except BaseException as error:
            journal.data['error']=str(error);journal.state('staging_failed');raise

def bind_final(journal):
    data=journal.data;atlas=Path(data['staged_atlas']);launcher=Path(data['staged_launcher'])
    dependencies=read(atlas/'dependencies.json');dependencies['ordinary_port']['root']=data['launcher'];write_json(atlas/'dependencies.json',dependencies)
    manifest=read(atlas/'manifest.json');manifest['files']['dependencies.json']=sha(atlas/'dependencies.json');write_json(atlas/'manifest.json',manifest)
    bridge=launcher/'atlas-lite-launcher.py'
    bridge.write_text("import runpy\nrunpy.run_path("+json.dumps(str(Path(data['atlas'])/'integration/ui/bbport_launcher_win.py'))+", run_name='__main__')\n",encoding='utf-8')
    receipt=read(atlas/'.install/receipt.json')
    receipt.update(atlas_folder=data['atlas'],launcher_root=data['launcher'],profile_path=data['profile_path'],
                   previous_atlas_fields=data['previous_atlas_fields'],update_journal=str(journal.path),
                   artifact_manifest_sha256=data['target']['atlas_manifest_sha256'])
    receipt['owned_files']['atlas-lite-launcher.py']=sha(bridge)
    write_json(atlas/'.install/receipt.json',receipt);write_json(launcher/'atlas-lite-install.json',receipt)

def change_association(data,fields,*,preserve_enabled=False):
    path=Path(data['profile_path']);profile=read(path)
    for key in ('atlas_dir','atlas_enabled'):
        if preserve_enabled and key=='atlas_enabled':continue
        if key in fields:profile[key]=fields[key]
        else:profile.pop(key,None)
    write_json(path,profile)

def activate(path,*,fail_after=None):
    journal=Journal(path);d=journal.data
    if d['state'] not in ('preflight_passed','activation_pending'):raise ValueError('Transaction is not ready for activation')
    launcher=Path(d['launcher']);atlas=Path(d['atlas'])
    with lock(launcher):
        wait_idle([launcher,atlas])
        active_receipt(launcher,atlas)
        bind_final(journal)
        # Drop staged defaults; the live mutable files are renamed into place.
        for name in MUTABLE:
            candidate=Path(d['staged_launcher'])/name
            if candidate.exists():
                regular_path(candidate,Path(d['transaction_root']))
                if candidate.is_dir():shutil.rmtree(candidate)
                else:candidate.unlink()
        journal.state('activation_pending')
        try:
            journal.move(launcher,Path(d['previous_launcher']))
            if fail_after==1:raise RuntimeError('Injected activation interruption')
            journal.move(atlas,Path(d['previous_atlas']))
            if fail_after==2:raise RuntimeError('Injected activation interruption')
            journal.move(Path(d['staged_launcher']),launcher)
            journal.move(Path(d['staged_atlas']),atlas)
            for name in MUTABLE:
                old=Path(d['previous_launcher'])/name
                if old.exists():journal.move(old,launcher/name)
            current_profile=read(d['profile_path'])
            change_association(d,{'atlas_dir':str(atlas),'atlas_enabled':current_profile.get('atlas_enabled',d['atlas_enabled'])})
            if d.get('pending'):
                if sha(launcher/'Bloodborne.stock.exe')!=d['target']['stock_launcher_sha256']:raise ValueError('Pending stock launcher identity mismatch')
            else:native_preflight(atlas,launcher)
            journal.state('active')
        except BaseException:
            journal.restore();change_association(d,d['old_atlas_fields'],preserve_enabled=True);raise
    return journal.data

def recover(path,*,rollback=False):
    journal=Journal(path);d=journal.data;launcher=Path(d['launcher']);atlas=Path(d['atlas'])
    with lock(launcher):
        wait_idle([launcher,atlas])
        if d['state']=='rolled_back':return d
        if d['state'] in ('staging','staging_failed'):
            Path(d['cancel_path']).write_text('cancel',encoding='ascii')
            deadline=time.monotonic()+40
            while alive(d.get('preparation_pid')) or running_under([Path(d['staged_launcher']),Path(d['staged_atlas'])]):
                if time.monotonic()>deadline:raise RuntimeError('Preparation shutdown is not confirmed; keep both installations and retry recovery after preparation stops')
                time.sleep(.25)
        if d['state']=='active' and not rollback:raise ValueError('This update is active; request rollback explicitly')
        if d['state']=='active':
            active_receipt(launcher,atlas)
            # Preserve new progress/settings, including mutable paths created
            # after the update. Never restore a stale snapshot of player data.
            for name in MUTABLE:
                current=launcher/name;old=Path(d['previous_launcher'])/name
                if current.exists() and not old.exists() and not any(a['source']==str(old) for a in d['actions']):
                    os.replace(current,old)
        journal.restore()
        change_association(d,d['old_atlas_fields'],preserve_enabled=True)
    return journal.data

def dispatch_helper(journal_path,action='--activate',after=None,*,relaunch=False):
    transaction=Path(journal_path).parent;host=transaction/'helper/Bloodborne.exe'
    command=[str(host),'--script',str(transaction/'coordinator.py'),action,str(journal_path)]
    if after:command+=['--after',str(after)]
    if relaunch:command+=['--relaunch']
    return subprocess.Popen(command,cwd=transaction,stdin=subprocess.DEVNULL,creationflags=NO_WINDOW)

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    actions=parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--update',action='store_true');actions.add_argument('--activate',type=Path)
    actions.add_argument('--recover',type=Path);actions.add_argument('--rollback',type=Path)
    actions.add_argument('--select-initial',action='store_true')
    parser.add_argument('--launcher',type=Path);parser.add_argument('--current-atlas',type=Path)
    parser.add_argument('--package',type=Path);parser.add_argument('--upstream-zip',type=Path)
    parser.add_argument('--catalog',type=Path);parser.add_argument('--profile',type=Path)
    parser.add_argument('--allow-candidate',action='store_true');parser.add_argument('--after',type=int)
    parser.add_argument('--relaunch',action='store_true')
    args=parser.parse_args(argv)
    if args.after:
        while alive(args.after):time.sleep(.25)
    if args.select_initial:
        select_initial(args.package,args.launcher);return 0
    if args.activate:result=activate(args.activate)
    elif args.recover:result=recover(args.recover)
    elif args.rollback:result=recover(args.rollback,rollback=True)
    else:
        if not all((args.launcher,args.current_atlas,args.package,args.catalog,args.profile)):
            raise ValueError('Combined update requires explicit launcher, current Atlas, fresh package, signed catalog and profile paths')
        upstream=args.upstream_zip
        local_build=None;seed_package=None
        if upstream is None:
            import rebuild
            directory=args.launcher.parent/('.atlas-download-'+os.urandom(16).hex());directory.mkdir()
            fresh,target,upstream=rebuild.matching_package(args.package,args.launcher,directory)
            if target.get('validation_status')=='local-build':
                # Authenticate against the new distribution's seed, then stage
                # through the same local-build verifier using that seed owner.
                rebuild.validate_result(args.package,fresh,upstream,target)
                local_build=target;seed_package=args.package
            args.package=fresh
        path=stage_update(args.launcher,args.current_atlas,args.package,upstream,args.catalog,args.profile,allow_candidate=args.allow_candidate,local_build=local_build,seed_package=seed_package)
        dispatch_helper(path,after=os.getpid());result={'state':'activation_pending','journal':str(path)}
    if args.activate and args.relaunch and result['state']=='active':
        environment=dict(os.environ,BB_LAUNCHER_SETTINGS_ROOT=str(Path(result['profile_path']).parent))
        subprocess.Popen([str(Path(result['launcher'])/'Bloodborne.exe')],cwd=result['launcher'],env=environment,stdin=subprocess.DEVNULL,creationflags=NO_WINDOW)
    print(json.dumps({'state':result['state'],'journal':str(args.activate or args.recover or args.rollback or result.get('journal',''))}))
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as error:
        print('Atlas update: '+str(error),file=sys.stderr);raise SystemExit(2)
