from pathlib import Path
import tempfile,sys
sys.path.insert(0,str(Path(__file__).parent/'src'))
import generate_atlas as generator
with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
    root=Path(temp);out=root/'output';stage=root/'stage';source=root/'new.json';source.write_text('new');out.mkdir();stage.mkdir();(out/'maps').mkdir();(out/'maps/atlas.json').write_text('old');(out/'maps/generated-assets.json').write_text('old manifest')
    original=generator.install_file;count=0
    def fail_once(source,dest):
        global count
        count+=1
        if count==2:raise OSError('deliberate commit failure')
        original(source,dest)
    generator.install_file=fail_once
    try:generator.commit_generated(out,stage,{'maps/atlas.json':source,'maps/catalog.json':source},{'schema':1})
    except OSError:pass
    else:raise AssertionError('Failure was not propagated')
    assert (out/'maps/atlas.json').read_text()=='old' and not (out/'maps/catalog.json').exists() and (out/'maps/generated-assets.json').read_text()=='old manifest'
    generator.install_file=original
    records=generator.commit_generated(out,stage,{'maps/atlas.json':source,'maps/catalog.json':source},{'schema':1})
    assert (out/'maps/atlas.json').read_text()=='new' and len(records)==2
print('ATLAS_GENERATOR_TRANSACTION_ROLLBACK_PASS')
