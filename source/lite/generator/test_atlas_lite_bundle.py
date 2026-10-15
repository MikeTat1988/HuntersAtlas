from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

import atlas_lite_bundle as bundle


class BundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="atlas-lite-test-")
        self.root = Path(self.temp.name)
        self.tools = self.root / "tools"
        (self.tools / "_internal").mkdir(parents=True)
        (self.tools / bundle.ENTRYPOINT).write_bytes(b"test executable")
        (self.tools / "_internal" / "library.bin").write_bytes(b"runtime payload")
        self.pack = self.root / "generator.atlaslite"
        bundle.build_bundle(self.tools, self.pack)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_verified_payload_runs_and_cleans_up(self) -> None:
        observed: dict[str, object] = {}

        class Process:
            def __init__(self, command: list[str], **kwargs: object):
                observed["command"] = command
                observed["exe_exists"] = Path(command[0]).is_file()
                observed["cwd_files"] = sorted(p.name for p in Path(command[0]).parent.iterdir())

            def wait(self, timeout: int | None = None) -> int:
                return 0

        self.assertEqual(
            bundle.run_bundle(self.pack, self.root, self.root / "output", temp_parent=self.root, popen_factory=Process),
            0,
        )
        self.assertTrue(observed["exe_exists"])
        self.assertIn("--staging-dir", observed["command"])
        self.assertEqual(list(self.root.glob("atlas-lite-prep-*")), [])

    def test_verify_extracts_realistic_tree_runs_version_probe_and_cleans(self) -> None:
        observed: dict[str, object] = {}
        observed["probes"] = []

        def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            observed["exists"] = Path(command[0]).is_file()
            observed["probes"].append(command[1:])
            if command[1:] == ["--self-test-imports"]:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout=json.dumps({"self_test_imports": "pass", "loaded_native_modules": []}) + "\n",
                    stderr="",
                )
            return subprocess.CompletedProcess(command, 0, stdout="1.0.0\n", stderr="")

        result = bundle.verify_bundle(self.pack, temp_parent=self.root, self_test_imports=True, run_factory=run)
        self.assertTrue(observed["exists"])
        self.assertEqual(observed["probes"], [["--version"], ["--self-test-imports"]])
        self.assertEqual(result["version_output"], "1.0.0")
        self.assertEqual(result["self_test_imports"]["self_test_imports"], "pass")
        self.assertEqual(list(self.root.glob("atlas-lite-verify-*")), [])

    def test_archive_path_traversal_is_rejected(self) -> None:
        payload = b"escape"
        manifest = {
            "format": bundle.FORMAT_VERSION,
            "entrypoint": bundle.ENTRYPOINT,
            "expanded_bytes": len(payload),
            "files": {"../../escape.exe": {"sha256": hashlib.sha256(payload).hexdigest(), "size": len(payload)}},
        }
        malicious = self.root / "malicious.zip"
        with zipfile.ZipFile(malicious, "w") as archive:
            archive.writestr(bundle.MANIFEST_NAME, json.dumps(manifest))
            archive.writestr("payload/../../escape.exe", payload)
        with zipfile.ZipFile(malicious) as archive:
            with self.assertRaisesRegex(ValueError, "Unsafe bundle path"):
                bundle._read_manifest(archive)
        self.assertFalse((self.root.parent / "escape.exe").exists())

    def test_cancellation_terminates_child_and_cleans_temp_runtime(self) -> None:
        observed: dict[str, object] = {}

        class Process:
            def __init__(self, command: list[str], **kwargs: object):
                observed["exe_exists"] = Path(command[0]).is_file()
                self.wait_count = 0

            def wait(self, timeout: int | None = None) -> int:
                self.wait_count += 1
                if self.wait_count == 1:
                    raise KeyboardInterrupt
                return 130

            def terminate(self) -> None:
                observed["terminated"] = True

            def kill(self) -> None:
                observed["killed"] = True

        with self.assertRaises(KeyboardInterrupt):
            bundle.run_bundle(self.pack, self.root, self.root / "output", temp_parent=self.root, popen_factory=Process)
        self.assertTrue(observed["exe_exists"])
        self.assertTrue(observed["terminated"])
        self.assertEqual(list(self.root.glob("atlas-lite-prep-*")), [])

    def test_payload_hash_mismatch_fails_before_launch_and_cleans_temp(self) -> None:
        corrupt = self.root / "corrupt.zip"
        with zipfile.ZipFile(self.pack) as original, zipfile.ZipFile(corrupt, "w", zipfile.ZIP_DEFLATED) as output:
            for info in original.infolist():
                data = original.read(info.filename)
                if info.filename == "payload/_internal/library.bin":
                    data = b"corrupted payload"
                output.writestr(info.filename, data)
        launched = False

        def popen(command: list[str], **kwargs: object):  # pragma: no cover - must not be called
            nonlocal launched
            launched = True
            raise AssertionError("corrupt bundle must not launch")

        with self.assertRaisesRegex(ValueError, "failed SHA-256 verification"):
            bundle.run_bundle(corrupt, self.root, self.root / "output", temp_parent=self.root, popen_factory=popen)
        self.assertFalse(launched)
        self.assertEqual(list(self.root.glob("atlas-lite-prep-*")), [])

    def test_lzma_bundle_round_trips_through_verified_extraction(self) -> None:
        lzma_pack = self.root / "generator-lzma.atlaslite"
        result = bundle.build_bundle(self.tools, lzma_pack, compression="lzma")
        self.assertEqual(result["compression"], "lzma")
        observed: list[bool] = []

        def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            observed.append(Path(command[0]).is_file())
            return subprocess.CompletedProcess(command, 0, stdout="1.0.0\n", stderr="")

        self.assertEqual(bundle.verify_bundle(lzma_pack, temp_parent=self.root, run_factory=run)["returncode"], 0)
        self.assertEqual(observed, [True])
        self.assertEqual(list(self.root.glob("atlas-lite-verify-*")), [])


if __name__ == "__main__":
    unittest.main()
