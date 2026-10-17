"""Failure-oriented checks for the real catalog, journal and adapter code."""
from pathlib import Path
import datetime,importlib.util,io,json,os,subprocess,sys,tempfile,unittest,zipfile
from unittest import mock

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
import catalog,transaction,coordinator
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
adapter=module('tested_atlas_adapter',HERE.parent/'integration/ui/atlas_adapter.py')
features=module('tested_atlas_features',HERE.parent/'integration/ui/atlas_feature_config.py')
identity=module('tested_asset_identity',HERE.parent/'generator/asset_identity.py')

class Updates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script="$r=New-Object Security.Cryptography.RSACryptoServiceProvider(3072);$r.PersistKeyInCsp=$false;$p=$r.ExportParameters($true);@{n=([BitConverter]::ToString($p.Modulus).Replace('-','').ToLowerInvariant());e=65537;d=([BitConverter]::ToString($p.D).Replace('-','').ToLowerInvariant())}|ConvertTo-Json -Compress;$r.Dispose()"
        cls.private=json.loads(subprocess.check_output(['powershell','-NoProfile','-Command',script],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)))
        cls.public={k:cls.private[k] for k in ('n','e')}
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.root=Path(self.temporary.name)
    def tearDown(self):self.temporary.cleanup()
    def data(self):
        return {'schema':1,'minimum_coordinator':1,'expires':(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(days=1)).isoformat(),
                'targets':[{'upstream_release':'windows-v1.8.1','upstream_commit':'a'*40,'platform':'windows-x86_64',
                            'adapter_protocol':1,'minimum_coordinator':1,'upstream_sha256':'b'*64,'atlas_manifest_sha256':'c'*64,
                            'validation_status':'candidate','upstream_url':'https://github.com/Supermedo/bloodborne_pc/releases/download/windows-v1.8.1/Bloodborne-Windows.zip'}]}
    def signed(self,data=None):
        data=data or self.data();path=self.root/'catalog.json'
        transaction.write_json(path,{'catalog':data,'signature':catalog.sign(data,self.private)});return path
    def journal(self):
        live=self.root/'launcher';stage=self.root/'new';backup=self.root/'backup';state=self.root/'transaction';state.mkdir()
        live.mkdir();stage.mkdir();(live/'runtime').write_text('old');(stage/'runtime').write_text('new')
        path=state/'journal.json';transaction.write_json(path,{'schema':1,'state':'activation_pending','transaction_root':str(state),
            'allowed_roots':[str(live),str(stage),str(backup)],'actions':[]})
        return transaction.Journal(path),live,stage,backup
    def test_signed_catalog_and_exact_known_target(self):
        data=catalog.load(self.signed(),self.public)
        self.assertEqual(catalog.resolve(data,'windows-v1.8.1',allow_candidate=True)['adapter_protocol'],1)
        with self.assertRaises(ValueError):catalog.resolve(data,'windows-v1.8.1')
        for tag in ('windows-v1.8.2','windows-v2.0','windows-v9.9'):
            with self.assertRaises(ValueError):catalog.resolve(data,tag,allow_candidate=True)
    def test_catalog_rejects_tampering_and_expiry(self):
        path=self.signed();envelope=json.loads(path.read_text());envelope['catalog']['targets'][0]['upstream_sha256']='d'*64
        transaction.write_json(path,envelope)
        with self.assertRaises(ValueError):catalog.load(path,self.public)
        data=self.data();data['expires']='2000-01-01T00:00:00+00:00'
        with self.assertRaises(ValueError):catalog.load(self.signed(data),self.public)
    def test_corrupt_download_leaves_no_active_artifact(self):
        target=self.root/'update.zip'
        with mock.patch.object(coordinator.urllib.request,'urlopen',return_value=io.BytesIO(b'corrupt')):
            with self.assertRaises(ValueError):coordinator.download('https://example.invalid/update.zip',target,'0'*64)
        self.assertFalse(target.exists());self.assertFalse(target.with_suffix('.partial').exists())
    def test_archive_rejects_traversal_and_case_duplicates(self):
        for names in (('../escape',),('bin/A.dll','bin/a.dll'),('C:/escape',)):
            archive=self.root/'input.zip'
            with zipfile.ZipFile(archive,'w') as z:
                for n in names:z.writestr(n,'x')
            for preserve_alias in (False,True):
                with self.assertRaises(ValueError):coordinator.safe_unpack(archive,self.root/'expanded',preserve_alias=preserve_alias)
    def test_crash_between_rename_and_checkpoint_recovers(self):
        journal,live,stage,backup=self.journal()
        journal.data['actions'].append({'source':str(live),'destination':str(backup),'applied':False});journal.save()
        os.replace(live,backup)
        transaction.Journal(journal.path).restore()
        self.assertEqual((live/'runtime').read_text(),'old');self.assertFalse(backup.exists())
    def test_rollback_preserves_new_progress_in_mutable_directory(self):
        journal,live,stage,backup=self.journal();(live/'user').mkdir();(live/'user/progress').write_text('before')
        journal.move(live,backup);journal.move(stage,live);journal.move(backup/'user',live/'user')
        (live/'user/progress').write_text('new progress')
        journal.restore()
        self.assertEqual((live/'runtime').read_text(),'old');self.assertEqual((live/'user/progress').read_text(),'new progress')
        self.assertEqual((stage/'runtime').read_text(),'new')
    def test_recovery_can_restart_after_an_interrupted_undo(self):
        journal,live,stage,backup=self.journal();journal.move(live,backup);journal.move(stage,live)
        original=journal.save;calls=0
        def interrupted_save():
            nonlocal calls
            calls+=1
            if calls==3:raise OSError('disk full after inverse rename')
            original()
        with mock.patch.object(journal,'save',side_effect=interrupted_save):
            with self.assertRaises(OSError):journal.restore()
        transaction.Journal(journal.path).restore()
        self.assertEqual((live/'runtime').read_text(),'old')
    def test_journal_and_locks_reject_unowned_paths_and_double_install(self):
        journal,live,stage,backup=self.journal()
        with self.assertRaises(ValueError):journal.move(live,self.root/'unowned')
        with transaction.lock(live):
            with self.assertRaises(RuntimeError):
                with transaction.lock(live):pass
        self.assertFalse((self.root/'.launcher.atlas-maintenance.lock').exists())
    def test_offline_refresh_keeps_authenticated_local_catalog(self):
        package=self.root/'package';updates=package/'updates';updates.mkdir(parents=True)
        path=self.signed();(updates/'catalog.json').write_bytes(path.read_bytes())
        transaction.write_json(updates/'catalog-source.json',{'url':'https://example.invalid/catalog'})
        previous=(updates/'catalog.json').read_bytes();load=catalog.load
        with mock.patch.object(coordinator.urllib.request,'urlopen',side_effect=OSError('offline')),\
             mock.patch.object(catalog,'load',side_effect=lambda p:load(p,self.public)):
            data,notice=coordinator.refresh_catalog(package)
        self.assertIn('offline',notice);self.assertEqual(data['schema'],1);self.assertEqual(previous,(updates/'catalog.json').read_bytes())
    def test_asset_key_ignores_launcher_and_detects_changed_game_inputs(self):
        game=self.root/'game';game.mkdir();(game/'eboot.bin').write_bytes(b'game')
        manifest={'files':{'tools/generator.atlaslite':'a'*64,'tools/extract_atlas_features.py':'b'*64},'feature_schema':1}
        first=identity.key(game,manifest)
        manifest['compatibility']={'upstream_release':'windows-v1.8.1'}
        self.assertEqual(first,identity.key(game,manifest))
        (game/'eboot.bin').write_bytes(b'changed game');self.assertNotEqual(first,identity.key(game,manifest))
    def test_all_feature_switch_combinations_keep_independent_map_configuration(self):
        for fog in (False,True):
            for travel in (False,True):
                env=features.environment({'atlas_fog_enabled':fog,'atlas_travel_enabled':travel})
                self.assertEqual(env['BB_MAP_FOG_ENABLED'],str(int(fog)))
                self.assertEqual(env['BB_MAP_TRAVEL_ENABLED'],str(int(travel)))
    def test_bundled_artifact_requires_the_signed_archive_digest(self):
        package=self.root/'atlas';(package/'.distribution').mkdir(parents=True)
        archive=package/'.distribution/windows-v1.8.1.zip';archive.write_bytes(b'fixture')
        entry={'upstream_release':'windows-v1.8.1','atlas_sha256':coordinator.sha(archive)}
        self.assertEqual(coordinator.bundled_archive(package,entry),archive.resolve())
        archive.write_bytes(b'tampered')
        with self.assertRaises(ValueError):coordinator.bundled_archive(package,entry)
        archive.unlink();self.assertIsNone(coordinator.bundled_archive(package,entry))

    def test_materialized_adapter_retains_authenticated_bundles(self):
        package=self.root/'distribution';(package/'.distribution').mkdir(parents=True)
        (package/'updates').mkdir()
        archive=package/'.distribution/windows-v1.8.1.zip'
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('HuntersAtlas/manifest.json','{}')
            z.writestr('HuntersAtlas/updates/coordinator.py','# fixture')
        data=self.data();entry=data['targets'][0];entry['atlas_sha256']=coordinator.sha(archive)
        (package/'updates/catalog.json').write_bytes(self.signed(data).read_bytes())
        load=catalog.load
        with mock.patch.object(catalog,'load',side_effect=lambda p,**kw:load(p,self.public,**kw)),mock.patch.object(coordinator,'fresh_package'):
            fresh=coordinator.materialize(package,entry,self.root/'work')
        self.assertEqual(coordinator.sha(fresh/'.distribution/windows-v1.8.1.zip'),entry['atlas_sha256'])
    def test_legacy_runtime_identity_does_not_claim_new_native_build_protocol(self):
        legacy={'upstream_release':'windows-v1.7.2','runtime_sha256':'a'*64}
        self.assertEqual(coordinator.release_identity({'legacy_runtime':legacy}),legacy)
        env=adapter.configure_network({'BB_NET_BACKEND':'thd'},dict(online=True,online_pool='huntersdream'),'1.7.2')
        self.assertEqual(env['BB_BRIDGE'],'1');self.assertNotIn('BB_NET_BACKEND',env)
    def test_fresh_bundle_supersedes_old_bundle_during_same_launcher_repair(self):
        current=self.root/'current';fresh=self.root/'fresh';staged=self.root/'staged'
        for p in (current,fresh,staged):(p/'.distribution').mkdir(parents=True);(p/'updates').mkdir()
        tag='windows-v1.8.1';name=tag+'.zip'
        (current/'.distribution'/name).write_bytes(b'old adapter')
        (fresh/'.distribution'/name).write_bytes(b'new adapter')
        entry={'upstream_release':tag,'atlas_sha256':coordinator.sha(fresh/'.distribution'/name)}
        path=fresh/'updates/catalog.json';path.write_text('signed catalog fixture')
        with mock.patch.object(catalog,'load',return_value={'targets':[entry]}):
            coordinator.copy_bundled(current,staged,path,fresh=fresh)
        self.assertEqual((staged/'.distribution'/name).read_bytes(),b'new adapter')
        self.assertEqual((current/'.distribution'/name).read_bytes(),b'old adapter')
    def test_network_adapter_cleans_stale_backend_and_preserves_current_pools(self):
        stale={key:'stale' for key in adapter.NETWORK_KEYS}
        disabled=adapter.configure_network(stale,{'online':False})
        self.assertNotIn('BB_THD_TOKEN',disabled);self.assertNotIn('BB_BRIDGE',disabled);self.assertNotIn('BB_ONLINE',disabled)
        thd=adapter.configure_network(stale,{'online':True,'online_pool':'huntersdream','thd_online_id':'fixture','thd_token':'fixture-token'})
        self.assertEqual(thd['BB_NET_BACKEND'],'thd');self.assertEqual(thd['BB_THD_TOKEN'],'fixture-token');self.assertNotIn('BB_BRIDGE',thd)
        public=adapter.configure_network(stale,{'online':True,'online_pool':'supermedo','supermedo_user':'fixture','supermedo_password':'fixture-secret'})
        self.assertNotIn('BB_THD_TOKEN',public);self.assertEqual(public['BB_SHADNET_SERVER'],'www.supermedo.com:31313')
    def test_rollback_association_preserves_user_disabled_atlas_and_unknown_settings(self):
        path=self.root/'settings.json';transaction.write_json(path,{'atlas_dir':'atlas','atlas_enabled':False,'future_setting':42})
        coordinator.change_association({'profile_path':str(path)},{'atlas_dir':'old-atlas','atlas_enabled':True},preserve_enabled=True)
        result=json.loads(path.read_text());self.assertFalse(result['atlas_enabled']);self.assertEqual(result['future_setting'],42)

    def test_current_pair_checks_adapter_manifest_even_with_identical_native_binary(self):
        package=self.root/'atlas';(package/'bin').mkdir(parents=True);(package/'.install').mkdir()
        (package/'bin/bb-probe.exe').write_bytes(b'native')
        profile={'upstream_release':'windows-v1.8.1','upstream_commit':'a'*40,'adapter_protocol':1}
        transaction.write_json(package/'manifest.json',{'compatibility':profile})
        (package/'.install/manifest.json').write_bytes(b'original signed artifact identity')
        entry={**profile,'runtime_sha256':coordinator.sha(package/'bin/bb-probe.exe'),
               'atlas_manifest_sha256':coordinator.sha(package/'.install/manifest.json')}
        transaction.write_json(package/'.install/receipt.json',{'artifact_manifest_sha256':entry['atlas_manifest_sha256']})
        self.assertTrue(coordinator.is_current(package,entry))
        entry['atlas_manifest_sha256']='0'*64
        self.assertFalse(coordinator.is_current(package,entry))

if __name__=='__main__':unittest.main()
