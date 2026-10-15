# Compatibility

| Component | Supported identity |
| --- | --- |
| Launcher adapter | `windows-v1.7.2-atlas1` |
| Atlas add-on | Hunter's Atlas 1.0 |
| Tested game metadata | CUSA00207, version 01.09 |
| Local generator | `generate_atlas.exe`, frozen CPython 3.12 dependencies included |

Folder names, region labels and a launcher's displayed version alone do not establish compatibility. The installer, launcher and generator check their respective fingerprints. Hunter's Atlas 1.0 does not claim compatibility with every Bloodborne port, game region or launcher version.

Cross/A is the supported US build’s native layout. Circle/B uses the existing Japanese/Asian Circle-confirm tweak. Atlas reads the verified applied native region predicate so a stale profile or inherited environment cannot disagree with the game; other unrecognized predicate patches disable the menu bridge. Controller navigation uses the game's logical input path; keyboard-remapped game actions remain meaningful. Optional direct shortcut availability is restricted to a verified top-level quick menu. Unsafe or unknown menu state hides the tile.

The add-on verifies every immutable payload file against its manifest. Generated maps have a separate manifest bound to the selected game fingerprint. Absolute paths, traversal, links, unlisted files, missing files and integrity mismatches are rejected. Only `settings/settings.ini` is mutable package configuration. The launcher persists selected folder and enable state in its profile.

Sixteen ordinary maps are generated. No Chalice generation, live NPC quest tracking, live gate-state tracking, universal controller-device certification or complete playthrough is claimed. Runtime stability and the remaining named scene checks are recorded in `QA.md`.

Atlas cursor audio is decoded from the supported installation's local `sprj_main.fsb`; no sound assets are distributed. Unsupported sound-bank layouts fail silently. Output follows the main audio-port volume, `BB_AUDIO_GAIN`, and `BB_AUDIO=none`. A separate sound-effects slider applied only inside the game's FMOD mixer is not currently tracked by these added cursor sounds.
