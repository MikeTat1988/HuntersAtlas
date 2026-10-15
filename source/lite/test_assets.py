import importlib.util,json,tempfile,unittest,zipfile
from pathlib import Path
spec=importlib.util.spec_from_file_location('assets',Path(__file__).parent/'bootstrap/assets.py')
assets=importlib.util.module_from_spec(spec);spec.loader.exec_module(assets)
class Tests(unittest.TestCase):
    def test_roundtrip_and_cleanup(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'map').write_bytes(b'{"same":"geometry"}')
            (root/'font').write_bytes(b'font-bytes')
            receipt={'files':{'maps/atlas.json':assets.digest(root/'map'),'art/native-font.ttf':assets.digest(root/'font')}}
            (root/'receipt').write_text(json.dumps(receipt))
            pack=root/'pack';r=assets.build({'maps/atlas.json':root/'map','art/native-font.ttf':root/'font','maps/generated-assets.json':root/'receipt'},pack)
            c={'root':root,'state_root':root/'state','manifest':{'asset_pack':{'path':'pack','sha256':r['sha256']}},'paths':{}}
            with assets.materialize(c) as p:
                self.assertEqual((p['maps']/'atlas.json').read_bytes(),(root/'map').read_bytes());expanded=p['maps'].parent
            self.assertFalse(expanded.exists())
    def test_bad_paths(self):
        for p in ('../maps/a','maps/../a','/maps/a','maps\\a','art/C:a','maps//a'):
            with self.assertRaises(ValueError):assets.safe(p)
    def test_corruption(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);f=root/'f';f.write_bytes(b'x');p=root/'pack'
            assets.build({'art/a':f},p)
            with zipfile.ZipFile(p,'a') as z:z.writestr('maps/evil',b'x')
            with self.assertRaises(ValueError):assets.unpack(p,root/'out')
    def test_art_only_first_install(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);f=root/'font';f.write_bytes(b'licensed fallback')
            p=root/'assets';r=assets.build({'art/fallback.ttf':f},p)
            self.assertFalse(r['prepared'])
            unpacked=root/'first';unpacked.mkdir();self.assertFalse(assets.unpack(p,unpacked)['prepared'])
            contract={'root':root,'state_root':root/'state','manifest':{'asset_pack':{'path':'assets','sha256':r['sha256']}},'paths':{}}
            with self.assertRaisesRegex(ValueError,'Settings.cmd'):
                with assets.materialize(contract):pass
            self.assertEqual(list((root/'state').iterdir()),[])
if __name__=='__main__':unittest.main()
