import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "integration" / "ui"
sys.path.insert(0, str(UI))
import atlas_addon

GAME_SHA = "d" * 64


def load_ui_module():
    path = UI / "bbport_launcher_win.py"
    spec = importlib.util.spec_from_file_location("atlas_lite_ui_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


class LiteLauncherBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.package = Path(self.temp.name) / "Hunter's Atlas"
        (self.package / "bootstrap").mkdir(parents=True)
        (self.package / "bin").mkdir()
        (self.package / "tools").mkdir()
        (self.package / "settings").mkdir()
        probe = self.package / "bin" / "bb-probe.exe"
        probe.write_bytes(b"verified probe fixture")
        probe_hash = hashlib.sha256(probe.read_bytes()).hexdigest()
        game_hash = GAME_SHA
        generator = self.package / "tools" / "prepare.py"
        generator.write_text("# test generator\n", encoding="utf-8")
        import zipfile
        pack = self.package / "assets.atlaslite"
        generated = {
            "schema": 1,
            "version": 1,
            "game_eboot_sha256": game_hash,
            "files": {"maps/atlas.json": "a" * 64, "maps/catalog.json": "b" * 64},
        }
        with zipfile.ZipFile(pack, "w", compression=zipfile.ZIP_LZMA) as archive:
            archive.writestr("maps/generated-assets.json", json.dumps(generated))
        pack_hash = hashlib.sha256(pack.read_bytes()).hexdigest()
        entry_source = '''
import hashlib, json
from pathlib import Path
SUPPORTED_GAME_SHA256 = "''' + GAME_SHA + '''"
def load_contract(root):
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    probe = root / "bin" / "bb-probe.exe"
    if hashlib.sha256(probe.read_bytes()).hexdigest() != manifest["files"]["bin/bb-probe.exe"]:
        raise ValueError("probe hash mismatch")
    pack = root / "assets.atlaslite"
    if hashlib.sha256(pack.read_bytes()).hexdigest() != manifest["files"]["assets.atlaslite"]:
        raise ValueError("asset pack hash mismatch")
    return {"manifest": manifest, "paths": {
        "probe": probe,
        "maps": root / "state" / "session-assets-fixture" / "maps",
        "config": root / "settings" / "settings.ini",
        "art": root / "state" / "session-assets-fixture" / "art",
        "catalog": root / "state" / "session-assets-fixture" / "maps" / "catalog.json",
        "font": root / "state" / "session-assets-fixture" / "art" / "native-font.ttf",
    }, "generator": root / "tools" / "prepare.py",
       "asset_pack": {"path": pack, "sha256": manifest["files"]["assets.atlaslite"]}}
'''
        entry_path = self.package / "bootstrap" / "entry.py"
        entry_path.write_text(entry_source, encoding="utf-8")
        (self.package / "manifest.json").write_text(json.dumps({
            "schema": 1,
            "id": "hunters-atlas-lite",
            "version": "fixture",
            "game_executables": [GAME_SHA],
            "files": {
                "bin/bb-probe.exe": probe_hash,
                "assets.atlaslite": pack_hash,
                "bootstrap/entry.py": hashlib.sha256(entry_path.read_bytes()).hexdigest(),
            },
        }), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_lite_resolver_delegates_validation_and_checks_game_fingerprint(self):
        package = atlas_addon.inspect_package(self.package, game_sha256=GAME_SHA)
        self.assertEqual(package.manifest["id"], "hunters-atlas-lite")
        self.assertTrue(package.generated_ready)
        self.assertIsNotNone(package.lite_contract)
        self.assertEqual(package.paths["probe"], (self.package / "bin" / "bb-probe.exe").resolve())
        with self.assertRaisesRegex(atlas_addon.AtlasManifestError, "does not support"):
            atlas_addon.inspect_package(self.package, game_sha256="wrong-game-sha")

    def test_lite_resolver_rejects_non_lite_and_altered_payload(self):
        manifest_path = self.package / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["id"] = "hunters-atlas"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(atlas_addon.AtlasManifestError, "Expected the verified"):
            atlas_addon.inspect_package(self.package, game_sha256=GAME_SHA)
        manifest["id"] = "hunters-atlas-lite"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        (self.package / "bin" / "bb-probe.exe").write_bytes(b"altered")
        with self.assertRaisesRegex(atlas_addon.AtlasManifestError, "Could not verify"):
            atlas_addon.inspect_package(self.package, game_sha256=GAME_SHA)

    def test_lite_resolver_rejects_entry_changed_after_manifest_creation(self):
        entry_path = self.package / "bootstrap" / "entry.py"
        entry_path.write_text(entry_path.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
        with self.assertRaisesRegex(atlas_addon.AtlasManifestError, "entry failed its SHA-256"):
            atlas_addon.inspect_package(self.package, game_sha256="supported-game-sha")

    def test_lite_resolver_checks_pack_hash_before_reading_metadata(self):
        pack = self.package / "assets.atlaslite"
        pack.write_bytes(pack.read_bytes() + b"altered")
        with self.assertRaisesRegex(atlas_addon.AtlasManifestError, "Could not verify the Hunter's Atlas package"):
            atlas_addon.inspect_package(self.package, game_sha256=GAME_SHA)

    def test_lite_readiness_uses_packed_metadata_for_selected_game(self):
        package = atlas_addon.inspect_package(self.package, game_sha256=GAME_SHA)
        self.assertTrue(package.generated_ready)
        self.assertEqual(package.paths["generator"], (self.package / "tools" / "prepare.py").resolve())
        self.assertFalse((self.package / "state").exists(), "inspection must not expand the asset archive")

        import zipfile
        pack = self.package / "assets.atlaslite"
        with zipfile.ZipFile(pack, "w", compression=zipfile.ZIP_LZMA) as archive:
            archive.writestr("maps/generated-assets.json", json.dumps({
                "schema": 1, "version": 1, "game_eboot_sha256": "e" * 64,
                "files": {"maps/atlas.json": "a" * 64, "maps/catalog.json": "b" * 64},
            }))
        manifest_path = self.package / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"]["assets.atlaslite"] = hashlib.sha256(pack.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        package = atlas_addon.inspect_package(self.package, game_sha256=GAME_SHA)
        self.assertFalse(package.generated_ready)
        self.assertIn("different game build", package.generated_message)
        self.assertFalse((self.package / "state").exists(), "mismatched inspection must stay read-only")
        with self.assertRaisesRegex(atlas_addon.AtlasManifestError, "different game build"):
            atlas_addon.atlas_environment({}, enabled=True, package=package)

    def test_lite_environment_clears_stale_map_hooks_and_keeps_launcher_preferences(self):
        package = atlas_addon.inspect_package(self.package, game_sha256=GAME_SHA)
        inherited = {
            "BB_PROBE": "old-probe.exe",
            "BB_ATLAS_QA": "1",
            "BB_MAP_DIR": "old-map-dir",
            "BB_MAP_TEST_TRACE": "old-trace.json",
            "BB_USER_DIR": "production-user",
            "BB_DLC_DIR": "production-dlc",
            "BB_PATCHES_DIR": "verified-patches",
            "BB_PATCHES_CONFIG": "production-patches.json",
        }
        enabled = atlas_addon.atlas_environment(inherited, enabled=True, package=package)
        self.assertEqual(Path(enabled["BB_LITE_PACKAGE"]), self.package.resolve())
        self.assertEqual(enabled["BB_ATLAS_ENABLED"], "1")
        for key in ("BB_PROBE", "BB_ATLAS_QA", "BB_MAP_DIR", "BB_MAP_TEST_TRACE"):
            self.assertNotIn(key, enabled)
        for key in ("BB_USER_DIR", "BB_DLC_DIR", "BB_PATCHES_DIR", "BB_PATCHES_CONFIG"):
            self.assertEqual(enabled[key], inherited[key])
        disabled = atlas_addon.atlas_environment(enabled, enabled=False)
        self.assertEqual(disabled["BB_ATLAS_ENABLED"], "0")
        self.assertNotIn("BB_LITE_PACKAGE", disabled)

    def test_play_command_routes_only_enabled_lite_to_bootstrap(self):
        launcher = load_ui_module()
        launcher.FROZEN = True
        entry = str((self.package / "bootstrap" / "integrated_play.py").resolve())
        self.assertEqual(launcher.run_command({"BB_LITE_PACKAGE": str(self.package)}),
                         [sys.executable, "--script", entry])
        self.assertEqual(launcher.run_command({"BB_ATLAS_ENABLED": "0"}),
                         [sys.executable, "--run"])
        launcher.FROZEN = False
        self.assertEqual(launcher.run_command({"BB_LITE_PACKAGE": str(self.package)}),
                         [sys.executable, entry])

    def test_lite_prepare_routes_through_frozen_launcher_script_cli(self):
        launcher = load_ui_module()
        package = atlas_addon.inspect_package(self.package, game_sha256=GAME_SHA)
        launcher.FROZEN = True
        self.assertEqual(launcher.atlas_prepare_command(package, Path("game")), [
            sys.executable, "--script", str((self.package / "tools" / "prepare.py").resolve()),
            "--game-dir", "game", "--output-dir", str(self.package.resolve()), "--headless",
        ])

    def test_stock_update_is_blocked_while_lite_is_installed_even_when_disabled(self):
        from types import SimpleNamespace
        launcher = load_ui_module()
        launcher.PORT_DIR = Path(self.temp.name)
        (launcher.PORT_DIR / 'atlas-lite-install.json').write_text('{}', encoding='utf-8')
        window = SimpleNamespace(process=None, messagebox=mock.Mock(), var=mock.Mock())
        window.var.return_value.get.return_value = False
        launcher.Launcher.install_update(window, '9.9.9', 'https://example.invalid/update.zip', '')
        window.messagebox.showwarning.assert_called_once()
        self.assertIn('Uninstall', window.messagebox.showwarning.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
