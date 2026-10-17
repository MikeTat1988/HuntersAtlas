# Hunter’s Atlas — controls and coverage

Open Bloodborne from the normal desktop shortcut, choose **Play**, then select the native in-game **Map** tile. The map shows live position and facing, pan, zoom, floor context and navigation through supported areas. Optional lamp travel uses the game’s normal travel and save operations. The map appears inside the game.

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

The game’s confirm-button setting is respected. Release controls after opening the map before moving its pointer. Shoulders cycle available destinations across supported maps and skip locked or unavailable lamps. Selection centers the destination and its floor. Undiscovered lamps are hidden and cannot be selected; they appear automatically once lit during play. Selecting a lamp never unlocks it.

## Optional features and marker limits

Remaining pickups, fast travel, boss reveal and NPC dialogue filtering can be configured independently. Turning fast travel or boss reveal off leaves the map available. Pickup markers use red for Blood Vials, purple for Madman’s Knowledge and Great One’s Wisdom, blue for weapons and clothing, and gold for Coldblood consumables. The four categories have individual switches.

Pickup markers come from fixed treasure objects and their collection flags. Monster drops, scripted awards without a fixed treasure object, hidden treasures and objects with unverified dynamic availability are omitted. Unknown collection state is hidden.

The **New dialogue only** mode currently covers Gilbert before transformation, Eileen’s initial Central Yharnam conversations, and Eileen’s early conversations outside Oedon Chapel. It uses quest and dialogue completion flags. Later Eileen stages, including the Henryk aftermath and wounded Eileen, and other NPCs are hidden in this mode. **All conversation sites** retains the original static sites.

Boss reveal uses each area’s main boss flag. Upper Cathedral Ward and Research Hall conservatively require both local bosses. Authored Central Yharnam surfaces inside the Cathedral Ward map use Gascoigne’s flag separately. The bossless Lecture Building reveals when one of its own lamps is unlocked, independently of Rom. Hunter’s Dream and the Abandoned Old Workshop remain visible. Available lamps stay accessible while their surrounding map is concealed.

Fast travel requires a valid living player and the game’s top-level quick menu. It uses the game’s return-point and stage-loading operations on the main game thread, including normal game saving. It changes the next respawn destination to the selected lamp. Travel is guarded by checks against the supported executable; a mismatch disables it. Gate markers remain static, and Chalice Dungeons are unsupported.

See [installation](INSTALL.md), [compatibility](COMPATIBILITY.md) and [QA status](QA.md).
