"""Filesystem transaction and migration tests; no real launchers or saves used."""
import hashlib
import importlib.util
import json
import os
import stat
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest import mock


SOURCE = Path(__file__).resolve().parents[1] / "installer.py"
SPEC = importlib.util.spec_from_file_location("owned_install_test", SOURCE)
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)
ASSETS_SOURCE = Path(__file__).resolve().parents[2] / "lite/bootstrap/assets.py"
ASSETS_SPEC = importlib.util.spec_from_file_location("owned_install_test_assets", ASSETS_SOURCE)
assets = importlib.util.module_from_spec(ASSETS_SPEC)
ASSETS_SPEC.loader.exec_module(assets)


def write(path, contents):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(contents.encode() if isinstance(contents, str) else contents)
    return path


def json_file(path, contents):
    return write(path, json.dumps(contents))


def snapshot(root):
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="Atlas installer Ω ")
        self.workspace = Path(self.temporary.name).resolve()
        self.source = self.workspace / "update source"
        self.target = self.workspace / "Atlas installed"
        self.launcher = self.workspace / "ordinary launcher"
        self.saves = self.workspace / "live saves"
        self.profile_source = self.workspace / "ordinary settings.json"
        self.make_package(self.source, "new package")
        write(self.launcher / "Bloodborne.exe", b"ordinary executable must not change")
        write(self.launcher / "bbport.ini", "upscaler=fsr\n")
        write(self.launcher / "input.ini", "confirm=circle\n")
        write(self.launcher / "mods.json", '{"selected":["mod"]}')
        write(self.launcher / "patches.json", '{"enabled":["dlc"]}')
        write(self.launcher / "patches/dlc.xml", "<Patch/>")
        write(self.saves / "savedata/save.bin", b"actual user save never opened")
        json_file(self.profile_source, {"game_dir": "Z:/game", "user_dir": str(self.saves),
                                        "dlc_dir": "Z:/dlc", "online": False,
                                        "atlas_enabled": True, "graphics_custom": "keep"})
        self.ordinary_before = snapshot(self.launcher)
        self.saves_before = snapshot(self.saves)
        self.profile_before = self.profile_source.read_bytes()
        # Only runtime identity/process enumeration are mocked. Every copy,
        # rename, metadata update and map-pack validation uses the real files.
        self.runtime = types.SimpleNamespace(load_contract=mock.Mock(return_value={}),
                                             ensure_no_game_processes=mock.Mock())
        self.core_patch = mock.patch.object(installer, "core", return_value=self.runtime)
        self.core_patch.start()

    def tearDown(self):
        self.core_patch.stop()
        self.temporary.cleanup()

    def make_package(self, root, content):
        write(root / "HuntersAtlas.exe", content)
        write(root / "bootstrap/assets.py", ASSETS_SOURCE.read_bytes())
        write(root / "settings/settings.ini", "fog=true\n")
        json_file(root / "manifest.json", {"schema": 1, "id": "hunters-atlas-lite",
                    "installation_model": "owned-runtime-v1", "files": {},
                    "feature_schema": 1, "asset_key_schema": 1})

    def install(self, **options):
        return installer.install(self.source, self.target, profile_source=self.profile_source,
                                 launcher=self.launcher, **options)

    def assert_ordinary_untouched(self):
        self.assertEqual(snapshot(self.launcher), self.ordinary_before)
        self.assertEqual(snapshot(self.saves), self.saves_before)
        self.assertEqual(self.profile_source.read_bytes(), self.profile_before)

    def test_first_install_preserves_live_save_path_and_copies_selected_configs(self):
        record = self.install()
        settings = installer.read(self.target / "state/profile/settings.json")
        self.assertEqual(settings["user_dir"], str(self.saves))
        self.assertEqual(settings["game_dir"], "Z:/game")
        self.assertEqual(settings["dlc_dir"], "Z:/dlc")
        self.assertEqual(settings["graphics_custom"], "keep")
        for name in ("bbport.ini", "input.ini", "mods.json", "patches.json"):
            self.assertEqual((self.target / "state/port" / name).read_bytes(),
                             (self.launcher / name).read_bytes())
        self.assertEqual(record["phase"], "complete")
        self.assertEqual(record["generator_invocations"], 0)
        self.assert_ordinary_untouched()

    def test_owned_update_retains_profile_state_settings_and_original_installation(self):
        self.make_package(self.target, "old package")
        custom = {"user_dir": str(self.saves), "atlas_enabled": False, "atlas_dir": str(self.target),
                  "confirm": "circle", "atlas_fog": False, "online": True}
        json_file(self.target / "state/profile/settings.json", custom)
        write(self.target / "state/port/input.ini", "confirm=circle\ncustom=1\n")
        write(self.target / "state/map-progress.json", '{"visited":[1,2]}')
        write(self.target / "settings/settings.ini", "fog=false\n")
        old = snapshot(self.target)
        record = self.install()
        self.assertEqual(installer.read(self.target / "state/profile/settings.json"), custom)
        self.assertEqual((self.target / "state/port/input.ini").read_text(), "confirm=circle\ncustom=1\n")
        self.assertEqual((self.target / "state/map-progress.json").read_text(), '{"visited":[1,2]}')
        self.assertEqual((self.target / "settings/settings.ini").read_text(), "fog=false\n")
        self.assertEqual(snapshot(Path(record["backup"])), old)
        self.assertEqual((self.target / "HuntersAtlas.exe").read_text(), "new package")
        self.assert_ordinary_untouched()

    def test_activation_rename_failure_restores_previous_directory(self):
        self.make_package(self.target, "old package")
        old = snapshot(self.target)
        original = Path.rename

        def injected(path, destination):
            if path.name.startswith(".atlas-owned-stage-"):
                raise PermissionError("Injected activation sharing violation")
            return original(path, destination)

        with mock.patch.object(Path, "rename", injected):
            with self.assertRaises(PermissionError):
                self.install()
        self.assertEqual(snapshot(self.target), old)
        self.assert_ordinary_untouched()

    def test_unrelated_destination_and_parent_child_paths_are_refused(self):
        write(self.target / "personal.txt", "preserve")
        with self.assertRaisesRegex(ValueError, "not an Atlas"):
            self.install()
        self.assertEqual((self.target / "personal.txt").read_text(), "preserve")
        with self.assertRaisesRegex(ValueError, "separate"):
            installer.install(self.source, self.source / "nested")
        with self.assertRaisesRegex(ValueError, "separate"):
            installer.install(self.source, self.workspace)

    def test_shortcut_failure_does_not_report_complete(self):
        with mock.patch.object(installer, "shortcut", side_effect=OSError("injected shortcut failure")):
            with self.assertRaisesRegex(OSError, "shortcut failure"):
                self.install(shortcut_path=self.workspace / "Bloodborne.lnk")
        receipt = self.target / "state/installation/receipt.json"
        self.assertFalse(receipt.exists() and installer.read(receipt).get("phase") == "complete")
        journals = list(self.workspace.glob(".atlas-owned-install-*.json"))
        self.assertTrue(journals)
        self.assertTrue(all(installer.read(path).get("phase") != "complete" for path in journals))
        self.assert_ordinary_untouched()

    def test_art_only_pack_is_not_imported_as_prepared_maps(self):
        self.make_package(self.target, "old package")
        font = write(self.workspace / "font.ttf", b"font")
        assets.build({"art/native-font.ttf": font}, self.target / "assets.atlaslite")
        old = installer.read(self.target / "manifest.json")
        old["asset_pack"] = {"path": "assets.atlaslite", "sha256": installer.sha(self.target / "assets.atlaslite")}
        json_file(self.target / "manifest.json", old)
        self.assertFalse(installer.retain_pack(self.target, self.source))
        self.assertFalse((self.source / "assets.atlaslite").exists())

    def test_invalid_previous_pack_is_never_imported(self):
        self.make_package(self.target, "old package")
        write(self.target / "assets.atlaslite", b"invalid pack bytes")
        old = installer.read(self.target / "manifest.json")
        old["asset_pack"] = {"path": "assets.atlaslite", "sha256": "0" * 64}
        json_file(self.target / "manifest.json", old)
        with self.assertRaisesRegex(ValueError, "integrity check"):
            installer.retain_pack(self.target, self.source)
        self.assertFalse((self.source / "assets.atlaslite").exists())

    def test_owned_update_reuses_verified_prepared_maps_without_running_generator(self):
        self.make_package(self.target, "old package")
        map_file = write(self.workspace / "map.json", b'{"schema":1}')
        features = write(self.workspace / "features.json", b'{"schema":1}')
        font = write(self.workspace / "font.ttf", b"font")
        receipt = json_file(self.workspace / "generated-assets.json", {
            "schema": 1, "feature_schema": 1,
            "files": {"maps/map.json": installer.sha(map_file),
                      "maps/features.json": installer.sha(features)}})
        assets.build({"maps/map.json": map_file, "maps/features.json": features,
                      "maps/generated-assets.json": receipt, "art/native-font.ttf": font},
                     self.target / "assets.atlaslite")
        for package in (self.source, self.target):
            manifest = installer.read(package / "manifest.json")
            manifest["files"].update({"tools/generator.atlaslite": "1" * 64,
                                      "tools/extract_atlas_features.py": "2" * 64})
            if package == self.target:
                manifest["asset_pack"] = {"path": "assets.atlaslite",
                                          "sha256": installer.sha(package / "assets.atlaslite")}
            json_file(package / "manifest.json", manifest)
        old_pack = (self.target / "assets.atlaslite").read_bytes()
        record = self.install()
        self.assertTrue(record["maps_reused"])
        self.assertEqual(record["generator_invocations"], 0)
        self.assertEqual((self.target / "assets.atlaslite").read_bytes(), old_pack)
        manifest = installer.read(self.target / "manifest.json")
        self.assertEqual(manifest["files"]["assets.atlaslite"], installer.sha(self.target / "assets.atlaslite"))
        self.assert_ordinary_untouched()

    def test_portable_same_directory_install_retains_state_and_saves(self):
        json_file(self.source / "state/profile/settings.json",
                  {"user_dir": str(self.saves), "atlas_dir": str(self.source), "atlas_enabled": True})
        write(self.source / "state/port/input.ini", "custom=1\n")
        record = installer.install(self.source, self.source, profile_source=self.profile_source,
                                   launcher=self.launcher)
        self.assertEqual(record["phase"], "complete")
        self.assertEqual((self.source / "state/port/input.ini").read_text(), "custom=1\n")
        self.assertEqual(installer.read(self.source / "state/profile/settings.json")["user_dir"], str(self.saves))
        self.assert_ordinary_untouched()

    def test_reparse_inside_package_is_refused(self):
        directory = self.source / "redirected"
        self.link_directory(directory, self.launcher)
        try:
            with self.assertRaisesRegex(ValueError, "Linked"):
                self.install()
        finally:
            self.unlink_directory(directory)

    def test_reparse_at_destination_root_is_refused_before_resolving(self):
        real = self.workspace / "real Atlas"
        self.make_package(real, "old package")
        self.link_directory(self.target, real)
        try:
            with self.assertRaisesRegex(ValueError, "Linked"):
                self.install()
            self.assertEqual((real / "HuntersAtlas.exe").read_text(), "old package")
        finally:
            self.unlink_directory(self.target)

    def latest_journal(self):
        return next(self.workspace.glob('.atlas-owned-install-*.json'))

    def test_only_recovery_can_reclaim_a_proven_dead_maintenance_owner(self):
        lock = self.target.parent / ('.' + self.target.name + '.owned-maintenance.lock')
        json_file(lock, {'pid': 424242, 'token': 'stale'})
        with mock.patch.object(installer, 'pid_alive', return_value=False):
            with self.assertRaises(FileExistsError):
                with installer.maintenance(self.target):
                    self.fail('normal installation stole a stale lock')
            with installer.maintenance(self.target, recovery=True):
                self.assertEqual(installer.read(lock)['pid'], os.getpid())
        self.assertFalse(lock.exists())
        json_file(lock, {'pid': os.getpid(), 'token': 'live'})
        original = lock.read_bytes()
        with self.assertRaisesRegex(RuntimeError, 'live process'):
            with installer.maintenance(self.target, recovery=True):
                self.fail('recovery stole a live lock')
        self.assertEqual(lock.read_bytes(), original)

    def test_crash_after_backup_move_recovers_without_changing_immutable_backup(self):
        class PowerLoss(BaseException):
            pass
        self.make_package(self.target, 'old package')
        old = snapshot(self.target)
        original = Path.rename

        def crash(path, destination):
            if path.name.startswith('.atlas-owned-stage-'):
                raise PowerLoss()
            return original(path, destination)

        with mock.patch.object(Path, 'rename', crash):
            with self.assertRaises(PowerLoss):
                self.install()
        journal = self.latest_journal()
        backup = Path(installer.read(journal)['backup'])
        self.assertFalse(self.target.exists())
        result = installer.recover(journal)
        self.assertEqual(result['phase'], 'recovered')
        self.assertEqual(snapshot(self.target), old)
        self.assertEqual(snapshot(backup), old)
        self.assert_ordinary_untouched()

    def test_failed_rollback_activation_is_retry_safe_and_keeps_backup_unchanged(self):
        self.make_package(self.target, 'old package')
        record = self.install()
        journal = self.latest_journal()
        backup = Path(record['backup'])
        immutable_backup = snapshot(backup)
        profile = self.target / 'state/profile/settings.json'
        settings = installer.read(profile)
        settings['latest_user_preference'] = 'retain after rollback'
        json_file(profile, settings)
        original = Path.rename

        def fail_activation(path, destination):
            if path.name.startswith('.atlas-owned-restore-'):
                raise PermissionError('Injected rollback activation failure')
            return original(path, destination)

        with mock.patch.object(Path, 'rename', fail_activation):
            with self.assertRaisesRegex(PermissionError, 'rollback activation'):
                installer.recover(journal, rollback=True)
        self.assertEqual(snapshot(backup), immutable_backup)
        self.assertFalse(self.target.exists())
        result = installer.recover(journal, rollback=True)
        self.assertEqual(result['phase'], 'rolled-back')
        self.assertEqual((self.target / 'HuntersAtlas.exe').read_text(), 'old package')
        self.assertEqual(installer.read(self.target / 'state/profile/settings.json')['latest_user_preference'],
                         'retain after rollback')
        self.assertEqual(snapshot(backup), immutable_backup)
        self.assertEqual(installer.recover(journal, rollback=True)['phase'], 'rolled-back')
        self.assert_ordinary_untouched()

    def test_same_target_rollback_restores_exact_initial_metadata_and_shortcut(self):
        profile = self.source / 'state/profile/settings.json'
        json_file(profile, {'user_dir': str(self.saves), 'atlas_dir': 'prior value', 'custom': 'keep'})
        write(self.source / 'state/installation/receipt.json', '{"old":"receipt"}')
        before = {name: (self.source / name).read_bytes() for name in (
            'state/profile/settings.json', 'state/installation/receipt.json', 'settings/settings.ini')}
        link = write(self.workspace / 'Bloodborne.lnk', b'original shortcut')
        with mock.patch.object(installer, 'shortcut', side_effect=lambda path, target, backup: path.write_bytes(b'owned shortcut')):
            installer.install(self.source, self.source, profile_source=self.profile_source,
                              launcher=self.launcher, shortcut_path=link)
        journal = self.latest_journal()
        installer.recover(journal, rollback=True)
        self.assertEqual(link.read_bytes(), b'original shortcut')
        for name, original in before.items():
            self.assertEqual((self.source / name).read_bytes(), original)
        self.assertFalse((self.source / 'state/port/input.ini').exists())
        self.assert_ordinary_untouched()

    def test_same_target_initialization_failure_has_recoverable_snapshot(self):
        profile = self.source / 'state/profile/settings.json'
        self.assertFalse(profile.exists())
        original = installer.initialize

        def fail_after_initialize(*args):
            original(*args)
            raise OSError('Injected metadata initialization failure')

        with mock.patch.object(installer, 'initialize', side_effect=fail_after_initialize):
            with self.assertRaisesRegex(OSError, 'initialization failure'):
                installer.install(self.source, self.source, profile_source=self.profile_source,
                                  launcher=self.launcher)
        self.assertTrue(profile.exists())
        self.assertEqual(installer.recover(self.latest_journal())['phase'], 'recovered')
        self.assertFalse(profile.exists())
        self.assert_ordinary_untouched()

    def test_missing_portable_root_never_reports_successful_recovery(self):
        installer.install(self.source, self.source, profile_source=self.profile_source, launcher=self.launcher)
        journal = self.latest_journal()
        self.source.rename(self.workspace / 'moved portable source')
        with self.assertRaises((ValueError, FileNotFoundError)):
            installer.recover(journal, rollback=True)
        self.assertNotIn(installer.read(journal)['phase'], ('rolled-back', 'recovered'))

    def test_cli_update_uses_independent_locator_and_never_defaults_to_extracted_package(self):
        self.make_package(self.target, 'old package')
        json_file(self.target / 'state/profile/settings.json', {'user_dir': str(self.saves)})
        locator = json_file(self.workspace / 'appdata/HuntersAtlas/installation.json', {
            'schema': 1, 'installation_model': 'owned-runtime-v1', 'target': str(self.target)})
        with mock.patch.object(installer, 'ROOT', self.source), \
                mock.patch.object(installer, 'locator_path', return_value=locator), \
                mock.patch.object(installer, 'install', return_value={'phase': 'complete'}) as install_call, \
                mock.patch('builtins.print'):
            installer.main(['--update', '--no-shortcut', '--profile-source', str(self.profile_source)])
        self.assertEqual(install_call.call_args.args, (self.source, self.target))
        self.assertIsNone(install_call.call_args.kwargs['shortcut_path'])
        self.assertEqual(installer.read(locator)['target'], str(self.target))

    def test_cli_failure_does_not_publish_installation_locator(self):
        locator = self.workspace / 'appdata/HuntersAtlas/installation.json'
        with mock.patch.object(installer, 'ROOT', self.source), \
                mock.patch.object(installer, 'locator_path', return_value=locator), \
                mock.patch.object(installer, 'pick_folder', return_value=self.launcher), \
                mock.patch.object(installer, 'install', side_effect=OSError('failed install')):
            with self.assertRaises(OSError):
                installer.main(['--target', str(self.target), '--no-shortcut',
                                '--profile-source', str(self.profile_source)])
        self.assertFalse(locator.exists())

    def test_windows_desktop_lookup_uses_shell_redirected_folder(self):
        redirected = self.workspace / 'OneDrive Ω/Redirected Desktop'
        redirected.mkdir(parents=True)

        def get_folder(window, folder_id, token, flags, buffer):
            self.assertEqual(folder_id, 0x0010)
            self.assertEqual(flags, 0)
            buffer.value = str(redirected)
            return 0

        function = mock.Mock(side_effect=get_folder)
        shell = types.SimpleNamespace(SHGetFolderPathW=function)
        with mock.patch.object(installer.ctypes, 'WinDLL', return_value=shell, create=True):
            self.assertEqual(installer.desktop_folder(), redirected)
        function.assert_called_once()

    def test_default_cli_shortcut_targets_redirected_desktop(self):
        redirected = self.workspace / 'OneDrive Ω/Redirected Desktop'
        redirected.mkdir(parents=True)
        locator = self.workspace / 'appdata/HuntersAtlas/installation.json'
        with mock.patch.object(installer, 'ROOT', self.source), \
                mock.patch.object(installer, 'locator_path', return_value=locator), \
                mock.patch.object(installer, 'desktop_folder', return_value=redirected), \
                mock.patch.object(installer, 'install', return_value={'phase': 'complete'}) as install_call, \
                mock.patch('builtins.print'):
            installer.main(['--target', str(self.target), '--launcher', str(self.launcher),
                            '--profile-source', str(self.profile_source)])
        self.assertEqual(install_call.call_args.kwargs['shortcut_path'], redirected / 'Bloodborne.lnk')

    def test_desktop_lookup_failure_happens_before_installation_or_locator_write(self):
        locator = self.workspace / 'appdata/HuntersAtlas/installation.json'
        with mock.patch.object(installer, 'ROOT', self.source), \
                mock.patch.object(installer, 'locator_path', return_value=locator), \
                mock.patch.object(installer, 'desktop_folder', side_effect=ValueError('Desktop unavailable')), \
                mock.patch.object(installer, 'install') as install_call:
            with self.assertRaisesRegex(ValueError, 'Desktop unavailable'):
                installer.main(['--target', str(self.target), '--launcher', str(self.launcher),
                                '--profile-source', str(self.profile_source)])
        install_call.assert_not_called()
        self.assertFalse(locator.exists())
        self.assertFalse(self.target.exists())

    def test_desktop_lookup_api_failure_or_missing_directory_has_no_wrong_fallback(self):
        for result, value in ((-2147467259, ''), (0, ''), (0, str(self.workspace / 'missing Desktop'))):
            with self.subTest(result=result, value=value):
                def get_folder(window, folder_id, token, flags, buffer):
                    buffer.value = value
                    return result
                shell = types.SimpleNamespace(SHGetFolderPathW=mock.Mock(side_effect=get_folder))
                with mock.patch.object(installer.ctypes, 'WinDLL', return_value=shell, create=True):
                    with self.assertRaisesRegex(ValueError, 'Desktop'):
                        installer.desktop_folder()
        with mock.patch.object(installer.ctypes, 'WinDLL', side_effect=OSError('no shell API'), create=True):
            with self.assertRaisesRegex(ValueError, 'lookup is unavailable'):
                installer.desktop_folder()

    def test_explicit_shortcut_and_no_shortcut_bypass_desktop_lookup(self):
        locator = self.workspace / 'appdata/HuntersAtlas/installation.json'
        explicit = self.workspace / 'chosen shortcut.lnk'
        for options, expected in ((['--shortcut', str(explicit)], explicit),
                                  (['--shortcut', str(explicit), '--no-shortcut'], None)):
            with self.subTest(options=options), \
                    mock.patch.object(installer, 'ROOT', self.source), \
                    mock.patch.object(installer, 'locator_path', return_value=locator), \
                    mock.patch.object(installer, 'desktop_folder', side_effect=AssertionError('unneeded Desktop lookup')), \
                    mock.patch.object(installer, 'install', return_value={'phase': 'complete'}) as install_call, \
                    mock.patch('builtins.print'):
                installer.main(['--target', str(self.target), '--launcher', str(self.launcher),
                                '--profile-source', str(self.profile_source), *options])
            self.assertEqual(install_call.call_args.kwargs['shortcut_path'], expected)

    def test_redirected_desktop_parent_junction_supports_shortcut_snapshot_and_recovery(self):
        actual = self.workspace / 'actual redirected desktop'
        actual.mkdir()
        alias = self.workspace / 'redirected desktop junction'
        self.link_directory(alias, actual)
        link = write(actual / 'Bloodborne.lnk', b'original redirected shortcut')
        record = {'shortcut': str(alias / 'Bloodborne.lnk')}
        journal = self.workspace / 'shortcut-recovery.json'
        try:
            def get_folder(window, folder_id, token, flags, buffer):
                buffer.value = str(alias)
                return 0
            shell = types.SimpleNamespace(SHGetFolderPathW=mock.Mock(side_effect=get_folder))
            with mock.patch.object(installer.ctypes, 'WinDLL', return_value=shell, create=True):
                self.assertEqual(installer.desktop_folder(), actual)
            installer.save_shortcut(record, journal)
            self.assertEqual(Path(record['shortcut']), link)
            write(link, b'new owned shortcut')
            installer.restore_shortcut(record)
            self.assertEqual(link.read_bytes(), b'original redirected shortcut')
            # The relaxation is only for external shortcuts. Install roots
            # still refuse this same directory redirect.
            with self.assertRaisesRegex(ValueError, 'Linked'):
                installer.regular_path(alias)
        finally:
            self.unlink_directory(alias)

    def test_cloud_shortcut_and_desktop_attributes_allow_backup_and_recovery(self):
        desktop = self.workspace / 'OneDrive cloud desktop'
        desktop.mkdir()
        link = write(desktop / 'Bloodborne.lnk', b'hydrated cloud shortcut')
        original_lstat = Path.lstat
        for tag in (0x9000001A, 0x9000101A, 0x9000F01A, 0x80000021):
            with self.subTest(tag=hex(tag)):
                def cloud_lstat(path, *args, **kwargs):
                    info = original_lstat(path, *args, **kwargs)
                    if path in (desktop, link):
                        return types.SimpleNamespace(st_mode=info.st_mode,
                            st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT, st_reparse_tag=tag)
                    return info
                record = {'shortcut': str(link)}
                journal = self.workspace / ('cloud-shortcut-' + str(tag) + '.json')
                write(link, b'hydrated cloud shortcut')
                with mock.patch.object(Path, 'lstat', cloud_lstat):
                    installer.save_shortcut(record, journal)
                    write(link, b'owned cloud shortcut')
                    installer.restore_shortcut(record)
                    self.assertEqual(link.read_bytes(), b'hydrated cloud shortcut')
                    with self.assertRaisesRegex(ValueError, 'Linked'):
                        installer.regular_path(link)

    def test_shortcut_file_unknown_reparse_or_name_surrogate_is_rejected(self):
        link = write(self.workspace / 'Bloodborne.lnk', b'shortcut bytes')
        original_lstat = Path.lstat
        for tag in (0xA0000003, 0xA000000C, 0x80000042, 0):
            with self.subTest(tag=hex(tag)):
                def linked_lstat(path, *args, **kwargs):
                    info = original_lstat(path, *args, **kwargs)
                    if path == link:
                        return types.SimpleNamespace(st_mode=info.st_mode,
                            st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT, st_reparse_tag=tag)
                    return info
                with mock.patch.object(Path, 'lstat', linked_lstat):
                    with self.assertRaisesRegex(ValueError, 'shortcut file'):
                        installer.shortcut_location(link)
        self.assertEqual(link.read_bytes(), b'shortcut bytes')

    def test_empty_imported_save_root_requires_original_launcher_and_uses_its_user_folder(self):
        json_file(self.profile_source, {'user_dir': '', 'game_dir': 'Z:/game'})
        with self.assertRaisesRegex(ValueError, 'original launcher folder'):
            installer.install(self.source, self.target, profile_source=self.profile_source)
        self.assertFalse(self.target.exists())
        self.install()
        self.assertEqual(installer.read(self.target / 'state/profile/settings.json')['user_dir'],
                         str(self.launcher / 'user'))

    def test_launcher_discovery_uses_legacy_receipt_and_copies_optional_graphics_assets(self):
        json_file(self.source / '.install/receipt.json', {'launcher_root': str(self.launcher)})
        self.assertEqual(installer.find_launcher(self.source, self.target, profile_source=self.profile_source), self.launcher)
        write(self.launcher / 'fsr4_shaders/custom.bin', b'fsr4')
        write(self.launcher / 'fsr4_411/custom.bin', b'fsr411')
        self.install()
        self.assertEqual((self.target / 'state/port/fsr4_shaders/custom.bin').read_bytes(), b'fsr4')
        self.assertEqual((self.target / 'state/port/fsr4_411/custom.bin').read_bytes(), b'fsr411')

    def migration_fixture(self):
        legacy = self.workspace / 'legacy Atlas in another folder'
        self.make_package(legacy, 'legacy package')
        json_file(legacy / '.install/receipt.json', {'launcher_root': str(self.launcher)})
        map_file = write(self.workspace / 'legacy-map.json', b'{"schema":1}')
        features = write(self.workspace / 'legacy-features.json', b'{"schema":1}')
        font = write(self.workspace / 'legacy-font.ttf', b'font')
        receipt = json_file(self.workspace / 'legacy-generated-assets.json', {
            'schema': 1, 'feature_schema': 1,
            'files': {'maps/map.json': installer.sha(map_file), 'maps/features.json': installer.sha(features)}})
        assets.build({'maps/map.json': map_file, 'maps/features.json': features,
                      'maps/generated-assets.json': receipt, 'art/native-font.ttf': font},
                     legacy / 'assets.atlaslite')
        for package in (legacy, self.source):
            manifest = installer.read(package / 'manifest.json')
            manifest['files'].update({'tools/generator.atlaslite': '1' * 64,
                                      'tools/extract_atlas_features.py': '2' * 64})
            if package == legacy:
                manifest.pop('installation_model')
                manifest['asset_pack'] = {'path': 'assets.atlaslite',
                                          'sha256': installer.sha(legacy / 'assets.atlaslite')}
            json_file(package / 'manifest.json', manifest)
        profile = installer.read(self.profile_source)
        profile['atlas_dir'] = str(legacy)
        json_file(self.profile_source, profile)
        self.profile_before = self.profile_source.read_bytes()
        return legacy

    def test_initial_new_folder_discovers_legacy_launcher_and_reuses_maps_from_ordinary_profile(self):
        legacy = self.migration_fixture()
        original_legacy = snapshot(legacy)
        expected_pack = (legacy / 'assets.atlaslite').read_bytes()
        self.assertEqual(installer.find_launcher(self.source, self.target, profile_source=self.profile_source), self.launcher)
        record = self.install()
        self.assertTrue(record['maps_reused'])
        self.assertEqual(record['maps_imported_from'], str(legacy))
        self.assertEqual(record['generator_invocations'], 0)
        self.assertEqual((self.target / 'assets.atlaslite').read_bytes(), expected_pack)
        self.assertEqual(snapshot(legacy), original_legacy)
        self.assert_ordinary_untouched()

    def test_portable_legacy_map_import_rolls_back_exact_manifest_and_original_art_pack(self):
        legacy = self.migration_fixture()
        original_legacy = snapshot(legacy)
        write(self.source / 'assets.atlaslite', b'original package art pack')
        manifest = installer.read(self.source / 'manifest.json')
        digest = installer.sha(self.source / 'assets.atlaslite')
        manifest['asset_pack'] = {'path': 'assets.atlaslite', 'sha256': digest}
        manifest['files']['assets.atlaslite'] = digest
        json_file(self.source / 'manifest.json', manifest)
        original_manifest = (self.source / 'manifest.json').read_bytes()
        original_art = (self.source / 'assets.atlaslite').read_bytes()
        record = installer.install(self.source, self.source, profile_source=self.profile_source, launcher=self.launcher)
        self.assertTrue(record['maps_reused'])
        self.assertEqual((self.source / 'assets.atlaslite').read_bytes(), (legacy / 'assets.atlaslite').read_bytes())
        installer.recover(self.latest_journal(), rollback=True)
        self.assertEqual((self.source / 'manifest.json').read_bytes(), original_manifest)
        self.assertEqual((self.source / 'assets.atlaslite').read_bytes(), original_art)
        self.assertEqual(snapshot(legacy), original_legacy)
        self.assert_ordinary_untouched()

    def test_initial_install_asks_for_original_launcher_even_with_explicit_save_folder(self):
        with mock.patch.object(installer, 'pick_folder', return_value=self.launcher) as picker:
            self.assertEqual(installer.find_launcher(self.source, self.target, profile_source=self.profile_source), self.launcher)
        picker.assert_called_once()
        json_file(self.target / 'state/profile/settings.json', {'user_dir': str(self.saves)})
        with mock.patch.object(installer, 'pick_folder') as picker:
            self.assertIsNone(installer.find_launcher(self.source, self.target, profile_source=self.profile_source))
        picker.assert_not_called()

    def test_update_and_rollback_ignore_generated_game_junctions_preserving_maps_profile_and_game(self):
        legacy = self.migration_fixture()
        self.make_package(self.target, 'old package')
        json_file(self.target / 'state/profile/settings.json', {
            'user_dir': str(self.saves), 'atlas_dir': str(self.target), 'custom_preference': 'keep'})
        pack = (legacy / 'assets.atlaslite').read_bytes()
        write(self.target / 'assets.atlaslite', pack)
        manifest = installer.read(self.target / 'manifest.json')
        manifest['asset_pack'] = installer.read(legacy / 'manifest.json')['asset_pack']
        manifest['files'].update(installer.read(self.source / 'manifest.json')['files'])
        json_file(self.target / 'manifest.json', manifest)
        game = self.workspace / 'real game must not be traversed or copied'
        write(game / 'sce_module/original.bin', b'original game module')
        write(game / 'maps/game-data.bin', b'original game geometry')
        game_before = snapshot(game)
        relative_links = ('state/compiled/native-hash/out/mod-game-fixture/sce_module',
                          'state/out/mod-game-legacy/sce_module',
                          'state/session-assets-stale/game-link')
        for relative in relative_links:
            link = self.target / relative
            link.parent.mkdir(parents=True, exist_ok=True)
            self.link_directory(link, game)
        # Source may itself be an already-run portable package. Its generated
        # links are ignored too, and its state is never copied to the update.
        source_link = self.source / 'state/compiled/portable/out/game-link'
        source_link.parent.mkdir(parents=True, exist_ok=True)
        self.link_directory(source_link, game)
        try:
            result = self.install()
            backup = Path(result['backup'])
            self.assertTrue(result['maps_reused'])
            self.assertEqual((self.target / 'assets.atlaslite').read_bytes(), pack)
            for cache in ('compiled', 'out', 'session-assets-stale'):
                self.assertFalse((self.target / 'state' / cache).exists())
            self.assertEqual(installer.read(self.target / 'state/profile/settings.json')['custom_preference'], 'keep')
            self.assertTrue(all((backup / path).is_dir() for path in relative_links))
            installer.recover(self.latest_journal(), rollback=True)
            self.assertEqual((self.target / 'HuntersAtlas.exe').read_text(), 'old package')
            self.assertEqual((self.target / 'assets.atlaslite').read_bytes(), pack)
            self.assertEqual(installer.read(self.target / 'state/profile/settings.json')['custom_preference'], 'keep')
            for cache in ('compiled', 'out', 'session-assets-stale'):
                self.assertFalse((self.target / 'state' / cache).exists())
            self.assertEqual(snapshot(game), game_before)
            self.assert_ordinary_untouched()
        finally:
            # Only unlink the exact test junctions; never recurse through them.
            for root in (self.target, *self.workspace.glob('Atlas installed.before-owned-*')):
                for relative in relative_links:
                    path = root / relative
                    if path.exists():
                        self.unlink_directory(path)
            if source_link.exists():
                self.unlink_directory(source_link)

    def test_generated_cache_policy_never_allows_links_in_profile_port_or_immutable_code(self):
        game = self.workspace / 'outside content'
        write(game / 'secret.txt', b'not an installation file')
        for relative in ('state/profile/linked', 'state/port/compiled', 'runtime/compiled'):
            with self.subTest(relative=relative):
                link = self.source / relative
                link.parent.mkdir(parents=True, exist_ok=True)
                self.link_directory(link, game)
                try:
                    with self.assertRaisesRegex(ValueError, 'Linked'):
                        self.install()
                finally:
                    self.unlink_directory(link)

    def test_default_builtin_patch_is_not_reapplied_as_an_external_patch_after_migration(self):
        builtin = '<Patch><Metadata Name="Resolution Patch 2560x1080" isEnabled="true"/></Patch>'
        write(self.source / 'runtime/port/patches/Bloodborne.xml', builtin)
        write(self.launcher / 'patches/Bloodborne.xml', builtin)
        settings = installer.read(self.profile_source)
        settings['patches_dir'] = str(self.launcher / 'patches')
        json_file(self.profile_source, settings)
        self.profile_before = self.profile_source.read_bytes()
        self.ordinary_before = snapshot(self.launcher)
        self.install()
        self.assertFalse((self.target / 'state/port/patches/Bloodborne.xml').exists())
        self.assertTrue((self.target / 'state/port/patches/dlc.xml').exists())
        self.assertEqual(installer.read(self.target / 'state/profile/settings.json')['patches_dir'], '')
        self.assertEqual((self.target / 'runtime/port/patches/Bloodborne.xml').read_text(), builtin)
        self.assert_ordinary_untouched()

    def link_directory(self, path, destination):
        if os.name == "nt":
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(path), str(destination)],
                                    capture_output=True, check=False)
            if result.returncode:
                self.skipTest("Junction creation unavailable")
        else:
            path.symlink_to(destination, target_is_directory=True)

    @staticmethod
    def unlink_directory(path):
        path.rmdir() if os.name == "nt" else path.unlink()


if __name__ == "__main__":
    unittest.main()
