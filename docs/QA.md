# Release validation

Hunter’s Atlas 1.0 is the sole current release. The owner tested and approved Atlas in play. A separate first installation from an art-only player ZIP into an independently downloaded official Windows v1.7.2 launcher also passed under Windows PowerShell 5.1, without any previous Atlas installation.

| Check | Result |
| --- | --- |
| Fresh installation and automatic preparation | Passed; installer exit 0 |
| Generated maps | 16 maps, 602 layers, 742,315 triangles, 442,011 walls |
| Markers and catalog | 44 lamps, 48 ladders, 66 NPCs, 85 gates, 320 regions |
| Generator duration | 567.91 seconds at BelowNormal priority |
| Current bootstrap in the stock launcher's private Python | Passed; package contract loaded, launch environment built |
| Current launcher readiness in that private Python | Ready — Hunter's Atlas 1.0 verified; generated_ready=true |
| Focused automated tests | 47 passed: bootstrap, UI bridge, preparation, asset storage, bundle and dependency template |
| Cancellation process-tree fixtures, Windows PowerShell 5.1 | Passed; successful tree termination and safe handling of denied/missing taskkill |
| Local test uninstall | Original launcher restored; 3,096 protected game/save/DLC files and ordinary launcher settings unchanged |

The prepared asset pack is 21,870,216 bytes with SHA-256 `b889555f3aae436a3a59c05c14f863e8e8e56ac7ab70b45a78fd63c394efda19`. It is generated locally and is not included in the player download. The player ZIP starts with owned art and a licensed fallback font only.

The complete preparation used the unchanged frozen generator. The final source refresh renamed the former internal edition identifier to Atlas and verified that identifier, source hashes, contract, environment and readiness in the stock interpreter. The installer cancellation fallback was tested separately; its successful preparation path is unchanged. A separate hidden-window smoke attempt was inconclusive and is not claimed as a pass.

## Scope and limits

The native map host is the owner-approved runtime with debug sections removed; retained executable sections and RVAs are byte-identical. Owner play approval and these technical checks do not certify every route, floor, controller, graphics device or full playthrough. Chalice Dungeons, live quest/gate tracking and unlisted game regions are unsupported. Only the exact game and launcher fingerprints in [Compatibility](COMPATIBILITY.md) are supported.
