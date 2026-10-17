"""Build private player/source review ZIPs for the owned in-game Atlas edition.

This script packages only manifest-pinned player files and a generic settings
seed. It never reads game data, saves, or personal launcher configuration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import stat
import zipfile


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CANDIDATE = ROOT / ".local/owned-integration-qa/candidate"
DEFAULT_RELEASE = Path(r"D:\Bloodborne\releases\HuntersAtlas-1.3-owned-ingame-review")
DEFAULT_BASE_SOURCE = ROOT / ".local/release-1.2-v19-20261017/windows-v1.9-final-corresponding-source.zip"
DEFAULT_UPSTREAM_SOURCE = ROOT / ".local/release-1.2-v19-20261017/forced-rebuild19-r2/rebuild/upstream-source.zip"
DEFAULT_RUNTIME_SOURCE = ROOT / ".local/release-inputs/runtime-dependency-source.zip"
UPSTREAM_SOURCE_SHA = "b993cb8be2a1ab9aae67d839b515d80369a730400a8de94990edaa5241ef5b6c"
GENERIC_SETTINGS = b"keyboard=0\ncontroller=0\n"


def digest(path: Path) -> str:
    hash_state = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            hash_state.update(block)
    return hash_state.hexdigest()


def ordinary(path: Path) -> bool:
    details = path.lstat()
    return path.is_file() and not path.is_symlink() and not (
        getattr(details, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def safe_name(name: str) -> bool:
    parts = name.split("/")
    return bool(name) and not name.startswith("/") and "\\" not in name and ":" not in name and all(
        part and part not in (".", "..") and not part.endswith((" ", ".")) for part in parts
    )


def add_bytes(archive: zipfile.ZipFile, name: str, content: bytes,
              compress_type: int = zipfile.ZIP_DEFLATED) -> None:
    if not safe_name(name):
        raise ValueError(f"Unsafe release entry: {name!r}")
    info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
    info.compress_type = compress_type
    info.external_attr = 0o100644 << 16
    archive.writestr(info, content, compresslevel=6 if compress_type == zipfile.ZIP_DEFLATED else None)


def add_file(archive: zipfile.ZipFile, name: str, source: Path,
             compress_type: int = zipfile.ZIP_DEFLATED) -> None:
    if not ordinary(source):
        raise ValueError(f"Release source is missing, linked, or not ordinary: {source}")
    add_bytes(archive, name, source.read_bytes(), compress_type)


def player_files(candidate: Path) -> tuple[dict, list[str]]:
    manifest_path = candidate / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("schema"), manifest.get("version"), manifest.get("installation_model")) != (
        1, "1.3", "owned-runtime-v1"
    ):
        raise ValueError("Candidate is not the sealed owned in-game 1.3 edition")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("Missing immutable candidate hash table")
    for name, expected in files.items():
        if not safe_name(name) or name.startswith(("state/", "settings/", ".install/", ".distribution/")):
            raise ValueError(f"Private or unsafe immutable candidate path: {name}")
        path = candidate / name
        if not ordinary(path) or digest(path) != expected:
            raise ValueError(f"Candidate immutable file failed SHA-256: {name}")
    canonical_docs = {
        "README.md": "source/owned/README.txt",
        "SOURCE-BUILD.md": "source/owned/SOURCE-BUILD.md",
        **{f"docs/{name}": f"docs/{name}" for name in (
            "INSTALL.md", "LAUNCHER-UPDATES.md", "COMPATIBILITY.md", "QA.md", "MAP-FEATURES.md",
        )},
        "docs/releases/v1.3.md": "docs/releases/v1.3.md",
    }
    for packaged, canonical in canonical_docs.items():
        source = ROOT / canonical
        if not ordinary(source) or digest(source) != files.get(packaged):
            raise ValueError(f"Player documentation is not sealed from current source: {packaged}")
    seed = candidate / "state/port/settings.ini"
    if not ordinary(seed) or seed.read_bytes().replace(b"\r\n", b"\n") != GENERIC_SETTINGS:
        raise ValueError("The only mutable player seed must be generic map settings")
    pack_name = manifest.get("asset_pack", {}).get("path")
    if pack_name != "assets.atlaslite" or files.get(pack_name) != manifest["asset_pack"].get("sha256"):
        raise ValueError("Asset pack is not pinned by the manifest")
    with zipfile.ZipFile(candidate / pack_name) as pack:
        pack_manifest = json.loads(pack.read("manifest.json"))
        if (pack_manifest.get("schema") != 1 or pack_manifest.get("prepared") is not False
                or not all(name.startswith("art/") for name in pack_manifest.get("files", {}))):
            raise ValueError("Player archive requires the art-only unprepared seed pack")
    included = sorted([*files, "manifest.json", "state/port/settings.ini"])
    if len(included) != len(set(included)):
        raise ValueError("Duplicate player file")
    return manifest, included


def source_files() -> list[Path]:
    folders = (
        ROOT / "source/lite",
        ROOT / "source/owned",
        ROOT / "source/generator/src",
        ROOT / "source/generator/licenses",
    )
    selected: list[Path] = []
    for folder in folders:
        for path in sorted(folder.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(ROOT).as_posix()
            if ("__pycache__" in path.parts or path.suffix in (".pyc", ".pyo")
                    or relative == "source/owned/tests/live_game.py"):
                continue
            if not ordinary(path):
                raise ValueError(f"Linked source file: {path}")
            selected.append(path)
    for path in sorted((ROOT / "source/generator").iterdir()):
        if path.is_file() and ordinary(path):
            selected.append(path)
    documentation = (
        "README.md", "source/SOURCE-BUILD.md",
        "docs/INSTALL.md", "docs/LAUNCHER-UPDATES.md", "docs/COMPATIBILITY.md",
        "docs/QA.md", "docs/MAP-FEATURES.md", "docs/releases/v1.3.md",
    )
    for relative in documentation:
        path = ROOT / relative
        if not ordinary(path):
            raise ValueError(f"Release documentation is missing or linked: {path}")
        selected.append(path)
    if not selected:
        raise ValueError("No source files selected")
    return sorted(set(selected))


def build(args: argparse.Namespace) -> dict:
    candidate = args.candidate.resolve(strict=True)
    release = args.release.resolve(strict=False)
    if args.public_ready and (args.audit_path is None
                              or args.audit_path.resolve(strict=False).parent == release):
        raise ValueError("A public-ready release requires an audit path outside the release folder")
    if release.exists() and any(release.iterdir()):
        raise ValueError(f"Review output directory is not empty: {release}")
    if digest(args.upstream_source) != UPSTREAM_SOURCE_SHA:
        raise ValueError("Native upstream source does not match native-build.json proof")
    native_proof = json.loads((candidate / "native-build.json").read_text(encoding="utf-8"))
    if native_proof.get("source_archive_sha256") != UPSTREAM_SOURCE_SHA:
        raise ValueError("Candidate native source proof does not match supplied upstream source")
    manifest, included = player_files(candidate)
    source_selected = source_files()
    initial_manifest_sha = digest(candidate / "manifest.json")
    release.mkdir(parents=True)
    player_name = args.player_name
    source_name = args.source_name
    if (not safe_name(player_name) or "/" in player_name or not player_name.endswith(".zip")
            or not safe_name(source_name) or "/" in source_name
            or not source_name.endswith(".zip") or player_name == source_name):
        raise ValueError("Release archive names must be distinct simple .zip filenames")
    with zipfile.ZipFile(release / player_name, "w", allowZip64=True) as archive:
        for name in included:
            add_file(archive, "HuntersAtlas/" + name, candidate / name)
    with zipfile.ZipFile(release / source_name, "w", allowZip64=True) as archive:
        # Carry the prior corresponding native tree intact, under a named source layer.
        with zipfile.ZipFile(args.base_source) as previous:
            for member in previous.infolist():
                if member.is_dir():
                    continue
                name = member.filename
                if not safe_name(name) or (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError(f"Unsafe prior source entry: {name}")
                add_bytes(archive, "corresponding/native-atlas-1.2/" + name, previous.read(member))
        for path in source_selected:
            add_file(archive, path.relative_to(ROOT).as_posix(), path)
        for label, path in (
            ("corresponding/upstream-windows-v1.9-source.zip", args.upstream_source),
            ("corresponding/runtime-dependency-source.zip", args.runtime_source),
            ("proof/native-build.json", candidate / "native-build.json"),
            ("proof/dependencies.json", candidate / "dependencies.json"),
            ("proof/manifest.json", candidate / "manifest.json"),
            ("proof/adapter-release.json", candidate / "adapter-release.json"),
            ("licenses/CPython/LICENSE.txt", candidate / "runtime/python/LICENSE.txt"),
        ):
            add_file(archive, label, path,
                     zipfile.ZIP_STORED if path.suffix == ".zip" else zipfile.ZIP_DEFLATED)
    if digest(candidate / "manifest.json") != initial_manifest_sha:
        raise ValueError("Candidate manifest changed during release packaging")
    with zipfile.ZipFile(release / player_name) as archive:
        members = set(archive.namelist())
        expected = {"HuntersAtlas/" + name for name in included}
        if members != expected:
            raise ValueError("Player archive member set differs from sealed file list")
        forbidden = ("/dvdroot_ps4/", "/savedata/", "/state/profile/", "/maps/", "native-font.ttf")
        if any(any(word in name.casefold() for word in forbidden) for name in members):
            raise ValueError("Player archive contains private or generated content")
    with zipfile.ZipFile(release / source_name) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or any(".local/" in name or "rejected" in name.casefold() for name in names):
            raise ValueError("Source archive contains duplicate or private workspace members")
    audit = {
        "schema": 1,
        "status": "PUBLIC_RELEASE_READY" if args.public_ready else "PRIVATE_REVIEW_NOT_PUBLISHED",
        "installation_model": "owned-runtime-v1",
        "candidate_manifest_sha256": initial_manifest_sha,
        "candidate_native_probe_sha256": digest(candidate / "bin/bb-probe.exe"),
        "player_file_count": len(included),
        "player_mutable_seed": "state/port/settings.ini",
        "player_asset_pack_prepared": False,
        "player_assets_sha256": manifest["asset_pack"]["sha256"],
        "source_file_count": len(source_selected),
        "source_inputs": {
            "prior_corresponding_source_sha256": digest(args.base_source),
            "upstream_windows_v1_9_source_sha256": digest(args.upstream_source),
            "runtime_dependency_source_sha256": digest(args.runtime_source),
        },
        "artifacts": {
            name: {"bytes": (release / name).stat().st_size, "sha256": digest(release / name)}
            for name in (player_name, source_name)
        },
        "excluded": ["game data", "prepared maps", "native font", "saves", "profile and input settings",
                     "rejected companion source"],
    }
    audit_path = args.audit_path.resolve(strict=False) if args.audit_path else release / "review-audit.json"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sums = [f"{digest(release / name)}  {name}" for name in (player_name, source_name)]
    if not args.public_ready and audit_path.parent == release:
        sums.append(f"{digest(audit_path)}  {audit_path.name}")
    (release / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="ascii")
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--release", type=Path, default=DEFAULT_RELEASE)
    parser.add_argument("--base-source", type=Path, default=DEFAULT_BASE_SOURCE)
    parser.add_argument("--upstream-source", type=Path, default=DEFAULT_UPSTREAM_SOURCE)
    parser.add_argument("--runtime-source", type=Path, default=DEFAULT_RUNTIME_SOURCE)
    parser.add_argument("--player-name", default="Hunters-Atlas-1.3-Windows.zip")
    parser.add_argument("--source-name", default="Hunters-Atlas-1.3-Source.zip")
    parser.add_argument("--audit-path", type=Path)
    parser.add_argument("--public-ready", action="store_true")
    result = build(parser.parse_args())
    print(json.dumps({"artifacts": result["artifacts"], "player_file_count": result["player_file_count"],
                      "source_file_count": result["source_file_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
