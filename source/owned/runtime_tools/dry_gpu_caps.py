"""Exercise the owned 720p scaled-auto launch, replacing only the final game process.

The fixture is an independent package copy. Ordinary preparation scripts and the
real GPU capability helper run; bb-probe.exe itself is intercepted before launch.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CANDIDATE = REPO / ".local/owned-integration-qa/candidate"
DEFAULT_FIXTURE = REPO / ".local/owned-integration-qa/gpu caps Ω/Atlas Owned 2"
DEFAULT_GAME = Path(r"D:\Bloodborne\Image0")
DEFAULT_PREPARED = REPO / ".local/owned-integration-qa/fresh maps Ω/Atlas Owned/assets.atlaslite"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def copy_sealed(candidate: Path, fixture: Path, prepared: Path) -> None:
    if fixture.exists():
        raise ValueError(f"Refusing to replace an existing GPU fixture: {fixture}")
    manifest = json.loads((candidate / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["files"].items():
        source = candidate / name
        if not source.is_file() or source.is_symlink() or sha(source) != expected:
            raise ValueError(f"Candidate file failed proof: {name}")
        target = fixture / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    for name in ("manifest.json", "state/port/settings.ini"):
        source, target = candidate / name, fixture / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    # This QA-only fixture receives a previously generated, verified map pack.
    # The player ZIP and sealed candidate continue to contain only the art seed.
    prepared = prepared.resolve(strict=True)
    with __import__("zipfile").ZipFile(prepared) as archive:
        prepared_manifest = json.loads(archive.read("manifest.json"))
        if prepared_manifest.get("schema") != 1 or prepared_manifest.get("prepared") is not True:
            raise ValueError("GPU fixture requires a validated prepared Atlas pack")
    shutil.copyfile(prepared, fixture / "assets.atlaslite")
    manifest["asset_pack"]["sha256"] = sha(fixture / "assets.atlaslite")
    manifest["files"]["assets.atlaslite"] = manifest["asset_pack"]["sha256"]
    (fixture / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"stage": "copied", "files": len(manifest["files"]) + 2,
                      "fixture": str(fixture), "manifest_sha256": sha(fixture / "manifest.json")}))


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Could not load verified runner: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run_fixture(fixture: Path, game: Path) -> int:
    sys.path.insert(0, str(fixture / "bootstrap"))
    core = load("atlas_gpu_dry_bootstrap", fixture / "bootstrap/entry.py")
    contract = core.load_contract(fixture)
    profile = {"game_dir": str(game), "atlas_enabled": True, "mods_enabled": False,
               "fps_mode": "uncap", "online": False}
    core.validate_game_source(contract, profile)
    state = contract["state_root"]
    mutable = state / "port"
    mutable.mkdir(parents=True, exist_ok=True)
    (mutable / "bbport.ini").write_text(
        "upscaler=off\noutput_res=1280x720\nlive_resolution=auto\n"
        "quit_to_desktop=0\nframe_gen=off\n", encoding="ascii"
    )
    (mutable / "patches").mkdir(exist_ok=True)
    inherited = {"SystemRoot": os.environ.get("SystemRoot", r"C:\Windows"),
                 "BB_GAME_DIR": str(game), "BB_USER_DIR": str(mutable / "user"),
                 "BB_CONFIG": str(mutable / "bbport.ini"), "BB_INPUT_CONFIG": str(mutable / "input.ini"),
                 "BB_MODS_DIR": str(mutable / "mods"), "BB_MODS_CONFIG": str(mutable / "mods.json"),
                 "BB_MODS_ENABLED": "0", "BB_PATCHES_DIR": str(mutable / "patches"),
                 "BB_PATCHES_CONFIG": str(mutable / "patches.json"),
                 "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}
    dlc = Path(r"D:\Bloodborne\DLC")
    if dlc.is_dir():
        inherited["BB_DLC_DIR"] = str(dlc)
    old_env = dict(os.environ)
    old_cwd = Path.cwd()
    old_argv = sys.argv[:]
    real_run = subprocess.run
    seen_caps: list[dict] = []
    seen_probe: list[list[str]] = []
    helper_path = (contract["base_root"] / "bin/bb-gpu-capabilities.exe").resolve(strict=True)

    def run(command, *args, **kwargs):
        if isinstance(command, (list, tuple)) and command:
            exe = Path(str(command[0])).resolve(strict=False)
            if exe == probe_path:
                seen_probe.append([str(item) for item in command])
                print(json.dumps({"stage": "final-game-probe-mocked", "exe": str(exe)}))
                return subprocess.CompletedProcess(command, 0)
            if exe == helper_path:
                result = real_run(command, *args, **kwargs)
                seen_caps.append({"command": [str(item) for item in command],
                                  "returncode": result.returncode,
                                  "stdout": str(result.stdout).strip()})
                return result
        return real_run(command, *args, **kwargs)

    try:
        with core.SessionLock(state / "session.lock"):
            with core._materialized_asset_paths(contract) as staged:
                paths = {**contract["paths"], **core._validated_materialized_paths(contract, staged)}
                probe_path = paths["probe"].resolve(strict=True)
                integrated = load("atlas_gpu_dry_integrated", fixture / "bootstrap/integrated_play.py")
                env = integrated.environment(core, contract, paths, inherited)
                os.environ.clear()
                os.environ.update(env)
                subprocess.run = run
                sys.argv = [str(contract["runner"])]
                runner = load("atlas_gpu_dry_runner", contract["runner"])
                result = runner.main()
                probe_hash = sha(probe_path)
    finally:
        subprocess.run = real_run
        sys.argv = old_argv
        os.chdir(old_cwd)
        os.environ.clear()
        os.environ.update(old_env)
    if result != 0 or len(seen_caps) != 1 or len(seen_probe) != 1:
        raise ValueError(f"Scaled-auto path incomplete: return={result}, caps={seen_caps}, probe={len(seen_probe)}")
    if seen_caps[0]["command"] != [str(helper_path), "--live-resolution"]:
        raise ValueError("Runner did not call the private port GPU helper")
    if seen_caps[0]["returncode"] != 0 or seen_caps[0]["stdout"] not in ("0", "1"):
        raise ValueError(f"GPU helper failed live-resolution dry capability query: {seen_caps[0]}")
    receipt = {"schema": 1, "status": "PASS_FINAL_PROBE_MOCKED", "output_resolution": "1280x720",
               "live_resolution": "auto", "gpu_helper": seen_caps[0],
               "probe_sha256": probe_hash, "game_eboot_sha256": sha(game / "eboot.bin")}
    (state / "gpu-caps-dry-run.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--game-dir", type=Path, default=DEFAULT_GAME)
    parser.add_argument("--prepared-pack", type=Path, default=DEFAULT_PREPARED)
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    candidate = args.candidate.resolve(strict=True)
    fixture = args.fixture.resolve(strict=False)
    game = args.game_dir.resolve(strict=True)
    if fixture == candidate or candidate in fixture.parents or fixture in candidate.parents:
        raise ValueError("GPU fixture must be separate from the candidate")
    if args.inside:
        return run_fixture(fixture.resolve(strict=True), game)
    copy_sealed(candidate, fixture, args.prepared_pack)
    python = fixture / "runtime/python/python.exe"
    windows = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    env = {"SystemRoot": str(windows), "PATH": os.pathsep.join((str(windows / "System32"), str(windows))),
           "PYTHONDONTWRITEBYTECODE": "1"}
    command = [str(python), "-I", "-B", str(Path(__file__).resolve()), "--inside",
               "--candidate", str(candidate), "--fixture", str(fixture), "--game-dir", str(game)]
    return subprocess.run(command, cwd=fixture, env=env, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
