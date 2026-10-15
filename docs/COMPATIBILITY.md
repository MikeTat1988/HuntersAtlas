# Compatibility

Atlas Lite 2.0.0 supports one verified Windows launcher and one verified game executable. The installer and bootstrap check these identities; a familiar folder name or displayed version is not sufficient.

| Component | Supported identity |
| --- | --- |
| Operating system | Windows 10 or Windows 11, 64-bit |
| Launcher | Official [Bloodborne for Windows v1.7.2](https://github.com/Supermedo/bloodborne_pc/releases/tag/windows-v1.7.2); stock `Bloodborne.exe` SHA-256 `4a8e67ce5c2a5e4d8f8add8b0e606caecd5a3389756aef683f3ded793d4f6a59` |
| Game | CUSA00207, version 1.09; `Image0/eboot.bin` SHA-256 `d65f0b4f01d59166aed16f8604196d8b7dd805abbf0758b356e8f1354c9429f9` |
| Atlas Lite | Hunter’s Atlas Lite 2.0.0 |

Other regions, game versions, launcher versions, and modified launcher executables are unverified and are rejected when their fingerprints do not match. The supported build must be selected in the ordinary launcher before installing Atlas Lite.

## Runtime and game data

The player package reuses the verified launcher’s private `_internal` runtime and required launcher files. It does not install a global Python runtime or compiler. Atlas Lite keeps its own bootstrap, configuration, generated files, and runtime state in its extracted package and profile. The installer binds the verified stock launcher copy for Lite and restores the original launcher when uninstalled.

The package contains no Bloodborne files, generated map data, or game font. On first use, Atlas Lite generates the 16 supported maps and font from the user’s own compatible game files. Map preparation normally takes 5–15 minutes. The selected launcher profile and saves are used for play; Atlas Lite does not make a second save copy.

The installer and Atlas runtime do not patch the game executable, game data, saves, or DLC. The installer does add its launcher integration and records the package association in the launcher profile. Keep the extracted Atlas Lite folder in place until it is uninstalled.

## Map and input limits

The map provides player-position and facing display, pan, zoom, floor context, and navigation through the supported areas. Markers do not follow live quest progress or gate state. Chalice Dungeons are not supported. These compatibility statements do not certify every route, floor transition, graphics device, controller model, or full playthrough; see [QA status](QA.md).
