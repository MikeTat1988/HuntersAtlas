"""Build the existing Atlas integration against an official launcher release.

Builds are local derivations, not maintainer-signed downloads. The shipped seed
is hash-pinned by the installed manifest; upstream inputs are resolved through
the official GitHub API, and conflicts stop the build instead of guessing.
"""
from __future__ import annotations
import contextlib,json,os,re,shutil,subprocess,time,urllib.request,zipfile
from pathlib import Path
import coordinator as c

API='https://api.github.com/repos/Supermedo/bloodborne_pc/'
TOOLS_URL='https://github.com/msys2/msys2-installer/releases/download/2026-09-27/msys2-base-x86_64-20260927.sfx.exe'
TOOLS_SHA='ad336cccfda47758b5e15cda993fbba421115cb0b126697daef1ee4dfe37209f'
PACKAGES=['git']+['mingw-w64-clang-x86_64-'+n for n in (
    'boost','clang','cmake','ffmpeg','fmt','glslang','miniupnpc','ninja','nlohmann-json',
    'openssl','pkgconf','protobuf','python','robin-map','sdl3','spirv-cross','spirv-headers',
    'spirv-tools','vulkan-headers','vulkan-loader','vulkan-memory-allocator','xxhash','zlib','zydis')]

class ProcessShutdownError(RuntimeError):
    """Retain the short drive if Windows cannot confirm the build tree stopped."""

def check_cancelled():
    c.check_cancelled()

def progress_message(message):
    check_cancelled()
    print(message,flush=True)

@contextlib.contextmanager
def short_workspace(directory):
    """Own a temporary DOS drive alias, independent of LongPathsEnabled.

    The physical workspace and logs survive failures. Never remove an alias
    unless it still points to the exact directory created for this build.
    """
    directory=c.regular_path(directory)
    if os.name!='nt':
        yield directory;return
    import ctypes
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.QueryDosDeviceW.argtypes=(ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_uint32)
    def target(letter):
        buffer=ctypes.create_unicode_buffer(32768)
        return buffer.value if api.QueryDosDeviceW(letter,buffer,len(buffer)) else None
    subst=Path(os.environ['SystemRoot'])/'System32/subst.exe'
    expected='\\??\\'+str(directory)
    letter=None
    for candidate in reversed('DEFGHIJKLMNOPQRSTUVWXYZ'):
        name=candidate+':'
        if target(name) is not None:continue
        result=subprocess.run([str(subst),name,str(directory)],capture_output=True,creationflags=c.NO_WINDOW,timeout=10)
        if result.returncode==0 and target(name)==expected:
            letter=name;break
    if letter is None:raise OSError('Atlas needs a free drive letter for a short build workspace; no launcher files were changed')
    receipt={'pid':os.getpid(),'drive':letter,'directory':str(directory),'released':False}
    safe_to_release=True
    try:
        c.write_json(directory/'workspace-drive.json',receipt)
        yield Path(letter+'/')
    except ProcessShutdownError:
        safe_to_release=False
        c.write_json(directory/'shutdown-failed.json',receipt)
        raise
    finally:
        if safe_to_release and target(letter)==expected:
            result=subprocess.run([str(subst),letter,'/D'],capture_output=True,creationflags=c.NO_WINDOW,timeout=10)
            if result.returncode:raise OSError('Could not release the owned Atlas build drive '+letter+'; logs remain at '+str(directory))
            receipt['released']=True;c.write_json(directory/'workspace-drive.json',receipt)

def api(url):
    request=urllib.request.Request(url,headers={'User-Agent':'HuntersAtlas-rebuild/1','Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(request,timeout=60) as r:return json.load(r)

def official(version,directory):
    if not re.fullmatch(r'\d+\.\d+(?:\.\d+){0,2}',version) or tuple(map(int,version.split('.'))) < (1,7):
        raise ValueError('Automatic rebuild requires an official Windows release from 1.7 onward')
    tag='windows-v'+version;release=api(API+'releases/tags/'+tag)
    if release.get('draft') or release.get('prerelease') or release.get('tag_name')!=tag:raise ValueError('Not an official stable release')
    assets=[a for a in release['assets'] if a['name']=='Bloodborne-Windows.zip']
    if len(assets)!=1:raise ValueError('Official Windows archive missing or ambiguous')
    a=assets[0];digest=(a.get('digest') or '').removeprefix('sha256:')
    if not re.fullmatch('[0-9a-f]{64}',digest):raise ValueError('Official release has no verifiable archive digest')
    expected='https://github.com/Supermedo/bloodborne_pc/releases/download/'+tag+'/Bloodborne-Windows.zip'
    if a['browser_download_url']!=expected:raise ValueError('Unexpected official archive location')
    archive=Path(directory)/'upstream.zip';c.download(expected,archive,digest)
    return dict(upstream_release=tag,upstream_url=expected,upstream_sha256=digest,archive=str(archive),release_id=release['id'])

def installed_version(launcher,directory):
    """Read VERSION from the stock host's existing --script calling frame."""
    launcher=Path(launcher);directory=Path(directory)
    host=launcher/'Bloodborne.stock.exe'
    if not host.is_file():host=launcher/'Bloodborne.exe'
    probe=directory/'launcher-version.py';result=directory/'launcher-version.json'
    probe.write_text('import inspect,json\nfrom pathlib import Path\n'
        'versions=[f.frame.f_globals.get("VERSION") for f in inspect.stack()]\n'
        'versions=[v for v in versions if isinstance(v,str)]\n'
        'Path('+repr(str(result))+').write_text(json.dumps(versions))\n',encoding='utf-8')
    subprocess.run([str(host),'--script',str(probe)],check=True,timeout=30,creationflags=c.NO_WINDOW)
    versions=set(c.read(result))
    if len(versions)!=1:raise ValueError('Cannot identify the installed stock launcher version')
    version=versions.pop()
    if not re.fullmatch(r'\d+\.\d+(?:\.\d+){0,2}',version):raise ValueError('Invalid installed launcher version')
    return version

def matching_package(package,launcher,directory,*,tools_cache=None,need_archive=True):
    """Select/build for the installed stock binary, never silently downgrade it."""
    package=Path(package);launcher=Path(launcher);directory=Path(directory)
    host=launcher/'Bloodborne.stock.exe'
    if not host.exists():host=launcher/'Bloodborne.exe'
    digest=c.sha(host)
    data=c.catalog.load(package/'updates/catalog.json',allow_expired=True)
    matches=[e for e in data['targets'] if e.get('stock_launcher_sha256')==digest]
    if len(matches)==1:
        entry=c.catalog.resolve(data,matches[0]['upstream_release'],allow_candidate=bool(c.read(package/'manifest.json').get('candidate')))
        if c.sha(package/'manifest.json')==entry['atlas_manifest_sha256']:
            c.fresh_package(package,entry);fresh=package
        else:fresh=c.materialize(package,entry,directory)
        archive=c.download(entry['upstream_url'],directory/'upstream.zip',entry['upstream_sha256']) if need_archive else None
        return fresh,entry,archive
    entry=official(installed_version(launcher,directory),directory)
    pristine=c.safe_unpack(entry['archive'],directory/'identity',strip_root=c.archive_root(entry['archive'],'run.py'))
    if c.sha(pristine/'Bloodborne.exe')!=digest:raise ValueError('Installed launcher does not match the official release')
    fresh,entry=build(package,entry,directory,tools_cache=tools_cache)
    return fresh,entry,Path(entry['archive'])

def source_archive(repository,commit,directory,name):
    if not re.fullmatch('[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository) or not re.fullmatch('[0-9a-f]{40}',commit):
        raise ValueError('Invalid immutable source identity')
    archive=directory/(name+'.zip');url='https://codeload.github.com/'+repository+'/zip/'+commit
    # Git source archives have no release-asset digest. The immutable commit and
    # HTTPS origin are recorded along with the exact received archive digest.
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'HuntersAtlas-rebuild/1'}),timeout=90) as r,archive.open('xb') as out:
        size=0
        while block:=r.read(1024*1024):
            check_cancelled()
            size+=len(block)
            if size>512*1024*1024:raise ValueError('Source archive exceeds limit')
            out.write(block)
    with zipfile.ZipFile(archive) as z:root=z.infolist()[0].filename.split('/')[0]
    check_cancelled()
    return c.safe_unpack(archive,directory/name,strip_root=root,preserve_alias=True),c.sha(archive)

def normalized(data):return data.replace(b'\r\n',b'\n') if b'\0' not in data[:8192] else data

def merge_file(base,new,ours,scratch,git):
    b=normalized(base.read_bytes()) if base.is_file() else None
    n=normalized(new.read_bytes()) if new.is_file() else None
    o=normalized(ours.read_bytes()) if ours.is_file() else None
    if b==n:return
    if o==b:
        if n is None:ours.unlink(missing_ok=True)
        else:ours.parent.mkdir(parents=True,exist_ok=True);ours.write_bytes(n)
        return
    if o==n:return
    if b is None or n is None or o is None:raise ValueError('Atlas source conflict: '+str(ours))
    if any(b'\0' in v[:8192] for v in (b,n,o)):raise ValueError('Binary source conflict: '+str(ours))
    scratch.mkdir(parents=True,exist_ok=True)
    paths=[scratch/name for name in ('ours','base','upstream')]
    for p,v in zip(paths,(o,b,n)):p.write_bytes(v)
    result=subprocess.run([str(git),'merge-file','-p',*map(str,paths)],capture_output=True,creationflags=c.NO_WINDOW)
    if result.returncode:raise ValueError('Atlas source merge requires review: '+str(ours))
    ours.write_bytes(result.stdout)

def merge_tree(base,new,ours,scratch,git):
    names={p.relative_to(root).as_posix() for root in (base,new) for p in root.rglob('*') if p.is_file()}
    for name in sorted(names):merge_file(base/name,new/name,ours/name,scratch,git)

def stop_process_tree(process):
    if process.poll() is not None:return
    if os.name=='nt':
        killer=Path(os.environ['SystemRoot'])/'System32/taskkill.exe'
        try:result=subprocess.run([str(killer),'/PID',str(process.pid),'/T','/F'],capture_output=True,creationflags=c.NO_WINDOW,timeout=30)
        except (OSError,subprocess.TimeoutExpired) as error:raise ProcessShutdownError('Cannot verify shutdown of Atlas build processes; keep the recovery workspace and its build drive') from error
        if result.returncode and process.poll() is None:raise ProcessShutdownError('Cannot verify shutdown of Atlas build processes; keep the recovery workspace and its build drive')
    else:process.kill()
    try:process.wait(timeout=30)
    except subprocess.TimeoutExpired as error:raise ProcessShutdownError('Atlas build processes did not exit; keep the recovery workspace and its build drive') from error

def run(command,log,*,env=None,cwd=None,progress=progress_message,timeout=7200,idle_timeout=1200,heartbeat=10):
    check_cancelled()
    display_log=str(Path(log).resolve())
    started=last_change=last_report=time.monotonic();size=Path(log).stat().st_size if Path(log).exists() else 0
    with Path(log).open('ab') as out:
        process=subprocess.Popen(list(map(str,command)),env=env,cwd=cwd,stdout=out,stderr=subprocess.STDOUT,creationflags=c.NO_WINDOW)
        try:
            while process.poll() is None:
                check_cancelled();now=time.monotonic();current=Path(log).stat().st_size
                if current!=size:size=current;last_change=now
                if now-started>timeout:raise TimeoutError('Atlas build exceeded its time limit; see '+display_log)
                if now-last_change>idle_timeout:raise TimeoutError('Atlas build produced no output for '+str(idle_timeout)+' seconds; see '+display_log)
                if now-last_report>=heartbeat:
                    with Path(log).open('rb') as stream:
                        stream.seek(max(0,size-2048));lines=stream.read().decode('utf-8',errors='replace').splitlines()
                    tail=next((line.strip() for line in reversed(lines) if line.strip()),'Waiting for build tools')
                    progress('Atlas build: '+str(int(now-started))+'s elapsed | '+tail[-240:]);last_report=now
                time.sleep(.2)
        finally:
            if process.poll() is None:stop_process_tree(process)
    if process.returncode:raise RuntimeError('Atlas rebuild command failed; see '+display_log)

def toolchain(cache,log,progress):
    cache=c.regular_path(cache);cache.mkdir(parents=True,exist_ok=True)
    root=cache/'msys64';bash=root/'usr/bin/bash.exe';ready=cache/'ready.json'
    if ready.is_file() and all((root/p).is_file() for p in ('usr/bin/git.exe','clang64/bin/cmake.exe','clang64/bin/clang++.exe')):return root
    progress('Preparing Atlas build tools (first rebuild only)…')
    if not bash.is_file():
        archive=c.download(TOOLS_URL,cache/'msys2.exe',TOOLS_SHA)
        run([archive,'-y','-o'+str(cache)],log,progress=progress)
    env=dict(os.environ,MSYSTEM='CLANG64',CHERE_INVOKING='yes',MSYS2_PATH_TYPE='minimal')
    run([bash,'-lc','true'],log,env=env,cwd=cache,progress=progress)
    # MSYS2 requires core and normal updates in separate processes.
    for _ in range(2):run([bash,'-lc','pacman --noconfirm -Syuu'],log,env=env,cwd=cache,progress=progress)
    run([bash,'-lc','pacman --noconfirm --needed -S '+' '.join(PACKAGES)],log,env=env,cwd=cache,progress=progress)
    c.write_json(ready,{'bootstrap_sha256':TOOLS_SHA,'packages':PACKAGES})
    return root

def msys_path(path):
    path=Path(path).absolute();return '/'+path.drive[0].lower()+path.as_posix()[2:]

def build(package,entry,directory,progress=progress_message,*,tools_cache=None):
    directory=c.regular_path(directory)
    work=directory/'rebuild';work.mkdir()
    progress('Atlas build workspace and logs: '+str(work))
    with short_workspace(work) as short:
        fresh,target=_build(package,entry,directory,progress,tools_cache=tools_cache,work=short)
        return work/fresh.relative_to(short),target

def _build(package,entry,directory,progress,*,tools_cache,work):
    package=c.regular_path(package);directory=c.regular_path(directory)
    manifest=c.read(package/'manifest.json');seed=package/'updates/rebuild-seed.zip'
    if c.sha(seed)!=manifest['files'].get('updates/rebuild-seed.zip'):raise ValueError('Atlas rebuild seed failed verification')
    commit=api(API+'commits/'+entry['upstream_release'])['sha']
    if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('Invalid upstream commit')
    entry=dict(entry,upstream_commit=commit)
    progress('Preparing Atlas for launcher '+entry['upstream_release'].removeprefix('windows-v')+'…')
    log=work/'build.log'
    if shutil.disk_usage(work).free<8*1024*1024*1024:raise OSError('Atlas rebuilding needs 8 GiB of free space')
    cache=Path(tools_cache) if tools_cache else Path(os.environ.get('LOCALAPPDATA',package.parent))/'HuntersAtlas/build-tools'
    tools=toolchain(cache,log,progress);git=tools/'usr/bin/git.exe'
    progress('Extracting the verified Atlas build sources…')
    c.safe_unpack(seed,work/'seed',preserve_alias=True);info=c.read(work/'seed/seed.json')
    new,source_sha=source_archive('Supermedo/bloodborne_pc',commit,work,'upstream-source')
    native=work/'seed/native';base=work/'seed/base'
    progress('Applying Atlas integration to the official source…')
    merge_tree(base,new,native,work/'merge',git)
    tree=api(API+'git/trees/'+commit+'?recursive=1')
    if tree.get('truncated'):raise ValueError('Incomplete upstream source tree')
    pins={n['path']:n['sha'] for n in tree['tree'] if n['mode']=='160000'}
    if pins!=info['submodules']:raise ValueError('Upstream dependency revisions changed; Atlas dependency review is required')
    # Version is read from adapter-release.json, rather than merged as a constant.
    ui_new=work/'launcher-ui.py';ui_new.write_bytes((new/'launcher/bbport_launcher_win.py').read_bytes())
    original_version=re.search(rb'^VERSION = .+$',(base/'launcher/bbport_launcher_win.py').read_bytes(),re.M).group(0)
    ui_new.write_bytes(re.sub(rb'^VERSION = .+$',lambda _:original_version,ui_new.read_bytes(),flags=re.M))
    merge_file(base/'launcher/bbport_launcher_win.py',ui_new,work/'seed/launcher.py',work/'merge',git)
    merge_file(base/'run.py',new/'run.py',work/'seed/runner.py',work/'merge',git)
    identity=dict(adapter_protocol=1,upstream_release=entry['upstream_release'],upstream_commit=commit,feature_schema=1)
    (native/'src/runtime_atlas_build.h').write_text('#pragma once\n#define BB_ATLAS_BUILD_JSON '+json.dumps(json.dumps(identity,separators=(',',':')))+'\n',encoding='utf-8')
    progress('Rebuilding Atlas runtime—please wait…')
    build_dir=work/'build';bash=tools/'usr/bin/bash.exe'
    script=work/'build.sh'
    import shlex
    q=lambda p:shlex.quote(msys_path(p))
    script.write_text('set -euo pipefail\nexport PATH=/clang64/bin:/usr/bin:$PATH\n'+
        'cmake -S '+q(native/'gpu')+' -B '+q(build_dir)+' -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo -DBB_PGO=off -DBB_LTO=OFF -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++\n'+
        'cmake --build '+q(build_dir)+' --target bb-probe -j 4\n',encoding='utf-8')
    env=dict(os.environ,MSYSTEM='CLANG64',CHERE_INVOKING='yes')
    run([bash,msys_path(script)],log,env=env,cwd=work,progress=progress)
    pristine=c.safe_unpack(entry['archive'],work/'pristine',strip_root=c.archive_root(entry['archive'],'run.py'))
    fresh=work/'package';fresh.mkdir()
    # Copy only pinned program files, never player saves, generated maps or state.
    for name in manifest['files']:
        if name=='updates/pending.json':continue
        source=c.inside(package,name);target=c.inside(fresh,name);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    for name in ('settings/settings.ini','updates/catalog.json'):
        source=package/name;target=fresh/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    # The seed contains the portable owned artwork pack, not generated game maps.
    shutil.copyfile(work/'seed/art.atlaslite',fresh/'assets.atlaslite')
    shutil.copyfile(work/'seed/launcher.py',fresh/'integration/ui/bbport_launcher_win.py')
    shutil.copyfile(work/'seed/runner.py',fresh/'bootstrap/run_lite.py')
    stripping=c.load_module('atlas_rebuild_strip',package/'updates/strip_runtime.py')
    (fresh/'bin/bb-probe.exe').unlink();stripping.strip(build_dir/'bb-probe.exe',fresh/'bin/bb-probe.exe',work/'strip.json')
    # The rebuilt binary must use the DLLs from the same portable compiler.
    for dll in (fresh/'bin').glob('*.dll'):
        matching=tools/'clang64/bin'/dll.name
        if matching.is_file():shutil.copyfile(matching,dll)
    pending=list((fresh/'bin').glob('*.dll'))+[fresh/'bin/bb-probe.exe'];seen=set()
    while pending:
        binary=pending.pop()
        if binary.name.lower() in seen:continue
        seen.add(binary.name.lower())
        imports=subprocess.run([str(tools/'clang64/bin/llvm-readobj.exe'),'--coff-imports',str(binary)],capture_output=True,check=True,creationflags=c.NO_WINDOW)
        for name in re.findall(rb'Name: ([^\r\n ]+\.dll)',imports.stdout,re.I):
            name=name.decode('ascii');matching=tools/'clang64/bin'/name
            if matching.is_file():
                target=fresh/'bin'/name;shutil.copyfile(matching,target);pending.append(target)
    proof=dict(identity,runtime_sha256=c.sha(fresh/'bin/bb-probe.exe'),source_archive_sha256=source_sha,seed_sha256=c.sha(seed),locally_built=True)
    c.write_json(fresh/'native-build.json',proof)
    identity.update(minimum_coordinator=1,map_schema=1)
    deps_module=c.load_module('atlas_rebuild_dependencies',package/'updates/build_dependencies.py')
    deps=deps_module.build_template(pristine,Path(entry['archive']),pristine,asset_url=entry['upstream_url'],release_page='https://github.com/Supermedo/bloodborne_pc/releases/tag/'+entry['upstream_release'])
    deps['compatibility']=identity;c.write_json(fresh/'dependencies.json',deps)
    receipt=c.read(fresh/'bootstrap/run_lite-source.json')
    receipt.update(source_sha256=c.sha(pristine/'run.py'),source_bytes=(pristine/'run.py').stat().st_size,copy_sha256=c.sha(fresh/'bootstrap/run_lite.py'),upstream_commit=commit)
    c.write_json(fresh/'bootstrap/run_lite-source.json',receipt);c.write_json(fresh/'adapter-release.json',identity)
    manifest.pop('legacy_runtime',None);manifest.pop('runtime_pending',None);manifest['compatibility']=identity
    manifest['asset_pack']['sha256']=c.sha(fresh/'assets.atlaslite')
    manifest['files']={p.relative_to(fresh).as_posix():c.sha(p) for p in fresh.rglob('*') if p.is_file() and p.relative_to(fresh).as_posix() not in ('manifest.json','settings/settings.ini','updates/catalog.json')}
    manifest['mutable_files']=['settings/settings.ini','updates/catalog.json','updates/pending.json']
    c.write_json(fresh/'manifest.json',manifest)
    entry.update(identity,platform='windows-x86_64',asset_key_schema=1,validation_status='local-build',
        stock_launcher_sha256=c.sha(pristine/'Bloodborne.exe'),runtime_sha256=proof['runtime_sha256'],
        atlas_manifest_sha256=c.sha(fresh/'manifest.json'),dependency_profile_sha256=c.sha(fresh/'dependencies.json'),
        seed_sha256=c.sha(seed),source_archive_sha256=source_sha)
    runtime_env=dict(os.environ)
    runtime_env['PATH']=os.pathsep.join(map(str,(fresh/'bin',pristine/'bin',Path(os.environ.get('SystemRoot','C:/Windows'))/'System32')))
    probe=subprocess.run([str(fresh/'bin/bb-probe.exe'),'--atlas-build-info'],env=runtime_env,capture_output=True,check=True,creationflags=c.NO_WINDOW,timeout=30)
    actual=json.loads(probe.stdout)
    if any(actual.get(k)!=identity[k] for k in ('upstream_release','upstream_commit','adapter_protocol','feature_schema')):
        raise ValueError('Rebuilt runtime identity check failed')
    c.write_json(work/'result.json',{'entry':entry,'package':str(directory/'rebuild/package'),'seed_sha256':c.sha(seed)})
    progress('Atlas rebuilt and verified. Checking existing maps…')
    return fresh,entry

def validate_result(current,fresh,archive,entry):
    manifest=c.read(Path(current)/'manifest.json')
    if entry.get('validation_status')!='local-build' or entry.get('seed_sha256')!=manifest['files'].get('updates/rebuild-seed.zip'):
        raise ValueError('Local build is not derived from this installed Atlas seed')
    if c.sha(Path(current)/'updates/rebuild-seed.zip')!=entry['seed_sha256'] or c.sha(archive)!=entry['upstream_sha256']:
        raise ValueError('Local build inputs changed')
    if c.sha(Path(fresh)/'manifest.json')!=entry['atlas_manifest_sha256']:raise ValueError('Local build output changed')
    c.verify_files(fresh,c.read(Path(fresh)/'manifest.json'))
    proof=c.read(Path(fresh)/'native-build.json')
    for key in ('upstream_release','upstream_commit','runtime_sha256','seed_sha256','source_archive_sha256'):
        if proof.get(key)!=entry.get(key):raise ValueError('Local build provenance mismatch: '+key)
    if c.sha(Path(fresh)/'bin/bb-probe.exe')!=entry['runtime_sha256']:raise ValueError('Local runtime changed')
    return entry

def prepare_update(package,launcher,version,profile,progress=print,*,tools_cache=None):
    """Prefer a verified bundle; automatically rebuild other official releases.

    Failure of Atlas preparation falls back to a playable official launcher.
    Failure to authenticate/download the launcher itself still stops the update.
    """
    package=c.regular_path(package);launcher=c.regular_path(launcher)
    c.active_receipt(launcher,package)
    manifest=c.read(package/'manifest.json');target=None
    try:
        data,_=c.refresh_catalog(package)
        target=c.catalog.resolve(data,'windows-v'+version,allow_candidate=bool(manifest.get('candidate')))
    except (ValueError,OSError):pass
    if not manifest.get('runtime_pending'):
        current=(target is not None and c.is_current(package,target)) or (target is None and c.release_identity(manifest).get('upstream_release')=='windows-v'+version)
        if current:
            try:c.native_preflight(package,launcher);return None
            except Exception:pass
    directory=launcher.parent/('.atlas-rebuild-'+os.urandom(16).hex());directory.mkdir()
    progress('Downloading and verifying launcher '+version+'…')
    if target:
        archive=c.download(target['upstream_url'],directory/'upstream.zip',target['upstream_sha256'])
        official_entry=dict(target,archive=str(archive))
    else:official_entry=official(version,directory);archive=Path(official_entry['archive'])
    errors=[]
    if target:
        try:
            progress('Installing the matching Atlas update…')
            fresh=c.materialize(package,target,directory)
            return c.stage_update(launcher,package,fresh,archive,package/'updates/catalog.json',profile,allow_candidate=bool(manifest.get('candidate')))
        except (InterruptedError,ProcessShutdownError):raise
        except Exception as error:errors.append(str(error))
    try:
        fresh,entry=build(package,official_entry,directory,progress,tools_cache=tools_cache)
        return c.stage_update(launcher,package,fresh,archive,package/'updates/catalog.json',profile,local_build=entry)
    except (InterruptedError,ProcessShutdownError):
        raise
    except Exception as error:
        errors.append(str(error));(directory/'failure.txt').write_text('\n'.join(errors),encoding='utf-8')
        progress('Completing launcher update; Atlas rebuild is pending.')
        return c.stage_pending(launcher,package,archive,official_entry,profile,'\n'.join(errors))
