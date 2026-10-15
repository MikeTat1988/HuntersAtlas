"""Isolated Hunter's Atlas Lite bootstrap for the ordinary frozen Windows launcher.

The launcher invokes this file with ``Bloodborne.exe --script entry.py``. This
standard-library bridge validates package inputs and stages the isolated runtime.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import time
from typing import Any


MANIFEST_ID = "hunters-atlas-lite"
DEPENDENCIES_ID = "hunters-atlas-lite-dependencies"
SUPPORTED_GAME_SHA256 = "d65f0b4f01d59166aed16f8604196d8b7dd805abbf0758b356e8f1354c9429f9"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SECRET_KEYS = frozenset({"BB_SHADNET_PASSWORD", "BB_SHADNET_NPID", "BB_USER_NAME"})
RESERVED_EXTRA_ENV = frozenset({
    "BB_PROBE", "BB_DATA_DIR", "BB_CONFIG", "BB_USER_DIR", "BB_GPU_USER_DIR",
    "BB_MAP_DIR", "BB_MAP_CONFIG", "BB_MAP_CATALOG", "BB_MAP_ART_DIR", "BB_MAP_FONT",
    "BB_ATLAS_ENABLED", "BB_ATLAS_QA", "BB_MAP_QA", "BB_LAUNCHER_SETTINGS_ROOT",
    "BB_INPUT_CONFIG",
    "BB_MAP_TEST_CONTROL", "BB_MAP_TEST_TRACE", "BB_MAP_UI_DUMP_TRIGGER", "BB_PAD_FILE", "BB_DUMP_DIR",
})


class BootstrapError(RuntimeError):
    """A package, profile, or launch prerequisite is invalid."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_game_source(contract: dict[str, Any], profile: dict[str, Any]) -> None:
    declared = contract.get("manifest", {}).get("game_executables", [SUPPORTED_GAME_SHA256])
    if declared != [SUPPORTED_GAME_SHA256]:
        raise BootstrapError("This Lite build does not support its declared game fingerprint.")
    game = Path(str(profile.get("game_dir", "")))
    executable = game / "eboot.bin"
    if not executable.is_file():
        raise BootstrapError("Choose the Bloodborne game folder containing eboot.bin in Settings.cmd.")
    if sha256_file(executable) != SUPPORTED_GAME_SHA256:
        raise BootstrapError("Unsupported Bloodborne executable. Atlas Lite supports the verified 1.09 build only; no game files were changed.")


def _json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BootstrapError(f"Could not read {label}: {error}") from error
    if not isinstance(value, dict):
        raise BootstrapError(f"{label} must contain a JSON object.")
    return value


def _relative(value: object, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise BootstrapError(f"{label} must be a non-empty relative path.")
    normalized = value.replace("\\", "/")
    parts = normalized.split("/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized) or any(
        item in ("", ".", "..") or ":" in item for item in parts
    ):
        raise BootstrapError(f"{label} must stay inside its declared root.")
    return PurePosixPath(*parts)


def _inside(root: Path, value: object, label: str, *, file: bool | None = None) -> Path:
    relative = _relative(value, label)
    base = root.resolve(strict=True)
    candidate = base.joinpath(*relative.parts)
    cursor = base
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink() or getattr(cursor, "is_junction", lambda: False)():
            raise BootstrapError(f"{label} must not traverse a symlink or junction.")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(base)
    except (OSError, RuntimeError, ValueError) as error:
        raise BootstrapError(f"{label} is missing or resolves outside its root.") from error
    if file is True and not resolved.is_file():
        raise BootstrapError(f"{label} must name a file.")
    if file is False and not resolved.is_dir():
        raise BootstrapError(f"{label} must name a directory.")
    return resolved


def _hash_table(root: Path, table: object, label: str) -> dict[str, Path]:
    if not isinstance(table, dict) or not table:
        raise BootstrapError(f"{label} must be a non-empty path-to-SHA-256 object.")
    resolved: dict[str, Path] = {}
    for name, expected in table.items():
        path = _inside(root, name, f"{label}[{name!r}]", file=True)
        if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected.lower()):
            raise BootstrapError(f"{label}[{name!r}] has an invalid SHA-256 value.")
        if sha256_file(path) != expected.lower():
            raise BootstrapError(f"SHA-256 check failed for {label} entry {name}.")
        canonical = _relative(name, label).as_posix().casefold()
        if canonical in resolved:
            raise BootstrapError(f"Duplicate case-insensitive path in {label}: {name}.")
        resolved[canonical] = path
    return resolved


def load_contract(root: Path) -> dict[str, Any]:
    """Validate Lite-owned files and separately typed ordinary-port dependencies."""
    root = root.resolve(strict=True)
    config = _json_object(root / "bootstrap" / "config.json", "bootstrap config")
    if config.get("schema") != 1 or config.get("edition") != "Lite":
        raise BootstrapError("bootstrap/config.json must declare schema 1 and edition Lite.")
    manifest_path = _inside(root, config.get("manifest", "manifest.json"), "manifest", file=True)
    manifest = _json_object(manifest_path, "Lite manifest")
    if manifest.get("schema") != 1 or manifest.get("id") != MANIFEST_ID:
        raise BootstrapError("Unsupported Lite manifest identity or schema.")
    own_files = _hash_table(root, manifest.get("files"), "manifest.files")

    deps_path = _inside(root, config.get("dependencies", "dependencies.json"),
                        "dependencies manifest", file=True)
    deps = _json_object(deps_path, "dependencies manifest")
    if deps.get("schema") != 1 or deps.get("id") != DEPENDENCIES_ID:
        raise BootstrapError("Unsupported Lite dependencies identity or schema.")
    ordinary = deps.get("ordinary_port")
    if not isinstance(ordinary, dict):
        raise BootstrapError("dependencies.ordinary_port must be an object.")
    try:
        base_root = Path(ordinary["root"]).expanduser().resolve(strict=True)
    except (KeyError, OSError, RuntimeError, TypeError) as error:
        raise BootstrapError("The verified ordinary-port root is missing.") from error
    base_files = _hash_table(base_root, ordinary.get("files"), "dependencies.ordinary_port.files")
    pinned_base_dlls = {path.resolve() for path in base_files.values()
                        if path.suffix.casefold() == ".dll" and path.parent.name.casefold() == "bin"}
    base_bin = base_root / "bin"
    if base_bin.is_dir():
        unpinned = [path for path in base_bin.glob("*.dll") if path.resolve() not in pinned_base_dlls]
        if unpinned:
            raise BootstrapError(f"Ordinary-port bin contains an unverified DLL: {unpinned[0].name}.")
    roles = ordinary.get("roles")
    if not isinstance(roles, dict):
        raise BootstrapError("dependencies.ordinary_port.roles must map roles to relative paths.")

    def required_common(role: str) -> Path:
        raw = roles.get(role)
        relative = _relative(raw, f"ordinary_port.roles.{role}")
        canonical = relative.as_posix().casefold()
        if canonical not in base_files:
            raise BootstrapError(f"Ordinary-port role {role} is not hash-pinned in dependencies.json.")
        return base_files[canonical]

    run_script = required_common("run_script")
    if run_script.name.casefold() != "run.py":
        raise BootstrapError("The ordinary run_script role must point to run.py.")
    if run_script.parent != base_root:
        raise BootstrapError("Ordinary run.py must be adjacent to dependencies.ordinary_port.root.")
    variants = ordinary.get("launcher_variants")
    if not isinstance(variants, dict) or not variants:
        raise BootstrapError("dependencies.ordinary_port.launcher_variants must pin supported launcher hashes.")
    normalized_variants: dict[str, dict[str, Any]] = {}
    for raw_hash, variant in variants.items():
        launcher_hash = str(raw_hash).lower()
        if not SHA256_RE.fullmatch(launcher_hash) or not isinstance(variant, dict):
            raise BootstrapError("Launcher variants must be keyed by executable SHA-256.")
        path = _relative(variant.get("path"), "launcher variant path")
        selected_name = str(ordinary.get("launcher_path", "Bloodborne.exe")).casefold()
        if selected_name not in ("bloodborne.exe", "bloodborne.stock.exe") or path.as_posix().casefold() != selected_name:
            raise BootstrapError("Supported launcher variants must name the selected ordinary launcher in the port root.")
        runtime_dir = variant.get("runtime_dir")
        if runtime_dir not in ("_internal", "_atlas_internal"):
            raise BootstrapError("Launcher runtime_dir must be _internal or _atlas_internal.")
        variant_files = variant.get("files")
        if not isinstance(variant_files, dict) or not variant_files:
            raise BootstrapError("Each launcher variant must pin its private interpreter runtime files.")
        for name in variant_files:
            rel = _relative(name, "launcher variant file").as_posix().casefold()
            if not rel.startswith(runtime_dir.casefold() + "/"):
                raise BootstrapError("Launcher variant files must stay inside their declared runtime_dir.")
        normalized_variants[launcher_hash] = {**variant, "path": path.as_posix()}
    launcher_path = base_root / ordinary.get("launcher_path", "Bloodborne.exe")
    if launcher_path.is_symlink() or getattr(launcher_path, "is_junction", lambda: False)():
        raise BootstrapError("Ordinary Bloodborne.exe must not be a symlink or junction.")
    actual_launcher_hash = sha256_file(launcher_path) if launcher_path.is_file() else ""
    selected_variant = normalized_variants.get(actual_launcher_hash)
    if selected_variant is None:
        raise BootstrapError("Bloodborne.exe does not match a supported ordinary-port launcher variant.")
    launcher = _inside(base_root, selected_variant["path"], "ordinary launcher", file=True)
    runtime_files = _hash_table(base_root, selected_variant["files"], "launcher variant files")
    runtime_dir = _inside(base_root, selected_variant["runtime_dir"], "launcher runtime directory", file=False)
    actual_runtime_files: set[str] = set()
    for path in runtime_dir.rglob("*"):
        if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
            raise BootstrapError("Ordinary launcher runtime must not contain symlinks or junctions.")
        if path.is_file():
            actual_runtime_files.add(path.relative_to(base_root).as_posix().casefold())
    if actual_runtime_files != set(runtime_files):
        raise BootstrapError("Ordinary launcher runtime files do not exactly match the selected variant allowlist.")
    if launcher.parent != base_root:
        raise BootstrapError("Ordinary launcher must be adjacent to dependencies.ordinary_port.root.")
    runner = _inside(root, config.get("runner", "bootstrap/run_lite.py"), "runner", file=True)
    entry = _inside(root, "bootstrap/entry.py", "entrypoint", file=True)
    source_receipt = _inside(root, "bootstrap/run_lite-source.json", "run_lite source receipt", file=True)
    for label, path in (("entrypoint", entry), ("runner", runner), ("source receipt", source_receipt)):
        if path.relative_to(root).as_posix().casefold() not in own_files:
            raise BootstrapError(f"Lite manifest does not hash its {label}.")
    receipt = _json_object(source_receipt, "run_lite source receipt")
    if (receipt.get("schema") != 1 or receipt.get("source_sha256") != sha256_file(run_script) or
            receipt.get("copy_sha256") != sha256_file(runner)):
        raise BootstrapError("run_lite source receipt does not match the verified ordinary run.py and Lite copy.")
    bin_paths: list[Path] = []
    for path in base_files.values():
        if path.suffix.casefold() == ".dll" and path.parent.name.casefold() == "bin":
            bin_paths.append(path)

    paths = manifest.get("paths")
    if not isinstance(paths, dict):
        raise BootstrapError("Lite manifest must define its owned runtime paths.")
    state_relative = _relative(config.get("state_dir", "state"), "state_dir")
    state_root = root.joinpath(*state_relative.parts)
    state_cursor = root
    for part in state_relative.parts:
        state_cursor = state_cursor / part
        if state_cursor.is_symlink() or getattr(state_cursor, "is_junction", lambda: False)():
            raise BootstrapError("state_dir must not traverse a symlink or junction.")
    try:
        state_root.resolve(strict=False).relative_to(root)
    except ValueError as error:
        raise BootstrapError("state_dir must stay inside the Lite package root.") from error
    raw_asset_pack = manifest.get("asset_pack")
    asset_pack = None
    if raw_asset_pack is not None:
        if not isinstance(raw_asset_pack, dict):
            raise BootstrapError("manifest.asset_pack must contain a path and SHA-256.")
        pack = _inside(root, raw_asset_pack.get("path"), "asset_pack.path", file=True)
        expected_pack_hash = raw_asset_pack.get("sha256")
        pack_key = pack.relative_to(root).as_posix().casefold()
        if (not isinstance(expected_pack_hash, str) or not SHA256_RE.fullmatch(expected_pack_hash.lower()) or
                sha256_file(pack) != expected_pack_hash.lower() or own_files.get(pack_key) != pack):
            raise BootstrapError("Lite asset pack must match its SHA-256 and manifest.files entry.")
        asset_manager = _inside(root, "bootstrap/assets.py", "asset manager", file=True)
        if asset_manager.relative_to(root).as_posix().casefold() not in own_files:
            raise BootstrapError("Packed mode requires a manifest-hashed bootstrap/assets.py.")
        asset_pack = {"path": pack, "sha256": expected_pack_hash.lower(), "manager": asset_manager}

    def owned_path(key: str, *, file: bool | None = None) -> Path:
        if asset_pack and key in {"maps", "art", "catalog", "font"}:
            rel = _relative(paths.get(key), f"paths.{key}")
            future = root.joinpath(*rel.parts)
            runtime_root = (state_root / "runtime-assets").resolve(strict=False)
            resolved = future.resolve(strict=False)
            try:
                resolved.relative_to(runtime_root)
            except ValueError as error:
                raise BootstrapError(f"Packed paths.{key} must stay under state/runtime-assets.") from error
            return resolved
        return _inside(root, paths.get(key), f"paths.{key}", file=file)

    owned_paths = {"probe": owned_path("probe", file=True), "maps": owned_path("maps", file=False),
                   "config": owned_path("config", file=True), "art": owned_path("art", file=False),
                   "catalog": owned_path("catalog", file=True), "font": owned_path("font", file=True)}
    probe_relative = owned_paths["probe"].relative_to(root)
    if (len(probe_relative.parts) != 2 or probe_relative.parts[0].casefold() != "bin" or
            probe_relative.name.casefold() != "bb-probe.exe"):
        raise BootstrapError("paths.probe must be Lite's bin/bb-probe.exe.")
    own_bin = root / "bin"
    pinned_own_bin = {path.resolve() for path in own_files.values() if path.parent.name.casefold() == "bin"}
    if own_bin.is_dir():
        unpinned = [path for path in own_bin.iterdir() if path.is_file() and
                    path.suffix.casefold() in {".dll", ".exe"} and path.resolve() not in pinned_own_bin]
        if unpinned:
            raise BootstrapError(f"Lite bin contains an unverified executable or DLL: {unpinned[0].name}.")
    for name in ("probe", "catalog", "font"):
        if asset_pack and name in {"catalog", "font"}:
            continue
        rel = owned_paths[name].relative_to(root).as_posix().casefold()
        if rel not in own_files:
            raise BootstrapError(f"Lite manifest does not hash its {name} file.")
    if not asset_pack and not any(path.relative_to(root).as_posix().casefold().startswith(
            owned_paths["art"].relative_to(root).as_posix().casefold().rstrip("/") + "/")
            for path in own_files.values()):
        raise BootstrapError("Lite manifest has no hashed files under paths.art.")

    generator = None
    if manifest.get("generator"):
        generator = _inside(root, manifest["generator"], "generator", file=True)
        if generator.relative_to(root).as_posix().casefold() not in own_files:
            raise BootstrapError("Lite generator must be covered by manifest.files.")
    return {"root": root, "config": config, "manifest": manifest, "own_files": own_files,
            "dependencies": deps, "base_root": base_root, "base_files": base_files,
            "launcher_variant": selected_variant, "launcher_hash": actual_launcher_hash,
            "base_bin_paths": bin_paths, "launcher": launcher, "run_script": run_script,
            "runner": runner, "entry": entry, "paths": owned_paths, "state_root": state_root,
            "generator": generator, "asset_pack": asset_pack}


def production_settings_path(environ: dict[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    appdata = env.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "bbport-launcher" / "settings.json"


def import_profile_once(state_root: Path, source: Path | None = None) -> Path:
    """Copy production launcher settings without modifying their source, exactly once."""
    profile = state_root / "profile"
    destination = profile / "settings.json"
    receipt = profile / "import-receipt.json"
    if receipt.exists():
        return destination
    source = source or production_settings_path()
    settings: dict[str, Any] = {}
    source_hash = None
    if source.is_file():
        try:
            raw = source.read_bytes()
            parsed = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise BootstrapError(f"Could not import existing launcher settings: {error}") from error
        if not isinstance(parsed, dict):
            raise BootstrapError("Existing launcher settings must contain a JSON object.")
        settings = parsed
        source_hash = hashlib.sha256(raw).hexdigest()
    else:
        settings = {"game_dir": "", "language": "1", "voice_language": "auto",
                    "fullscreen": False, "hdr": False, "present_mode": "Mailbox",
                    "fps_mode": "uncap", "frame_cap": "", "mods_enabled": True,
                    "atlas_enabled": False}
    # These are edition-owned destinations; importing stock output paths could overwrite ordinary runtime files.
    settings["user_dir"] = str(state_root / "user")
    settings["atlas_enabled"] = bool(settings.get("atlas_enabled", False))
    profile.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)
    _atomic_json(destination, settings)
    _atomic_json(receipt, {"schema": 1, "source_sha256": source_hash,
                           "imported_sha256": sha256_file(destination),
                           "imported_at_epoch": int(time.time())})
    return destination


def import_port_data_once(base_root: Path, state_root: Path) -> None:
    """Copy the ordinary launcher's editable graphics/input/mod settings into Lite once."""
    receipt = state_root / "profile" / "port-data-import-receipt.json"
    if receipt.exists():
        return
    copied: dict[str, str] = {}
    for name in ("bbport.ini", "input.ini", "mods.json", "patches.json"):
        source = base_root / name
        target = state_root / name
        if not source.is_file() or target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = source.read_bytes()
        target.write_bytes(raw)
        copied[name] = hashlib.sha256(raw).hexdigest()
    _atomic_json(receipt, {"schema": 1, "copied_sha256": copied,
                           "imported_at_epoch": int(time.time())})


def _atomic_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def load_profile(path: Path) -> dict[str, Any]:
    value = _json_object(path, "Lite profile")
    return value


def _truth(value: Any) -> bool:
    return value is True or str(value).strip().casefold() in {"1", "true", "yes", "on"}


def _ini_value(path: Path, key: str) -> str | None:
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            match = re.fullmatch(rf"{re.escape(key)}=(.*)", line.strip())
            if match:
                return match.group(1)
    except OSError:
        pass
    return None


def game_environment(contract: dict[str, Any], profile: dict[str, Any],
                     inherited: dict[str, str] | None = None, *, qa_timeout: int | None = None,
                     qa_control_dir: str | os.PathLike[str] | None = None) -> dict[str, str]:
    """Translate standard launcher preferences to a child-only, Lite-isolated environment."""
    env = dict(os.environ if inherited is None else inherited)
    for key in tuple(env):
        canonical = key.upper()
        if (canonical.startswith("BB_MAP_") or canonical.startswith("BB_ATLAS") or canonical == "BB_PROBE"
                or canonical in {"BB_PAD_FILE", "BB_DUMP_DIR", "BB_LITE_QA_CONTROL_DIR"}):
            env.pop(key, None)

    state, root, paths = contract["state_root"], contract["root"], contract["paths"]
    data_dir = state
    user_dir = state / "user"
    mods_dir = Path(str(profile.get("mods_dir") or data_dir / "mods"))
    # XML definitions are read-only dependencies of the verified ordinary port.
    # The enable/disable selection stays private in state/patches.json. Pointing
    # at an empty private directory silently drops enabled patches, including DLC.
    patches_dir = Path(str(profile.get("patches_dir") or contract["base_root"] / "patches"))
    env.update({
        "BB_GAME_DIR": str(profile.get("game_dir", "")),
        "BB_DATA_DIR": str(data_dir),
        "BB_CONFIG": str(data_dir / "bbport.ini"),
        "BB_USER_DIR": str(user_dir),
        "BB_GPU_USER_DIR": str(user_dir),
        "BB_INPUT_CONFIG": str(data_dir / "input.ini"),
        "BB_MODS_DIR": str(mods_dir),
        "BB_MODS_CONFIG": str(data_dir / "mods.json"),
        "BB_MODS_ENABLED": "1" if _truth(profile.get("mods_enabled", True)) else "0",
        "BB_PATCHES_DIR": str(patches_dir),
        "BB_PATCHES_CONFIG": str(data_dir / "patches.json"),
        "BB_PROBE": str(paths["probe"]),
        "BB_MAP_DIR": str(paths["maps"]),
        "BB_MAP_CONFIG": str(paths["config"]),
        "BB_MAP_CATALOG": str(paths["catalog"]),
        "BB_MAP_ART_DIR": str(paths["art"]),
        "BB_MAP_FONT": str(paths["font"]),
        "BB_ATLAS_ENABLED": "1" if _truth(profile.get("atlas_enabled")) else "0",
        "BB_MAP_QA": "0",
        "BB_ATLAS_QA": "0",
        "BB_ENTER_BUTTON": "0" if _ini_value(data_dir / "bbport.ini", "tweak_circle_confirm") == "1" else "1",
        "BB_LAUNCHER_SETTINGS_ROOT": str(state / "profile"),
        "BB_LITE_PORT_DIR": str(contract["base_root"]),
        "BB_LITE_ENTRY": str(contract["entry"]),
        "BB_LITE_BOOTSTRAP_PID": str(os.getpid()),
        "BB_LITE_MINIMUM_DISK": "1" if contract["config"].get("compact_prepared_cache", False) else "0",
        # run.py's developer fallback prepends MSYS2 when the probe's own folder
        # lacks SDL3.dll. This private nonexistent root disables that fallback;
        # the child PATH contains only the verified Lite/base DLL folders.
        "MSYS2_ROOT": str(root / ".disabled-msys2-fallback"),
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
    })
    direct = {
        "language": "BB_LANGUAGE", "voice_language": "BB_VOICE_LANGUAGE",
        "fullscreen": "BB_FULLSCREEN", "present_mode": "BB_PRESENT_MODE",
        "fps_mode": "BB_FPS", "frame_cap": "BB_FPS_LIMIT",
        "draw_pipe": "BB_DRAW_PIPE", "readbacks": "BB_READBACKS",
        "frames_ahead": "BB_FRAMES_AHEAD",
    }
    for key, target in direct.items():
        value = profile.get(key)
        if value is None or value == "":
            continue
        if key in ("fullscreen",):
            value = "1" if _truth(value) else "0"
        env[target] = str(value)
    for key, target in (("hdr", "BB_HDR"), ("frame_stats", "BB_FRAME_STATS"),
                        ("gpu_profile", "BB_GPU_PROFILE"), ("vk_validation", "BB_VK_VALIDATION")):
        if _truth(profile.get(key)):
            env[target] = "1"
        else:
            env.pop(target, None)
    if profile.get("dlc_dir"):
        env["BB_DLC_DIR"] = str(profile["dlc_dir"])
    else:
        env.pop("BB_DLC_DIR", None)
    if str(profile.get("player_name", "")).strip():
        env["BB_USER_NAME"] = str(profile["player_name"]).strip()
    else:
        env.pop("BB_USER_NAME", None)

    for item in str(profile.get("extra_env", "")).split():
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        if key.upper() not in RESERVED_EXTRA_ENV and not key.upper().startswith(("BB_MAP_", "BB_ATLAS", "BB_LITE_")):
            env[key] = value
    if _truth(profile.get("online")):
        server = str(profile.get("online_server") or "srv.shadps4.net:31313").strip()
        community = str(profile.get("online_community") or "https://thehuntersdream.com").strip()
        scheme, separator, rest = community.rpartition("://")
        community_host = rest.split("/")[0].split(":")[0] if separator else community.split("/")[0]
        community_url = f"{scheme or 'https'}://{community_host}"
        webapi = str(profile.get("online_webapi") or "").strip()
        if community_host and community_host in webapi:
            webapi = ""
        if not webapi:
            host = server.rsplit(":", 1)[0] if server.count(":") == 1 else server
            webapi = f"http://{host}:31315"
        env["BB_SHADNET_SERVER"] = server
        env["BB_SHADNET_WEBAPI"] = webapi
        env["BB_COMMUNITY_SERVER"] = community_url
        env["BB_SHADNET_NPID"] = str(profile.get("online_npid", "")).strip()
        env["BB_SHADNET_PASSWORD"] = str(profile.get("online_password", ""))
        env["BB_ONLINE"] = "1"
        env["BB_UPNP"] = "1" if _truth(profile.get("online_upnp", True)) else "0"
        if profile.get("online_pool") == "huntersdream":
            env["BB_BRIDGE"] = "1"
            env["BB_BRIDGE_LIVE_MAP"] = "1" if _truth(profile.get("bridge_live_map", True)) else "0"
            env["BB_SHADNET_NPID"] = ""
            env["BB_SHADNET_PASSWORD"] = ""
        else:
            env.pop("BB_BRIDGE", None)
            env.pop("BB_BRIDGE_LIVE_MAP", None)
    else:
        for key in ("BB_ONLINE", "BB_SHADNET_SERVER", "BB_SHADNET_WEBAPI", "BB_SHADNET_NPID",
                    "BB_SHADNET_PASSWORD", "BB_COMMUNITY_SERVER", "BB_UPNP", "BB_BRIDGE",
                    "BB_BRIDGE_LIVE_MAP"):
            env.pop(key, None)

    system_root = Path(env.get("SystemRoot", r"C:\Windows"))
    system32 = system_root / "System32"
    private_bin = root / "bin"
    base_bins = {path.parent for path in contract["base_bin_paths"]}
    path_parts = [str(system32)]
    if private_bin.is_dir():
        path_parts.insert(0, str(private_bin))
    path_parts.extend(str(path) for path in sorted(base_bins, key=lambda p: str(p).casefold()))
    env["PATH"] = os.pathsep.join(dict.fromkeys(path_parts))

    if qa_timeout is not None:
        if not contract["config"].get("qa_enabled"):
            raise BootstrapError("--qa-timeout requires bootstrap/config.json qa_enabled=true.")
        if qa_timeout < 1 or qa_timeout > 86400:
            raise BootstrapError("QA timeout must be between 1 and 86400 seconds.")
        env["BB_TIMEOUT"] = str(qa_timeout)
        env["BB_ATLAS_QA"] = "1"
        env["BB_MAP_QA"] = "1"
        env["BB_LITE_QA_TIMEOUT"] = str(qa_timeout)
    else:
        env.pop("BB_TIMEOUT", None)
        env.pop("BB_LITE_QA_TIMEOUT", None)
    if qa_control_dir is not None:
        if not contract["config"].get("qa_enabled"):
            raise BootstrapError("--qa-control-dir requires bootstrap/config.json qa_enabled=true.")
        raw_qa_dir = Path(qa_control_dir).expanduser()
        qa_root = (state / "qa").resolve(strict=False)
        qa_dir = raw_qa_dir.resolve(strict=False) if raw_qa_dir.is_absolute() else (qa_root / raw_qa_dir).resolve(strict=False)
        try:
            qa_dir.relative_to(qa_root)
        except ValueError as error:
            raise BootstrapError("QA control directory must stay inside Lite state/qa.") from error
        env["BB_ATLAS_QA"] = "1"
        env["BB_MAP_QA"] = "1"
        env["BB_MAP_TEST_CONTROL"] = str(qa_dir / "control.txt")
        env["BB_MAP_TEST_TRACE"] = str(qa_dir / "trace.json")
        env["BB_MAP_UI_DUMP_TRIGGER"] = str(qa_dir / "capture.trigger")
        env["BB_DUMP_DIR"] = str(qa_dir / "captures")
        env["BB_LITE_QA_CONTROL_DIR"] = str(qa_dir)
        pad_file = qa_dir / "pad.txt"
        if pad_file.is_file():
            env["BB_PAD_FILE"] = str(pad_file)
    return env


def _redacted_env(env: dict[str, str]) -> dict[str, str]:
    return {key: ("<redacted>" if key.upper() in SECRET_KEYS or any(
                      marker in key.upper() for marker in ("PASSWORD", "TOKEN", "NPID", "ACCOUNT"))
                  else value) for key, value in sorted(env.items()) if key.upper().startswith(("BB_", "PATH"))}


def _redact_output(line: bytes, env: dict[str, str]) -> bytes:
    for key, value in env.items():
        if value and (key.upper() in SECRET_KEYS or any(
                marker in key.upper() for marker in ("PASSWORD", "TOKEN", "NPID", "ACCOUNT"))):
            line = line.replace(value.encode("utf-8", errors="ignore"), b"<redacted>")
    return line


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        # On Windows, os.kill(pid, 0) is not a harmless liveness probe: CPython
        # implements non-console signals through TerminateProcess. Query a
        # synchronization handle instead, which never signals the target.
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        open_process = kernel32.OpenProcess
        open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        open_process.restype = wintypes.HANDLE
        get_exit_code = kernel32.GetExitCodeProcess
        get_exit_code.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        get_exit_code.restype = wintypes.BOOL
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = (wintypes.HANDLE,)
        close_handle.restype = wintypes.BOOL

        # PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE
        handle = open_process(0x1000 | 0x00100000, False, pid)
        if not handle:
            # Access denied means the process exists but belongs to another
            # security context. ERROR_INVALID_PARAMETER means no such PID.
            return ctypes.get_last_error() != 87
        try:
            exit_code = wintypes.DWORD()
            if not get_exit_code(handle, ctypes.byref(exit_code)):
                return True  # Conservative: inability to query is not proof of exit.
            return exit_code.value == 259  # STILL_ACTIVE
        finally:
            close_handle(handle)
    try:
        os.kill(pid, 0)
    except OSError as error:
        return error.errno == 1  # EPERM: process exists but is not ours to inspect.
    return True


def wait_for_pid(pid: int) -> None:
    """Wait for a previous Lite bootstrap process before a restart takes its lock."""
    if pid <= 0 or not _pid_alive(pid):
        return
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        open_process = kernel32.OpenProcess
        open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        open_process.restype = wintypes.HANDLE
        wait_for_single_object = kernel32.WaitForSingleObject
        wait_for_single_object.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        wait_for_single_object.restype = wintypes.DWORD
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = (wintypes.HANDLE,)
        close_handle.restype = wintypes.BOOL
        handle = open_process(0x00100000, False, pid)
        if handle:
            try:
                result = wait_for_single_object(handle, 0xFFFFFFFF)
                if result != 0:
                    raise BootstrapError(f"Could not wait for the previous Lite session (PID {pid}).")
            finally:
                close_handle(handle)
            return
    while _pid_alive(pid):
        time.sleep(0.25)


def _report_startup_error(root: Path | None, message: str) -> None:
    if root is not None:
        try:
            base = root.resolve(strict=True)
            state = root / "state"
            if not state.is_symlink() and not getattr(state, "is_junction", lambda: False)():
                target = state.resolve(strict=False)
                target.relative_to(base)
                target.mkdir(parents=True, exist_ok=True)
                with (target / "bootstrap-error.log").open("a", encoding="utf-8") as stream:
                    stream.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
        except (OSError, ValueError, RuntimeError):
            pass
    if getattr(sys, "frozen", False):
        try:
            import tkinter as tk
            from tkinter import messagebox
            window = tk.Tk()
            window.withdraw()
            messagebox.showerror("Hunter's Atlas Lite", message, parent=window)
            window.destroy()
            return
        except Exception:
            pass
    print(f"Hunter's Atlas Lite: {message}", file=sys.stderr)


class SessionLock:
    """Exclusive Lite session marker with conservative stale-PID recovery."""
    def __init__(self, path: Path):
        self.path = path
        self.owned = False

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    state = json.loads(self.path.read_text(encoding="utf-8"))
                    pid = int(state.get("pid", -1))
                except (OSError, ValueError, TypeError, AttributeError):
                    pid = -1
                if pid > 0 and _pid_alive(pid):
                    raise BootstrapError(f"Hunter's Atlas Lite already has an active session (PID {pid}).")
                try:
                    self.path.unlink()
                except OSError as error:
                    raise BootstrapError(f"Could not clear a stale Lite session lock: {error}") from error
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump({"pid": os.getpid(), "started_at_epoch": int(time.time())}, stream)
            self.owned = True
            return self
        raise BootstrapError("Could not acquire the Lite session lock.")

    def __exit__(self, *_exc):
        if self.owned:
            try:
                state = json.loads(self.path.read_text(encoding="utf-8"))
                if int(state.get("pid", -1)) == os.getpid():
                    self.path.unlink(missing_ok=True)
            except (OSError, ValueError, TypeError, AttributeError):
                pass


def _windows_process_names(kernel32: Any | None = None) -> list[tuple[str, int]]:
    """Read the process list through Toolhelp without opening/signalling game processes."""
    import ctypes
    from ctypes import wintypes

    api = kernel32 or ctypes.WinDLL("kernel32", use_last_error=True)

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260),
        ]

    snapshot = api.CreateToolhelp32Snapshot
    snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    snapshot.restype = wintypes.HANDLE
    first = api.Process32FirstW
    first.argtypes = (wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
    first.restype = wintypes.BOOL
    following = api.Process32NextW
    following.argtypes = (wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
    following.restype = wintypes.BOOL
    close = api.CloseHandle
    close.argtypes = (wintypes.HANDLE,)
    close.restype = wintypes.BOOL

    handle = snapshot(0x00000002, 0)  # TH32CS_SNAPPROCESS
    if not handle or handle == ctypes.c_void_p(-1).value:
        raise BootstrapError("Could not inspect running game processes safely.")
    result: list[tuple[str, int]] = []
    try:
        item = PROCESSENTRY32W()
        item.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if not first(handle, ctypes.byref(item)):
            if ctypes.get_last_error() == 18:  # ERROR_NO_MORE_FILES
                return result
            raise BootstrapError("Could not enumerate running game processes safely.")
        while True:
            result.append((str(item.szExeFile), int(item.th32ProcessID)))
            if not following(handle, ctypes.byref(item)):
                if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES
                    raise BootstrapError("Could not finish enumerating running game processes safely.")
                break
        return result
    finally:
        close(handle)


def ensure_no_game_processes(*, process_names: set[str] | None = None,
                             enumerator: Any | None = None) -> None:
    """Refuse a second edition while a known game probe is running; never terminate it."""
    if os.name != "nt" and enumerator is None:
        return
    names = {name.casefold() for name in (process_names or {"bb-probe.exe", "bb-play.exe"})}
    running = (enumerator or _windows_process_names)()
    conflicts = [(name, pid) for name, pid in running if name.casefold() in names]
    if conflicts:
        names_and_pids = ", ".join(f"{name} (PID {pid})" for name, pid in conflicts)
        raise BootstrapError(f"A Bloodborne game process is already running: {names_and_pids}.")


def _generator_command(contract: dict[str, Any]) -> list[str]:
    generator = contract.get("generator")
    if generator is None:
        raise BootstrapError("Lite manifest does not yet define a hash-verified generator.")
    if generator.suffix.casefold() == ".py":
        return [str(contract["launcher"]), "--script", str(generator)]
    return [str(generator)]


def _materialized_asset_paths(contract: dict[str, Any]):
    packed = contract.get("asset_pack")
    if not packed:
        return nullcontext(contract["paths"])
    import importlib.util
    spec = importlib.util.spec_from_file_location("atlas_lite_assets", packed["manager"])
    if spec is None or spec.loader is None:
        raise BootstrapError("Could not load the hash-verified Lite asset manager.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    materialize = getattr(module, "materialize", None)
    if not callable(materialize):
        raise BootstrapError("bootstrap/assets.py must expose materialize(contract).")
    return materialize(contract)


def _validated_materialized_paths(contract: dict[str, Any], paths: object) -> dict[str, Path]:
    required = {"maps", "art", "catalog", "font"}
    if not isinstance(paths, dict) or set(paths) not in (required, required | {"probe"}):
        raise BootstrapError("Asset manager must return maps, art, catalog, font, and optionally probe paths.")
    state_root = contract["state_root"].resolve(strict=True)
    result: dict[str, Path] = {}
    session_root_name: str | None = None
    for key, is_file in (("maps", False), ("art", False), ("catalog", True), ("font", True)):
        try:
            path = Path(paths[key]).resolve(strict=True)
            relative = path.relative_to(state_root)
        except (OSError, TypeError, ValueError, RuntimeError) as error:
            raise BootstrapError(f"Materialized {key} path is missing or outside the Lite state folder.") from error
        if not relative.parts or not relative.parts[0].casefold().startswith("session-assets-"):
            raise BootstrapError(f"Materialized {key} path must stay in a temporary Lite session-assets folder.")
        if session_root_name is None:
            session_root_name = relative.parts[0]
        elif relative.parts[0] != session_root_name:
            raise BootstrapError("Materialized assets must share one temporary session folder.")
        if is_file and not path.is_file():
            raise BootstrapError(f"Materialized {key} path must be a file.")
        if not is_file and not path.is_dir():
            raise BootstrapError(f"Materialized {key} path must be a directory.")
        result[key] = path
    if "probe" in paths:
        raw_probe = Path(paths["probe"])
        cursor = raw_probe
        while cursor != cursor.parent:
            if cursor.is_symlink() or getattr(cursor, "is_junction", lambda: False)():
                raise BootstrapError("Materialized probe must not traverse a symlink or junction.")
            cursor = cursor.parent
        try:
            probe = raw_probe.resolve(strict=True)
            relative = probe.relative_to(state_root)
        except (OSError, TypeError, ValueError, RuntimeError) as error:
            raise BootstrapError("Materialized probe is missing or outside the Lite state folder.") from error
        if (not relative.parts or relative.parts[0] != session_root_name or len(relative.parts) != 3 or
                relative.parts[1].casefold() != "bin" or relative.parts[2].casefold() != "bb-probe.exe" or
                not probe.is_file()):
            raise BootstrapError("Materialized probe must be bin/bb-probe.exe in the shared session-assets folder.")
        verified_probe = contract["paths"]["probe"]
        if sha256_file(probe) != sha256_file(verified_probe):
            raise BootstrapError("Materialized probe SHA-256 does not match the verified Lite probe.")
        result["probe"] = probe
    return result


def _run_generator(contract: dict[str, Any]) -> int:
    return subprocess.run(_generator_command(contract), cwd=str(contract["root"]), check=False,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode


def show_settings(profile_path: Path, contract: dict[str, Any]) -> int:
    """Small Lite-only settings window: game folder and Atlas toggle."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    profile = load_profile(profile_path)
    window = tk.Tk()
    window.title("Hunter's Atlas Lite")
    window.geometry("580x190")
    window.minsize(480, 170)
    frame = ttk.Frame(window, padding=16)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Bloodborne game folder").grid(row=0, column=0, sticky="w")
    game_var = tk.StringVar(value=str(profile.get("game_dir", "")))
    ttk.Entry(frame, textvariable=game_var).grid(row=1, column=0, sticky="ew", pady=(4, 10))
    def browse():
        chosen = filedialog.askdirectory(title="Choose the Bloodborne game folder",
                                         initialdir=game_var.get() or None)
        if chosen:
            game_var.set(chosen)
    ttk.Button(frame, text="Browse…", command=browse).grid(row=1, column=1, padx=(8, 0))
    enabled_var = tk.BooleanVar(value=_truth(profile.get("atlas_enabled")))
    ttk.Checkbutton(frame, text="Enable Hunter's Atlas map", variable=enabled_var).grid(
        row=2, column=0, sticky="w", pady=(0, 12))
    buttons = ttk.Frame(frame)
    buttons.grid(row=3, column=0, columnspan=2, sticky="ew")
    ttk.Label(frame, text="Settings and saves are stored in the Lite profile.").grid(
        row=4, column=0, columnspan=2, sticky="w", pady=(12, 0))
    frame.columnconfigure(0, weight=1)
    def save():
        profile["game_dir"] = game_var.get().strip()
        profile["atlas_enabled"] = bool(enabled_var.get())
        _atomic_json(profile_path, profile)
        messagebox.showinfo("Hunter's Atlas Lite", "Lite settings saved.", parent=window)
    ttk.Button(buttons, text="Save", command=save).pack(side="left")
    def prepare():
        generator = contract.get("generator")
        if generator is None:
            messagebox.showinfo("Hunter's Atlas Lite",
                                "Map preparation is available when the Lite generator is packaged.",
                                parent=window)
            return
        try:
            result = subprocess.run(_generator_command(contract), cwd=str(contract["root"]), check=False,
                                    capture_output=True, text=True, encoding="utf-8", errors="replace")
        except OSError as error:
            messagebox.showerror("Hunter's Atlas Lite", f"Could not start map preparation: {error}",
                                 parent=window)
            return
        detail = (result.stdout + result.stderr).strip()[-3000:]
        if result.returncode == 0:
            messagebox.showinfo("Hunter's Atlas Lite", "Map preparation completed.\n" + detail, parent=window)
        else:
            messagebox.showerror("Hunter's Atlas Lite",
                                 f"Map preparation failed (exit {result.returncode}).\n{detail}", parent=window)
    ttk.Button(buttons, text="Prepare maps…", command=prepare).pack(side="left", padx=8)
    ttk.Button(buttons, text="Close", command=window.destroy).pack(side="right")
    window.mainloop()
    return 0


def _launch(contract: dict[str, Any], profile: dict[str, Any], *, dry_run: bool = False,
            qa_timeout: int | None = None, qa_control_dir: str | os.PathLike[str] | None = None) -> int:
    if not dry_run:
        validate_game_source(contract, profile)
    state = contract["state_root"]
    state.mkdir(parents=True, exist_ok=True)
    for name in ("out", "user"):
        (state / name).mkdir(parents=True, exist_ok=True)
    log_path = state / "last_run.log"
    if dry_run:
        env = game_environment(contract, profile, qa_timeout=qa_timeout, qa_control_dir=qa_control_dir)
        print(json.dumps({"edition": "Lite", "launcher": str(contract["launcher"]),
                          "command": [str(contract["launcher"]), "--script", str(contract["runner"])],
                          "environment": _redacted_env(env)}, ensure_ascii=False, indent=2))
        return 0
    with SessionLock(state / "session.lock"):
        with _materialized_asset_paths(contract) as active_paths:
            if contract.get("asset_pack"):
                active_paths = _validated_materialized_paths(contract, active_paths)
            # The asset manager returns only the four staged map/art paths.
            # Keep the already verified Lite probe and config paths in place.
            launch_contract = {**contract, "paths": {**contract["paths"], **active_paths}}
            env = game_environment(launch_contract, profile, qa_timeout=qa_timeout,
                                   qa_control_dir=qa_control_dir)
            if qa_control_dir is not None:
                Path(env["BB_MAP_TEST_CONTROL"]).parent.mkdir(parents=True, exist_ok=True)
                env["BB_DUMP_DIR"] and Path(env["BB_DUMP_DIR"]).mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as log:
                log.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Lite launch\n")
                log.flush()
                process = subprocess.Popen([str(contract["launcher"]), "--script", str(contract["runner"])],
                                           cwd=str(contract["base_root"]), env=env,
                                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                assert process.stdout is not None
                for line in iter(process.stdout.readline, b""):
                    log.write(_redact_output(line, env).decode("utf-8", errors="replace"))
                    log.flush()
                process.stdout.close()
                return process.wait()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hunter's Atlas Lite bootstrap")
    parser.add_argument("--settings", action="store_true", help="open Lite profile settings")
    parser.add_argument("--prepare", action="store_true", help="run the Lite-owned map generator")
    parser.add_argument("--dry-run", action="store_true", help="print the sanitized Lite launch contract")
    parser.add_argument("--qa-timeout", type=int, help="set a bounded timeout for an explicitly enabled QA run")
    parser.add_argument("--after", type=int, help="wait for the prior Lite bootstrap process before restart")
    parser.add_argument("--qa-control-dir", help="enable map QA hooks in a directory under Lite state/qa")
    args = parser.parse_args(argv)
    root = None
    try:
        root = Path(__file__).resolve().parents[1]
        contract = load_contract(root)
        if args.after is not None:
            wait_for_pid(args.after)
        profile_path = import_profile_once(contract["state_root"])
        import_port_data_once(contract["base_root"], contract["state_root"])
        if args.settings:
            return show_settings(profile_path, contract)
        if args.prepare:
            return _run_generator(contract)
        profile = load_profile(profile_path)
        if not args.dry_run:
            ensure_no_game_processes()
        return _launch(contract, profile, dry_run=args.dry_run, qa_timeout=args.qa_timeout,
                       qa_control_dir=args.qa_control_dir)
    except BootstrapError as error:
        _report_startup_error(root, str(error))
        return 2
    except Exception as error:
        _report_startup_error(root, f"Startup failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
