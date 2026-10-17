# Hunter’s Atlas 1.2

A fullscreen navigation map for Bloodborne on Windows, with live position,
floor context and 16 supported areas.

**[Download the latest release](https://github.com/MikeTat1988/HuntersAtlas/releases/latest)** ·
[What’s new in 1.2](docs/releases/v1.2.md) ·
[Previous releases](https://github.com/MikeTat1988/HuntersAtlas/releases)

Choose **Hunters-Atlas-1.2.zip** to play. The separate Source ZIP is for developers.
[Hunter’s Atlas 1.0](https://github.com/MikeTat1988/HuntersAtlas/releases/tag/v1.0)
remains available.

## Features

- Live player position, facing, pan, zoom, recentering and floor context.
- Optional fast travel to discovered lamps, with confirmation. Undiscovered lamps stay hidden.
- Optional pickup dots: red Blood Vials, purple Knowledge/Wisdom, blue equipment and gold Coldblood. Monster drops are excluded.
- Optional map reveal after defeating an area’s boss.
- NPC markers, including a new-dialogue filter for verified Gilbert and early Eileen conversations.
- Automatic Atlas preparation when updating the official launcher; valid maps are reused.

Fog, fast travel and pickup categories can be switched off independently in the launcher.
See [controls and coverage](docs/MAP-FEATURES.md).

![Hunter’s Atlas map](examples/great-bridge.png)

## Install and play

1. Set your game folder in the official launcher, then close the game and launcher.
2. Extract **Hunters-Atlas-1.2.zip** into a permanent folder outside the game and launcher folders.
3. Run **Install.cmd**, select the launcher folder and wait for map preparation (usually 5–15 minutes).
4. Reopen the launcher → **Mods & patches** → tick **Enable Hunter’s Atlas**. Wait for **Ready**, then **Play**. In the game’s quick menu, select **Map**.

**You must enable Hunter’s Atlas after installation.**

![Enable Hunter’s Atlas and choose its features in Mods & patches](examples/launcher-settings.png)

Already using Atlas? Close the game and launcher, extract 1.2 into a **new folder**,
and run **Update.cmd from that new extraction**. Select your existing launcher.
This installs Atlas 1.2 for the launcher version you already have.

Afterward, use the launcher’s normal **Update** button whenever you want a newer
launcher. Atlas prepares automatically and the launcher restarts. The first
rebuild may take several minutes and downloads its tools automatically. Versions
1.7.2, 1.8.1, 1.8.2 and 1.9 have bundled adapters, so they do not need compilation.
Other official versions use the rebuild fallback with live progress and logs.
See [installation](docs/INSTALL.md) and [updates/recovery](docs/LAUNCHER-UPDATES.md).

## Compatibility

Windows 10/11, 64-bit, and the verified **CUSA00207 1.09** game build.
Launcher **1.7.2 → 1.8.2** was tested. Other official Windows releases from 1.7
onward use automatic rebuilding; incompatible upstream changes can require an
Atlas repair. A failed Atlas rebuild does not block a verified launcher update.
See [compatibility](docs/COMPATIBILITY.md).

Maps and the game font are generated from your own game files. No game files,
generated maps or saves are distributed. Your usual saves and settings remain
selected. Travel uses the game’s normal loading/saving and sets the next respawn
destination. Keep the installed Atlas folder in place; use **Uninstall.cmd** to
restore the stock launcher for its current version.

## Source and credits

[Build guide](source/SOURCE-BUILD.md) · [Licenses and notices](source/licenses/README.md) ·
[Validation](docs/QA.md)

Built for [Supermedo’s Bloodborne for Windows](https://github.com/Supermedo/bloodborne_pc).
Hunter’s Atlas is an independent community project, unaffiliated with FromSoftware
or Sony Interactive Entertainment.
