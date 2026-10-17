#!/usr/bin/env python3
"""Drive the native menu/controller route for an isolated live-game QA session."""
from __future__ import annotations

import json
import hashlib
import math
import os
from pathlib import Path
import re
import struct
import sys
import time
import zlib


REPO = Path(__file__).resolve().parents[3]
QA_ROOT = REPO / ".local" / "owned-integration-qa"


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def wait_for(predicate, label: str, timeout: float = 45.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = read_json(TRACE)
        if predicate(state):
            return state
        if state.get("feature_error"):
            raise RuntimeError(f"Native Atlas reported a feature error: {state['feature_error']}")
        time.sleep(0.2)
    raise TimeoutError(f"Timed out waiting for {label}; last trace: {read_json(TRACE)}")


def pad(tokens: str = "", hold: float = 0.35, settle: float = 0.45) -> None:
    PAD.write_text(tokens, encoding="ascii")
    time.sleep(hold)
    PAD.write_text("", encoding="ascii")
    time.sleep(settle)


def qa_command(text: str, timeout: float = 12.0) -> None:
    CONTROL.write_text(text + "\n", encoding="ascii")
    deadline = time.monotonic() + timeout
    while CONTROL.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Native QA control was not consumed: {text}")
        time.sleep(0.1)


def near(a: float, b: float, epsilon: float = 0.02) -> bool:
    return math.isclose(float(a), float(b), rel_tol=epsilon, abs_tol=epsilon)


def raw_rgba_to_png(source: Path, destination: Path, width: int, height: int) -> None:
    pixels = source.read_bytes()
    if len(pixels) != width * height * 4:
        raise RuntimeError(f"Unexpected raw frame size for {source.name}: {len(pixels)} bytes")

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (struct.pack(">I", len(body)) + kind + body +
                struct.pack(">I", zlib.crc32(kind + body) & 0xffffffff))

    scanlines = b"".join(b"\0" + pixels[y * width * 4:(y + 1) * width * 4]
                         for y in range(height))
    png = (b"\x89PNG\r\n\x1a\n" +
           chunk(b"IHDR", struct.pack(">2I5B", width, height, 8, 6, 0, 0, 0)) +
           chunk(b"IDAT", zlib.compress(scanlines, 3)) + chunk(b"IEND", b""))
    destination.write_bytes(png)


def capture_first_frame(session: Path, timeout: float = 40.0) -> dict:
    qa_root = session / "map-qa"
    captures = qa_root / "captures"
    captures.mkdir(parents=True, exist_ok=True)
    prior_frames = set(captures.glob("output_*_*.raw"))
    trigger = qa_root / "frame.trigger"
    trigger.write_text("capture\n", encoding="ascii")
    deadline = time.monotonic() + timeout
    frames: list[Path] = []
    while time.monotonic() < deadline:
        frames = sorted(p for p in captures.glob("output_*_*.raw") if p not in prior_frames)
        if frames:
            break
        time.sleep(0.25)
    if not frames:
        raise TimeoutError("No presented-frame dump arrived before the capture timeout.")
    converted = []
    for raw in frames:
        match = re.search(r"_(\d+)_(\d+)x(\d+)\.raw$", raw.name)
        if not match:
            raise RuntimeError(f"Cannot read dimensions from frame dump: {raw.name}")
        _, width, height = map(int, match.groups())
        png = raw.with_suffix(".png")
        raw_rgba_to_png(raw, png, width, height)
        converted.append(str(png))
    result = {"frames": converted, "trace": read_json(qa_root / "trace.json"),
              "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    (session / "frame-evidence.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    global SESSION, TRACE, CONTROL, PAD, CAPTURE
    args = sys.argv[1:]
    capture_only = len(args) == 2 and args[1] == "--capture-only"
    one_press = len(args) == 3 and args[1] == "--press"
    if len(args) not in (1, 2, 3) or (len(args) == 2 and not capture_only) or one_press is False and len(args) == 3:
        print(f"Usage: {Path(sys.argv[0]).name} <label> [--capture-only | --press BUTTON]", file=sys.stderr)
        return 2
    label = args[0]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}", label):
        raise SystemExit("Use the same short letters/numbers/dash/underscore label as live_game.py.")
    SESSION = QA_ROOT / "runs" / label
    if not SESSION.is_dir() or not (SESSION / "launch.json").is_file():
        raise SystemExit(f"No live session for label {label!r}.")
    qa_root = SESSION / "map-qa"
    TRACE, CONTROL = qa_root / "trace.json", qa_root / "control.txt"
    PAD, CAPTURE = qa_root / "pad.txt", qa_root / "capture.trigger"
    if not PAD.is_file():
        raise SystemExit("The live process has not initialized its private pad file yet.")

    if capture_only:
        evidence = capture_first_frame(SESSION)
        print(json.dumps({"captured": True, "session": str(SESSION), **evidence},
                         ensure_ascii=False, indent=2))
        return 0
    if one_press:
        button = args[2]
        if button not in {"cross", "circle", "square", "triangle", "options", "up", "down", "left", "right"}:
            raise SystemExit("--press accepts only one named controller button.")
        PAD.write_text(button, encoding="ascii")
        time.sleep(0.35)
        PAD.write_text("", encoding="ascii")
        time.sleep(0.5)
        print(json.dumps({"pressed_once": button, "trace": read_json(TRACE)},
                         ensure_ascii=False, indent=2))
        return 0

    state = read_json(TRACE)
    if not state.get("valid"):
        raise RuntimeError("No live character yet. Capture the current frame with --capture-only, "
                           "inspect it, advance one visible prompt with --press BUTTON, and retry.")
    frame_evidence = read_json(SESSION / "frame-evidence.json")
    if not any(Path(path).is_file() for path in frame_evidence.get("frames", [])):
        raise RuntimeError("A verified rendered frame is required before native menu input; "
                           "capture it with --capture-only first.")

    if state.get("open"):
        map_open = state
        confirm = "cross" if int(state.get("confirm", 0)) == 0x4000 else "circle" \
            if int(state.get("confirm", 0)) == 0x2000 else None
        if confirm is None:
            raise RuntimeError(f"Unexpected native confirm button: {state.get('confirm')}")
        cancel = "circle" if confirm == "cross" else "cross"
        evidence = {"native_menu_tile": {"focus": state.get("native_focus"),
                                         "atlas_focus": state.get("atlas_focus"),
                                         "map_opened_from_tile": True},
                    "map_opened": map_open, "confirmed_with": confirm,
                    "resumed_existing_map": True}
    else:
        if not state.get("menu_top"):
            pad("options")
            state = wait_for(lambda x: x.get("menu_top") is True, "native top-level menu")
        if not state.get("menu_supported"):
            raise RuntimeError(f"Native menu is unsupported in this session: {state}")

        # Reach native focus index 2 with real scripted D-pad input. At index 2,
        # one additional Right focuses Atlas's added tile; no QA `open` shortcut.
        for _ in range(12):
            state = wait_for(lambda x: x.get("menu_top") is True, "native menu focus")
            if state.get("native_focus") == 2:
                break
            pad("right")
        else:
            raise RuntimeError(f"Could not navigate native menu to Atlas tile anchor 2: {state}")
        pad("right")
        state = wait_for(lambda x: x.get("atlas_focus") is True and x.get("tile") is True,
                         "controller focus on the native-menu Atlas tile")
        confirm = "cross" if int(state.get("confirm", 0)) == 0x4000 else "circle" \
            if int(state.get("confirm", 0)) == 0x2000 else None
        if confirm is None:
            raise RuntimeError(f"Unexpected native confirm button: {state.get('confirm')}")
        cancel = "circle" if confirm == "cross" else "cross"
        native_tile = state
        pad(confirm)
        map_open = wait_for(lambda x: x.get("open") is True, "Atlas map opened from the native menu")
        if not map_open.get("menu") or not map_open.get("valid"):
            raise RuntimeError(f"Atlas map did not open over a valid native menu session: {map_open}")
        evidence = {"native_menu_tile": native_tile, "map_opened": map_open,
                    "confirmed_with": confirm}

    # Capture the actual first map view while it is still centered on the
    # player's current location. Do this before panning or selecting a lamp.
    captures = SESSION / "map-qa" / "captures"
    captures.mkdir(parents=True, exist_ok=True)
    prior_map_frames = set(captures.glob("map-ui_*_*.raw"))
    CAPTURE.write_text("map-initial\n", encoding="ascii")
    deadline = time.monotonic() + 20.0
    initial_map_frames: list[Path] = []
    while time.monotonic() < deadline:
        initial_map_frames = sorted(p for p in captures.glob("map-ui_*_*.raw")
                                    if p not in prior_map_frames)
        if initial_map_frames:
            break
        time.sleep(0.2)
    if not initial_map_frames:
        raise TimeoutError("No initial player-centered map swapchain frame arrived.")
    initial_frame = initial_map_frames[0]
    dimensions = re.search(r"_(\d+)_(\d+)x(\d+)\.raw$", initial_frame.name)
    if not dimensions:
        raise RuntimeError(f"Cannot read dimensions from map frame: {initial_frame.name}")
    _, width, height = map(int, dimensions.groups())
    initial_png = initial_frame.with_suffix(".png")
    raw_rgba_to_png(initial_frame, initial_png, width, height)
    evidence["initial_player_centered_map"] = {
        "trace": map_open,
        "frame": str(initial_png),
        "captured_before_controller_pan_and_lamp_selection": True,
    }

    # Exercise mapped controller navigation, analog pan, and shoulder zoom.
    pad("")
    before = wait_for(lambda x: x.get("open") is True, "map ready for controller input")
    pad("rx=220", hold=0.8, settle=0.5)
    after_pan = wait_for(lambda x: x.get("open") is True and
                         (not near(before.get("cx", 0), x.get("cx", 0)) or
                          not near(before.get("cz", 0), x.get("cz", 0))),
                         "right-stick pan changed the map center", timeout=25)
    pad("r2", hold=0.35, settle=0.3)
    zoom_in = wait_for(lambda x: x.get("open") is True and
                       not near(after_pan.get("zoom", 0), x.get("zoom", 0)),
                       "R2 zoom-in changed map scale", timeout=25)
    pad("l2", hold=0.35, settle=0.3)
    zoom_out = wait_for(lambda x: x.get("open") is True and
                        not near(zoom_in.get("zoom", 0), x.get("zoom", 0)),
                        "L2 zoom-out changed map scale", timeout=25)

    # QA may select an available destination, but both opening the native
    # confirmation and requesting travel are performed with controller input.
    # First prove cancellation leaves the native travel status untouched.
    travel_ready = False
    if map_open.get("travel_supported") and int(map_open.get("available_lamps", 0)) > 0:
        qa_command("lamp-next")
        selected = wait_for(lambda x: int(x.get("selected_destination", -1)) >= 0,
                            "QA-selected available lamp")
        pad(confirm)
        dialog = wait_for(lambda x: int(x.get("travel_dialog", -1)) >= 0,
                          "native travel confirmation dialog")
        pad(cancel)
        state = wait_for(lambda x: int(x.get("travel_dialog", -1)) < 0 and x.get("open") is True,
                         "cancelled travel confirmation")
        if state.get("travel_status") != dialog.get("travel_status"):
            raise RuntimeError("Travel status changed during cancellation; a travel request may have fired.")
        evidence["travel_cancel"] = {"selection": selected.get("selected_destination"),
                                     "dialog": dialog.get("travel_dialog"),
                                     "travel_status": state.get("travel_status")}
        travel_ready = True
    else:
        evidence["travel_cancel"] = "skipped: no supported available lamp"

    CAPTURE.write_text("map\n", encoding="ascii")
    time.sleep(2)
    evidence["map_visible"] = read_json(TRACE)
    # The opposite confirm/cancel button closes the map through the regular
    # controller route. Native Map tile opening above is separately asserted.
    pad(cancel)
    closed = wait_for(lambda x: x.get("open") is False and x.get("menu_top") is True,
                      "map closed back to the native menu")
    pad("options")
    returned = wait_for(lambda x: x.get("menu") is False and x.get("valid") is True,
                        "return to live gameplay")
    evidence["close_return"] = {"native_menu": closed, "gameplay": returned}

    # The copied-save QA request authorizes one normal in-game travel. Capture
    # and close the first map before travel, then reopen it through the native
    # tile and confirm the actual destination using controller input.
    if travel_ready:
        pad("options")
        menu_again = wait_for(lambda x: x.get("menu_top") is True and x.get("menu_supported") is True,
                              "native menu before travel map reopen")
        for _ in range(12):
            if menu_again.get("native_focus") == 2:
                break
            pad("right")
            menu_again = wait_for(lambda x: x.get("menu_top") is True, "native menu focus for travel")
        else:
            raise RuntimeError(f"Could not navigate native menu to Atlas tile for travel: {menu_again}")
        pad("right")
        wait_for(lambda x: x.get("atlas_focus") is True and x.get("tile") is True,
                 "Atlas tile focus before travel")
        pad(confirm)
        travel_map = wait_for(lambda x: x.get("open") is True and x.get("menu") is True,
                              "Atlas reopened from native tile for travel")
        source_title = travel_map.get("title")
        source_block = travel_map.get("block")
        if int(travel_map.get("available_lamps", 0)) <= 0:
            raise RuntimeError(f"Travel was previously available but no lamp is now listed: {travel_map}")
        qa_command("lamp-next")
        destination = wait_for(lambda x: int(x.get("selected_destination", -1)) >= 0,
                               "available destination for native travel")
        pad(confirm)
        wait_for(lambda x: int(x.get("travel_dialog", -1)) >= 0,
                 "native travel confirmation for the real request")
        CAPTURE.write_text("travel-confirm\n", encoding="ascii")
        pad(confirm)
        travelled = wait_for(lambda x: int(x.get("travel_status", 0)) == 3 or
                             int(x.get("travel_status", 0)) < 0,
                             "native travel completion or rejection", timeout=75)
        if int(travelled.get("travel_status", 0)) != 3:
            raise RuntimeError(f"Native travel failed/rejected: {travelled}")
        arrived = wait_for(lambda x: x.get("valid") is True and x.get("open") is False,
                           "gameplay resumed at the travelled destination", timeout=90)
        if arrived.get("block") == source_block:
            raise RuntimeError(f"Travel status completed but the player stayed in source block {source_block}.")
        evidence["travel_complete"] = {
            "source_title": source_title,
            "source_block": source_block,
            "selection": destination.get("selected_destination"),
            "status": travelled.get("travel_status"),
            "destination_title": arrived.get("title"),
            "destination_block": arrived.get("block"),
            "destination_layer": arrived.get("current_layer"),
        }
    else:
        evidence["travel_complete"] = "skipped: no supported available lamp"
    launch = read_json(SESSION / "launch.json")
    source_tree = Path(launch["source_savedata"])
    expected = launch.get("source_savedata_sha256", {})
    actual = {p.relative_to(source_tree).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(source_tree.rglob("*")) if p.is_file()}
    if actual != expected:
        raise RuntimeError("The protected source save changed during copied-save QA.")
    evidence["source_save_unchanged"] = True
    (SESSION / "controller-qa.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "session": str(SESSION),
                      "native_map_tile": True, "controller_pan_zoom": True,
                      "travel_confirmation_cancelled": isinstance(evidence["travel_cancel"], dict)},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
