# Compatibility

| Component | Supported identity |
| --- | --- |
| Launcher adapter | `windows-v1.7.2-atlas1` |
| Stock launcher accepted by installer | SHA-256 `4a8e67ce5c2a5e4d8f8add8b0e606caecd5a3389756aef683f3ded793d4f6a59` |
| Matching stock `run.py` | SHA-256 `2f69776954c3ba10fd9a3aedfbaf383950d6c63a7c11f35337f0d5d0e1ed38c4` |
| Atlas runtime | `hunters-atlas-runtime-1.4.0-beta1` |
| Tested game metadata | CUSA00207, version 01.09 |
| Required `Image0/eboot.bin` | SHA-256 `d65f0b4f01d59166aed16f8604196d8b7dd805abbf0758b356e8f1354c9429f9` |
| Local generator | `generate_atlas.exe`, frozen CPython 3.12 dependencies included |

Folder names, region labels and a launcher's displayed version alone do not establish compatibility. The installer, launcher and generator check their respective fingerprints. This beta does not claim compatibility with every Bloodborne port, game region or launcher version.

Cross/A is the supported US build’s native layout. Circle/B uses the existing Japanese/Asian Circle-confirm tweak. Atlas reads the verified applied native region predicate so a stale profile or inherited environment cannot disagree with the game; other unrecognized predicate patches disable the menu bridge. Controller navigation uses the game's logical input path; keyboard-remapped game actions remain meaningful. Optional direct shortcut availability is restricted to a verified top-level quick menu. Unsafe or unknown menu state hides the tile.

The add-on's manifest hashes every immutable payload file. Generated maps have a separate manifest bound to the selected game fingerprint. Absolute paths, traversal, links, unlisted files, missing files and hash mismatches are rejected. Only `settings/settings.ini` is mutable package configuration. The launcher persists selected folder and enable state in its profile.

Sixteen ordinary maps are generated. No Chalice generation, live NPC quest tracking, live gate-state tracking, universal controller-device certification or complete playthrough is claimed. Runtime stability and the remaining named scene checks are recorded in `QA.md`.
