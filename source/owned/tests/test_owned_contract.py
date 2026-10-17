"""Trust-boundary tests for the independent in-game Atlas installation."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


BOOTSTRAP = Path(__file__).resolve().parents[2] / "lite" / "bootstrap"


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


core = module("owned_test_entry", BOOTSTRAP / "entry.py")
owned = module("owned_test_contract", BOOTSTRAP / "owned_contract.py")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class OwnedContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="Atlas contract Ω ")
        self.root = Path(self.temp.name) / "Atlas owned"
        self.external = Path(self.temp.name) / "Upstream launcher"
        self.root.mkdir()
        self.external.mkdir()
        self.root = self.root.resolve()
        self.external = self.external.resolve()
        (self.external / "Bloodborne.exe").write_bytes(b"upstream launcher unrelated to Atlas")
        self.fixed = {}
        for name in (
            "bootstrap/entry.py", "bootstrap/owned_contract.py", "bootstrap/run_lite.py",
            "bootstrap/assets.py", "runtime/port/run.py", "runtime/port/scripts/prepare.py",
            "runtime/port/bin/base.dll", "runtime/python/python.exe", "runtime/python/pythonw.exe",
            "runtime/python/python310.dll", "runtime/python/Lib/__future__.py",
            "integration/ui/bbport_launcher_win.py", "bin/bb-probe.exe",
            "bin/bb-gpu-capabilities.exe", "bin/render.dll", "tools/prepare.py",
            "assets.atlaslite",
        ):
            self.write(name, name.encode())
        self.write("settings/settings.ini", b"[map]\n", fixed=False)
        self.config = {"schema": 1, "edition": "Atlas", "installation_model": owned.MODEL,
                       "dependencies": "dependencies.json", "manifest": "manifest.json",
                       "state_dir": "state"}
        compatibility = {"adapter_protocol": 1, "upstream_release": owned.RELEASE,
                         "upstream_commit": owned.COMMIT}
        self.deps = {"schema": 1, "id": core.DEPENDENCIES_ID,
                     "compatibility": compatibility.copy(),
                     "ordinary_port": {"root": "runtime/port", "roles": {"run_script": "run.py"}},
                     "owned_runtime": {"schema": 1, "python": "runtime/python/python.exe",
                                       "pythonw": "runtime/python/pythonw.exe",
                                       "ui": "integration/ui/bbport_launcher_win.py",
                                       "upstream_release": owned.RELEASE}}
        self.manifest = {"schema": 1, "id": core.MANIFEST_ID,
                         "installation_model": owned.MODEL,
                         "compatibility": compatibility.copy(),
                         "game_executables": [core.SUPPORTED_GAME_SHA256],
                         "generator": "tools/prepare.py",
                         "asset_pack": {"path": "assets.atlaslite", "sha256": sha(self.root / "assets.atlaslite")},
                         "paths": {"probe": "bin/bb-probe.exe", "config": "settings/settings.ini",
                                   "maps": "state/runtime-assets/maps", "art": "state/runtime-assets/art",
                                   "catalog": "state/runtime-assets/maps/catalog.json",
                                   "font": "state/runtime-assets/art/native-font.ttf"}}
        self.proof = dict(compatibility, runtime_sha256=sha(self.root / "bin/bb-probe.exe"))
        self.save_metadata()

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, value, fixed=True):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
        if fixed:
            self.fixed[name] = path
        return path

    def save_metadata(self):
        receipt = {"schema": 1, "source_sha256": sha(self.root / "runtime/port/run.py"),
                   "copy_sha256": sha(self.root / "bootstrap/run_lite.py")}
        self.write("bootstrap/run_lite-source.json", json.dumps(receipt).encode())
        self.deps["ordinary_port"]["files"] = {
            name.removeprefix("runtime/port/"): sha(path) for name, path in self.fixed.items()
            if name.startswith("runtime/port/")}
        self.write("dependencies.json", json.dumps(self.deps).encode())
        self.write("bootstrap/config.json", json.dumps(self.config).encode())
        self.write("native-build.json", json.dumps(self.proof).encode())
        self.manifest["files"] = {name: sha(path) for name, path in self.fixed.items()}
        self.write("manifest.json", json.dumps(self.manifest).encode(), fixed=False)

    def load(self):
        return owned.load_contract(self.root, self.config, core)

    def test_external_launcher_upgrade_and_removal_cannot_change_owned_runtime(self):
        before = self.load()
        (self.external / "Bloodborne.exe").write_bytes(b"incompatible future launcher")
        self.assertEqual(self.load()["launcher_hash"], before["launcher_hash"])
        shutil.rmtree(self.external)
        after = self.load()
        self.assertEqual(after["launcher"], self.root / "runtime/python/python.exe")
        self.assertEqual(after["base_root"], self.root / "runtime/port")
        self.assertTrue(after["owned_runtime"])
        self.assertEqual(after["paths"]["maps"], self.root / "state/runtime-assets/maps")

    def test_owned_python_and_dll_modification_are_rejected(self):
        for name in ("runtime/python/Lib/__future__.py", "runtime/port/bin/base.dll", "bin/render.dll"):
            with self.subTest(name=name):
                path = self.root / name
                original = path.read_bytes()
                path.write_bytes(b"modified")
                with self.assertRaisesRegex(core.BootstrapError, "SHA-256"):
                    self.load()
                path.write_bytes(original)

    def test_unlisted_loadable_and_nonloadable_runtime_files_are_rejected(self):
        for name in ("runtime/python/malicious.pyd", "runtime/port/scripts/extra.py", "bin/extra.dll",
                     "integration/ui/extra.py", "bootstrap/__pycache__/entry.cpython-310.pyc"):
            with self.subTest(name=name):
                path = self.write(name, b"unlisted", fixed=False)
                with self.assertRaisesRegex(core.BootstrapError, "unverified file"):
                    self.load()
                path.unlink()

    def test_external_root_and_relative_traversal_are_rejected_even_when_metadata_is_rehashed(self):
        for root in (str(self.external), "../../Upstream launcher", "runtime/port/../port"):
            with self.subTest(root=root):
                self.deps["ordinary_port"]["root"] = root
                self.save_metadata()
                with self.assertRaisesRegex(core.BootstrapError, "ordinary_port.root"):
                    self.load()

    def test_declared_owned_python_cannot_point_at_external_or_other_packaged_executable(self):
        for value in (str(self.external / "Bloodborne.exe"), "../outside.exe", "bin/bb-probe.exe"):
            self.deps["owned_runtime"]["python"] = value
            self.save_metadata()
            with self.assertRaisesRegex(core.BootstrapError, "owned_runtime.python"):
                self.load()

    def test_missing_gpu_helper_is_rejected_before_game_start(self):
        (self.root / "bin/bb-gpu-capabilities.exe").unlink()
        with self.assertRaises(core.BootstrapError):
            self.load()

    def test_native_runtime_must_match_proof_even_if_manifest_is_rehashed(self):
        self.write("bin/bb-probe.exe", b"different native runtime")
        self.save_metadata()
        with self.assertRaisesRegex(core.BootstrapError, "native build digest"):
            self.load()

    def test_mixed_or_unknown_native_identity_is_rejected(self):
        self.proof["upstream_commit"] = "0" * 40
        self.save_metadata()
        with self.assertRaisesRegex(core.BootstrapError, "compatibility identity"):
            self.load()

    def test_unsupported_schemas_and_game_declarations_are_rejected(self):
        self.config["installation_model"] = "owned-runtime-v2"
        self.save_metadata()
        with self.assertRaisesRegex(core.BootstrapError, "installation schema"):
            self.load()
        self.config["installation_model"] = owned.MODEL
        self.manifest["game_executables"] = ["0" * 64]
        self.save_metadata()
        with self.assertRaisesRegex(core.BootstrapError, "game fingerprint"):
            self.load()

    def test_dependency_allowlist_cannot_omit_a_manifest_pinned_port_file(self):
        del self.deps["ordinary_port"]["files"]["bin/base.dll"]
        self.write("dependencies.json", json.dumps(self.deps).encode())
        self.manifest["files"]["dependencies.json"] = sha(self.root / "dependencies.json")
        self.write("manifest.json", json.dumps(self.manifest).encode(), fixed=False)
        with self.assertRaisesRegex(core.BootstrapError, "exactly match"):
            self.load()

    def test_packed_assets_cannot_escape_or_enter_immutable_trees(self):
        for value in ("../outside/maps", "runtime/port/maps", "state/maps"):
            self.manifest["paths"]["maps"] = value
            self.save_metadata()
            with self.assertRaises(core.BootstrapError):
                self.load()

    def test_mutable_state_does_not_invalidate_owned_runtime(self):
        self.write("state/profile/settings.json", b'{"atlas_enabled":true}', fixed=False)
        self.write("state/user/savedata/save.bin", b"copied QA save", fixed=False)
        self.write("settings/settings.ini", b"[map]\nfog=false\n", fixed=False)
        self.assertTrue(self.load()["owned_runtime"])

    def test_junction_or_symlink_in_owned_dependency_is_rejected(self):
        source = self.root / "runtime/port/scripts"
        outside = Path(self.temp.name) / "redirected scripts"
        source.rename(outside)
        if os.name == "nt":
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(source), str(outside)],
                                    capture_output=True, check=False)
            if result.returncode:
                outside.rename(source)
                self.skipTest("Junction creation unavailable")
        else:
            source.symlink_to(outside, target_is_directory=True)
        try:
            with self.assertRaisesRegex(core.BootstrapError, "reparse point"):
                self.load()
        finally:
            if os.name == "nt":
                source.rmdir()
            else:
                source.unlink()
            outside.rename(source)


if __name__ == "__main__":
    unittest.main()
