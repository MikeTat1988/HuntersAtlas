# Hunter’s Atlas 1.1 — controls and coverage

This candidate adds lamp selection and optional fast travel, remaining pickup dots, NPC dialogue filtering, and boss-based map reveal. These features are individually configurable in the launcher.

## Controls

| Action | Xbox | PlayStation | Keyboard and mouse |
| --- | --- | --- | --- |
| Previous and next available lamp | LB and RB | L1 and R1 | Q and E |
| Move pointer | Left stick | Left stick | Mouse |
| Pan | Right stick | Right stick | Drag |
| Zoom out and in | LT and RT | L2 and R2 | Minus and plus, or wheel |
| Select and confirm | A normally | Cross normally | Click or Enter |
| Cancel and back | B normally | Circle normally | Escape |
| Recenter | Y | Triangle | Home |
| Elevation shading | X | Square | H |

The game's confirm-button setting is respected. Release controls after opening the map before moving its pointer. Shoulders cycle available destinations across the supported maps and skip locked or unavailable lamps. Selection centers the destination and its floor. Undiscovered lamps are hidden and cannot be selected. They appear automatically once lit during gameplay; selecting a lamp never unlocks it.

## Launcher options

In Mods, enable Hunter's Atlas and choose the feature options. Remaining pickups, fast travel, and boss reveal initially default off. NPC markers initially show all existing conversation sites. Settings take effect on the next game launch or game restart.

Fast travel and boss reveal are independent checkboxes. Turning either or both off leaves the map available. Turning Atlas itself off disables its subordinate controls and runs the ordinary launcher runtime.

Pickups use red for Blood Vials, purple for Madman's Knowledge and Great One's Wisdom, blue for weapons and clothing, and gold for Coldblood consumables. The four categories have individual switches. Markers are extracted from fixed treasure objects and their collection flags. Monster drops, scripted awards without a fixed treasure object, hidden treasures, and objects with unverified dynamic availability are omitted. Unknown collection state is hidden.

New dialogue only currently covers Gilbert before transformation, Eileen's initial Central Yharnam conversations, and Eileen's early conversations outside Oedon Chapel. It uses quest and dialogue completion flags. Later Eileen stages, including the Henryk aftermath and wounded Eileen, and other NPCs are hidden in this mode. All conversation sites retains the original static sites.

Boss reveal uses each area's main boss flag. Upper Cathedral Ward and Research Hall conservatively require both local bosses. Authored Central Yharnam surfaces inside the Cathedral Ward map use Gascoigne's flag separately. The bossless Lecture Building reveals when one of its own lamps is unlocked, independently of Rom. Hunter's Dream and the Abandoned Old Workshop remain visible. Available lamps stay accessible while their surrounding map is concealed.

Map fast travel requires a valid living player and the game's top-level quick menu. It uses the game's return-point and stage-loading operations on the main game thread, including normal game saving. It changes the next respawn destination to the selected lamp. Installation does not edit the game files or saves. The native entry points are checked against the supported executable; a mismatch disables travel.

## Installation and updates

Follow [installation](INSTALL.md). After installation, enable Hunter’s Atlas in
**Mods & patches** before playing. Existing installations use Update.cmd from a
fresh extraction; launcher upgrades use the launcher’s ordinary Update button.
See [updates and recovery](LAUNCHER-UPDATES.md).
