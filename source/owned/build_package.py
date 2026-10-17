"""Stage and seal the private, in-game Hunter's Atlas runtime.

Stage copies only SHA-pinned edition files from a verified integrated backup,
only SHA-pinned ordinary-port files from the official Windows v1.9 ZIP, and a
private CPython 3.10 installation. It never copies game data or user saves.

Root-owned app, installer, bootstrap, and UI changes are overlaid after stage.
Seal then writes dependencies.json and manifest.json from the final immutable
candidate tree. Both phases preserve candidate/state, including maps and saves.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import zipfile


REPO = Path(__file__).resolve().parents[2]
QA_ROOT = REPO / ".local/owned-integration-qa"
DEFAULT_CANDIDATE = QA_ROOT / "candidate"
DEFAULT_BACKUP = Path(r"D:\Bloodborne\rollback\Atlas-1.2-before-independent-20261017-213957\legacy-installed")
DEFAULT_ARCHIVE = Path(r"D:\Bloodborne\.atlas-rebuild-dba598535e2a6fb904779c189bae7634\upstream.zip")
DEFAULT_PYTHON = Path(os.environ.get("ATLAS_BUILD_PYTHON_HOME", sys.base_prefix))
DEFAULT_ART = REPO / ".local/standalone-1.3-qa/art.atlaslite"
OFFICIAL_SHA = "d2df6aa37530f0d21f577c5cc05bd3366b1f95e8f402b96cab89bbd8c8a219e5"
UPSTREAM_COMMIT = "652f9a494c47cc8c1ab16f28b456372eaa8103f8"
EXTRA_PORT_FILES = {
    "patches/Bloodborne.xml": "d78cb9bae79c4c682501c8da978fb355ac0dab656e6d9c18f6ec6730a0ec0a78",
    "patches/redzone.json": "10ae6c6f891c3ed8be71fa8e92ce7236843d07a2b5d5813268eab74b52692e28",
    "tools/legacy-cpu-plan.json": "626a63f356c55f9a9a770f55fddfd3f15cccbd4751620ce799f1813d1c2eabc0",
}
EXCLUDE_EDITION = {"assets.atlaslite", "dependencies.json", "manifest.json",
                   "integration/AtlasLauncher.exe"}
EXCLUDE_PYTHON_TOP = {"Doc", "include", "libs", "Scripts", "Tools", "NEWS.txt"}
EXCLUDE_LIB_DIR = {"site-packages", "test", "idlelib", "__pycache__"}
EXCLUDE_LIB_FILE = {"*.pyc", "*.pyo"}


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def is_reparse(path: Path) -> bool:
    details = path.lstat()
    return path.is_symlink() or bool(getattr(details, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def safe_root(candidate: Path) -> Path:
    candidate = candidate.absolute()
    qa = QA_ROOT.absolute()
    if candidate != qa / "candidate":
        raise ValueError("The private candidate must be .local/owned-integration-qa/candidate")
    for parent in (candidate, *candidate.parents):
        if parent.exists() and is_reparse(parent):
            raise ValueError(f"Reparse point in candidate path: {parent}")
    return candidate


def safe_relative(name: str) -> Path:
    if (not name or "\\" in name or ":" in name or name.startswith("/")
            or name.endswith("/")):
        raise ValueError(f"Unsafe package path: {name!r}")
    parts = name.split("/")
    if any(part in ("", ".", "..") or part.endswith((".", " ")) for part in parts):
        raise ValueError(f"Unsafe package path: {name!r}")
    return Path(*parts)


def copy_verified(source: Path, target: Path, expected: str, *, preserve_overlay: bool = False) -> None:
    if not source.is_file() or is_reparse(source) or sha(source) != expected:
        raise ValueError(f"Source is missing or does not match pinned SHA-256: {source}")
    if target.exists():
        if is_reparse(target):
            raise ValueError(f"Reparse point in candidate: {target}")
        if sha(target) == expected or preserve_overlay:
            return
        raise ValueError(f"Candidate already has a different file: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    if sha(target) != expected or os.path.samefile(source, target):
        raise ValueError(f"Candidate copy failed integrity or independence check: {target}")


def copy_bytes(data: bytes, target: Path, expected: str) -> None:
    if sha_bytes(data) != expected:
        raise ValueError(f"Official archive member failed SHA-256: {target}")
    if target.exists():
        if is_reparse(target) or sha(target) != expected:
            raise ValueError(f"Candidate already has a different file: {target}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    if sha(target) != expected:
        raise ValueError(f"Candidate archive copy failed integrity check: {target}")


def copy_python_tree(source: Path, target: Path) -> dict[str, str]:
    if not (source / "python.exe").is_file() or not (source / "DLLs/_tkinter.pyd").is_file():
        raise ValueError("Selected CPython 3.10 installation lacks Tk")
    files: dict[str, str] = {}
    for folder in ("DLLs", "Lib", "tcl"):
        origin = source / folder
        if not origin.is_dir() or is_reparse(origin):
            raise ValueError(f"Missing or linked Python runtime directory: {origin}")
        for base, dirnames, filenames in os.walk(origin, followlinks=False):
            current = Path(base)
            for dirname in list(dirnames):
                path = current / dirname
                if is_reparse(path):
                    raise ValueError(f"Reparse point in Python runtime: {path}")
                if folder == "Lib" and dirname in EXCLUDE_LIB_DIR:
                    dirnames.remove(dirname)
            for filename in sorted(filenames):
                path = current / filename
                if is_reparse(path):
                    raise ValueError(f"Reparse point in Python runtime: {path}")
                if not path.is_file() or path.suffix in (".pyc", ".pyo"):
                    continue
                relative = path.relative_to(source)
                name = relative.as_posix()
                expected = sha(path)
                copy_verified(path, target / relative, expected)
                files[name] = expected
    for path in sorted(source.iterdir()):
        if path.name in EXCLUDE_PYTHON_TOP or path.is_dir():
            continue
        if is_reparse(path):
            raise ValueError(f"Reparse point in Python runtime: {path}")
        if path.name not in {"python.exe", "pythonw.exe", "python3.dll", "python310.dll",
                             "vcruntime140.dll", "vcruntime140_1.dll", "LICENSE.txt"}:
            continue
        expected = sha(path)
        copy_verified(path, target / path.name, expected)
        files[path.name] = expected
    return files


def check_art_pack(path: Path) -> str:
    if not path.is_file() or is_reparse(path):
        raise ValueError("Art-only seed pack is missing or linked")
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("schema") != 1 or manifest.get("prepared") is not False:
            raise ValueError("Seed assets must be an unprepared art-only pack")
        records = manifest.get("files")
        if not isinstance(records, dict) or not records or any(not name.startswith("art/") for name in records):
            raise ValueError("Seed assets contain non-art files")
        if set(archive.namelist()) != {"manifest.json", *records}:
            raise ValueError("Seed archive does not match manifest")
        total = 0
        for name, record in records.items():
            safe_relative(name)
            data = archive.read(name)
            if len(data) != record.get("size") or sha_bytes(data) != record.get("sha256"):
                raise ValueError(f"Seed art failed SHA-256: {name}")
            total += len(data)
        if total != manifest.get("expanded_bytes"):
            raise ValueError("Seed art total length mismatch")
    return sha(path)


def verify_provenance(backup: Path, archive: Path) -> tuple[dict, dict]:
    original_manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    original_deps = json.loads((backup / "dependencies.json").read_text(encoding="utf-8"))
    if (original_manifest.get("compatibility", {}).get("upstream_commit") != UPSTREAM_COMMIT or
            original_deps.get("compatibility", {}).get("upstream_commit") != UPSTREAM_COMMIT or
            sha(archive) != OFFICIAL_SHA):
        raise ValueError("Backup or official v1.9 archive provenance mismatch")
    if (sha(backup / "bin/bb-probe.exe") !=
            json.loads((backup / "native-build.json").read_text(encoding="utf-8"))["runtime_sha256"]):
        raise ValueError("Integrated native bb-probe proof mismatch")
    return original_manifest, original_deps


def stage(args: argparse.Namespace, candidate: Path) -> None:
    backup = args.backup.resolve(strict=True)
    archive_path = args.official_zip.resolve(strict=True)
    python = args.python_home.resolve(strict=True)
    art = args.art_pack.resolve(strict=True)
    original_manifest, original_deps = verify_provenance(backup, archive_path)
    art_sha = check_art_pack(art)
    candidate.mkdir(parents=True, exist_ok=True)
    for relative, expected in sorted(original_manifest["files"].items()):
        if relative in EXCLUDE_EDITION or relative.startswith(("state/", "settings/", "updates/", ".install/", ".distribution/")):
            continue
        name = safe_relative(relative)
        copy_verified(backup / name, candidate / name, expected,
                      preserve_overlay=relative.startswith(("bootstrap/", "integration/ui/"))
                      or relative in {"README.md", "Install.cmd", "Update.cmd", "Uninstall.cmd"})
    copy_verified(art, candidate / "assets.atlaslite", art_sha)

    ordinary = {**original_deps["ordinary_port"]["files"], **EXTRA_PORT_FILES}
    with zipfile.ZipFile(archive_path) as zipfile_source:
        names = set(zipfile_source.namelist())
        for relative, expected in sorted(ordinary.items()):
            name = safe_relative(relative)
            archive_name = "bbport-windows/" + relative
            if archive_name not in names:
                raise ValueError(f"Official v1.9 closure member missing: {relative}")
            copy_bytes(zipfile_source.read(archive_name), candidate / "runtime/port" / name, expected)
        gpu = "bin/bb-gpu-capabilities.exe"
        copy_bytes(zipfile_source.read("bbport-windows/" + gpu), candidate / gpu, ordinary[gpu])
    python_files = copy_python_tree(python, candidate / "runtime/python")

    owned = REPO / "source/owned"
    for filename in ("app.py", "installer.py"):
        source = owned / filename
        if source.is_file():
            target = candidate / "owned" / filename
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
    mutable_settings = candidate / "state/port/settings.ini"
    if not mutable_settings.exists():
        mutable_settings.parent.mkdir(parents=True, exist_ok=True)
        mutable_settings.write_text("keyboard=0\ncontroller=0\n", encoding="ascii")

    receipt = {"schema": 1, "stage": "owned-runtime-v1", "backup": str(backup),
               "backup_manifest_sha256": sha(backup / "manifest.json"),
               "official_zip": str(archive_path), "official_zip_sha256": OFFICIAL_SHA,
               "art_pack_sha256": art_sha, "python_home": str(python),
               "python_exe_sha256": python_files["python.exe"],
               "private_port_files": len(ordinary), "private_python_files": len(python_files)}
    QA_ROOT.mkdir(parents=True, exist_ok=True)
    (QA_ROOT / "stage-receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                                                  encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))


def immutable_files(candidate: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(candidate.rglob("*")):
        if is_reparse(path):
            raise ValueError(f"Reparse point in candidate: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(candidate).as_posix()
        if relative == "manifest.json" or relative.startswith("state/") or relative.startswith("settings/"):
            continue
        if "__pycache__" in path.parts or path.suffix in (".pyc", ".pyo"):
            raise ValueError(f"Generated Python cache in immutable candidate: {relative}")
        files[relative] = sha(path)
    return files


def prune_unused_runtime(candidate: Path) -> list[str]:
    """Drop inactive legacy installers/updater and duplicate private-port DLLs."""
    removed: list[str] = []
    legacy = candidate / "updates"
    if legacy.exists():
        if is_reparse(legacy) or not legacy.is_dir():
            raise ValueError(f"Unsafe legacy updater path: {legacy}")
        for path in sorted(legacy.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if is_reparse(path):
                raise ValueError(f"Reparse point in legacy updater: {path}")
            if path.is_file():
                removed.append(path.relative_to(candidate).as_posix())
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        legacy.rmdir()
    old_installer = candidate / "installer"
    if old_installer.exists():
        if is_reparse(old_installer) or not old_installer.is_dir():
            raise ValueError(f"Unsafe legacy installer path: {old_installer}")
        for filename in ("Manage-Atlas.ps1", "Preparation-Process.ps1", "Update-Atlas.ps1"):
            path = old_installer / filename
            if path.exists():
                if is_reparse(path) or not path.is_file():
                    raise ValueError(f"Unsafe legacy installer file: {path}")
                removed.append(path.relative_to(candidate).as_posix())
                path.unlink()
        if not any(old_installer.iterdir()):
            old_installer.rmdir()
    own_bin = candidate / "bin"
    port_bin = candidate / "runtime/port/bin"
    for path in sorted(own_bin.glob("*.dll")):
        peer = port_bin / path.name
        if is_reparse(path) or (peer.exists() and is_reparse(peer)):
            raise ValueError(f"Reparse point in binary dependency: {path}")
        if peer.is_file() and sha(path) == sha(peer):
            removed.append(path.relative_to(candidate).as_posix())
            path.unlink()
    return removed


def refresh_official_port_resources(candidate: Path, archive_path: Path) -> None:
    """Add the three hash-pinned ordinary-port resources absent from the old proof."""
    archive_path = archive_path.resolve(strict=True)
    if sha(archive_path) != OFFICIAL_SHA:
        raise ValueError("Official Windows v1.9 archive provenance mismatch")
    with zipfile.ZipFile(archive_path) as archive:
        for relative, expected in EXTRA_PORT_FILES.items():
            source = "bbport-windows/" + relative
            copy_bytes(archive.read(source), candidate / "runtime/port" / safe_relative(relative), expected)


def overlay_owned_sources(candidate: Path) -> None:
    def install(source: Path, target: Path) -> None:
        if not source.is_file() or is_reparse(source):
            raise ValueError(f"Canonical owned source is missing or linked: {source}")
        if target.exists() and is_reparse(target):
            raise ValueError(f"Candidate overlay target is linked: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file() or sha(source) != sha(target):
            shutil.copyfile(source, target)

    for filename in ("entry.py", "integrated_play.py", "owned_contract.py", "assets.py"):
        install(REPO / "source/lite/bootstrap" / filename, candidate / "bootstrap" / filename)
    profile = REPO / "source/lite/compatibility/profiles/windows-v1.9"
    runner = profile / "run_lite.py"
    install(runner, candidate / "bootstrap/run_lite.py")
    install(profile / "bbport_launcher_win.py", candidate / "integration/ui/bbport_launcher_win.py")
    for filename in ("app.py", "installer.py"):
        install(REPO / "source/owned" / filename, candidate / "owned" / filename)
    install(REPO / "source/owned/README.txt", candidate / "README.md")
    install(REPO / "source/owned/SOURCE-BUILD.md", candidate / "SOURCE-BUILD.md")
    for filename in ("INSTALL.md", "LAUNCHER-UPDATES.md", "COMPATIBILITY.md",
                     "QA.md", "MAP-FEATURES.md"):
        install(REPO / "docs" / filename, candidate / "docs" / filename)
    install(REPO / "docs/releases/v1.3.md", candidate / "docs/releases/v1.3.md")

    source_receipt = candidate / "bootstrap/run_lite-source.json"
    receipt = json.loads(source_receipt.read_text(encoding="utf-8"))
    receipt["copy_sha256"] = sha(runner)
    source_run = candidate / "runtime/port/run.py"
    if receipt.get("source_sha256") != sha(source_run):
        raise ValueError("Runner source receipt does not match private official run.py")
    source_receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    config_path = candidate / "bootstrap/config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["installation_model"] = "owned-runtime-v1"
    config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for filename, option in (("Install.cmd", ""), ("Update.cmd", "--update "),
                             ("Uninstall.cmd", "--uninstall ")):
        command = ('@echo off\r\nsetlocal\r\n"%~dp0runtime\\python\\python.exe" -I -B '
                   '"%~dp0owned\\installer.py" ' + option +
                   '%*\r\nexit /b %ERRORLEVEL%\r\n')
        (candidate / filename).write_bytes(command.encode("ascii"))


def seal(args: argparse.Namespace, candidate: Path) -> None:
    backup = args.backup.resolve(strict=True)
    overlay_owned_sources(candidate)
    refresh_official_port_resources(candidate, args.official_zip)
    removed = prune_unused_runtime(candidate)
    mutable_settings = candidate / "state/port/settings.ini"
    if not mutable_settings.is_file():
        mutable_settings.parent.mkdir(parents=True, exist_ok=True)
        mutable_settings.write_text("keyboard=0\ncontroller=0\n", encoding="ascii")
    if args.launcher_exe is not None:
        launcher = args.launcher_exe.resolve(strict=True)
        destination = candidate / "HuntersAtlas.exe"
        if not destination.is_file() or sha(launcher) != sha(destination):
            shutil.copyfile(launcher, destination)
    original_manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    original_deps = json.loads((backup / "dependencies.json").read_text(encoding="utf-8"))
    required = ("runtime/python/python.exe", "runtime/python/pythonw.exe", "runtime/port/run.py",
                "bin/bb-probe.exe", "bin/bb-gpu-capabilities.exe", "integration/ui/bbport_launcher_win.py",
                "owned/app.py", "owned/installer.py", "HuntersAtlas.exe", "assets.atlaslite")
    for relative in required:
        if not (candidate / relative).is_file():
            raise ValueError(f"Candidate is missing required owned file: {relative}")
    art_sha = check_art_pack(candidate / "assets.atlaslite")
    port_root = candidate / "runtime/port"
    pinned = {**original_deps["ordinary_port"]["files"], **EXTRA_PORT_FILES}
    actual_port = {p.relative_to(port_root).as_posix(): sha(p) for p in port_root.rglob("*") if p.is_file()}
    if actual_port != pinned:
        raise ValueError("Private ordinary port differs from SHA-pinned official v1.9 closure")
    deps = dict(original_deps)
    deps["ordinary_port"] = {"root": "runtime/port", "files": pinned,
                             "roles": {"run_script": "run.py"}}
    deps["owned_runtime"] = {"schema": 1, "python": "runtime/python/python.exe",
                             "pythonw": "runtime/python/pythonw.exe",
                             "ui": "integration/ui/bbport_launcher_win.py",
                             "upstream_release": "windows-v1.9"}
    deps.pop("working_port_comparison", None)
    deps["selection_policy"] = {"included": ["run.py", "scripts/**/*.py", "bin/*.(dll|exe)"],
                                "excluded": ["official executable", "official private interpreter",
                                             "user game files", "user saves"]}
    (candidate / "dependencies.json").write_text(json.dumps(deps, indent=2, sort_keys=True) + "\n",
                                                   encoding="utf-8")
    manifest_path = candidate / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else original_manifest
    if manifest.get("id") != "hunters-atlas-lite" or manifest.get("schema") != 1:
        raise ValueError("Candidate Atlas manifest identity changed")
    manifest["installation_model"] = "owned-runtime-v1"
    manifest["version"] = "1.3"
    manifest["asset_pack"] = {"path": "assets.atlaslite", "sha256": art_sha}
    manifest.setdefault("paths", {})["config"] = "state/port/settings.ini"
    manifest["files"] = immutable_files(candidate)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for relative, expected in manifest["files"].items():
        if sha(candidate / safe_relative(relative)) != expected:
            raise ValueError(f"Candidate file changed during seal: {relative}")
    receipt = {"schema": 1, "installation_model": "owned-runtime-v1",
               "manifest_sha256": sha(manifest_path), "dependencies_sha256": sha(candidate / "dependencies.json"),
               "asset_pack_sha256": art_sha, "private_port_files": len(pinned),
               "immutable_files": len(manifest["files"]), "pruned_paths": removed,
               "native_probe_sha256": sha(candidate / "bin/bb-probe.exe")}
    (QA_ROOT / "seal-receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                                                 encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("stage", "seal"))
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--backup", type=Path, default=DEFAULT_BACKUP)
    parser.add_argument("--official-zip", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--python-home", type=Path, default=DEFAULT_PYTHON)
    parser.add_argument("--art-pack", type=Path, default=DEFAULT_ART)
    parser.add_argument("--launcher-exe", type=Path, help="Compiled owned native frontdoor (seal phase)")
    args = parser.parse_args()
    candidate = safe_root(args.candidate)
    if args.phase == "stage":
        stage(args, candidate)
    else:
        seal(args, candidate)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Owned package build failed: {error}", file=sys.stderr)
        raise SystemExit(1)
