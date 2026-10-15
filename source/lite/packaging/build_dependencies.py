#!/usr/bin/env python3
"""Build a path-portable Atlas Lite dependency template from a pristine release.

The generated JSON pins the ordinary launcher's Python entry point and scripts,
direct bin EXE/DLL files, the stock executable hash as a launcher variant, and
the launcher-private interpreter runtime. The executable stays out of the
common files table so an installer can verify the pristine tree before binding
its copied launcher as Bloodborne.stock.exe. Patches, FSR shader models, and
Python cache files are excluded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys
import zipfile
from typing import Any


DEPENDENCIES_ID = "hunters-atlas-lite-dependencies"
DEFAULT_ASSET_URL = (
    "https://github.com/Supermedo/bloodborne_pc/releases/download/"
    "windows-v1.7.2/"
    "Bloodborne-Windows.zip"
)
DEFAULT_RELEASE_PAGE = "https://github.com/Supermedo/bloodborne_pc/releases/tag/windows-v1.7.2"
STOCK_SOURCE_NAME = "Bloodborne.exe"
RUNTIME_DIR = "_internal"
CHUNK_SIZE = 1024 * 1024


class BuildError(RuntimeError):
    """Raised when source provenance or the exact dependency selection fails."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_reparse(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())


def _relative(path: Path, root: Path) -> str:
    return PurePosixPath(*path.relative_to(root).parts).as_posix()


def _walk_regular_files(directory: Path) -> list[Path]:
    if not directory.is_dir() or _is_reparse(directory):
        raise BuildError(f"Required source directory is missing or redirected: {directory.name}")
    result: list[Path] = []
    for current, dirnames, filenames in os.walk(directory, topdown=True, followlinks=False):
        current_path = Path(current)
        kept_dirs: list[str] = []
        for name in dirnames:
            child = current_path / name
            if name.casefold() == "__pycache__":
                continue
            if _is_reparse(child):
                raise BuildError(f"Reparse directory is not allowed in dependency tree: {name}")
            kept_dirs.append(name)
        dirnames[:] = kept_dirs
        for name in filenames:
            path = current_path / name
            if _is_reparse(path):
                raise BuildError(f"Reparse file is not allowed in dependency tree: {name}")
            if path.is_file():
                result.append(path)
    return sorted(result, key=lambda item: _relative(item, directory.parent).casefold())


def _selected_source_files(pristine: Path) -> tuple[dict[str, Path], dict[str, Path]]:
    """Return package common files and exact private-runtime files."""
    common: dict[str, Path] = {}
    run_script = pristine / "run.py"
    if not run_script.is_file() or _is_reparse(run_script):
        raise BuildError("Pristine root must contain a regular run.py.")
    common["run.py"] = run_script

    for path in _walk_regular_files(pristine / "scripts"):
        if path.suffix.casefold() == ".py":
            common[_relative(path, pristine)] = path

    bin_dir = pristine / "bin"
    if not bin_dir.is_dir() or _is_reparse(bin_dir):
        raise BuildError("Pristine root must contain a regular bin directory.")
    unsupported_bin_files: list[str] = []
    for path in sorted(bin_dir.iterdir(), key=lambda item: item.name.casefold()):
        if _is_reparse(path):
            raise BuildError(f"Reparse entry is not allowed in bin: {path.name}")
        if not path.is_file():
            continue
        if path.suffix.casefold() in {".dll", ".exe"}:
            common[_relative(path, pristine)] = path
        else:
            unsupported_bin_files.append(path.name)
    if unsupported_bin_files:
        names = ", ".join(sorted(unsupported_bin_files, key=str.casefold))
        raise BuildError(f"Unclassified direct bin data needs an explicit release rule: {names}")

    launcher = pristine / STOCK_SOURCE_NAME
    if not launcher.is_file() or _is_reparse(launcher):
        raise BuildError(f"Pristine root must contain {STOCK_SOURCE_NAME}.")
    runtime_root = pristine / RUNTIME_DIR
    runtime_paths = _walk_regular_files(runtime_root)
    if not runtime_paths:
        raise BuildError("Pristine launcher runtime directory is empty.")
    runtime = {_relative(path, pristine): path for path in runtime_paths}
    return dict(sorted(common.items(), key=lambda item: item[0].casefold())), dict(
        sorted(runtime.items(), key=lambda item: item[0].casefold())
    )


def _zip_root(archive: zipfile.ZipFile) -> str:
    matches: set[str] = set()
    for name in archive.namelist():
        normalized = name.replace("\\", "/").rstrip("/")
        if PurePosixPath(normalized).name.casefold() == "run.py":
            matches.add(str(PurePosixPath(normalized).parent))
    if len(matches) != 1:
        raise BuildError("Official ZIP must contain exactly one root run.py to establish its extracted root.")
    return next(iter(matches))


def _zip_hash(archive: zipfile.ZipFile, member: str) -> str:
    try:
        info = archive.getinfo(member)
    except KeyError as error:
        raise BuildError(f"Selected file is absent from the official ZIP: {member}") from error
    digest = hashlib.sha256()
    with archive.open(info, "r") as stream:
        for block in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify_archive_members(
    archive: zipfile.ZipFile,
    zip_root: str,
    selected: dict[str, Path],
    pristine_root: Path,
) -> None:
    by_casefold = {name.replace("\\", "/").casefold(): name for name in archive.namelist()}
    for relative, path in selected.items():
        member = f"{zip_root}/{relative}"
        stored_name = by_casefold.get(member.casefold())
        if stored_name is None:
            raise BuildError(f"Pristine file is not present in the official ZIP: {relative}")
        expected = sha256_file(path)
        actual = _zip_hash(archive, stored_name)
        if expected != actual:
            raise BuildError(f"Pristine tree differs from official ZIP for {relative}.")

    runtime_prefix = f"{zip_root}/{RUNTIME_DIR}/".casefold()
    archive_runtime: set[str] = set()
    for name in archive.namelist():
        normalized = name.replace("\\", "/")
        folded = normalized.casefold()
        if folded.startswith(runtime_prefix) and not normalized.endswith("/"):
            relative = normalized[len(f"{zip_root}/{RUNTIME_DIR}/"):]
            if "__pycache__" not in PurePosixPath(relative).parts:
                archive_runtime.add(f"{RUNTIME_DIR}/{relative}".casefold())
    pristine_runtime = {name.casefold() for name in selected if name.casefold().startswith("_internal/")}
    if archive_runtime != pristine_runtime:
        missing = sorted(archive_runtime - pristine_runtime)
        extra = sorted(pristine_runtime - archive_runtime)
        raise BuildError(
            "Pristine _internal file set does not exactly match the official ZIP "
            f"(missing={missing[:5]}, extra={extra[:5]})."
        )


def _working_comparison(
    working_root: Path,
    common: dict[str, Path],
    runtime: dict[str, Path],
    launcher: Path,
) -> dict[str, Any]:
    if not working_root.is_dir():
        raise BuildError("Working-port comparison root does not exist.")
    expected = {**common, **runtime, STOCK_SOURCE_NAME: launcher}
    same: list[str] = []
    different: list[dict[str, str]] = []
    missing: list[str] = []
    compared_paths: dict[str, Path] = {}
    for relative, source_path in expected.items():
        candidate = working_root.joinpath(*PurePosixPath(relative).parts)
        if relative == STOCK_SOURCE_NAME and (working_root / "Bloodborne.stock.exe").is_file():
            candidate = working_root / "Bloodborne.stock.exe"
        if not candidate.is_file() or _is_reparse(candidate):
            missing.append(relative)
            continue
        pristine_hash = sha256_file(source_path)
        working_hash = sha256_file(candidate)
        compared_paths[relative] = candidate
        if pristine_hash == working_hash:
            same.append(relative)
        else:
            different.append({
                "path": relative,
                "pristine_sha256": pristine_hash,
                "working_sha256": working_hash,
            })
    return {
        "working_root": ".",
        "selected_launcher_name": "Bloodborne.stock.exe" if (working_root / "Bloodborne.stock.exe").is_file()
        else STOCK_SOURCE_NAME,
        "same": sorted(same, key=str.casefold),
        "different": sorted(different, key=lambda row: row["path"].casefold()),
        "missing": sorted(missing, key=str.casefold),
        "counts": {"same": len(same), "different": len(different), "missing": len(missing)},
        "interpretation": "Hash comparison only; differences are reported without treating the working port as release provenance.",
    }


def build_template(
    pristine_root: Path,
    official_zip: Path,
    working_root: Path,
    *,
    asset_url: str = DEFAULT_ASSET_URL,
    release_page: str = DEFAULT_RELEASE_PAGE,
) -> dict[str, Any]:
    pristine = pristine_root.resolve(strict=True)
    if _is_reparse(pristine_root):
        raise BuildError("Pristine root must not be a symlink or junction.")
    official_zip = official_zip.resolve(strict=True)
    if not asset_url.startswith("https://") or not release_page.startswith("https://"):
        raise BuildError("Official asset and release provenance must use HTTPS URLs.")

    common, runtime = _selected_source_files(pristine)
    launcher = pristine / STOCK_SOURCE_NAME
    with zipfile.ZipFile(official_zip, "r") as archive:
        root_in_zip = _zip_root(archive)
        _verify_archive_members(archive, root_in_zip, {**common, **runtime, STOCK_SOURCE_NAME: launcher}, pristine)

    common_hashes = {name: sha256_file(path) for name, path in common.items()}
    runtime_hashes = {name: sha256_file(path) for name, path in runtime.items()}
    launcher_hash = sha256_file(launcher)
    output: dict[str, Any] = {
        "schema": 1,
        "id": DEPENDENCIES_ID,
        "ordinary_port": {
            "root": ".",
            "files": common_hashes,
            "roles": {"run_script": "run.py"},
            "launcher_path": STOCK_SOURCE_NAME,
            "launcher_variants": {
                launcher_hash: {
                    "path": STOCK_SOURCE_NAME,
                    "runtime_dir": RUNTIME_DIR,
                    "files": runtime_hashes,
                }
            },
        },
        "provenance": {
            "project": "Supermedo/bloodborne_pc",
            "release_page_url": release_page,
            "asset_url": asset_url,
            "asset_filename": official_zip.name,
            "asset_sha256": sha256_file(official_zip),
            "archive_root": root_in_zip,
            "archive_launcher_path": f"{root_in_zip}/{STOCK_SOURCE_NAME}",
            "template_launcher_path": STOCK_SOURCE_NAME,
            "installer_bound_launcher_path": "Bloodborne.stock.exe",
            "verification": "Every pinned ordinary file and the complete _internal file set matched this official ZIP by SHA-256.",
        },
        "working_port_comparison": _working_comparison(
            working_root.resolve(strict=True), common, runtime, launcher
        ),
        "selection_policy": {
            "included": ["run.py", "scripts/**/*.py", "bin/*.(dll|exe)", "launcher variant Bloodborne.exe", "_internal/**/*"],
            "excluded": ["patches/**", "fsr4_shaders/**", "__pycache__/**", "scripts non-Python files", "bin non-DLL/EXE files"],
            "excluded_bin_files_found": [],
        },
    }
    rendered = json.dumps(output, ensure_ascii=False)
    if "D:\\\\" in rendered or "C:\\\\Users\\\\" in rendered:
        raise BuildError("Generated template unexpectedly contains a personal absolute path.")
    return output


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pristine-root", required=True, type=Path)
    parser.add_argument("--official-zip", required=True, type=Path)
    parser.add_argument("--working-root", required=True, type=Path)
    parser.add_argument("--asset-url", default=DEFAULT_ASSET_URL)
    parser.add_argument("--release-page", default=DEFAULT_RELEASE_PAGE)
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("dependency-template.json"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = build_template(
            args.pristine_root,
            args.official_zip,
            args.working_root,
            asset_url=args.asset_url,
            release_page=args.release_page,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (BuildError, OSError, zipfile.BadZipFile, RuntimeError, ValueError) as error:
        print(f"dependency-template: {error}", file=sys.stderr)
        return 2
    counts = result["working_port_comparison"]["counts"]
    variant = next(iter(result["ordinary_port"]["launcher_variants"].values()))
    print(json.dumps({
        "output": args.output.name,
        "asset_sha256": result["provenance"]["asset_sha256"],
        "pinned_common_files": len(result["ordinary_port"]["files"]),
        "launcher_runtime_files": len(variant["files"]),
        "working_port_comparison": counts,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
