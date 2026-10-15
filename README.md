# Hunter's Atlas

An optional, in-game map for Bloodborne's matching Windows PC launcher. Select the Atlas folder, enable it, and use the launcher's normal **Play** button. A fourth **Map** tile appears in the quick menu.

![Hunter's Atlas — Great Bridge](examples/great-bridge.png)

**[Download the beta](https://github.com/MikeTat1988/HuntersAtlas/releases/tag/v1.4.0-beta2)** · **[Easy installation](docs/INSTALL.md)** · **[Compatibility](docs/COMPATIBILITY.md)** · **[Testing and known limits](docs/QA.md)**

## What it does

- Follows your position and facing through 16 supported main-game/DLC maps.
- Adds a clickable Map tile beside System, with controller navigation and the game's Cross/Circle Confirm mapping.
- Wraps through Map in both directions and reads the game's cursor sounds locally for Atlas selection and confirmation.
- Supports pan, zoom, elevation shading, recenter and Back.
- Keeps other storeys faded for context. Dark, scratched interiors distinguish inferred enclosed spaces from pale floors.
- Preserves the painted sides with a central frame and soft map-edge fades.
- Shows static lamp, ladder, gate and NPC sites. These are locations, not live quest or door states.
- Prepares maps and the native font locally from your own game files. No game download is included.

## Install in a few steps

1. Download **Hunters-Atlas-1.4.0-beta2.zip** from [Releases](https://github.com/MikeTat1988/HuntersAtlas/releases), rather than GitHub's **Code → Download ZIP** source archive. Extract the full archive into a folder you can keep. The package files (`manifest.json`, `runtime`, `art`, `maps`, `settings`, `tools`) sit beside `Install.ps1` at the release root.
2. Close the launcher and game. Run `Install.ps1` with PowerShell and enter your existing launcher folder. It installs the compatible adapter and retains the original executable for rollback. If your launcher does not match, it stops with an explanation.
3. Open your usual `Bloodborne.exe`. The Atlas package path is the extracted release root. If it is not already selected in **Mods & patches → Hunter's Atlas**, browse to that root once. Select **Prepare Atlas maps** if prompted. Preparation takes several minutes and needs no separately installed Python.
4. Enable Hunter's Atlas and click the ordinary **Play** button. In the game's quick menu, move right from System to Map and Confirm, or click Map.

Disable Atlas in the same launcher panel to use its original runtime. See [installation and uninstall instructions](docs/INSTALL.md) for the command-line alternative and exact rollback procedure.

## Compatibility and beta status

This is **1.4.0-beta2**, for the fingerprinted **Windows v1.7.2 Atlas adapter** and tested **CUSA00207 01.09** executable. It is not a universal plug-in for arbitrary bbport/shadPS4 builds. The installer and manifest check exact identities; see [the compatibility matrix](docs/COMPATIBILITY.md).

Normal packaged Play, enable/disable, native Confirm layouts, injected runtime input, named scene captures and exact launcher restoration were tested. Physical-device, focus-loss and disconnect acceptance remains incomplete. An idle title-screen attract movie can still cause a guest fault; its stock-versus-Atlas cause is unresolved. No complete playthrough, universal controller support or human visual approval is claimed. [Read the QA record](docs/QA.md) before installing.

Chalice Dungeons, live quest state and live gate state are outside this beta. Collision-derived geometry and inferred interiors can have omissions. The package does not replace learning the game; it gives you another optional way to navigate it.

## Examples

| Quick-menu entry | Enclosed interiors |
| --- | --- |
| ![Fourth Map tile](examples/quick-menu.png) | ![Scratched tower interiors](examples/tower-interiors.png) |

| Clinic | Hunter's Dream | Hunter's Nightmare DLC |
| --- | --- | --- |
| ![Clinic](examples/clinic.png) | ![Dream](examples/dream.png) | ![DLC](examples/dlc.png) |

These are actual captured runtime images. Some use earlier builds with the same final map layout; [capture provenance](examples/README.md) identifies them. Images are examples for review, not a certification of every route or height.

## Source, attribution and licenses

The corresponding implementation is under [`source/`](source/), including the native host, matching launcher adapter, complete generator and required vendored source. Start with [SOURCE-BUILD.md](source/SOURCE-BUILD.md). Runtime/dependency source archives and checksums are attached to the release; large compiled packages are deliberately kept out of Git history.

Source inventory hashes describe the corresponding-source release ZIP. Git may apply upstream vendors' line-ending rules on checkout; use that ZIP when comparing exact archived bytes. Generator input hashes are preserved explicitly on Windows checkouts.

Hunter's Atlas builds on [Supermedo's bloodborne_pc](https://github.com/Supermedo/bloodborne_pc), its bbport runtime and incorporated projects. Recorded baselines are native `e699fdf76ff001df159dab049dfdac1a3446f13d` and launcher `e5d04e2ba4864ccf40de6c3cf6aa532855320b0d`. This is an independent community add-on, not an official FromSoftware/Sony project.

The native host and Atlas additions retain their GPL notices; see [LICENSE](LICENSE), individual source headers and [dependency notices](source/licenses/). Other components and art retain their respective licenses/provenance. Development and original illustrative assets used AI assistance. Game-derived maps and fonts are generated on the user's computer and are not distributed here.

Bug reports are welcome: include the exact launcher/runtime version, area, steps and relevant error lines. Remove account identifiers and private paths; do not upload saves or game files.
