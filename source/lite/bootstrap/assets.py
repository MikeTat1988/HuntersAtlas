"""Lossless runtime asset storage. Expanded files live only for a locked Atlas session."""
from __future__ import annotations
from contextlib import contextmanager
import hashlib, json, shutil, stat, tempfile, zipfile
from pathlib import Path, PurePosixPath

LIMIT=256*1024*1024

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        while b:=f.read(1024*1024):h.update(b)
    return h.hexdigest()

def safe(name):
    if not isinstance(name,str) or not name or '\\' in name or ':' in name:
        raise ValueError('Invalid asset path')
    p=PurePosixPath(name)
    if p.is_absolute() or any(s in ('','.','..') for s in name.split('/')):
        raise ValueError('Asset traversal')
    if p.parts[0] not in ('maps','art'):raise ValueError('Unexpected asset root')
    return p

def build(inputs:dict[str,Path], target:Path):
    records={}
    for name,path in sorted(inputs.items()):
        safe(name);records[name]={'sha256':digest(path),'size':path.stat().st_size}
    size=sum(v['size'] for v in records.values())
    if size>LIMIT:raise ValueError('Asset size limit')
    prepared='maps/generated-assets.json' in records
    if not prepared and any(not name.startswith('art/') for name in records):raise ValueError('Incomplete prepared assets')
    metadata={'schema':1,'prepared':prepared,'files':records,'expanded_bytes':size}
    target.parent.mkdir(parents=True,exist_ok=True)
    temp=target.with_suffix(target.suffix+'.building')
    try:
        with zipfile.ZipFile(temp,'w',compression=zipfile.ZIP_LZMA) as z:
            for name,path in sorted(inputs.items()):
                info=zipfile.ZipInfo(name,(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_LZMA
                z.writestr(info,path.read_bytes())
            info=zipfile.ZipInfo('manifest.json',(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_LZMA
            z.writestr(info,json.dumps(metadata,sort_keys=True,separators=(',',':')))
        temp.replace(target)
    finally:temp.unlink(missing_ok=True)
    return dict(metadata,packed_bytes=target.stat().st_size,sha256=digest(target))

def unpack(pack:Path, destination:Path):
    with zipfile.ZipFile(pack) as z:
        manifest=json.loads(z.read('manifest.json'))
        if manifest.get('schema')!=1 or not isinstance(manifest.get('files'),dict):raise ValueError('Invalid asset manifest')
        files=manifest['files'];seen=set();total=0
        for info in z.infolist():
            if info.filename=='manifest.json':continue
            p=safe(info.filename);key=str(p).casefold()
            if key in seen:raise ValueError('Duplicate asset')
            seen.add(key)
            if info.filename not in files:raise ValueError('Unlisted asset')
            mode=info.external_attr>>16
            if stat.S_ISLNK(mode):raise ValueError('Linked asset')
            record=files[info.filename]
            if not isinstance(record['size'],int) or info.file_size!=record['size']:raise ValueError('Asset length')
            total+=info.file_size
            if info.file_size>32*1024*1024 or total>LIMIT:raise ValueError('Asset bounds')
        if seen!={str(safe(n)).casefold() for n in files}:raise ValueError('Missing asset')
        if total!=manifest['expanded_bytes']:raise ValueError('Asset total length')
        for name,record in files.items():
            out=destination.joinpath(*safe(name).parts)
            out.parent.mkdir(parents=True,exist_ok=True)
            h=hashlib.sha256();count=0
            with z.open(name) as src,out.open('xb') as dst:
                while block:=src.read(1024*1024):
                    count+=len(block)
                    if count>record['size']:raise ValueError('Asset exceeds declared size')
                    h.update(block);dst.write(block)
            if h.hexdigest()!=record['sha256'] or count!=record['size']:raise ValueError('Asset hash mismatch')
    prepared=manifest.get('prepared','maps/generated-assets.json' in files)
    if prepared:
        receipt=json.loads((destination/'maps/generated-assets.json').read_text())
        for name,expected in receipt['files'].items():
            rel=safe(name);path=destination.joinpath(*rel.parts)
            if not path.is_file() or digest(path)!=expected:raise ValueError('Generated asset receipt mismatch')
    elif any(not name.startswith('art/') for name in files):raise ValueError('Incomplete prepared assets')
    manifest['prepared']=prepared
    return manifest

@contextmanager
def materialize(contract):
    spec=contract['manifest'].get('asset_pack')
    if not spec:
        yield contract['paths'];return
    pack=contract['root']/spec['path']
    if digest(pack)!=spec['sha256']:raise ValueError('Asset pack failed integrity check')
    state=contract['state_root'];state.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='session-assets-',dir=state) as temp:
        root=Path(temp);manifest=unpack(pack,root)
        if not manifest['prepared']:raise ValueError('Maps are not prepared yet. Open Settings.cmd and choose Prepare maps.')
        if contract.get('manifest',{}).get('feature_schema')==1:
            receipt=json.loads((root/'maps/generated-assets.json').read_text(encoding='utf-8'))
            if receipt.get('feature_schema')!=1 or not (root/'maps/features.json').is_file():
                raise ValueError('Prepare Atlas maps for the current feature schema.')
        paths=dict(maps=root/'maps',catalog=root/'maps/catalog.json',
                   art=root/'art',font=root/'art/native-font.ttf')
        if not paths['font'].is_file():paths['font']=root/'art/fallback.ttf'
        # NGX explicitly probes beside the executable, so PATH alone is insufficient.
        # Materialize verified existing-port SDK libraries only for this session.
        if contract.get('config',{}).get('stage_dlss',False):
            binary=root/'bin';binary.mkdir()
            probe=binary/'bb-probe.exe';source=contract['paths']['probe']
            shutil.copyfile(source,probe)
            if digest(source)!=digest(probe):raise ValueError('Staged runtime hash mismatch')
            for name in ('bbport_dlss.dll','nvngx_dlss.dll'):
                source=contract['base_files'].get('bin/'+name)
                if source is None:raise ValueError('Missing verified DLSS prerequisite: '+name)
                shutil.copyfile(source,binary/name)
                if digest(source)!=digest(binary/name):raise ValueError('Staged DLSS hash mismatch')
            # Newer tested runtimes load the frame-generation plugin beside
            # the host executable too. Earlier adapters need no such plugin.
            source=contract['base_files'].get('bin/nvngx_dlssg.dll')
            if source is not None:
                shutil.copyfile(source,binary/source.name)
                if digest(source)!=digest(binary/source.name):raise ValueError('Staged frame-generation hash mismatch')
            paths['probe']=probe
        (root/'session-receipt.json').write_text(json.dumps({'expanded_bytes':manifest['expanded_bytes'],'sha256':spec['sha256']}))
        try:
            yield paths
        finally:
            cleanup_prepared_cache(contract)

def cleanup_prepared_cache(contract):
    """Drop only named, reproducible Atlas preparation intermediates after a session."""
    if not contract.get('config',{}).get('compact_prepared_cache',False):return
    state=contract['state_root'].resolve()
    root=contract['root'].resolve()
    state.relative_to(root)
    out=state/'out'
    if out.is_symlink() or getattr(out,'is_junction',lambda:False)():raise ValueError('Unsafe Atlas preparation directory')
    names=('analysis.json','boot-libc.bin','boot-linked.bin','boot.bin','content-profile.json',
           'content.bin','eboot.elf','entry.bin','libc-link.json','link.json','patches.bin')
    for name in names:
        path=out/name
        if path.is_symlink():raise ValueError('Linked preparation file')
        if path.is_file():path.unlink()
