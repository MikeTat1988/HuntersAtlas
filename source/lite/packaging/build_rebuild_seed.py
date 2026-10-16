"""Export the reviewed Atlas delta on an exact stock source baseline.

Unrelated working-tree renderer/save changes are deliberately not exported.
The baseline and expanded vendor source must already be downloaded and verified
by the release builder. No game data, generated maps, or private keys are used.
"""
from pathlib import Path
import argparse,json,zipfile

OVERLAYS={
    'gpu/bbgpu.h','gpu/shim/bbgpu.cpp','gpu/shim/window.cpp',
    'gpu/shim/bbport_overlay.cpp','gpu/shim/bbport_overlay.h',
    'gpu/shadps4/video_core/renderer_vulkan/vk_presenter.cpp',
    'src/probe.c','src/runtime_pad.c','src/runtime_services.c','src/runtime_audio.c',
}

def build(base,native,ui,runner,art,pins,commit,release,output):
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        names={p.relative_to(root).as_posix() for root in (base,native) for p in root.rglob('*')
               if p.is_file() and not any(n in p.parts for n in ('.git','__pycache__'))}
        for name in sorted(names):
            stock=base/name;local=native/name
            selected=local if name in OVERLAYS or not stock.is_file() else stock
            if selected.is_file():z.write(selected,'native/'+name)
            if stock.is_file():z.write(stock,'base/'+name)
        for source,name in ((ui,'launcher.py'),(runner,'runner.py'),(art,'art.atlaslite')):z.write(source,name)
        z.writestr('seed.json',json.dumps({'upstream_release':release,'upstream_commit':commit,
            'submodules':pins,'atlas_modified_stock_files':sorted(OVERLAYS)}))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('base','native','ui','runner','art','pins','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--commit',required=True);p.add_argument('--release',required=True)
    a=p.parse_args();build(a.base,a.native,a.ui,a.runner,a.art,json.loads(a.pins.read_text())[a.release],a.commit,a.release,a.output)
