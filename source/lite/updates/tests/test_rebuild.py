"""Rebuild boundaries: real merges, missing versions, and tampered derivations."""
from pathlib import Path
import json,shutil,sys,tempfile,unittest
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import coordinator as c,rebuild

class Rebuild(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def file(self,name,value):
        p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(value);return p
    def test_nonoverlapping_native_edits_merge(self):
        base='a\nb\nc\nd\ne\nf\ng\nh\ni\n'
        b=self.file('base',base);n=self.file('new',base.replace('b\n','upstream\n'));o=self.file('ours',base.replace('h\n','atlas\n'))
        rebuild.merge_file(b,n,o,self.root/'scratch',shutil.which('git'))
        self.assertIn('upstream',o.read_text());self.assertIn('atlas',o.read_text())
    def test_overlapping_changes_do_not_replace_working_source(self):
        b=self.file('base','a\nb\nc\n');n=self.file('new','a\nupstream\nc\n');o=self.file('ours','a\natlas\nc\n')
        with self.assertRaisesRegex(ValueError,'requires review'):rebuild.merge_file(b,n,o,self.root/'scratch',shutil.which('git'))
        self.assertEqual(o.read_text(),'a\natlas\nc\n')
    def test_removed_upstream_file_with_atlas_changes_is_conflict(self):
        b=self.file('base','old');o=self.file('ours','atlas')
        with self.assertRaises(ValueError):rebuild.merge_file(b,self.root/'missing',o,self.root/'scratch',shutil.which('git'))
        self.assertEqual(o.read_text(),'atlas')
    def test_unknown_future_major_uses_official_metadata(self):
        release={'tag_name':'windows-v2.0','id':1,'assets':[{'name':'Bloodborne-Windows.zip','digest':'sha256:'+'a'*64,
            'browser_download_url':'https://github.com/Supermedo/bloodborne_pc/releases/download/windows-v2.0/Bloodborne-Windows.zip'}]}
        with mock.patch.object(rebuild,'api',return_value=release),mock.patch.object(c,'download') as download:
            result=rebuild.official('2.0',self.root)
            self.assertEqual(result['upstream_release'],'windows-v2.0');download.assert_called_once()
    def test_unverified_release_does_not_download(self):
        release={'tag_name':'windows-v1.8.2','id':1,'assets':[{'name':'Bloodborne-Windows.zip','digest':None}]}
        with mock.patch.object(rebuild,'api',return_value=release),mock.patch.object(c,'download') as download:
            with self.assertRaises(ValueError):rebuild.official('1.8.2',self.root)
            download.assert_not_called()
    def test_versions_and_urls_are_not_shell_commands(self):
        for version in ('1.6.9','1.8.2;echo x','../1.8.2','latest'):
            with self.assertRaises(ValueError):rebuild.official(version,self.root)
    def test_local_result_cannot_skip_seed_validation(self):
        current=self.root/'current';current.mkdir();c.write_json(current/'manifest.json',{'files':{'updates/rebuild-seed.zip':'a'*64}})
        with self.assertRaisesRegex(ValueError,'not derived'):
            rebuild.validate_result(current,self.root/'fresh',self.root/'archive',{'validation_status':'local-build','seed_sha256':'b'*64})

    def test_missing_adapter_and_build_failure_still_stage_launcher(self):
        package=self.root/'atlas';launcher=self.root/'launcher';package.mkdir();launcher.mkdir()
        c.write_json(package/'manifest.json',{'files':{},'compatibility':{'upstream_release':'windows-v1.7.2'}})
        official={'archive':str(self.root/'upstream.zip'),'upstream_release':'windows-v1.8.2'}
        with (mock.patch.object(c,'active_receipt'),mock.patch.object(c,'refresh_catalog',side_effect=ValueError('expired')),
             mock.patch.object(rebuild,'official',return_value=official),mock.patch.object(rebuild,'build',side_effect=ValueError('conflict')),
             mock.patch.object(c,'stage_pending',return_value=self.root/'journal.json') as fallback):
            result=rebuild.prepare_update(package,launcher,'1.8.2',self.root/'settings.json',lambda _:None)
            self.assertEqual(result,self.root/'journal.json');fallback.assert_called_once()

    def test_failed_launcher_authentication_does_not_activate_anything(self):
        package=self.root/'atlas';launcher=self.root/'launcher';package.mkdir();launcher.mkdir()
        c.write_json(package/'manifest.json',{'files':{}})
        with (mock.patch.object(c,'active_receipt'),mock.patch.object(c,'refresh_catalog',side_effect=ValueError('missing')),
             mock.patch.object(rebuild,'official',side_effect=ValueError('bad digest')),mock.patch.object(c,'stage_pending') as fallback):
            with self.assertRaisesRegex(ValueError,'bad digest'):rebuild.prepare_update(package,launcher,'1.8.2',self.root/'settings.json',lambda _:None)
            fallback.assert_not_called()

    def test_fresh_distribution_repairs_matching_launcher_without_downgrade(self):
        package=self.root/'atlas';launcher=self.root/'launcher';package.mkdir();launcher.mkdir()
        self.file('launcher/Bloodborne.stock.exe','stock')
        c.write_json(package/'manifest.json',{'candidate':True})
        entry={'upstream_release':'windows-v1.8.2','stock_launcher_sha256':c.sha(launcher/'Bloodborne.stock.exe'),
               'atlas_manifest_sha256':c.sha(package/'manifest.json'),'upstream_url':'official','upstream_sha256':'a'*64}
        with (mock.patch.object(c.catalog,'load',return_value={'targets':[entry]}),mock.patch.object(c.catalog,'resolve',return_value=entry),
              mock.patch.object(c,'fresh_package'),mock.patch.object(c,'materialize') as materialize,
              mock.patch.object(c,'download') as download):
            fresh,target,archive=rebuild.matching_package(package,launcher,self.root,need_archive=False)
        self.assertEqual(fresh,package);self.assertEqual(target['upstream_release'],'windows-v1.8.2')
        self.assertIsNone(archive);materialize.assert_not_called();download.assert_not_called()

if __name__=='__main__':unittest.main()
