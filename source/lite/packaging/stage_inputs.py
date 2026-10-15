"""Stage current release build inputs, without keeping another Atlas installation."""
import argparse,hashlib,json,shutil,zipfile
from pathlib import Path

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-dir',required=True,type=Path)
    parser.add_argument('--generator-bundle',required=True,type=Path)
    parser.add_argument('--wrapper',required=True,type=Path)
    parser.add_argument('--dependency-source',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();out=args.output.resolve()
    if out.exists():raise ValueError('Choose a new output directory')
    out.mkdir(parents=True);runtime=out/'runtime';runtime.mkdir()
    for p in args.runtime_dir.iterdir():
        if p.is_file() and p.suffix.lower() in ('.exe','.dll'):shutil.copy2(p,runtime/p.name)
    shutil.copy2(args.generator_bundle,out/'generator.atlaslite')
    shutil.copy2(args.wrapper,out/'AtlasLiteLauncher.exe')
    target=out/'runtime-dependency-source.zip'
    with zipfile.ZipFile(args.dependency_source) as src,zipfile.ZipFile(target,'w',compression=zipfile.ZIP_STORED) as dst:
        count=0
        for item in src.infolist():
            prefix='runtime-dependencies/'
            if item.is_dir() or not item.filename.startswith(prefix):continue
            name=item.filename[len(prefix):]
            if not name or '..' in Path(name).parts or ':' in name or name.startswith('/'):raise ValueError('Unsafe source member')
            with src.open(item) as original,dst.open(name,'w',force_zip64=True) as copy:shutil.copyfileobj(original,copy)
            count+=1
    if not count:raise ValueError('Dependency source tree missing')
    with zipfile.ZipFile(target) as z:assert z.testzip() is None
    report={'schema':1,'files':{p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()},'dependency_source_members':count}
    (out/'inputs.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'files':len(report['files']),'dependency_source_members':count,'source_sha256':sha(target)},indent=2))
if __name__=='__main__':main()
