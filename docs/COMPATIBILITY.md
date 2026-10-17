# Compatibility

Hunter’s Atlas 1.3 runs as an independent installation with its own tested Windows 1.9 runtime. The ordinary desktop Bloodborne shortcut opens the game; **Play** leads to the native in-game **Map** tile. Atlas updates arrive in Atlas packages. Updating a separate ordinary launcher does not replace Atlas or its maps.

| Component | Verified identity |
| --- | --- |
| Operating system requirement | Windows 10 or Windows 11, 64-bit |
| Game | CUSA00207, version 1.09 |
| Game executable | `Image0/eboot.bin` SHA-256 `d65f0b4f01d59166aed16f8604196d8b7dd805abbf0758b356e8f1354c9429f9` |
| Atlas runtime | Tested Windows 1.9 runtime with its own Python, Tk and required DLLs |
| Player package | `Hunters-Atlas-1.3-Windows.zip` |
| Source package | `Hunters-Atlas-1.3-Source.zip` |
| Package size | About 177 MB download; about 415 MB installed, plus generated caches |

The verified game build and tested runtime do not establish support for other game builds, all graphics devices, or every Windows configuration. The package does not include Bloodborne files, generated maps, native font or saves. It requires no system Python, compiler or official launcher private interpreter.

## Data and map limits

Keep the Atlas package in an ordinary local directory outside OneDrive/synced or linked folders. The desktop shortcut can use the Windows Desktop location even when it is redirected.

Install imports the selected game, DLC, save location and launcher preferences. Maps are prepared from the player’s own game files if a compatible pack is unavailable, then reused. Atlas keeps its own profile and settings. Updating Atlas preserves those along with valid maps; rebuildable caches are recreated as needed. If the imported Atlas preference is off, enable it under **Mods & patches** before choosing **Play** from the normal desktop shortcut, then open the native in-game Map tile.

The map provides live player position and facing, pan, zoom, floor context and navigation across supported areas. Gate markers remain static. See [controls and coverage](MAP-FEATURES.md) for input, NPC dialogue stages, fixed pickups and boss reveal rules. Chalice Dungeons are not supported. The test record in [QA status](QA.md) does not certify every route, floor transition, controller or GPU.
