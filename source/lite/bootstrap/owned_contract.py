"""Validation for Atlas's self-contained, in-game runtime installation.

No path in this contract is resolved against an installed upstream launcher.
The ordinary_port name is retained for the existing preparation/run interfaces;
its contents are now immutable files owned by the Atlas package.
"""
from __future__ import annotations

from pathlib import Path
import stat
from typing import Any


MODEL = "owned-runtime-v1"
RELEASE = "windows-v1.9"
COMMIT = "652f9a494c47cc8c1ab16f28b456372eaa8103f8"


def load_contract(root: Path, config: dict[str, Any], core: Any) -> dict[str, Any]:
    """Validate the owned installation and return the existing launch contract."""
    Error = core.BootstrapError

    def reject_reparse(path: Path, label: str) -> None:
        try:
            info = path.lstat()
        except FileNotFoundError:
            return
        # is_junction is unavailable on the bundled Python 3.10. The Windows
        # reparse attribute also catches junctions and other redirection types.
        if (stat.S_ISLNK(info.st_mode) or
                getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise Error(f"{label} must not traverse a symlink, junction, or reparse point.")

    reject_reparse(root, "Atlas root")
    root = root.resolve(strict=True)

    def inside(base: Path, raw: object, label: str, *, file: bool | None = None) -> Path:
        relative = core._relative(raw, label)
        cursor = base
        reject_reparse(cursor, label)
        for part in relative.parts:
            cursor = cursor / part
            reject_reparse(cursor, label)
        return core._inside(base, raw, label, file=file)

    def hash_table(base: Path, table: object, label: str) -> dict[str, Path]:
        if isinstance(table, dict):
            for raw in table:
                inside(base, raw, label, file=True)
        return core._hash_table(base, table, label)

    if (config.get("schema") != 1 or config.get("edition") != "Atlas" or
            config.get("installation_model") != MODEL):
        raise Error("Unsupported Atlas owned installation schema or model.")
    manifest_path = inside(root, config.get("manifest", "manifest.json"), "manifest", file=True)
    manifest = core._json_object(manifest_path, "Atlas manifest")
    if (manifest.get("schema") != 1 or manifest.get("id") != core.MANIFEST_ID or
            manifest.get("installation_model") != MODEL):
        raise Error("Unsupported Atlas owned manifest identity, schema, or model.")
    if manifest.get("runtime_pending"):
        raise Error("Atlas runtime update is pending; finish recovery before starting the game.")
    if manifest.get("game_executables") != [core.SUPPORTED_GAME_SHA256]:
        raise Error("Unsupported Atlas game fingerprint declaration.")
    own_files = hash_table(root, manifest.get("files"), "manifest.files")

    def pinned(raw: object, label: str) -> Path:
        path = inside(root, raw, label, file=True)
        if own_files.get(path.relative_to(root).as_posix().casefold()) != path:
            raise Error(f"{label} must be hash-pinned in manifest.files.")
        return path

    config_path = pinned("bootstrap/config.json", "bootstrap config")
    if core._json_object(config_path, "bootstrap config") != config:
        raise Error("Bootstrap config changed during contract validation.")
    deps_path = pinned(config.get("dependencies", "dependencies.json"), "dependencies manifest")
    deps = core._json_object(deps_path, "dependencies manifest")
    if deps.get("schema") != 1 or deps.get("id") != core.DEPENDENCIES_ID:
        raise Error("Unsupported Atlas owned dependencies identity or schema.")
    ordinary = deps.get("ordinary_port")
    runtime = deps.get("owned_runtime")
    if not isinstance(ordinary, dict) or not isinstance(runtime, dict):
        raise Error("Owned dependencies must declare ordinary_port and owned_runtime objects.")
    if runtime.get("schema") != 1 or runtime.get("upstream_release") != RELEASE:
        raise Error("Unsupported Atlas owned runtime schema or release.")
    if ordinary.get("root") != "runtime/port":
        raise Error("Owned ordinary_port.root must be runtime/port inside Atlas.")
    base_root = inside(root, ordinary["root"], "owned port root", file=False)
    base_files = hash_table(base_root, ordinary.get("files"), "dependencies.ordinary_port.files")
    for path in base_files.values():
        pinned(path.relative_to(root).as_posix(), "owned port dependency")
    roles = ordinary.get("roles")
    if not isinstance(roles, dict):
        raise Error("dependencies.ordinary_port.roles must be an object.")
    run_relative = core._relative(roles.get("run_script"), "run_script").as_posix().casefold()
    if run_relative != "run.py" or run_relative not in base_files:
        raise Error("Owned run_script must be the hash-pinned runtime/port/run.py.")
    run_script = base_files[run_relative]

    def runtime_file(key: str, expected: str) -> Path:
        if runtime.get(key) != expected:
            raise Error(f"owned_runtime.{key} must be {expected}.")
        return pinned(runtime[key], f"owned_runtime.{key}")

    python = runtime_file("python", "runtime/python/python.exe")
    pythonw = runtime_file("pythonw", "runtime/python/pythonw.exe")
    ui = runtime_file("ui", "integration/ui/bbport_launcher_win.py")
    entry = pinned("bootstrap/entry.py", "entrypoint")
    runner = pinned(config.get("runner", "bootstrap/run_lite.py"), "runner")
    source_receipt = pinned("bootstrap/run_lite-source.json", "run_lite source receipt")
    receipt = core._json_object(source_receipt, "run_lite source receipt")
    if (receipt.get("schema") != 1 or receipt.get("source_sha256") != core.sha256_file(run_script) or
            receipt.get("copy_sha256") != core.sha256_file(runner)):
        raise Error("run_lite source receipt does not match the owned run.py and Atlas copy.")

    # A complete allowlist prevents a forgotten DLL, Python module or native
    # extension from silently changing the tested dependency closure.
    immutable_trees = ("bin", "bootstrap", "integration", "runtime", "tools", "owned")
    for directory in immutable_trees:
        tree = root / directory
        if not tree.exists():
            continue
        reject_reparse(tree, "owned runtime tree")
        for path in tree.rglob("*"):
            reject_reparse(path, "owned runtime tree")
            if path.is_file() and path.relative_to(root).as_posix().casefold() not in own_files:
                raise Error(f"Owned runtime contains an unverified file: {path.relative_to(root)}.")
    actual_base = {path.relative_to(base_root).as_posix().casefold()
                   for path in base_root.rglob("*") if path.is_file()}
    if actual_base != set(base_files):
        raise Error("Owned port files do not exactly match dependencies.ordinary_port.files.")

    paths = manifest.get("paths")
    if not isinstance(paths, dict):
        raise Error("Atlas manifest must define its owned runtime paths.")
    probe = pinned(paths.get("probe"), "paths.probe")
    if probe.relative_to(root).as_posix().casefold() != "bin/bb-probe.exe":
        raise Error("paths.probe must be Atlas's bin/bb-probe.exe.")
    pinned("bin/bb-gpu-capabilities.exe", "GPU capabilities helper")
    declared = manifest.get("compatibility")
    dependency_compat = deps.get("compatibility")
    proof = core._json_object(pinned("native-build.json", "native build proof"), "native build proof")
    for label, identity in (("manifest", declared), ("dependencies", dependency_compat), ("native build", proof)):
        if (not isinstance(identity, dict) or identity.get("adapter_protocol") != 1 or
                identity.get("upstream_release") != RELEASE or identity.get("upstream_commit") != COMMIT):
            raise Error(f"Unsupported or mixed Atlas {label} compatibility identity.")
    if proof.get("runtime_sha256") != core.sha256_file(probe):
        raise Error("Atlas native build digest mismatch.")

    state_relative = core._relative(config.get("state_dir", "state"), "state_dir")
    if state_relative.parts[0].casefold() in immutable_trees:
        raise Error("state_dir must not be inside an immutable runtime tree.")
    state_root = root.joinpath(*state_relative.parts)
    cursor = root
    for part in state_relative.parts:
        cursor = cursor / part
        reject_reparse(cursor, "state_dir")
    state_root = state_root.resolve(strict=False)
    try:
        state_root.relative_to(root)
    except ValueError as error:
        raise Error("state_dir must stay inside Atlas.") from error
    for path in own_files.values():
        if state_root == path or state_root in path.parents:
            raise Error("state_dir must not contain immutable manifest files.")

    asset_pack = None
    raw_pack = manifest.get("asset_pack")
    if raw_pack is not None:
        if not isinstance(raw_pack, dict):
            raise Error("manifest.asset_pack must be an object.")
        pack = pinned(raw_pack.get("path"), "asset_pack.path")
        if raw_pack.get("sha256") != core.sha256_file(pack):
            raise Error("Atlas asset pack SHA-256 does not match its manifest entry.")
        manager = pinned("bootstrap/assets.py", "asset manager")
        asset_pack = {"path": pack, "sha256": raw_pack["sha256"], "manager": manager}

    def asset_path(key: str, *, file: bool) -> Path:
        if asset_pack and key in {"maps", "art", "catalog", "font"}:
            relative = core._relative(paths.get(key), f"paths.{key}")
            future = root.joinpath(*relative.parts)
            cursor = root
            for part in relative.parts:
                cursor = cursor / part
                reject_reparse(cursor, f"paths.{key}")
            resolved = future.resolve(strict=False)
            try:
                resolved.relative_to(state_root / "runtime-assets")
            except ValueError as error:
                raise Error(f"Packed paths.{key} must stay under state/runtime-assets.") from error
            return resolved
        if key in {"catalog", "font"}:
            return pinned(paths.get(key), f"paths.{key}")
        return inside(root, paths.get(key), f"paths.{key}", file=file)

    owned_paths = {"probe": probe, "config": asset_path("config", file=True),
                   "maps": asset_path("maps", file=False), "art": asset_path("art", file=False),
                   "catalog": asset_path("catalog", file=True), "font": asset_path("font", file=True)}
    if not asset_pack:
        for key in ("maps", "art"):
            tree = owned_paths[key]
            contents = [path for path in tree.rglob("*") if path.is_file()]
            if not contents:
                raise Error(f"Atlas manifest has no hashed files under paths.{key}.")
            for path in contents:
                pinned(path.relative_to(root).as_posix(), f"paths.{key} file")
    generator = pinned(manifest["generator"], "generator") if manifest.get("generator") else None
    return {"root": root, "config": config, "manifest": manifest, "own_files": own_files,
            "dependencies": deps, "base_root": base_root, "base_files": base_files,
            "base_bin_paths": [path for path in base_files.values()
                               if path.suffix.casefold() == ".dll" and path.parent.name.casefold() == "bin"],
            "launcher": python, "launcher_hash": core.sha256_file(python),
            "launcher_variant": {"path": runtime["python"], "owned_runtime": True},
            "run_script": run_script, "runner": runner, "entry": entry,
            "paths": owned_paths, "state_root": state_root, "generator": generator,
            "asset_pack": asset_pack, "owned_runtime": True, "python": python,
            "pythonw": pythonw, "ui": ui}
