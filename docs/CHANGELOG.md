# Hunter’s Atlas 1.0

- Hotfix: use serial draw preparation for Atlas sessions following a GPU FMask conversion assertion; the owner's repeat test completed without that crash. This is a stability workaround, not proof that every renderer crash is resolved.
- Simplifies the map footer to Zoom, Recenter and Back; removes the Pan and Elevation controls from the main map screen.
- Adds an isolated Atlas launcher integration for the verified official Windows launcher.
- Generates the 16 supported maps and required font locally from the user’s compatible game files; neither maps nor game files are included in the player package.
- Uses the verified stock launcher’s private runtime and selected launcher dependencies without requiring a separately installed Python runtime or compiler for players.
- Checks the launcher and CUSA00207 1.09 game fingerprints before installation or launch.
- Keeps Atlas configuration, generated assets, and runtime state within its package and profile, and provides an installer/uninstaller that backs up and restores the original launcher.
- Includes corresponding source, native GPL source and vendored inputs, source-build instructions, and third-party notices in the source release.
