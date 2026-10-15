"""Focused tests for the official launcher dependency inventory builder."""
from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import build_dependencies as builder


class BuildDependenciesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.pristine = self.base / "pristine"
        self.working = self.base / "working"
        self.archive = self.base / "official.zip"
        for directory in (
            self.pristine / "scripts" / "nested",
            self.pristine / "scripts" / "__pycache__",
            self.pristine / "bin",
            self.pristine / "_internal" / "PIL",
            self.pristine / "patches",
            self.pristine / "fsr4_shaders",
            self.working / "scripts" / "nested",
            self.working / "bin",
            self.working / "_internal" / "PIL",
        ):
            directory.mkdir(parents=True, exist_ok=True)
        files = {
            "run.py": b"# official runner\n",
            "scripts/launch.py": b"print('launch')\n",
            "scripts/nested/helper.py": b"VALUE = 1\n",
            "scripts/notes.txt": b"exclude me\n",
            "scripts/__pycache__/ignored.pyc": b"cache",
            "bin/bb-probe.exe": b"MZ-probe",
            "bin/lib.dll": b"MZ-library",
            "_internal/python314.dll": b"MZ-python",
            "_internal/PIL/_imaging.pyd": b"MZ-pyd",
            "patches/redzone.json": b"exclude me",
            "fsr4_shaders/model.bin": b"exclude me",
            "Bloodborne.exe": b"MZ-stock-launcher",
        }
        for relative, content in files.items():
            path = self.pristine / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        for relative in (
            "run.py", "scripts/launch.py", "scripts/nested/helper.py", "bin/bb-probe.exe",
            "bin/lib.dll", "_internal/python314.dll", "_internal/PIL/_imaging.pyd",
        ):
            path = self.pristine / relative
            target = self.working / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
        (self.working / "Bloodborne.stock.exe").write_bytes((self.pristine / "Bloodborne.exe").read_bytes())
        with zipfile.ZipFile(self.archive, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(self.pristine.rglob("*")):
                if path.is_file():
                    archive.write(path, "bbport-windows/" + path.relative_to(self.pristine).as_posix())

    def test_builds_portable_template_with_exact_allowlist_and_comparison(self) -> None:
        result = builder.build_template(self.pristine, self.archive, self.working)
        ordinary = result["ordinary_port"]
        self.assertEqual(ordinary["root"], ".")
        self.assertEqual(ordinary["launcher_path"], "Bloodborne.exe")
        self.assertEqual(ordinary["roles"]["run_script"], "run.py")
        self.assertIn("scripts/nested/helper.py", ordinary["files"])
        self.assertIn("bin/lib.dll", ordinary["files"])
        self.assertNotIn("Bloodborne.exe", ordinary["files"])
        self.assertNotIn("Bloodborne.stock.exe", ordinary["files"])
        self.assertEqual(set(ordinary["roles"]), {"run_script"})
        self.assertNotIn("scripts/notes.txt", ordinary["files"])
        self.assertNotIn("patches/redzone.json", ordinary["files"])
        self.assertNotIn("fsr4_shaders/model.bin", ordinary["files"])
        self.assertNotIn("scripts/__pycache__/ignored.pyc", ordinary["files"])
        variant = next(iter(ordinary["launcher_variants"].values()))
        self.assertEqual(variant["path"], "Bloodborne.exe")
        self.assertEqual(variant["runtime_dir"], "_internal")
        self.assertEqual(set(variant["files"]), {"_internal/python314.dll", "_internal/PIL/_imaging.pyd"})
        self.assertEqual(result["working_port_comparison"]["counts"], {"same": 8, "different": 0, "missing": 0})
        serialized = json.dumps(result)
        self.assertNotIn(str(self.pristine), serialized)
        self.assertNotIn(str(self.working), serialized)
        self.assertEqual(result["provenance"]["asset_filename"], "official.zip")
        self.assertEqual(result["provenance"]["archive_root"], "bbport-windows")
        self.assertIn("/download/windows-v1.7.2/", result["provenance"]["asset_url"])
        self.assertIn("/tag/windows-v1.7.2", result["provenance"]["release_page_url"])

    def test_rejects_pristine_file_that_does_not_match_official_archive(self) -> None:
        (self.pristine / "run.py").write_text("modified", encoding="utf-8")
        with self.assertRaisesRegex(builder.BuildError, "differs from official ZIP"):
            builder.build_template(self.pristine, self.archive, self.working)

    def test_rejects_unclassified_direct_bin_data(self) -> None:
        (self.pristine / "bin" / "codec.dat").write_bytes(b"data")
        with self.assertRaisesRegex(builder.BuildError, "Unclassified direct bin data"):
            builder.build_template(self.pristine, self.archive, self.working)


if __name__ == "__main__":
    unittest.main()
