# Validation and known limits — Hunter's Atlas 1.0

The installer, launcher integration and Atlas runtime were checked together before this clean end-user test. The 1.0 player archive has a rebuilt launcher adapter and installer with Windows `Install.cmd`/`Uninstall.cmd` entry points. The native Atlas runtime executable is byte-identical to the previously validated build. A fresh install by the owner is still pending, so the public release remains unpublished.

## Checks already completed

- The launcher add-on was installed and removed through its own installer. Removal restored the exact stock launcher and retained the rollback copy.
- A fresh extraction of the complete package and two install, launcher, and uninstall cycles succeeded on an isolated test profile. The extracted archive kept its empty `maps` folder and had no nested package directory.
- A fresh player-archive install under Restricted PowerShell policy generated all 16 maps and the font automatically. It took 8 minutes 45 seconds on the test PC, displayed percentage progress through completion, selected the extracted Atlas folder in the launcher profile, and wrote detailed diagnostics to the rollback folder's `atlas-install.log`.
- The final player archive also passed an isolated reinstall with already prepared maps: it reused the maps, selected the extracted folder, and restored the exact stock launcher on uninstall. No real game, save, launcher or profile files changed during that final test.
- The launcher map-preparation UI now displays concise percentage/status messages and writes detailed generator output to an AppData log instead of printing raw JSON in the UI.
- Normal Play loaded a copied save in Cathedral Ward. Left and right navigation included the Map tile, Confirm and Back worked, and mouse hover/click/back worked.
- Atlas selection and confirmation decoded the supported game's local cursor sounds. Runtime checks used a silent audio backend; the fully muted path remained silent.
- The map was captured in the game at Great Bridge, Clinic, Hunter's Dream and Hunter's Nightmare. Those captures are examples, not human visual approval.
- Original launcher settings, game executable and saves were checked unchanged during the isolated package tests.

## Known limits

- The clean download and installation on the owner's everyday profile still needs the owner's review before publication.
- Physical gamepad-device behavior, focus loss and controller disconnect have not been certified. The input checks used the game's logical input path and injected mouse events.
- An idle title-screen attract movie can cause a guest read fault; whether Atlas contributes is unresolved.
- Atlas cursor sounds follow the main output volume and full mute. A separate sound-effects slider inside the game's FMOD mixer may not affect these added clips.
- Chalice maps, live quest or gate state, every route in all 16 maps, universal launcher compatibility and a complete playthrough are not claimed.
- Visual examples are provided for review. Human visual approval has not been claimed.

If the launcher reports that Bloodborne: The Old Hunters is missing, stop there and report the message. Do not change game files or saves while diagnosing it.
