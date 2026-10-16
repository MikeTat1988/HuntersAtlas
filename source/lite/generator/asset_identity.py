"""Content identity of map inputs, independent of the launcher/runtime release."""
import hashlib,json
from pathlib import Path

MAPS=('21_00','21_01','22_00','23_00','24_00','24_01','24_02','25_00','26_00','27_00','28_00','32_00','33_00','34_00','35_00','36_00')
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        while b:=stream.read(1024*1024):h.update(b)
    return h.hexdigest()

def key(game,manifest):
    game=Path(game).resolve(strict=True);root=game/'dvdroot_ps4'
    paths={game/'eboot.bin',game/'sce_sys/param.sfo',root/'param/gameparam/gameparam.parambnd.dcx',
           root/'msg/engus/item.msgbnd.dcx',root/'msg/engus/menu.msgbnd.dcx',root/'menu/enggb/font.gfx'}
    for mid in MAPS:
        name='m'+mid+'_00_00'
        for folder,suffix in (('map/mapstudio','.msb.dcx'),('event','.emevd.dcx'),('script/talk','.talkesdbnd.dcx')):
            paths.add(root/folder/(name+suffix))
        for pattern in ('*.hkxbhd','*.hkxbdt','*.hkxbhd.patch','*.hkxbdt.patch'):
            paths.update((root/'map'/name).glob(pattern))
    paths.update((root/'event').glob('common*.emevd.dcx'))
    inputs={p.relative_to(game).as_posix():sha(p) for p in sorted(paths) if p.is_file()}
    value=dict(schema=1,map_schema=1,feature_schema=manifest.get('feature_schema',0),generator_version='1.0.0',
               generator_sha256=manifest['files']['tools/generator.atlaslite'],
               feature_reader_sha256=manifest['files']['tools/extract_atlas_features.py'],inputs=inputs)
    value['digest']=hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return value
