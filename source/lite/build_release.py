"""Build the portable player ZIP and complete corresponding-source ZIP."""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,shutil,struct,subprocess,tempfile,zipfile
from pathlib import Path

VERSION='1.0'
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        while data:=f.read(1024*1024):h.update(data)
    return h.hexdigest()

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def copy(src,dst):
    dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)

def write_json(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def source_zip(destination,dependency_source):
    result=subprocess.run(['git','-C',str(REPO),'ls-files','--cached','--others','--exclude-standard','-z'],capture_output=True,check=True)
    names={n.decode('utf-8') for n in result.stdout.split(b'\0') if n}
    with zipfile.ZipFile(destination,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name in sorted(names):
            p=REPO/name
            if p.is_file() and '.local' not in p.parts and p.suffix!='.pyc':z.write(p,name)
        if (REPO/'source/runtime-dependencies').is_dir():
            return
        with zipfile.ZipFile(dependency_source) as deps:
            prefixed=any(i.filename.startswith('runtime-dependencies/') for i in deps.infolist())
            selected=0
            for item in deps.infolist():
                if item.is_dir():continue
                name=item.filename
                if prefixed:
                    if not name.startswith('runtime-dependencies/'):continue
                else:name='runtime-dependencies/'+name
                if '..' in Path(name).parts or name.startswith('/') or ':' in name:raise ValueError('Unsafe dependency source archive')
                z.writestr(name,deps.read(item));selected+=1
            if not selected:raise ValueError('Corresponding dependency source archive is empty')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('runtime-dir','generator-bundle','launcher-root','wrapper','dependency-source','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--player-only',action='store_true',help='Build a validation player package; final releases also require the source ZIP')
    args=p.parse_args();out=args.output.resolve()
    if out.exists():raise ValueError('Output must be a new directory; preserve existing releases')
    out.mkdir(parents=True);package=out/'HuntersAtlas';package.mkdir()
    assets=load('atlas_lite_build_assets',HERE/'bootstrap/assets.py')
    deps=load('atlas_lite_build_deps',HERE/'packaging/build_dependencies.py')
    # The checked-in template comes from the official supported immutable release.
    template=json.loads((HERE/'packaging/dependency-template.json').read_text(encoding='utf-8'))
    stock=template['ordinary_port']
    for name,expected in stock['files'].items():
        if sha(args.launcher_root/name)!=expected:raise ValueError('Unsupported build prerequisite '+name)
    for exe_hash,variant in stock['launcher_variants'].items():
        if sha(args.launcher_root/variant['path'])!=exe_hash:raise ValueError('Unsupported launcher executable')
        for name,expected in variant['files'].items():
            if sha(args.launcher_root/name)!=expected:raise ValueError('Unsupported interpreter runtime '+name)
    copy(args.runtime_dir/'bb-probe.exe',package/'bin/bb-probe.exe')
    # Input is a release build with debug sections already removed. Full binaries
    # can be prepared with strip_runtime.py; no game code is modified by that step.
    pe=load('atlas_lite_strip_check',HERE/'strip_runtime.py')
    if any(s['name'].startswith('.debug_') for s in pe.sections((package/'bin/bb-probe.exe').read_bytes())[3]):
        raise ValueError('Use strip_runtime.py before packaging the runtime')
    for dll in args.runtime_dir.glob('*.dll'):
        shared=args.launcher_root/'bin'/dll.name
        if not shared.is_file() or sha(dll)!=sha(shared):copy(dll,package/'bin'/dll.name)
    for n in ('entry.py','assets.py','run_lite.py','run_lite-source.json','integrated_play.py','config.json'):copy(HERE/'bootstrap'/n,package/'bootstrap'/n)
    for n in ('prepare.py','atlas_lite_bundle.py'):copy(HERE/'generator'/n,package/'tools'/n)
    copy(args.generator_bundle,package/'tools/generator.atlaslite')
    copy(args.wrapper,package/'integration/AtlasLauncher.exe')
    for ui in (HERE/'integration/ui').glob('*.py'):copy(ui,package/'integration/ui'/ui.name)
    copy(REPO/'installer/Manage-Atlas.ps1',package/'installer/Manage-Atlas.ps1')
    for name in ('Install.cmd','Uninstall.cmd','LICENSE'):copy(REPO/name,package/name)
    readme=(REPO/'README.md').read_text(encoding='utf-8')
    readme=readme.replace('(examples/','(https://raw.githubusercontent.com/MikeTat1988/HuntersAtlas/main/examples/')
    for prefix in ('docs/','source/'):
        readme=readme.replace('('+prefix,'(https://github.com/MikeTat1988/HuntersAtlas/blob/v'+VERSION+'/'+prefix)
    (package/'README.md').write_text(readme,encoding='utf-8')
    # Notices are data; GPL dependency source is in the simultaneous source download.
    for f in (REPO/'source/licenses/notices').rglob('*'):
        if f.is_file():copy(f,package/'licenses/runtime'/f.relative_to(REPO/'source/licenses/notices'))
    for f in (REPO/'source/generator/licenses').rglob('*'):
        if f.is_file() and 'soulstruct-source' not in f.parts:copy(f,package/'licenses/generator'/f.relative_to(REPO/'source/generator/licenses'))
    copy(REPO/'source/art/LICENSE-DejaVu.txt',package/'licenses/LICENSE-DejaVu.txt')
    write_json(package/'dependencies.json',template)
    with tempfile.TemporaryDirectory(prefix='atlas-owned-art-',dir=out) as temp:
        from PIL import Image
        art=Path(temp)/'art';art.mkdir()
        for name in ('background','icons','menu','parchment'):
            with Image.open(REPO/'source/art'/(name+'.png')) as im:
                im=im.convert('RGBA');(art/(name+'.bbra')).write_bytes(b'BBRA'+struct.pack('<II',*im.size)+im.tobytes())
        copy(REPO/'source/art/fallback.ttf',art/'fallback.ttf')
        art_receipt=assets.build({'art/'+f.name:f for f in art.iterdir()},package/'assets.atlaslite')
    if art_receipt['prepared']:raise ValueError('Public package must not contain generated game maps/font')
    manifest={'schema':1,'id':'hunters-atlas-lite','version':VERSION,
        'game_executables':['d65f0b4f01d59166aed16f8604196d8b7dd805abbf0758b356e8f1354c9429f9'],
        'paths':{'probe':'bin/bb-probe.exe','maps':'state/runtime-assets/maps','config':'settings/settings.ini','art':'state/runtime-assets/art','catalog':'state/runtime-assets/maps/catalog.json','font':'state/runtime-assets/art/native-font.ttf'},
        'generator':'tools/prepare.py','asset_pack':{'path':'assets.atlaslite','sha256':art_receipt['sha256']}}
    # Atlas shortcut configuration is owned by this package, not the launcher profile.
    copy(HERE/'packaging/settings.ini',package/'settings/settings.ini')
    manifest['files']={f.relative_to(package).as_posix():sha(f) for f in package.rglob('*') if f.is_file() and f.relative_to(package).as_posix()!='settings/settings.ini'}
    manifest['mutable_files']=['settings/settings.ini']
    write_json(package/'manifest.json',manifest)
    player=out/f'Hunters-Atlas-{VERSION}.zip'
    with zipfile.ZipFile(player,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for f in sorted(package.rglob('*')):
            if f.is_file():z.write(f,'HuntersAtlas/'+f.relative_to(package).as_posix())
    if args.player_only:
        with zipfile.ZipFile(player) as z:
            if z.testzip():raise ValueError('Archive CRC verification failed')
        print(json.dumps({'validation_only':True,'player':str(player),'bytes':player.stat().st_size,'sha256':sha(player)},indent=2))
        return
    sources=out/f'Hunters-Atlas-Source-{VERSION}.zip'
    source_zip(sources,args.dependency_source)
    for archive in (player,sources):
        with zipfile.ZipFile(archive) as z:
            if z.testzip():raise ValueError('Archive CRC verification failed')
    report={'schema':1,'version':VERSION,'player':{'name':player.name,'bytes':player.stat().st_size,'sha256':sha(player),'extracted_bytes':sum(f.stat().st_size for f in package.rglob('*') if f.is_file())},
        'source':{'name':sources.name,'bytes':sources.stat().st_size,'sha256':sha(sources)},
        'components':{'runtime':sha(package/'bin/bb-probe.exe'),'generator':sha(package/'tools/generator.atlaslite'),'launcher_wrapper':sha(package/'integration/AtlasLauncher.exe')},
        'includes_game_maps_or_font':False,'depends_on_installed_previous_atlas':False}
    write_json(out/'release-manifest.json',report)
    (out/'SHA256SUMS.txt').write_text('\n'.join(sha(f)+'  '+f.name for f in (player,sources))+'\n',encoding='ascii')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
