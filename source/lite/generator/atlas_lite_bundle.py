"""Build and run the self-contained, compressed Atlas preparation bundle.

The bundle carries the existing frozen CPython 3.12 generator unchanged. At
runtime the wrapper needs only the standard library; it verifies every payload
file while extracting into a temporary directory and removes that directory
when generation exits or is cancelled.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable, Sequence

FORMAT_VERSION = 1
MANIFEST_NAME = "manifest.json"
PAYLOAD_ROOT = "payload/"
ENTRYPOINT = "generate_atlas.exe"
LITE_ENTRYPOINT = "generate_atlas_lite.exe"
ENTRYPOINTS = {ENTRYPOINT, LITE_ENTRYPOINT}
CHUNK_SIZE = 1024 * 1024


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_SIZE):
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


def _safe_relative(name: str) -> PurePosixPath:
    if not name or "\\" in name or name.startswith("/") or ":" in name:
        raise ValueError(f"Unsafe bundle path: {name!r}")
    relative = PurePosixPath(name)
    if any(part in ("", ".", "..") for part in relative.parts):
        raise ValueError(f"Unsafe bundle path: {name!r}")
    return relative


def build_bundle(source_tools: Path, destination: Path, compression: str = "deflate") -> dict[str, object]:
    """Compress the exact frozen executable tree and write its hash manifest."""
    codecs = {"deflate": zipfile.ZIP_DEFLATED, "lzma": zipfile.ZIP_LZMA}
    if compression not in codecs:
        raise ValueError("compression must be 'deflate' or 'lzma'")
    source_tools = source_tools.resolve(strict=True)
    exe = next((source_tools / name for name in (ENTRYPOINT, LITE_ENTRYPOINT) if (source_tools / name).is_file()), None)
    internal = source_tools / "_internal"
    if exe is None or not internal.is_dir():
        raise ValueError("source-tools must contain a supported generator executable and _internal/")
    entrypoint = exe.name

    files = [exe, *sorted(p for p in internal.rglob("*") if p.is_file())]
    records: dict[str, dict[str, object]] = {}
    for path in files:
        relative = path.relative_to(source_tools).as_posix()
        _safe_relative(relative)
        digest, size = _sha256_file(path)
        records[relative] = {"sha256": digest, "size": size}

    manifest = {
        "format": FORMAT_VERSION,
        "entrypoint": entrypoint,
        "files": records,
        "expanded_bytes": sum(int(row["size"]) for row in records.values()),
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".building")
    try:
        with zipfile.ZipFile(temporary, "w", compression=codecs[compression], compresslevel=9, allowZip64=True) as archive:
            archive.writestr(MANIFEST_NAME, json.dumps(manifest, sort_keys=True, separators=(",", ":")))
            for path in files:
                relative = path.relative_to(source_tools).as_posix()
                archive.write(path, PAYLOAD_ROOT + relative)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()

    packed_bytes = destination.stat().st_size
    return {
        "bundle": str(destination),
        "files": len(records),
        "expanded_bytes": manifest["expanded_bytes"],
        "packed_bytes": packed_bytes,
        "ratio": round(packed_bytes / int(manifest["expanded_bytes"]), 4),
        "compression": compression,
        "sha256": _sha256_file(destination)[0],
    }


def _read_manifest(archive: zipfile.ZipFile) -> tuple[dict[str, object], dict[str, zipfile.ZipInfo]]:
    try:
        manifest = json.loads(archive.read(MANIFEST_NAME))
    except (KeyError, json.JSONDecodeError) as exc:
        raise ValueError("bundle manifest is missing or invalid") from exc
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT_VERSION:
        raise ValueError("unsupported Atlas bundle format")
    if manifest.get("entrypoint") not in ENTRYPOINTS or not isinstance(manifest.get("files"), dict):
        raise ValueError("bundle entrypoint or file table is invalid")

    infos: dict[str, zipfile.ZipInfo] = {}
    for info in archive.infolist():
        name = info.filename
        if name == MANIFEST_NAME:
            continue
        if not name.startswith(PAYLOAD_ROOT) or info.is_dir():
            raise ValueError(f"unexpected archive member: {name!r}")
        relative = name[len(PAYLOAD_ROOT) :]
        _safe_relative(relative)
        if relative in infos:
            raise ValueError(f"duplicate archive member: {relative!r}")
        # Refuse Unix symlink entries. Extraction always creates ordinary files.
        mode = (info.external_attr >> 16) & 0xFFFF
        if mode and (mode & 0o170000) == 0o120000:
            raise ValueError(f"symbolic links are not allowed in bundle: {relative!r}")
        infos[relative] = info

    records = manifest["files"]
    if set(infos) != set(records):
        raise ValueError("archive members do not match the manifest")
    for relative, record in records.items():
        _safe_relative(relative)
        if not isinstance(record, dict) or not isinstance(record.get("sha256"), str) or not isinstance(record.get("size"), int):
            raise ValueError(f"invalid manifest record for {relative!r}")
    if manifest["entrypoint"] not in records:
        raise ValueError("bundle is missing its generator executable")
    return manifest, infos


def _extract_verified(archive: zipfile.ZipFile, root: Path, manifest: dict[str, object], infos: dict[str, zipfile.ZipInfo]) -> None:
    records = manifest["files"]
    for relative, info in infos.items():
        output = root.joinpath(*_safe_relative(relative).parts)
        # Resolve containment before creating directories, including on Windows.
        resolved = output.resolve()
        if root.resolve() not in resolved.parents:
            raise ValueError(f"bundle path escapes temporary directory: {relative!r}")
        output.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        with archive.open(info, "r") as src, output.open("xb") as dst:
            while chunk := src.read(CHUNK_SIZE):
                size += len(chunk)
                digest.update(chunk)
                dst.write(chunk)
        record = records[relative]
        if size != record["size"] or digest.hexdigest() != record["sha256"]:
            raise ValueError(f"bundle payload failed SHA-256 verification: {relative}")
    executable = root / manifest["entrypoint"]
    if not executable.is_file():
        raise ValueError("generator executable is missing after extraction")


PopenFactory = Callable[..., subprocess.Popen]


def run_bundle(
    bundle: Path,
    game_dir: Path,
    output_dir: Path,
    *,
    replace: bool = False,
    temp_parent: Path | None = None,
    popen_factory: PopenFactory = subprocess.Popen,
) -> int:
    """Verify, unpack, execute the generator, then remove the unpacked runtime."""
    bundle = bundle.resolve(strict=True)
    if temp_parent is not None:
        temp_parent = temp_parent.resolve(strict=True)
        if not temp_parent.is_dir():
            raise ValueError("temporary parent must be a directory")
    with zipfile.ZipFile(bundle, "r") as archive:
        manifest, infos = _read_manifest(archive)
        with tempfile.TemporaryDirectory(prefix="atlas-lite-prep-", dir=temp_parent) as temp_name:
            temp_root = Path(temp_name).resolve()
            _extract_verified(archive, temp_root, manifest, infos)
            stage = temp_root / "generator-stage"
            stage.mkdir()
            command = [
                str(temp_root / manifest["entrypoint"]),
                "--game-dir",
                str(game_dir.resolve()),
                "--output-dir",
                str(output_dir.resolve()),
                "--staging-dir",
                str(stage),
            ]
            if replace:
                command.append("--replace")
            launch_options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {}
            process = popen_factory(command, **launch_options)
            try:
                return int(process.wait())
            except KeyboardInterrupt:
                # The Windows child is a separate process. Terminate it and
                # wait before TemporaryDirectory removes its executable files.
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                raise


def verify_bundle(
    bundle: Path,
    *,
    temp_parent: Path | None = None,
    self_test_imports: bool = False,
    run_factory: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> dict[str, object]:
    """Verify every file and exercise the real frozen executable's --version."""
    bundle = bundle.resolve(strict=True)
    if temp_parent is not None:
        temp_parent = temp_parent.resolve(strict=True)
        if not temp_parent.is_dir():
            raise ValueError("temporary parent must be a directory")
    with zipfile.ZipFile(bundle, "r") as archive:
        manifest, infos = _read_manifest(archive)
        with tempfile.TemporaryDirectory(prefix="atlas-lite-verify-", dir=temp_parent) as temp_name:
            temp_root = Path(temp_name).resolve()
            _extract_verified(archive, temp_root, manifest, infos)
            executable = str(temp_root / manifest["entrypoint"])
            result = run_factory([executable, "--version"], capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"bundled generator --version exited with {result.returncode}: {result.stderr}")
            report: dict[str, object] = {
                "entrypoint": str(manifest["entrypoint"]),
                "version_output": result.stdout.strip(),
                "expanded_bytes": manifest["expanded_bytes"],
                "files": len(manifest["files"]),
                "returncode": result.returncode,
            }
            if self_test_imports:
                imports_result = run_factory([executable, "--self-test-imports"], capture_output=True, text=True)
                if imports_result.returncode != 0:
                    raise RuntimeError(
                        f"bundled generator --self-test-imports exited with {imports_result.returncode}: "
                        f"{imports_result.stderr or imports_result.stdout}"
                    )
                try:
                    import_report = json.loads(imports_result.stdout.strip().splitlines()[-1])
                except (IndexError, json.JSONDecodeError) as exc:
                    raise RuntimeError("bundled generator import self-test produced no JSON receipt") from exc
                if import_report.get("self_test_imports") != "pass":
                    raise RuntimeError("bundled generator import self-test did not pass")
                report["self_test_imports"] = import_report
            return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    pack = commands.add_parser("pack", help="compress an existing frozen generator tree")
    pack.add_argument("--source-tools", type=Path, required=True)
    pack.add_argument("--output", type=Path, required=True)
    pack.add_argument("--compression", choices=("deflate", "lzma"), default="deflate")
    verify = commands.add_parser("verify", help="verify and launch the packed generator's version probe")
    verify.add_argument("--bundle", type=Path, required=True)
    verify.add_argument("--temp-parent", type=Path)
    verify.add_argument("--self-test-imports", action="store_true")
    run = commands.add_parser("run", help="run a packed generator without a permanent runtime install")
    run.add_argument("--bundle", type=Path, required=True)
    run.add_argument("--game-dir", type=Path, required=True)
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--temp-parent", type=Path)
    run.add_argument("--replace", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "pack":
        print(json.dumps(build_bundle(args.source_tools, args.output, args.compression), sort_keys=True))
        return 0
    if args.command == "verify":
        print(
            json.dumps(
                verify_bundle(args.bundle, temp_parent=args.temp_parent, self_test_imports=args.self_test_imports),
                sort_keys=True,
            )
        )
        return 0
    return run_bundle(
        args.bundle,
        args.game_dir,
        args.output_dir,
        replace=args.replace,
        temp_parent=args.temp_parent,
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
