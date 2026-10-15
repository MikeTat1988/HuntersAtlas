"""Headless first-install map preparation for a packaged Hunter's Atlas."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from types import ModuleType
from typing import Any, Callable


class PreparationCancelled(RuntimeError):
    """Raised when the installer requests cancellation before commit."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load packaged module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _inside(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _resolve_game_dir(path: Path) -> Path:
    game = path.expanduser().resolve(strict=True)
    if not (game / "dvdroot_ps4").is_dir() and (game / "Image0" / "dvdroot_ps4").is_dir():
        game = game / "Image0"
    return game


def _is_cancelled(cancel_file: Path | None) -> bool:
    return cancel_file is not None and cancel_file.exists()


def _console_write(text: str) -> None:
    stream = getattr(sys, "stdout", None)
    if stream is not None:
        stream.write(text)
        stream.flush()


def _log(log_path: Path, record: dict[str, Any]) -> None:
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    with log_path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(line + "\n")
        stream.flush()
    _console_write(line + "\n")


class _ChildProcess:
    """Popen adapter that drains child output and can be cancelled via a file."""

    def __init__(self, child: subprocess.Popen[bytes], reader: threading.Thread,
                 monitor: threading.Thread, stop: threading.Event):
        self._child = child
        self._reader = reader
        self._monitor = monitor
        self._stop = stop

    def wait(self, timeout: float | None = None) -> int:
        result = self._child.wait(timeout=timeout)
        self._stop.set()
        self._reader.join(timeout=10)
        self._monitor.join(timeout=10)
        return int(result)

    def terminate(self) -> None:
        if self._child.poll() is None:
            self._child.terminate()

    def kill(self) -> None:
        if self._child.poll() is None:
            self._child.kill()


def _logged_popen_factory(log_path: Path, cancel_file: Path | None) -> Callable[..., _ChildProcess]:
    def factory(command: list[str], **options: Any) -> _ChildProcess:
        options["stdout"] = subprocess.PIPE
        options["stderr"] = subprocess.STDOUT
        if os.name == "nt":
            options.setdefault("creationflags", getattr(subprocess, "CREATE_NO_WINDOW", 0))
        child = subprocess.Popen(command, **options)
        stop = threading.Event()

        def read_output() -> None:
            assert child.stdout is not None
            with child.stdout:
                for raw_line in iter(child.stdout.readline, b""):
                    line = raw_line.decode("utf-8", errors="replace")
                    with log_path.open("a", encoding="utf-8", newline="\n") as stream:
                        stream.write(line)
                        stream.flush()
                    _console_write(line)

        def watch_cancel() -> None:
            while not stop.wait(0.2):
                if _is_cancelled(cancel_file):
                    try:
                        if child.poll() is None:
                            child.terminate()
                            child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()
                    except OSError:
                        pass
                    return

        reader = threading.Thread(target=read_output, name="atlas-lite-generator-log", daemon=True)
        monitor = threading.Thread(target=watch_cancel, name="atlas-lite-generator-cancel", daemon=True)
        reader.start()
        monitor.start()
        return _ChildProcess(child, reader, monitor, stop)

    return factory


def _restore(path: Path, backup: Path | None) -> None:
    if backup is None:
        path.unlink(missing_ok=True)
        return
    replacement = path.with_name(path.name + ".rollback")
    shutil.copy2(backup, replacement)
    os.replace(replacement, path)


def _commit_pair(candidate_pack: Path, candidate_manifest: Path, pack_path: Path,
                 manifest_path: Path, rollback_dir: Path,
                 cancelled: Callable[[], bool], validate: Callable[[], None]) -> None:
    rollback_dir.mkdir(parents=True, exist_ok=True)
    pack_backup: Path | None = None
    manifest_backup: Path | None = None
    if pack_path.is_file():
        pack_backup = rollback_dir / "assets.atlaslite.before"
        shutil.copy2(pack_path, pack_backup)
    if manifest_path.is_file():
        manifest_backup = rollback_dir / "manifest.json.before"
        shutil.copy2(manifest_path, manifest_backup)
    try:
        if cancelled():
            raise PreparationCancelled("Preparation cancelled before commit.")
        os.replace(candidate_pack, pack_path)
        if cancelled():
            raise PreparationCancelled("Preparation cancelled during commit.")
        os.replace(candidate_manifest, manifest_path)
        if cancelled():
            raise PreparationCancelled("Preparation cancelled during commit.")
        validate()
        if cancelled():
            raise PreparationCancelled("Preparation cancelled before commit completed.")
    except BaseException:
        # Restore both files even if only one replacement happened. Backups are
        # byte copies so the pre-preparation installation is recovered exactly.
        restore_errors: list[BaseException] = []
        for path, backup in ((manifest_path, manifest_backup), (pack_path, pack_backup)):
            try:
                _restore(path, backup)
            except BaseException as error:  # preserve the original failure below
                restore_errors.append(error)
        if restore_errors:
            raise RuntimeError("Preparation failed and rollback was incomplete: " + "; ".join(map(str, restore_errors)))
        raise


def _validate_contract_paths(root: Path, output_dir: Path, contract: dict[str, Any]) -> tuple[Path, Path, Path, Path]:
    package_root = root.resolve(strict=True)
    output = output_dir.expanduser().resolve(strict=True)
    if output != package_root or contract["root"].resolve(strict=True) != package_root:
        raise ValueError("--output-dir must be the installed Atlas package root containing this prepare.py.")
    own_files: dict[str, Path] = contract["own_files"]

    def pinned(path: Path, label: str) -> Path:
        resolved = path.resolve(strict=True)
        relative = resolved.relative_to(package_root).as_posix().casefold()
        if own_files.get(relative) != resolved:
            raise ValueError(f"The packaged {label} is not pinned by manifest.files: {relative}")
        return resolved

    driver = pinned(package_root / "tools" / "atlas_lite_bundle.py", "bundle runner")
    bundle_path = pinned(package_root / "tools" / "generator.atlaslite", "generator bundle")
    pack_spec = contract.get("asset_pack")
    if not isinstance(pack_spec, dict):
        raise ValueError("The Atlas manifest must declare its asset pack before preparation.")
    manager = pack_spec.get("manager")
    if not isinstance(manager, Path) or manager.resolve(strict=True) != pinned(package_root / "bootstrap" / "assets.py", "asset manager"):
        raise ValueError("The prepared asset manager is not the verified bundled implementation.")
    script_path = Path(__file__).resolve(strict=True)
    expected_script = contract.get("generator")
    if expected_script is None or expected_script.resolve(strict=True) != script_path:
        raise ValueError("The running preparation script does not match manifest.generator.")
    pinned(script_path, "preparation script")
    pack_path = Path(pack_spec["path"]).resolve(strict=True)
    expected_pack = (package_root / "assets.atlaslite").resolve(strict=True)
    if pack_path != expected_pack:
        raise ValueError("The Atlas asset pack must be the package's assets.atlaslite file.")
    manifest_relative = Path(contract.get("config", {}).get("manifest", "manifest.json"))
    if manifest_relative.is_absolute() or ".." in manifest_relative.parts:
        raise ValueError("The package manifest path is unsafe.")
    manifest_path = (package_root / manifest_relative).resolve(strict=True)
    if not _inside(package_root, manifest_path):
        raise ValueError("The package manifest must remain inside the Atlas root.")
    return driver, bundle_path, pack_path, manifest_path


def _prepare(game_dir: Path, output_dir: Path, *, cancel_file: Path | None = None,
             notify: Callable[[dict[str, Any]], None] | None = None,
             module_loader: Callable[[str, Path], ModuleType] = _load_module,
             contract_loader: Callable[[ModuleType, Path], dict[str, Any]] | None = None) -> dict[str, Any]:
    emit = notify or (lambda record: print(json.dumps(record, ensure_ascii=False), flush=True))
    root = Path(__file__).resolve().parents[1]
    bootstrap_path = root / "bootstrap" / "entry.py"
    assets_path = root / "bootstrap" / "assets.py"
    bundle_driver_path = root / "tools" / "atlas_lite_bundle.py"
    bootstrap = module_loader("lite_prepare_entry", bootstrap_path)
    assets = module_loader("lite_prepare_assets", assets_path)
    bundle = module_loader("lite_prepare_bundle", bundle_driver_path)
    contract = (contract_loader or (lambda entry, package: entry.load_contract(package)))(bootstrap, root)
    driver_path, bundle_path, pack_path, manifest_path = _validate_contract_paths(root, output_dir, contract)
    # The driver path check above is intentionally manifest-based; import the
    # exact verified helper from that path rather than using a system Python.
    if Path(bundle.__file__).resolve(strict=True) != driver_path:
        raise ValueError("Loaded bundle runner differs from the manifest-pinned helper.")

    game = _resolve_game_dir(game_dir)
    state = Path(contract["state_root"]).resolve(strict=False)
    if not _inside(root.resolve(), state):
        raise ValueError("Preparation state must remain inside the installed Atlas package.")
    if _inside(game, root.resolve()) or _inside(root.resolve(), game):
        raise ValueError("The Atlas package and selected game directory must be separate.")
    if cancel_file is not None:
        cancel_file = cancel_file.expanduser().resolve(strict=False)
        if _is_cancelled(cancel_file):
            raise PreparationCancelled("Cancellation was already requested.")

    state.mkdir(parents=True, exist_ok=True)
    log_path = state / "preparation.log"
    lock_type = getattr(bootstrap, "SessionLock", None)
    lock = lock_type(state / "session.lock") if lock_type else None
    if lock is None:
        raise ValueError("The verified bootstrap does not expose its session lock.")

    emit({"stage": "preflight", "progress": 0, "game_dir": str(game)})
    with lock:
        log_path.write_text("", encoding="utf-8")
        with tempfile.TemporaryDirectory(prefix="preparation-work-", dir=state) as temporary:
            work = Path(temporary)
            generated = work / "generated"
            generated.mkdir()
            _log(log_path, {"stage": "generation", "progress": 1})
            popen_factory = _logged_popen_factory(log_path, cancel_file)
            code = bundle.run_bundle(bundle_path, game, generated, temp_parent=state,
                                     popen_factory=popen_factory)
            if code:
                if _is_cancelled(cancel_file):
                    raise PreparationCancelled("Map preparation was cancelled. The previous asset pack is unchanged.")
                raise RuntimeError(f"The bundled generator exited with status {code}; the previous asset pack is unchanged. Log: {log_path}")
            if _is_cancelled(cancel_file):
                raise PreparationCancelled("Map preparation was cancelled. The previous asset pack is unchanged.")

            # Reuse only release-owned visual art. Existing maps and fonts are
            # deliberately ignored; all map data and the native font come from
            # this run's selected game directory.
            previous = work / "release-assets"
            previous.mkdir()
            source_asset_manifest = assets.unpack(pack_path, previous)
            art_root = previous / "art"
            if not art_root.is_dir():
                raise ValueError("The art-only release pack does not contain its art/ directory.")
            final_root = work / "final-assets"
            final_root.mkdir()
            for source in sorted(art_root.rglob("*")):
                if source.is_file() and source.name.casefold() != "native-font.ttf":
                    relative = source.relative_to(art_root)
                    target = final_root / "art" / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
            fresh_font = generated / "art" / "native-font.ttf"
            if not fresh_font.is_file():
                raise ValueError("The selected game did not produce the required native font.")
            target_font = final_root / "art" / "native-font.ttf"
            target_font.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(fresh_font, target_font)

            generated_maps = generated / "maps"
            generated_manifest = generated_maps / "generated-assets.json"
            if not generated_manifest.is_file():
                raise ValueError("The frozen generator did not produce maps/generated-assets.json.")
            for source in sorted(generated_maps.rglob("*")):
                if source.is_file():
                    target = final_root / "maps" / source.relative_to(generated_maps)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)

            inputs = {
                path.relative_to(final_root).as_posix(): path
                for folder in ("maps", "art")
                for path in (final_root / folder).rglob("*")
                if path.is_file()
            }
            candidate_pack = work / "assets.atlaslite.new"
            pack_receipt = assets.build(inputs, candidate_pack)
            if _sha256(candidate_pack) != pack_receipt.get("sha256"):
                raise ValueError("The candidate asset pack hash changed after creation.")
            verify_root = work / "verify"
            verify_root.mkdir()
            verified_manifest = assets.unpack(candidate_pack, verify_root)
            if not verified_manifest.get("prepared"):
                raise ValueError("The candidate pack did not validate as prepared.")
            if _is_cancelled(cancel_file):
                raise PreparationCancelled("Map preparation was cancelled. The previous asset pack is unchanged.")

            new_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            pack_relative = pack_path.relative_to(root.resolve()).as_posix()
            new_manifest["asset_pack"]["sha256"] = pack_receipt["sha256"]
            new_manifest["files"][pack_relative] = pack_receipt["sha256"]
            candidate_manifest = work / "manifest.json.new"
            candidate_manifest.write_text(
                json.dumps(new_manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )

            def validate_committed_package() -> None:
                committed = json.loads(manifest_path.read_text(encoding="utf-8"))
                if committed.get("asset_pack", {}).get("sha256") != _sha256(pack_path):
                    raise ValueError("Committed pack does not match manifest.asset_pack.sha256.")
                if committed.get("files", {}).get(pack_relative) != _sha256(pack_path):
                    raise ValueError("Committed pack does not match manifest.files.")
                contract_loader_fn = contract_loader or (lambda entry, package: entry.load_contract(package))
                contract_loader_fn(bootstrap, root.resolve())

            _log(log_path, {"stage": "commit", "progress": 99})
            _commit_pair(candidate_pack, candidate_manifest, pack_path, manifest_path,
                         work / "rollback", lambda: _is_cancelled(cancel_file), validate_committed_package)
            _log(log_path, {"stage": "complete", "progress": 100,
                            "asset_pack_sha256": pack_receipt["sha256"],
                            "prepared": True,
                            "source_asset_pack_prepared": bool(source_asset_manifest.get("prepared"))})
            return {"asset_pack_sha256": pack_receipt["sha256"],
                    "asset_pack_bytes": pack_path.stat().st_size,
                    "log": str(log_path)}


def main(argv: list[str] | None = None) -> int:
    for stream in (getattr(sys, "stdout", None), getattr(sys, "stderr", None)):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True,
                        help="Selected Bloodborne 1.09 Image0 directory or its parent.")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="Installed Hunter's Atlas package root.")
    parser.add_argument("--headless", action="store_true", required=True,
                        help="Run without opening a GUI; intended for the installer launcher.")
    parser.add_argument("--cancel-file", type=Path,
                        help="Optional file created by the installer to request cancellation.")
    args = parser.parse_args(argv)
    try:
        result = _prepare(args.game_dir, args.output_dir, cancel_file=args.cancel_file)
    except PreparationCancelled as error:
        _console_write(json.dumps({"stage": "cancelled", "error": str(error)}, ensure_ascii=False) + "\n")
        return 130
    except Exception as error:
        message = json.dumps({"stage": "error", "error": str(error)}, ensure_ascii=False) + "\n"
        stream = getattr(sys, "stderr", None)
        if stream is not None:
            stream.write(message)
            stream.flush()
        return 1
    _console_write(json.dumps({"stage": "complete", **result}, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
