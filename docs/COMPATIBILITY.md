# Compatibility

Hunter’s Atlas 1.1 includes verified adapters for the identities below and automatic rebuilding for other official releases from 1.7 onward. The installer and bootstrap check file identities. Launcher 1.7.2 and migration to 1.8.2 were tested; 1.7.1 was not separately verified.

| Component | Supported identity |
| --- | --- |
| Operating system | Windows 10 or Windows 11, 64-bit |
| Bundled launcher adapter | Official [Bloodborne for Windows v1.8.1](https://github.com/Supermedo/bloodborne_pc/releases/tag/windows-v1.8.1); stock `Bloodborne.exe` SHA-256 `4d1df0129c5144b78a444f547ca615b4a4888247419a16c4688e5eaf0d46c598` |
| Upstream source | Commit `bee7ec16213022f15bf34084b5587f1ff09e0e65`; all changed native sources rebased, including the new networking vendor layout |
| Official launcher archive | Release ID `413830421`, asset ID `643916924`, `Bloodborne-Windows.zip`; SHA-256 `caf7a433ba2ab7c37b3aecba4ec20815d2871a53705bb7513adcc519c607e850` |
| Initial launcher | v1.7.2, stock SHA-256 `4a8e67ce5c2a5e4d8f8add8b0e606caecd5a3389756aef683f3ded793d4f6a59`; supported for a fresh install and the automatic paired migration to 1.8.1 |
| Game | CUSA00207, version 1.09; `Image0/eboot.bin` SHA-256 `d65f0b4f01d59166aed16f8604196d8b7dd805abbf0758b356e8f1354c9429f9` |
| Atlas | Hunter’s Atlas 1.1 |

Other regions, game versions and modified launcher executables remain unverified. The automatic rebuild path additionally accepts official Windows release metadata from 1.7 onward, authenticates the archive, and builds a new Atlas runtime from that release's source. Version 1.8.2 is the first automatic rebuild target. There is no version-range bypass of file verification. Future source conflicts or incompatible dependencies can require an Atlas repair; the verified launcher update can still complete with Atlas pending. See [updates and recovery](LAUNCHER-UPDATES.md).

## Runtime and game data

The player package reuses the verified launcher’s private `_internal` runtime and required launcher files. It does not install a global Python runtime or compiler. Atlas keeps its own bootstrap, configuration, generated files, and runtime state in its extracted package and profile. The installer binds the verified stock launcher copy for Atlas and restores the original launcher when uninstalled.

The package contains no Bloodborne files, generated map data, or game font. On first use, Atlas generates the 16 supported maps and font from the user’s own compatible game files. Map preparation normally takes 5–15 minutes. The selected launcher profile and saves are used for play; Atlas does not make a second save copy.

Installation does not patch the original game executable, game data, saves, or DLC. Optional fast travel installs a guarded hook in the loaded game image and calls the game's normal travel and save operations on the main thread. It changes the next respawn destination. The installer adds launcher integration and records the package association in the launcher profile. Keep the extracted Atlas folder in place until it is uninstalled.

## Map and input limits

The map provides player-position and facing display, pan, zoom, floor context, and navigation through the supported areas. Gate markers remain static. See [controls and coverage](MAP-FEATURES.md) for the limited supported NPC dialogue stages, verified fixed pickups, and boss reveal rules. Chalice Dungeons are not supported. These compatibility statements do not certify every route, floor transition, graphics device, controller model, or full playthrough; see [QA status](QA.md).
