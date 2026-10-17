"""Build a standalone install with authenticated adapters for known launchers.

Inputs are pristine, previously built native releases. This does not relabel or
recompile a native binary. The simultaneous source ZIP includes the exact legacy
corresponding-source archive and current source for all shared adapter changes.
"""
from __future__ import annotations
import argparse,datetime,importlib.util,json,shutil,sys,zipfile
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'updates'))
import catalog,coordinator
import build_release

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    coordinator.write_json(path,value)

def patch(package,tag,seed=None,*,version=build_release.VERSION,release=False):
    # Common Python and installer code is identical in both adapters.
    for source,destination in ((HERE/'bootstrap',package/'bootstrap'),(HERE/'integration/ui',package/'integration/ui'),
                               (HERE/'generator',package/'tools'),(HERE/'updates',package/'updates')):
        destination.mkdir(parents=True,exist_ok=True)
        for p in source.iterdir():
            if p.is_file() and p.suffix in ('.py','.json'):
                if p.name in ('run_lite.py','run_lite-source.json'):continue
                shutil.copyfile(p,destination/p.name)
    for name in ('atlas_adapter.py','atlas_feature_config.py'):
        shutil.copyfile(HERE/'integration/ui'/name,package/'bootstrap'/name)
    # Keep reviewed upstream UI/runner changes bound to their exact adapter.
    profile=HERE/'compatibility/profiles'/tag
    for name,destination in (('bbport_launcher_win.py','integration/ui/bbport_launcher_win.py'),('run_lite.py','bootstrap/run_lite.py')):
        if (profile/name).is_file():shutil.copyfile(profile/name,package/destination)
    if seed:
        shutil.copyfile(seed,package/'updates/rebuild-seed.zip')
        shutil.copyfile(HERE/'strip_runtime.py',package/'updates/strip_runtime.py')
        shutil.copyfile(HERE/'packaging/build_dependencies.py',package/'updates/build_dependencies.py')
    for name in ('Manage-Atlas.ps1','Update-Atlas.ps1','Preparation-Process.ps1'):
        shutil.copyfile(build_release.REPO/'installer'/name,package/'installer'/name)
    for name in ('Install.cmd','Uninstall.cmd','Update.cmd'):
        shutil.copyfile(build_release.REPO/name,package/name)
    shutil.copyfile(build_release.REPO/('docs/INSTALL.md' if release else 'docs/AUTO-UPDATE-TEST.md'),package/'README.md')
    if release:
        readme=(package/'README.md').read_text(encoding='utf-8')
        for name in ('LAUNCHER-UPDATES.md','COMPATIBILITY.md'):
            readme=readme.replace('('+name+')','(docs/'+name+')')
        (package/'README.md').write_text(readme,encoding='utf-8')
    for name in ('LAUNCHER-UPDATES.md','COMPATIBILITY.md','QA.md','MAP-FEATURES.md','INSTALL.md'):
        (package/'docs').mkdir(exist_ok=True)
        shutil.copyfile(build_release.REPO/'docs'/name,package/'docs'/name)
    manifest=coordinator.read(package/'manifest.json')
    manifest['version']=version
    if release:manifest.pop('candidate',None)
    else:manifest['candidate']='combined automatic update test; owner approval pending'
    if release:
        for stale in (package/'MAP-FEATURES-CANDIDATE.md',package/'docs/MAP-FEATURES-CANDIDATE.md',package/'docs/AUTO-UPDATE-TEST.md'):
            stale.unlink(missing_ok=True)
    manifest['feature_schema']=1
    manifest['asset_key_schema']=1
    if tag=='windows-v1.7.2':
        manifest.pop('compatibility',None)
        manifest['legacy_runtime']=dict(upstream_release=tag,upstream_commit='e5d04e2ba4864ccf40de6c3cf6aa532855320b0d',
            adapter_protocol=1,minimum_coordinator=1,map_schema=1,feature_schema=1,
            runtime_sha256=coordinator.sha(package/'bin/bb-probe.exe'))
    identity=coordinator.release_identity(manifest)
    if identity['upstream_release']!=tag:raise ValueError('Unexpected native release input')
    write(package/'adapter-release.json',identity)
    (package/'updates/catalog.json').unlink(missing_ok=True)
    manifest['files']={p.relative_to(package).as_posix():coordinator.sha(p) for p in package.rglob('*')
        if p.is_file() and not p.relative_to(package).as_posix().startswith('.distribution/') and p.relative_to(package).as_posix() not in ('manifest.json','settings/settings.ini')}
    manifest['mutable_files']=['settings/settings.ini','updates/catalog.json']
    write(package/'manifest.json',manifest)
    dependencies=coordinator.read(package/'dependencies.json')
    target={key:identity[key] for key in ('upstream_release','upstream_commit','adapter_protocol','minimum_coordinator','map_schema','feature_schema')}
    target.update(platform='windows-x86_64',asset_key_schema=1,validation_status='validated' if release else 'candidate',
        upstream_url=dependencies['provenance']['asset_url'],upstream_sha256=dependencies['provenance']['asset_sha256'],
        stock_launcher_sha256=next(iter(dependencies['ordinary_port']['launcher_variants'])),
        runtime_sha256=coordinator.sha(package/'bin/bb-probe.exe'),atlas_manifest_sha256=coordinator.sha(package/'manifest.json'),
        atlas_artifact_url=None,dependency_profile_sha256=coordinator.sha(package/'dependencies.json'),
        migration={'receipt_schemas':[1,2],'rollback':'retain previous pair'})
    return target

def archive(root,destination):
    with zipfile.ZipFile(destination,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(root.rglob('*')):
            if p.is_file():z.write(p,'HuntersAtlas/'+p.relative_to(root).as_posix())

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('legacy-player','legacy-source','target-package','dependency-source','signing-key','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--legacy-runtime-dir',type=Path)
    parser.add_argument('--target-runtime-dir',type=Path)
    parser.add_argument('--rebuild-seed',type=Path)
    parser.add_argument('--additional-package',type=Path,action='append',default=[],help='Verified adapter for another official launcher')
    parser.add_argument('--additional-source',type=Path,action='append',default=[],help='Exact corresponding source archive for an additional native adapter')
    parser.add_argument('--version',default=build_release.VERSION)
    parser.add_argument('--release',action='store_true',help='Prepare versioned publication assets locally; does not publish')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    legacy=out/'HuntersAtlas';target=out/'target/HuntersAtlas'
    coordinator.safe_unpack(args.legacy_player,legacy,strip_root=coordinator.archive_root(args.legacy_player,'manifest.json'))
    coordinator.verify_files(legacy,coordinator.read(legacy/'manifest.json'))
    if not args.legacy_runtime_dir and coordinator.sha(legacy/'bin/bb-probe.exe')!='7d9c10f6c72caa7f5ca194ddf5e1bd3ecdf20eb059e8f0ae63c7b432f853c897':
        raise ValueError('The exact verified 1.7.2 feature runtime is required')
    shutil.copytree(args.target_package,target)
    for package,runtime,tag in ((legacy,args.legacy_runtime_dir,'windows-v1.7.2'),(target,args.target_runtime_dir,'windows-v1.8.1')):
        if runtime:
            proof=coordinator.read(runtime/'native-build.json')
            if proof.get('upstream_release')!=tag or proof.get('runtime_sha256')!=coordinator.sha(runtime/'bb-probe.exe'):
                raise ValueError('The rebuilt runtime proof does not match its adapter')
            if tag=='windows-v1.7.2' and proof.get('corresponding_source_sha256')!=coordinator.sha(args.legacy_source):
                raise ValueError('Legacy corresponding source does not match the rebuilt native proof')
            shutil.copyfile(runtime/'bb-probe.exe',package/'bin/bb-probe.exe')
            shutil.copyfile(runtime/'native-build.json',package/'native-build.json')
    for name in ('generator.atlaslite','extract_atlas_features.py'):
        shutil.copyfile(target/'tools'/name,legacy/'tools'/name)
    old=patch(legacy,'windows-v1.7.2',args.rebuild_seed,version=args.version,release=args.release)
    new=patch(target,'windows-v1.8.1',args.rebuild_seed,version=args.version,release=args.release)
    targets=[old,new]
    extras=[]
    if len(args.additional_package)!=len(args.additional_source):raise ValueError('Every additional adapter needs its exact corresponding source archive')
    for index,input_package in enumerate(args.additional_package):
        coordinator.verify_files(input_package,coordinator.read(input_package/'manifest.json'))
        tag=coordinator.release_identity(coordinator.read(input_package/'manifest.json'))['upstream_release']
        if any(t['upstream_release']==tag for t in targets):raise ValueError('Duplicate bundled launcher adapter')
        extra=out/('adapter-'+str(index))/'HuntersAtlas'
        shutil.copytree(input_package,extra)
        entry=patch(extra,tag,args.rebuild_seed,version=args.version,release=args.release)
        extras.append((extra,entry));targets.append(entry)
    # No catalog in its own archive: the signed catalog authenticates archive and manifest.
    bundled=legacy/'.distribution/windows-v1.8.1.zip';bundled.parent.mkdir(exist_ok=True)
    archive(target,bundled);new['atlas_sha256']=coordinator.sha(bundled)
    for extra,entry in extras:
        path=bundled.parent/(entry['upstream_release']+'.zip')
        archive(extra,path);entry['atlas_sha256']=coordinator.sha(path)
    private=coordinator.read(args.signing_key);public=coordinator.read(HERE/'updates/trusted-key.json')
    if private['n']!=public['n']:raise ValueError('Wrong catalog signing key')
    data=dict(schema=1,minimum_coordinator=1,expires=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(days=90)).isoformat(),targets=targets)
    envelope=dict(catalog=data,signature=catalog.sign(data,private))
    write(legacy/'updates/catalog.json',envelope);write(target/'updates/catalog.json',envelope)
    for extra,entry in extras:
        write(extra/'updates/catalog.json',envelope);coordinator.fresh_package(extra,entry)
    catalog.load(legacy/'updates/catalog.json')
    coordinator.fresh_package(target,new)
    suffix='' if args.release else '-auto-update-test'
    player=out/f'Hunters-Atlas-{args.version}{suffix}.zip';archive(legacy,player)
    source=out/f'Hunters-Atlas-Source-{args.version}{suffix}.zip'
    build_release.source_zip(source,args.dependency_source)
    with zipfile.ZipFile(source,'a',compression=zipfile.ZIP_STORED) as z:
        if args.rebuild_seed:z.write(args.rebuild_seed,'corresponding-source/automatic-rebuild-seed.zip')
        z.write(args.legacy_source,'corresponding-source/legacy-1.7.2-source.zip')
        z.writestr('corresponding-source/legacy-1.7.2-identity.json',json.dumps(dict(runtime_sha256=old['runtime_sha256'],
            source_archive_sha256=coordinator.sha(args.legacy_source),source_archive='legacy-1.7.2-source.zip',
            changes='Legacy native corresponding source is in this nested archive. Shared Python adapters and installer use current source/lite and installer. The original legacy runner remains unchanged.'),indent=2))
        for extra_source,(_,entry) in zip(args.additional_source,extras):
            z.write(extra_source,'corresponding-source/'+entry['upstream_release']+'-source.zip')
            z.writestr('corresponding-source/'+entry['upstream_release']+'-identity.json',json.dumps(dict(
                runtime_sha256=entry['runtime_sha256'],source_archive_sha256=coordinator.sha(extra_source),
                upstream_commit=entry['upstream_commit']),indent=2))
    report={'player':{'path':str(player),'sha256':coordinator.sha(player),'bytes':player.stat().st_size},
        'source':{'path':str(source),'sha256':coordinator.sha(source),'bytes':source.stat().st_size},'targets':data['targets']}
    for p in (player,source,bundled):
        with zipfile.ZipFile(p) as z:
            if z.testzip():raise ValueError('ZIP CRC failure')
    write(out/'release-manifest.json',report)
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
