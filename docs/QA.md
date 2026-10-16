# Release validation — Hunter’s Atlas 1.1

The owner confirmed that installation and the launcher update worked on
October 16, 2026. Automated checks used disposable launchers and copied saves.

| Check | Result |
| --- | --- |
| Repair an installed Atlas on launcher 1.7.2 | Passed |
| Ordinary launcher Update callback, 1.7.2 → 1.8.2 | Passed: native rebuild, activation and automatic restart |
| Restarted launcher status | Ready; Atlas enabled |
| Map reuse | Verified pack reused without regeneration |
| In-game map and lamp selection on 1.8.2 | Passed |
| Travel to Tomb of Oedon | Completed; arrival verified |
| Undiscovered Grand Cathedral lamp | Hidden |
| Confirmation proportions | Passed at 1920×1080 and 3840×2160 |
| Travel/items disabled | Map still usable; optional controls removed |
| Build tools from an empty directory | Portable bootstrap and compilation passed |
| Injected Atlas build failure | Verified launcher activated; maps/settings retained; stock game route used |
| Uninstall from pending state | Restored new stock launcher |
| Python unit suites | Updates 27; UI bridge 10; bootstrap 20; dependency packaging 3 |
| Production protection | 17 recorded launcher/save hashes unchanged during update QA |

The initial gameplay harness attempted travel before the game menu was ready.
The normal travel guard rejected it. Retesting after the native menu became
available completed travel and the 1080p/4K/1080p resize sequence.

Desktop capture was unavailable during update QA. The button callback and Ready
status were checked through the actual Tk widgets. Map layout was inspected in
native render captures. The supplied launcher screenshot illustrates the setup;
it was captured before the 1.1 version label was prepared.

The 1.1 packaging changes version metadata, release status and documentation;
the verified bundled 1.7.2 and 1.8.1 native executables are retained byte-for-byte.
The release preparation report records the final archive checks and hashes.

## Coverage limits

These checks do not certify every destination, death/respawn sequence, story
restriction, pickup collection, NPC stage, reveal boundary, controller or GPU.
NPC filtering is limited to the stages in [controls and coverage](MAP-FEATURES.md).
Chalice Dungeons and unlisted game builds remain unsupported. Future upstream
source conflicts can require an Atlas integration repair.
