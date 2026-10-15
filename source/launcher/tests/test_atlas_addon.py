import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import atlas_addon
import bbport_launcher_win


GAME_BYTES = b'fixture eboot fingerprint'
GAME_HASH = hashlib.sha256(GAME_BYTES).hexdigest()


class AtlasAddonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='Atlas Café מיפוי ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'Atlas package 外部 drive'
        (self.root / 'runtime').mkdir(parents=True)
        (self.root / 'maps').mkdir()
        (self.root / 'art').mkdir()
        (self.root / 'settings').mkdir()
        payloads = {
            'runtime/bb-probe.exe': b'probe fixture',
            'settings/settings.ini': b'map_enabled=0\n',
            'art/icons.bbra': b'art fixture',
            'art/fallback.ttf': b'font fixture',
            'tools/generate_atlas.exe': b'generator fixture',
        }
        for name, data in payloads.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.manifest = {
            'id': 'hunters-atlas',
            'version': '1.4.0-beta1',
            'launcher_builds': [atlas_addon.LAUNCHER_BUILD],
            'game_executables': [GAME_HASH],
            'runtime_build': atlas_addon.RUNTIME_BUILD,
            'mutable_files': ['settings/settings.ini'],
            'paths': {
                'probe': 'runtime/bb-probe.exe',
                'maps': 'maps',
                'config': 'settings/settings.ini',
                'art': 'art',
                'catalog': 'maps/catalog.json',
                'font': 'art/fallback.ttf',
            },
            'generated': {
                'manifest': 'maps/generated-assets.json',
                'required': ['maps/atlas.json', 'maps/catalog.json'],
                'generator': 'tools/generate_atlas.exe',
            },
            'files': {name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()
                      if name != 'settings/settings.ini'},
            'capabilities': ['navigation-map'],
        }
        generated_payloads = {'maps/atlas.json': b'{"maps":[]}',
                              'maps/catalog.json': b'{"areas":[]}'}
        for name, data in generated_payloads.items():
            (self.root / name).write_bytes(data)
        (self.root / 'maps/generated-assets.json').write_text(json.dumps({
            'schema': 1, 'version': 1, 'game_eboot_sha256': GAME_HASH,
            'game_version': 'fixture',
            'files': {name: hashlib.sha256(data).hexdigest()
                      for name, data in generated_payloads.items()},
        }), encoding='utf-8')
        self.write_manifest()

    def write_manifest(self):
        (self.root / atlas_addon.MANIFEST_NAME).write_text(
            json.dumps(self.manifest), encoding='utf-8')

    def inspect(self, **kwargs):
        return atlas_addon.inspect_package(self.root, game_sha256=GAME_HASH, **kwargs)

    def test_valid_package_resolves_unicode_paths_and_checks_hashes(self):
        package = self.inspect()
        self.assertEqual(package.display_version, '1.4.0-beta1')
        self.assertEqual(package.paths['probe'], (self.root / 'runtime/bb-probe.exe').resolve())
        self.assertEqual(package.paths['maps'], (self.root / 'maps').resolve())
        self.assertEqual(package.paths['generator'], (self.root / 'tools/generate_atlas.exe').resolve())
        self.assertTrue(package.generated_ready)

    def test_external_package_paths_are_absolute_and_child_only(self):
        package = self.inspect()
        source = {'PATH': 'keep', 'BB_PROBE': 'stale-probe', 'BB_MAP_DIR': 'stale-map',
                  'BB_MAP_CONFIG': 'stale-config', 'BB_MAP_ENABLED': '0', 'BB_ATLAS_ENABLED': '0'}
        child = atlas_addon.atlas_environment(source, enabled=True, package=package, enter_button='0')
        self.assertEqual(child['PATH'], 'keep')
        self.assertEqual(child['BB_ATLAS_ENABLED'], '1')
        self.assertEqual(child['BB_PROBE'], str(package.paths['probe']))
        self.assertEqual(child['BB_MAP_DIR'], str(package.paths['maps']))
        self.assertEqual(child['BB_ENTER_BUTTON'], '0')
        self.assertNotIn('BB_MAP_ENABLED', child)
        self.assertEqual(source['BB_PROBE'], 'stale-probe')

    def test_invalid_confirm_selection_fails_closed(self):
        with self.assertRaisesRegex(atlas_addon.AtlasManifestError, 'Cross.*Circle'):
            atlas_addon.atlas_environment({}, enabled=True, package=self.inspect(), enter_button='2')

    def test_disabled_clears_every_inherited_atlas_override(self):
        inherited = {key: 'stale' for key in atlas_addon.ENV_KEYS}
        inherited['BB_ATLAS_ENABLED'] = '1'
        inherited['BB_MAP_TEST_TRACE'] = 'stale-test'
        inherited['BB_MAP_UI_DUMP'] = 'stale-dump'
        inherited['BB_MAP_UI_DUMP_TRIGGER'] = 'stale-trigger'
        inherited['BB_MAP_UNEXPECTED_OVERRIDE'] = 'stale-map'
        inherited['BB_PAD_FILE'] = 'stale-pad'
        inherited['bb_map_legacy_lowercase'] = 'stale-lowercase'
        child = atlas_addon.atlas_environment(inherited, enabled=False)
        self.assertEqual(child['BB_ATLAS_ENABLED'], '0')
        for key in atlas_addon.ENV_KEYS:
            if key != 'BB_ATLAS_ENABLED':
                self.assertNotIn(key, child)
        self.assertFalse(any(key.startswith('BB_MAP_') for key in child))
        self.assertNotIn('bb_map_legacy_lowercase', child)
        self.assertNotIn('BB_PAD_FILE', child)
        self.assertNotIn('BB_MAP_UI_DUMP_TRIGGER', child)

    def test_atlas_qa_overrides_require_explicit_child_opt_in(self):
        package = self.inspect()
        inherited = {'BB_ATLAS_QA': '1', 'BB_MAP_TEST_TRACE': 'trace',
                     'BB_MAP_UI_DUMP': 'dump', 'BB_MAP_UI_DUMP_TRIGGER': 'trigger',
                     'BB_PAD_FILE': 'pad-test'}
        child = atlas_addon.atlas_environment(inherited, enabled=True, package=package)
        self.assertEqual(child['BB_ATLAS_QA'], '1')
        self.assertEqual(child['BB_MAP_TEST_TRACE'], 'trace')
        self.assertEqual(child['BB_MAP_UI_DUMP'], 'dump')
        self.assertEqual(child['BB_MAP_UI_DUMP_TRIGGER'], 'trigger')
        self.assertEqual(child['BB_PAD_FILE'], 'pad-test')
        ordinary = atlas_addon.atlas_environment(
            {'BB_MAP_TEST_TRACE': 'trace', 'BB_PAD_FILE': 'pad-test'},
            enabled=True, package=package)
        self.assertNotIn('BB_MAP_TEST_TRACE', ordinary)
        self.assertNotIn('BB_PAD_FILE', ordinary)
        self.assertNotIn('BB_MAP_UI_DUMP_TRIGGER', ordinary)
        disabled = atlas_addon.atlas_environment(inherited, enabled=False)
        self.assertNotIn('BB_ATLAS_QA', disabled)
        self.assertNotIn('BB_MAP_TEST_TRACE', disabled)
        self.assertNotIn('BB_MAP_UI_DUMP_TRIGGER', disabled)

    def test_stock_probe_resolution_prefers_packaged_bin_over_development_out(self):
        port = Path(self.temp.name) / 'launcher with spaces'
        packaged = port / 'bin' / 'bb-probe.exe'
        development = port / 'out' / 'bb-probe.exe'
        packaged.parent.mkdir(parents=True)
        development.parent.mkdir(parents=True)
        packaged.write_bytes(b'stock release probe')
        development.write_bytes(b'development probe')
        self.assertEqual(atlas_addon.stock_probe(port), packaged.resolve())

    def test_launcher_build_mismatch_is_rejected(self):
        with self.assertRaisesRegex(atlas_addon.AtlasManifestError, 'launcher build'):
            self.inspect(launcher_build='windows-v1.7.3-atlas1')

    def test_runtime_build_mismatch_is_rejected(self):
        with self.assertRaisesRegex(atlas_addon.AtlasManifestError, 'runtime build'):
            self.inspect(runtime_build='different-runtime')

    def test_game_executable_mismatch_is_rejected(self):
        with self.assertRaisesRegex(atlas_addon.AtlasManifestError, 'game build'):
            atlas_addon.inspect_package(self.root, game_sha256='0' * 64)

    def test_missing_game_fingerprint_is_rejected(self):
        with self.assertRaisesRegex(atlas_addon.AtlasManifestError, 'fingerprint'):
            atlas_addon.inspect_package(self.root)

    def test_tampered_runtime_hash_is_rejected(self):
        (self.root / 'runtime/bb-probe.exe').write_bytes(b'tampered')
        with self.assertRaisesRegex(atlas_addon.AtlasManifestError, 'SHA-256'):
            self.inspect()

    def test_invalid_manifest_id_is_rejected(self):
        self.manifest['id'] = 'other-package'
        self.write_manifest()
        with self.assertRaisesRegex(atlas_addon.AtlasManifestError, 'add-on id'):
            self.inspect()

    def test_parent_traversal_and_absolute_paths_are_rejected(self):
        for invalid in ('../outside.exe', 'maps/../../outside.exe', r'C:\outside.exe', r'\\server\share'):
            with self.subTest(invalid=invalid):
                self.manifest['paths']['probe'] = invalid
                self.write_manifest()
                with self.assertRaises(atlas_addon.AtlasManifestError):
                    self.inspect()
        self.manifest['paths']['probe'] = 'runtime/bb-probe.exe'
        self.write_manifest()

    def test_symlink_escape_is_rejected_when_host_allows_symlink_creation(self):
        outside = Path(self.temp.name) / 'outside.exe'
        outside.write_bytes(b'external')
        linked = self.root / 'runtime/external.exe'
        try:
            linked.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest('The current Windows account cannot create symlinks.')
        self.manifest['paths']['probe'] = 'runtime/external.exe'
        self.manifest['files']['runtime/external.exe'] = hashlib.sha256(b'external').hexdigest()
        self.write_manifest()
        with self.assertRaisesRegex(atlas_addon.AtlasManifestError, 'outside'):
            self.inspect()

    def test_manifest_requires_hash_entries_for_immutable_runtime_assets(self):
        del self.manifest['files']['art/fallback.ttf']
        self.write_manifest()
        with self.assertRaisesRegex(atlas_addon.AtlasManifestError, 'font file'):
            self.inspect()

    def test_package_rejects_unhashed_extra_files(self):
        (self.root / 'maps/ignored.json').write_text('{}', encoding='utf-8')
        with self.assertRaisesRegex(atlas_addon.AtlasManifestError, 'Unhashed file'):
            self.inspect()

    def test_missing_generated_assets_are_recognized_only_for_status_and_prepare(self):
        (self.root / 'maps/generated-assets.json').unlink()
        (self.root / 'maps/atlas.json').unlink()
        (self.root / 'maps/catalog.json').unlink()
        with self.assertRaisesRegex(atlas_addon.AtlasManifestError, 'not been prepared'):
            self.inspect()
        package = self.inspect(allow_unprepared=True)
        self.assertFalse(package.generated_ready)
        self.assertEqual(package.paths['catalog'], (self.root / 'maps/catalog.json').resolve())
        self.assertTrue(package.generated_message)
        with self.assertRaisesRegex(atlas_addon.AtlasManifestError, 'not been prepared'):
            atlas_addon.atlas_environment({}, enabled=True, package=package)

    def test_normal_launcher_play_environment_blocks_unprepared_local_maps(self):
        for name in ('maps/atlas.json', 'maps/catalog.json', 'maps/generated-assets.json'):
            (self.root / name).unlink()
        game = Path(self.temp.name) / 'game root'
        game.mkdir()
        (game / 'eboot.bin').write_bytes(GAME_BYTES)
        settings = {**bbport_launcher_win.APP_DEFAULTS, 'game_dir': str(game),
                    'atlas_dir': str(self.root), 'atlas_enabled': True}
        with self.assertRaisesRegex(atlas_addon.AtlasManifestError, 'not been prepared'):
            bbport_launcher_win.game_environment(settings)

    def test_launcher_confirm_follows_game_ini_and_ignores_legacy_profile_choice(self):
        game = Path(self.temp.name) / 'game root'
        game.mkdir()
        (game / 'eboot.bin').write_bytes(GAME_BYTES)
        config = Path(self.temp.name) / 'bbport.ini'
        settings = {**bbport_launcher_win.APP_DEFAULTS, 'game_dir': str(game),
                    'atlas_dir': str(self.root), 'atlas_enabled': True}
        for ini_value, legacy, expected in (('1', '1', '0'), ('0', '0', '1'), (None, '0', '1')):
            with self.subTest(ini_value=ini_value, legacy=legacy):
                config.write_text('' if ini_value is None else f'tweak_circle_confirm={ini_value}\n',
                                  encoding='utf-8')
                settings['enter_button'] = legacy
                with mock.patch.dict(os.environ, {'BB_CONFIG': str(config), 'BB_ENTER_BUTTON': legacy}):
                    before = dict(os.environ)
                    child = bbport_launcher_win.game_environment(settings)
                    self.assertEqual(child['BB_ENTER_BUTTON'], expected)
                    self.assertEqual(dict(os.environ), before)
                self.assertEqual(settings['enter_button'], legacy)

    def test_disabled_launcher_keeps_stock_runtime_without_reading_confirm_ini(self):
        settings = {**bbport_launcher_win.APP_DEFAULTS, 'atlas_enabled': False, 'enter_button': '0'}
        stock = Path(self.temp.name) / 'stock-probe.exe'
        with mock.patch.object(bbport_launcher_win, 'load_ini', side_effect=AssertionError('disabled reads INI')), \
                mock.patch.object(atlas_addon, 'stock_probe', return_value=stock), \
                mock.patch.dict(os.environ, {'BB_ENTER_BUTTON': '0', 'BB_ATLAS_ENABLED': '1',
                                            'BB_PROBE': 'stale', 'BB_MAP_DIR': 'stale'}):
            before = dict(os.environ)
            child = bbport_launcher_win.game_environment(settings)
            self.assertEqual(child['BB_PROBE'], str(stock))
            self.assertEqual(child['BB_ATLAS_ENABLED'], '0')
            self.assertNotIn('BB_ENTER_BUTTON', child)
            self.assertNotIn('BB_MAP_DIR', child)
            self.assertEqual(dict(os.environ), before)

    def test_generated_assets_are_bound_to_selected_game_and_validated(self):
        package = self.inspect()
        self.assertTrue(package.generated_ready)
        self.manifest['game_executables'] = ['0' * 64]
        self.write_manifest()
        with self.assertRaisesRegex(atlas_addon.AtlasManifestError, 'different game folder'):
            atlas_addon.inspect_package(self.root, game_sha256='0' * 64)

    def test_generated_font_is_optional_and_selected_only_when_hashed(self):
        native = self.root / 'art/native-font.ttf'
        native.write_bytes(b'local extracted font')
        output_path = self.root / 'maps/generated-assets.json'
        output = json.loads(output_path.read_text(encoding='utf-8'))
        output['files']['art/native-font.ttf'] = hashlib.sha256(native.read_bytes()).hexdigest()
        output_path.write_text(json.dumps(output), encoding='utf-8')
        package = self.inspect()
        self.assertEqual(package.paths['font'], native.resolve())
        self.assertEqual(package.generated_font, native.resolve())
        output['files']['tools/replace-probe.exe'] = '0' * 64
        output_path.write_text(json.dumps(output), encoding='utf-8')
        with self.assertRaisesRegex(atlas_addon.AtlasManifestError, 'outside the allowed output list'):
            self.inspect()

    def test_generated_collision_maps_match_only_named_map_json_pattern(self):
        map_path = self.root / 'maps/m01_02_03_04.json'
        map_path.write_text('{"collision":[]}', encoding='utf-8')
        manifest_path = self.root / 'maps/generated-assets.json'
        output = json.loads(manifest_path.read_text(encoding='utf-8'))
        output['files']['maps/m01_02_03_04.json'] = hashlib.sha256(map_path.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(output), encoding='utf-8')
        self.assertTrue(self.inspect().generated_ready)
        output['files']['maps/m01_02_bad_04.json'] = hashlib.sha256(map_path.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(output), encoding='utf-8')
        with self.assertRaisesRegex(atlas_addon.AtlasManifestError, 'outside the allowed output list'):
            self.inspect()

    def test_generated_map_tampering_marks_prepare_available_but_blocks_play(self):
        (self.root / 'maps/catalog.json').write_text('{"changed":true}', encoding='utf-8')
        with self.assertRaisesRegex(atlas_addon.AtlasManifestError, 'failed its SHA-256'):
            self.inspect()
        package = self.inspect(allow_unprepared=True)
        self.assertFalse(package.generated_ready)
        self.assertIn('SHA-256', package.generated_message)

    def test_package_status_reports_recognized_unprepared_package(self):
        for name in ('maps/atlas.json', 'maps/catalog.json', 'maps/generated-assets.json'):
            (self.root / name).unlink()
        game = Path(self.temp.name) / 'eboot.bin'
        game.write_bytes(GAME_BYTES)
        package, status = atlas_addon.package_status(self.root, game_executable=game)
        self.assertIsNotNone(package)
        self.assertFalse(package.generated_ready)
        self.assertIn('not been prepared', status)

    def test_generator_output_delta_is_limited_to_generated_files(self):
        before = atlas_addon.package_file_inventory(self.root)
        (self.root / 'maps/atlas.json').write_text('{"new":true}', encoding='utf-8')
        (self.root / 'maps/generated-assets.json').write_text('{}', encoding='utf-8')
        atlas_addon.validate_generated_output_delta(self.root, before)
        (self.root / 'settings/settings.ini').write_text('changed by generator', encoding='utf-8')
        with self.assertRaisesRegex(atlas_addon.AtlasManifestError, 'unapproved package file'):
            atlas_addon.validate_generated_output_delta(self.root, before)

    def test_mutable_config_changes_do_not_invalidate_package_payload(self):
        package = self.inspect()
        self.assertEqual(package.paths['config'], (self.root / 'settings/settings.ini').resolve())
        (self.root / 'settings/settings.ini').write_text('enabled=0\nkeyboard=F6\n', encoding='utf-8')
        self.inspect()

    def test_launcher_settings_profile_can_be_redirected_for_isolated_runs(self):
        profile = Path(self.temp.name) / 'isolated launcher profile'
        env = dict(os.environ)
        env['BB_LAUNCHER_SETTINGS_ROOT'] = str(profile)
        env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1])
        code = ('import bbport_launcher_win as launcher; '
                'print(launcher.CONFIG_FILE); print(launcher.CONFIG_DIR)')
        result = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True,
                                text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [str(profile / 'settings.json'), str(profile)])
        self.assertFalse(profile.exists(), 'Importing the launcher must not create profile files.')


if __name__ == '__main__':
    unittest.main()
