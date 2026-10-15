from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent
ASSETS_SOURCE = SOURCE.parent / "bootstrap" / "assets.py"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_assets():
    spec = importlib.util.spec_from_file_location("lite_test_assets", ASSETS_SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class SessionLock:
    def __init__(self, path: Path):
        self.path = path

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("locked", encoding="utf-8")
        return self

    def __exit__(self, *_args):
        self.path.unlink(missing_ok=True)


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="lite-prepare-test-", dir=HERE)
        self.temp = Path(self.temporary.name)
        self.root = self.temp / "package"
        self.tools = self.root / "tools"
        self.bootstrap_dir = self.root / "bootstrap"
        self.tools.mkdir(parents=True)
        self.bootstrap_dir.mkdir()
        self.game = self.temp / "Image0"
        (self.game / "dvdroot_ps4").mkdir(parents=True)
        (self.root / "manifest.json").write_text("{}\n", encoding="utf-8")
        (self.tools / "prepare.py").write_bytes((SOURCE / "prepare.py").read_bytes())
        (self.tools / "atlas_lite_bundle.py").write_text("# pinned test helper\n", encoding="utf-8")
        (self.tools / "generator.atlaslite").write_bytes(b"frozen generator bundle")
        (self.bootstrap_dir / "assets.py").write_bytes(ASSETS_SOURCE.read_bytes())
        (self.bootstrap_dir / "entry.py").write_text("# entry is injected in unit tests\n", encoding="utf-8")
        self.assets = load_assets()
        self.pack = self.root / "assets.atlaslite"
        self._write_old_pack(prepared=True)
        self.manifest_path = self.root / "manifest.json"
        self.manifest_path.write_text(json.dumps({
            "schema": 1,
            "files": {"assets.atlaslite": digest(self.pack)},
            "asset_pack": {"path": "assets.atlaslite", "sha256": digest(self.pack)},
            "generator": "tools/prepare.py",
        }, indent=2) + "\n", encoding="utf-8")
        self.script = self._load_prepare()

    def tearDown(self):
        self.temporary.cleanup()

    def _write_old_pack(self, *, prepared: bool):
        old = self.temp / "old"
        old.mkdir()
        (old / "art").mkdir()
        (old / "art" / "background.bbra").write_bytes(b"release-owned background")
        (old / "art" / "native-font.ttf").write_bytes(b"stale personal font")
        if prepared:
            (old / "maps").mkdir()
            (old / "maps" / "m21_00_00_00.json").write_text('{"source":"old-personal-map"}', encoding="utf-8")
            old_maps = {"maps/m21_00_00_00.json": old / "maps" / "m21_00_00_00.json"}
            (old / "maps" / "generated-assets.json").write_text(json.dumps({
                "files": {name: digest(path) for name, path in old_maps.items()}
            }), encoding="utf-8")
        source_files = {
            path.relative_to(old).as_posix(): path
            for path in old.rglob("*") if path.is_file()
        }
        self.assets.build(source_files, self.pack)

    def _load_prepare(self):
        spec = importlib.util.spec_from_file_location("lite_test_prepare", self.tools / "prepare.py")
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        return module

    def _contract(self):
        own_files = {
            path.relative_to(self.root).as_posix().casefold(): path.resolve()
            for path in (self.tools / "prepare.py", self.tools / "atlas_lite_bundle.py",
                         self.tools / "generator.atlaslite", self.bootstrap_dir / "assets.py")
        }
        return {
            "root": self.root.resolve(),
            "state_root": (self.root / "state").resolve(),
            "own_files": own_files,
            "config": {"manifest": "manifest.json"},
            "generator": (self.tools / "prepare.py").resolve(),
            "asset_pack": {"path": self.pack.resolve(), "manager": (self.bootstrap_dir / "assets.py").resolve()},
        }

    def _dependencies(self, generator_result=0, *, cancel_file: Path | None = None):
        contract = self._contract()
        assets = self.assets

        def fake_run_bundle(bundle_path, game_dir, output_dir, **kwargs):
            self.assertEqual(bundle_path, self.tools / "generator.atlaslite")
            self.assertEqual(game_dir, self.game)
            maps = output_dir / "maps"
            art = output_dir / "art"
            maps.mkdir(parents=True)
            art.mkdir()
            (maps / "atlas.json").write_text('{"maps":[{"id":"new-map"}]}', encoding="utf-8")
            (maps / "catalog.json").write_text('{"new-map":{"regions":[]}}', encoding="utf-8")
            (maps / "new-map.json").write_text('{"source":"current-game"}', encoding="utf-8")
            (art / "native-font.ttf").write_bytes(b"fresh-game-native-font")
            files = {f"maps/{path.name}": digest(path) for path in maps.glob("*.json")}
            files["art/native-font.ttf"] = digest(art / "native-font.ttf")
            (maps / "generated-assets.json").write_text(json.dumps({"files": files}), encoding="utf-8")
            if cancel_file is not None:
                cancel_file.write_text("cancel", encoding="utf-8")
            return generator_result

        entry = SimpleNamespace(SessionLock=SessionLock, load_contract=lambda root: contract)
        bundle = SimpleNamespace(__file__=str(self.tools / "atlas_lite_bundle.py"), run_bundle=fake_run_bundle)

        def module_loader(name, path):
            if name == "lite_prepare_entry":
                return entry
            if name == "lite_prepare_assets":
                return assets
            if name == "lite_prepare_bundle":
                return bundle
            raise AssertionError(name)

        return module_loader, lambda _entry, _root: contract

    def _run(self, generator_result=0, *, cancel_file: Path | None = None):
        module_loader, contract_loader = self._dependencies(generator_result, cancel_file=cancel_file)
        return self.script._prepare(self.game, self.root, cancel_file=cancel_file,
                                    notify=lambda _record: None, module_loader=module_loader,
                                    contract_loader=contract_loader)

    def test_rebuild_uses_only_fresh_maps_and_keeps_release_art(self):
        result = self._run()
        verify = self.temp / "verified"
        verify.mkdir()
        content = self.assets.unpack(self.pack, verify)
        self.assertTrue(content["prepared"])
        self.assertIn("maps/new-map.json", content["files"])
        self.assertNotIn("maps/m21_00_00_00.json", content["files"])
        self.assertEqual((verify / "maps" / "new-map.json").read_text(encoding="utf-8"), '{"source":"current-game"}')
        self.assertEqual((verify / "art" / "native-font.ttf").read_bytes(), b"fresh-game-native-font")
        self.assertEqual((verify / "art" / "background.bbra").read_bytes(), b"release-owned background")
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["files"]["assets.atlaslite"], digest(self.pack))
        self.assertEqual(manifest["asset_pack"]["sha256"], digest(self.pack))
        self.assertEqual(result["asset_pack_sha256"], digest(self.pack))
        self.assertFalse(list((self.root / "state").glob("preparation-work-*")))

    def test_generation_failure_preserves_pack_and_manifest(self):
        old_pack = self.pack.read_bytes()
        old_manifest = self.manifest_path.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "previous asset pack is unchanged"):
            self._run(generator_result=7)
        self.assertEqual(self.pack.read_bytes(), old_pack)
        self.assertEqual(self.manifest_path.read_bytes(), old_manifest)
        self.assertFalse(list((self.root / "state").glob("preparation-work-*")))

    def test_cancelled_generation_preserves_pack_and_manifest(self):
        old_pack = self.pack.read_bytes()
        old_manifest = self.manifest_path.read_bytes()
        cancel_file = self.temp / "cancel.request"
        with self.assertRaisesRegex(self.script.PreparationCancelled, "cancelled"):
            self._run(cancel_file=cancel_file)
        self.assertEqual(self.pack.read_bytes(), old_pack)
        self.assertEqual(self.manifest_path.read_bytes(), old_manifest)
        self.assertFalse(list((self.root / "state").glob("preparation-work-*")))

    def test_failed_postcommit_contract_validation_rolls_back_both_files(self):
        before_pack = self.temp / "assets.before"
        before_manifest = self.temp / "manifest.before"
        before_pack.write_bytes(b"old pack")
        before_manifest.write_bytes(b"old manifest")
        candidate_pack = self.temp / "assets.new"
        candidate_manifest = self.temp / "manifest.new"
        candidate_pack.write_bytes(b"new pack")
        candidate_manifest.write_bytes(b"new manifest")
        rollback = self.temp / "rollback"
        with self.assertRaisesRegex(RuntimeError, "validation refused"):
            self.script._commit_pair(candidate_pack, candidate_manifest, before_pack, before_manifest,
                                     rollback, lambda: False,
                                     lambda: (_ for _ in ()).throw(RuntimeError("validation refused")))
        self.assertEqual(before_pack.read_bytes(), b"old pack")
        self.assertEqual(before_manifest.read_bytes(), b"old manifest")

    def test_cancellation_between_pair_replacements_rolls_back(self):
        old_pack = self.temp / "assets.before"
        old_manifest = self.temp / "manifest.before"
        old_pack.write_bytes(b"old pack")
        old_manifest.write_bytes(b"old manifest")
        candidate_pack = self.temp / "assets.new"
        candidate_manifest = self.temp / "manifest.new"
        candidate_pack.write_bytes(b"new pack")
        candidate_manifest.write_bytes(b"new manifest")
        polls = iter((False, True))
        with self.assertRaises(self.script.PreparationCancelled):
            self.script._commit_pair(candidate_pack, candidate_manifest, old_pack, old_manifest,
                                     self.temp / "rollback", lambda: next(polls), lambda: None)
        self.assertEqual(old_pack.read_bytes(), b"old pack")
        self.assertEqual(old_manifest.read_bytes(), b"old manifest")

    def test_cancel_file_terminates_frozen_child_and_drains_log(self):
        cancel_file = self.temp / "child.cancel"
        log_path = self.temp / "child.log"
        factory = self.script._logged_popen_factory(log_path, cancel_file)
        process = factory([sys.executable, "-c", "import time; print('child-started', flush=True); time.sleep(30)"])
        timer = threading.Timer(0.4, lambda: cancel_file.write_text("cancel", encoding="utf-8"))
        timer.start()
        try:
            result = process.wait(timeout=8)
        finally:
            timer.cancel()
            process.terminate()
        self.assertNotEqual(result, 0)
        self.assertIn("child-started", log_path.read_text(encoding="utf-8"))

    def test_output_root_must_be_package_root(self):
        module_loader, contract_loader = self._dependencies()
        with self.assertRaisesRegex(ValueError, "installed Atlas package root"):
            self.script._prepare(self.game, self.temp, notify=lambda _record: None,
                                 module_loader=module_loader, contract_loader=contract_loader)


if __name__ == "__main__":
    unittest.main()
