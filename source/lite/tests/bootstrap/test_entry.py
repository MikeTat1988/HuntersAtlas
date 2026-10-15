import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


SOURCE = Path(__file__).resolve().parents[2] / "bootstrap" / "entry.py"
SPEC = importlib.util.spec_from_file_location("atlas_lite_bootstrap", SOURCE)
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


def write(path: Path, content: bytes | str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
    return path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "Atlas Lite"
        self.base = Path(self.temp.name) / "ordinary port"
        self.root.mkdir(parents=True)
        self.base.mkdir(parents=True)
        own = {
            "bootstrap/entry.py": write(self.root / "bootstrap/entry.py", SOURCE.read_bytes()),
            "bootstrap/run_lite.py": write(self.root / "bootstrap/run_lite.py",
                                             (SOURCE.parent / "run_lite.py").read_bytes()),
            "bin/bb-probe.exe": write(self.root / "bin/bb-probe.exe", b"probe"),
            "maps/m01.json": write(self.root / "maps/m01.json", b"{}"),
            "settings/config.json": write(self.root / "settings/config.json", "{}"),
            "maps/catalog.json": write(self.root / "maps/catalog.json", "{}"),
            "art/font.ttf": write(self.root / "art/font.ttf", b"font"),
        }
        self.root.joinpath("maps").mkdir(exist_ok=True)
        base_files = {
            "run.py": write(self.base / "run.py", b"run"),
            "scripts/prepare.py": write(self.base / "scripts/prepare.py", b"prepare"),
            "bin/base.dll": write(self.base / "bin/base.dll", b"dll"),
            "patches/dlc-enabled.xml": write(
                self.base / "patches/dlc-enabled.xml",
                "<Patch><Metadata><Name>Old Hunters DLC</Name></Metadata></Patch>"),
        }
        stock_launcher = write(self.base / "Bloodborne.exe", b"stock launcher")
        stock_runtime = write(self.base / "_internal/python314.dll", b"stock runtime")
        adapter_launcher = write(self.base / "Bloodborne-adapter.tmp", b"adapter launcher")
        adapter_runtime = write(self.base / "_atlas_internal/python312.dll", b"adapter runtime")
        variants = {
            digest(stock_launcher): {"path": "Bloodborne.exe", "runtime_dir": "_internal",
                                    "files": {"_internal/python314.dll": digest(stock_runtime)}},
            digest(adapter_launcher): {"path": "Bloodborne.exe", "runtime_dir": "_atlas_internal",
                                      "files": {"_atlas_internal/python312.dll": digest(adapter_runtime)}},
        }
        receipt = {
            "schema": 1,
            "source_sha256": digest(base_files["run.py"]),
            "copy_sha256": digest(own["bootstrap/run_lite.py"]),
        }
        own["bootstrap/run_lite-source.json"] = write(
            self.root / "bootstrap/run_lite-source.json", json.dumps(receipt))
        manifest = {
            "schema": 1,
            "id": bootstrap.MANIFEST_ID,
            "files": {name: digest(path) for name, path in own.items()},
            "paths": {
                "probe": "bin/bb-probe.exe", "maps": "maps", "config": "settings/config.json",
                "art": "art", "catalog": "maps/catalog.json", "font": "art/font.ttf",
            },
        }
        write(self.root / "manifest.json", json.dumps(manifest))
        dependencies = {
            "schema": 1,
            "id": bootstrap.DEPENDENCIES_ID,
            "ordinary_port": {
                "root": str(self.base),
                "files": {name: digest(path) for name, path in base_files.items()},
                "roles": {"run_script": "run.py"},
                "launcher_variants": variants,
            },
        }
        write(self.root / "dependencies.json", json.dumps(dependencies))
        write(self.root / "bootstrap/config.json", json.dumps({
            "schema": 1, "edition": "Lite", "manifest": "manifest.json",
            "runner": "bootstrap/run_lite.py", "dependencies": "dependencies.json",
            "state_dir": "state", "qa_enabled": False,
        }))
        self.contract = bootstrap.load_contract(self.root)
        (self.base / "Bloodborne-adapter.tmp").unlink()

    def tearDown(self):
        self.temp.cleanup()

    def test_contract_hashes_owned_and_external_files(self):
        self.assertEqual(self.contract["launcher"], (self.base / "Bloodborne.exe").resolve())
        self.assertEqual(self.contract["run_script"], (self.base / "run.py").resolve())
        self.assertEqual(self.contract["runner"], (self.root / "bootstrap/run_lite.py").resolve())
        self.assertEqual(self.contract["state_root"], (self.root / "state").resolve())
        self.assertEqual(len(self.contract["base_bin_paths"]), 1)

    def test_selects_only_exact_launcher_hash_variants(self):
        adapter = write(self.base / "Bloodborne.exe", b"adapter launcher")
        self.assertEqual(bootstrap.load_contract(self.root)["launcher_hash"], digest(adapter))
        write(self.base / "Bloodborne.exe", b"unknown launcher")
        with self.assertRaisesRegex(bootstrap.BootstrapError, "does not match a supported"):
            bootstrap.load_contract(self.root)

    def test_packed_asset_paths_are_staged_inside_state_for_the_session_only(self):
        pack = write(self.root / "assets.atlaslite", b"pack")
        manager_text = (
            "from contextlib import contextmanager\n"
            "import shutil\n"
            "import tempfile\n"
            "from pathlib import Path\n"
            "@contextmanager\n"
            "def materialize(contract):\n"
            "    contract['state_root'].mkdir(parents=True, exist_ok=True)\n"
            "    root = Path(tempfile.mkdtemp(prefix='session-assets-test', dir=contract['state_root']))\n"
            "    try:\n"
            "        (root / 'maps').mkdir()\n"
            "        (root / 'art').mkdir()\n"
            "        (root / 'bin').mkdir()\n"
            "        shutil.copyfile(contract['paths']['probe'], root / 'bin/bb-probe.exe')\n"
            "        (root / 'maps/catalog.json').write_text('{}', encoding='utf-8')\n"
            "        (root / 'art/font.ttf').write_bytes(b'font')\n"
            "        yield {'maps': root / 'maps', 'art': root / 'art',\n"
            "               'catalog': root / 'maps/catalog.json', 'font': root / 'art/font.ttf',\n"
            "               'probe': root / 'bin/bb-probe.exe'}\n"
            "    finally:\n"
            "        shutil.rmtree(root)\n"
        )
        manager = write(self.root / "bootstrap/assets.py", manager_text)
        manifest_path = self.root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"]["assets.atlaslite"] = digest(pack)
        manifest["files"]["bootstrap/assets.py"] = digest(manager)
        manifest["asset_pack"] = {"path": "assets.atlaslite", "sha256": digest(pack)}
        manifest["paths"].update({
            "maps": "state/runtime-assets/maps", "art": "state/runtime-assets/art",
            "catalog": "state/runtime-assets/maps/catalog.json",
            "font": "state/runtime-assets/art/native-font.ttf",
        })
        write(manifest_path, json.dumps(manifest))
        packed = bootstrap.load_contract(self.root)
        with bootstrap._materialized_asset_paths(packed) as paths:
            checked = bootstrap._validated_materialized_paths(packed, paths)
            session_root = checked["maps"].parent
            self.assertTrue(session_root.name.startswith("session-assets-"))
            self.assertEqual(checked["font"].read_bytes(), b"font")
            self.assertEqual(checked["probe"].read_bytes(), b"probe")
            checked["probe"].write_bytes(b"tampered probe")
            with self.assertRaisesRegex(bootstrap.BootstrapError, "probe SHA-256"):
                bootstrap._validated_materialized_paths(packed, paths)
            self.assertTrue(session_root.exists())
        self.assertFalse(session_root.exists())

        class Completed:
            stdout = io.BytesIO()

            @staticmethod
            def wait():
                return 0

        with mock.patch.object(bootstrap.subprocess, "Popen", return_value=Completed()) as launch, mock.patch.object(bootstrap, "validate_game_source"):
            self.assertEqual(bootstrap._launch(packed, {}), 0)
        launch_env = launch.call_args.kwargs["env"]
        self.assertIn("session-assets-", launch_env["BB_PROBE"])
        self.assertTrue(launch_env["BB_PROBE"].endswith("bin\\bb-probe.exe"))
        self.assertIn("session-assets-", launch_env["BB_MAP_DIR"])

    def test_rejects_tampered_external_dependency(self):
        write(self.base / "bin/base.dll", b"modified")
        with self.assertRaisesRegex(bootstrap.BootstrapError, "SHA-256 check failed"):
            bootstrap.load_contract(self.root)

    def test_rejects_unlisted_dll_in_a_search_directory(self):
        write(self.base / "bin/unlisted.dll", b"not pinned")
        with self.assertRaisesRegex(bootstrap.BootstrapError, "unverified DLL"):
            bootstrap.load_contract(self.root)

    def test_python_generator_uses_the_verified_frozen_script_role(self):
        generator = self.root / "tools/prepare.py"
        generator.parent.mkdir(parents=True, exist_ok=True)
        generator.write_text("pass\n", encoding="utf-8")
        self.contract["generator"] = generator
        self.assertEqual(bootstrap._generator_command(self.contract),
                         [str(self.contract["launcher"]), "--script", str(generator)])
        self.contract["generator"] = self.root / "tools/generate.exe"
        self.assertEqual(bootstrap._generator_command(self.contract), [str(self.root / "tools/generate.exe")])

    def test_environment_clears_inherited_atlas_hooks_and_pins_b_paths(self):
        inherited = {
            "PATH": "C:\\msys64\\clang64\\bin;C:\\custom",
            "BB_PROBE": "C:\\old-atlas\\probe.exe",
            "BB_MAP_DIR": "C:\\old-atlas\\maps",
            "BB_MAP_QA": "1",
            "BB_ATLAS_ENABLED": "1",
            "BB_MAP_TEST_CONTROL": "C:\\old-atlas\\control.txt",
            "BB_PAD_FILE": "C:\\old-atlas\\pad.txt",
            "BB_DUMP_DIR": "C:\\old-atlas\\captures",
            "SystemRoot": "C:\\Windows",
        }
        profile = {
            "game_dir": "D:\\Bloodborne\\CUSA03173",
            "language": "8", "voice_language": "en", "fps_mode": "60",
            "frame_cap": "60", "fullscreen": True, "hdr": True,
            "atlas_enabled": False,
            "extra_env": "BB_PROBE=C:\\spoof.exe BB_MAP_QA=1 CUSTOM_SETTING=ok",
        }
        env = bootstrap.game_environment(self.contract, profile, inherited)
        self.assertEqual(env["BB_PROBE"], str((self.root / "bin/bb-probe.exe").resolve()))
        self.assertEqual(env["BB_MAP_DIR"], str((self.root / "maps").resolve()))
        self.assertEqual(env["BB_ATLAS_ENABLED"], "0")
        self.assertEqual(env["BB_MAP_QA"], "0")
        self.assertNotIn("BB_MAP_TEST_CONTROL", env)
        self.assertNotIn("BB_PAD_FILE", env)
        self.assertNotIn("BB_DUMP_DIR", env)
        self.assertEqual(env["BB_LITE_PORT_DIR"], str(self.base.resolve()))
        self.assertEqual(env["BB_LITE_ENTRY"], str((self.root / "bootstrap/entry.py").resolve()))
        self.assertIn(".disabled-msys2-fallback", env["MSYS2_ROOT"])
        self.assertEqual(env["BB_LANGUAGE"], "8")
        self.assertEqual(env["BB_FPS"], "60")
        self.assertEqual(env["CUSTOM_SETTING"], "ok")
        self.assertNotIn("clang64", env["PATH"].lower())
        self.assertNotIn("BB_MAP_QA=1", str(bootstrap._redacted_env(env)))

    def test_enabled_dlc_patch_resolves_from_verified_base_with_private_patch_config(self):
        dlc_dir = self.root / "dlc"
        dlc_dir.mkdir()
        patch_config = self.root / "state" / "patches.json"
        selected_patch = "dlc-enabled.xml/Old Hunters DLC"
        write(patch_config, json.dumps({"enabled": [selected_patch], "disabled": []}))
        profile = {"dlc_dir": str(dlc_dir)}

        env = bootstrap.game_environment(self.contract, profile, inherited={"SystemRoot": "C:\\Windows"})
        selection = json.loads(Path(env["BB_PATCHES_CONFIG"]).read_text(encoding="utf-8"))
        self.assertEqual(selection, {"enabled": [selected_patch], "disabled": []})
        selected_filename = selection["enabled"][0].split("/", 1)[0]
        definition = Path(env["BB_PATCHES_DIR"]) / selected_filename
        configured = Path(env["BB_PATCHES_CONFIG"])
        self.assertTrue(definition.is_file(), "enabled DLC patch XML must resolve from the verified base")
        self.assertEqual(configured.resolve(), patch_config.resolve())
        self.assertEqual(Path(env["BB_PATCHES_DIR"]).resolve(), (self.base / "patches").resolve())
        self.assertEqual(env["BB_DLC_DIR"], str(dlc_dir))

        custom_dir = self.root / "custom-patches"
        custom_dir.mkdir()
        custom_xml = write(custom_dir / "custom.xml", "<patch />")
        custom_env = bootstrap.game_environment(
            self.contract, {**profile, "patches_dir": str(custom_dir)},
            inherited={"SystemRoot": "C:\\Windows"})
        self.assertEqual(Path(custom_env["BB_PATCHES_DIR"]).resolve(), custom_dir.resolve())
        self.assertTrue((Path(custom_env["BB_PATCHES_DIR"]) / custom_xml.name).is_file())
        self.assertEqual(Path(custom_env["BB_PATCHES_CONFIG"]).resolve(), patch_config.resolve())

    def test_qa_timeout_requires_explicit_package_gate(self):
        with self.assertRaisesRegex(bootstrap.BootstrapError, "qa_enabled=true"):
            bootstrap.game_environment(self.contract, {}, {}, qa_timeout=10)
        self.contract["config"]["qa_enabled"] = True
        env = bootstrap.game_environment(self.contract, {}, {}, qa_timeout=10)
        self.assertEqual(env["BB_TIMEOUT"], "10")
        self.assertEqual(env["BB_ATLAS_QA"], "1")

    def test_qa_control_hooks_are_confined_to_explicit_b_state_directory(self):
        self.contract["config"]["qa_enabled"] = True
        qa_dir = self.contract["state_root"] / "qa" / "scenario-1"
        env = bootstrap.game_environment(self.contract, {}, {}, qa_control_dir=qa_dir)
        self.assertEqual(env["BB_ATLAS_QA"], "1")
        self.assertEqual(env["BB_MAP_QA"], "1")
        self.assertEqual(env["BB_MAP_TEST_CONTROL"], str(qa_dir / "control.txt"))
        self.assertEqual(env["BB_MAP_TEST_TRACE"], str(qa_dir / "trace.json"))
        with self.assertRaisesRegex(bootstrap.BootstrapError, "inside Lite state/qa"):
            bootstrap.game_environment(self.contract, {}, {}, qa_control_dir=self.root / "outside")

    def test_online_preferences_keep_the_hunters_dream_bridge_behavior(self):
        env = bootstrap.game_environment(self.contract, {
            "online": True, "online_pool": "huntersdream", "online_server": "srv.example:31313",
            "online_webapi": "", "online_community": "https://thehuntersdream.com/path",
            "online_npid": "player-id", "online_password": "secret", "bridge_live_map": False,
        }, {})
        self.assertEqual(env["BB_SHADNET_SERVER"], "srv.example:31313")
        self.assertEqual(env["BB_SHADNET_WEBAPI"], "http://srv.example:31315")
        self.assertEqual(env["BB_COMMUNITY_SERVER"], "https://thehuntersdream.com")
        self.assertEqual(env["BB_BRIDGE"], "1")
        self.assertEqual(env["BB_BRIDGE_LIVE_MAP"], "0")
        self.assertEqual(env["BB_SHADNET_NPID"], "")
        self.assertEqual(env["BB_SHADNET_PASSWORD"], "")

    def test_profile_import_is_copy_only_once_and_routes_user_state(self):
        source = Path(self.temp.name) / "production" / "settings.json"
        raw = json.dumps({"game_dir": "D:\\game", "language": "8", "user_dir": "D:\\A\\user",
                          "online_password": "secret", "atlas_enabled": True}).encode()
        write(source, raw)
        source_hash = digest(source)
        destination = bootstrap.import_profile_once(self.contract["state_root"], source)
        imported = json.loads(destination.read_text(encoding="utf-8"))
        receipt = json.loads(destination.with_name("import-receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(imported["game_dir"], "D:\\game")
        self.assertEqual(imported["language"], "8")
        self.assertEqual(imported["user_dir"], str(self.contract["state_root"] / "user"))
        self.assertEqual(receipt["source_sha256"], source_hash)
        self.assertEqual(digest(source), source_hash)
        write(source, b"changed later")
        self.assertEqual(bootstrap.import_profile_once(self.contract["state_root"], source), destination)
        self.assertEqual(json.loads(destination.read_text(encoding="utf-8"))["language"], "8")

    def test_session_lock_blocks_second_session_and_releases(self):
        lock_path = self.contract["state_root"] / "session.lock"
        with bootstrap.SessionLock(lock_path):
            with self.assertRaisesRegex(bootstrap.BootstrapError, "active session"):
                with bootstrap.SessionLock(lock_path):
                    pass
        self.assertFalse(lock_path.exists())

    def test_pid_liveness_probe_does_not_signal_a_live_child(self):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            deadline = time.monotonic() + 5
            while child.poll() is not None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertIsNone(child.poll(), "child exited before the liveness check")
            self.assertTrue(bootstrap._pid_alive(child.pid))
            self.assertIsNone(child.poll(), "liveness probe unexpectedly terminated the child")
        finally:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=5)

    def test_global_game_guard_refuses_known_probe_processes_without_signalling_them(self):
        enumerator = lambda: [("bb-probe.exe", 4321), ("other.exe", 9876)]
        with self.assertRaisesRegex(bootstrap.BootstrapError, r"bb-probe.exe \(PID 4321\)"):
            bootstrap.ensure_no_game_processes(enumerator=enumerator)
        bootstrap.ensure_no_game_processes(enumerator=lambda: [("other.exe", 9876)])

    def test_selected_game_fingerprint_is_checked_before_launch(self):
        game = self.root / "game"
        executable = write(game / "eboot.bin", b"supported fixture")
        with mock.patch.object(bootstrap, "SUPPORTED_GAME_SHA256", digest(executable)):
            bootstrap.validate_game_source({"manifest": {}}, {"game_dir": str(game)})
            write(executable, b"different game")
            with self.assertRaisesRegex(bootstrap.BootstrapError, "Unsupported Bloodborne executable"):
                bootstrap.validate_game_source({"manifest": {}}, {"game_dir": str(game)})

    @unittest.skipUnless(os.name == "nt", "Toolhelp process snapshot is Windows-specific")
    def test_toolhelp_snapshot_is_read_only_and_contains_this_process(self):
        names = bootstrap._windows_process_names()
        self.assertIn((Path(sys.executable).name, os.getpid()), names)

    def test_dry_run_redacts_password_values(self):
        values = {"BB_SHADNET_PASSWORD": "do-not-print", "BB_SHADNET_NPID": "account-id", "BB_FPS": "60"}
        redacted = bootstrap._redacted_env(values)
        self.assertEqual(redacted["BB_SHADNET_PASSWORD"], "<redacted>")
        self.assertEqual(redacted["BB_SHADNET_NPID"], "<redacted>")
        self.assertNotIn("do-not-print", json.dumps(redacted))
        self.assertNotIn("account-id", json.dumps(redacted))
        output = bootstrap._redact_output(b"login account-id password do-not-print\n", values)
        self.assertNotIn(b"account-id", output)
        self.assertNotIn(b"do-not-print", output)


if __name__ == "__main__":
    unittest.main()
