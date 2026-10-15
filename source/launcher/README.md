# Hunter's Atlas launcher integration

This workspace owns the frozen-matching Windows v1.7.2 launcher copy, the add-on resolver,
its focused tests, and the rebuilt launcher output. It does not modify the installed launcher,
the user's AppData settings, saves, or `working/map-source`.

The launcher build identifier is `windows-v1.7.2-atlas1`. The accepted runtime identifier is
`hunters-atlas-runtime-1.4.0-beta1`. The currently fingerprinted game executable is
`Image0/eboot.bin` with SHA-256
`d65f0b4f01d59166aed16f8604196d8b7dd805abbf0758b356e8f1354c9429f9`.

An extracted add-on folder must contain root `manifest.json` with this contract:

```json
{
  "id": "hunters-atlas",
  "version": "1.4.0-beta1",
  "launcher_builds": ["windows-v1.7.2-atlas1"],
  "game_executables": ["<SHA-256 of supported Image0/eboot.bin>"],
  "runtime_build": "hunters-atlas-runtime-1.4.0-beta1",
  "mutable_files": ["settings/settings.ini"],
  "generated": {
    "manifest": "maps/generated-assets.json",
    "required": ["maps/atlas.json", "maps/catalog.json"],
    "generator": "tools/generate_atlas.exe"
  },
  "paths": {
    "probe": "runtime/bb-probe.exe",
    "maps": "maps",
    "config": "settings/settings.ini",
    "art": "art",
    "catalog": "maps/catalog.json",
    "font": "art/fallback.ttf"
  },
  "files": {
    "runtime/bb-probe.exe": "<SHA-256>",
    "tools/generate_atlas.exe": "<SHA-256>",
    "art/fallback.ttf": "<SHA-256>",
    "art/icons.bbra": "<SHA-256>"
  },
  "capabilities": ["navigation-map"]
}
```

Every immutable file in the package must appear in `files` and pass its SHA-256 check. The only
mutable package file is the shortcut settings file in `mutable_files`; launcher enable state and
folder selection remain in the launcher profile. Generated maps and optional `art/native-font.ttf`
are excluded from immutable package hashes and covered by `maps/generated-assets.json`, which
binds their SHA-256 values to the selected `Image0/eboot.bin` fingerprint. The generator may emit
`maps/atlas.json`, `maps/catalog.json`, collision files matching `maps/mNN_NN_NN_NN.json`, and the
optional local font. The generated manifest has `schema: 1`, `version: 1`, `game_eboot_sha256`,
`game_version`, and a `files` SHA-256 map; it does not hash itself. The licensed fallback font
remains immutable and is used if the local font was not generated.

Mods & patches recognizes an extracted but unprepared package and offers **Prepare Atlas maps**.
It runs the hash-verified `tools/generate_atlas.exe` directly with the configured game folder and
selected Atlas folder, supplies a separate temporary staging folder, shows its progress output,
uses the generator's bounded `--replace` mode to repair stale generated outputs, then revalidates
all generated hashes before enabling Atlas. It requires no developer PATH,
manually selected executable, or game data shipped inside the Atlas package. The resolver rejects
absolute/drive paths, traversal, links, bad hashes, unsupported game fingerprints, generator
writes outside the approved output set, and unlisted extra files. Unicode and spaces in folders
are supported.

Run focused tests from the repository root:

```powershell
& 'python' -m unittest discover -s working/atlas-dev/launcher/tests -v
```

PyInstaller 6.22.3 builds the new directory-style frozen executable from the owned source and
matching v1.7.2 helpers. The build uses the bundled MSYS Clang Python 3.14 environment and places
the Tcl/Tk runtime, `_tkinter`, and Tcl scripts inside `_atlas_internal`; it does not depend on
the stock `_internal` tree. Run `build_frozen_launcher.ps1`. The resulting executable and
`run.py` are under `build/dist/Bloodborne`; `build/source-receipt.json` records the executable
hash, exact frozen module source checks, and a successful GUI smoke test using an isolated profile.
The adapter bundle carries the Python 3.14.8 PSF license and Tcl/Tk `license.terms` in
`_atlas_internal/THIRD-PARTY-NOTICES`. The Python 3.14.8 source package is not bundled in this
archive; its MSYS2 package-source URL is
`https://mirror.msys2.org/mingw/sources/mingw-w64-python-3.14.8-1.src.tar.zst`. The bundled Python
PSF and Tcl/Tk notices are retained. The build does not install over `launcher-v1.7`.

The PyInstaller dependencies are isolated in `_atlas_internal`, so an adapter install can keep
the stock launcher's `_internal` directory untouched. `atlas_install.py` installs into a separate
launcher copy only after checking the exact stock v1.7 executable hash, matching `run.py`, build
receipt, and complete hash-valid Atlas folder. Build the standalone public installer with
`build_frozen_installer.ps1`; it produces `build/installer-dist/AtlasSetup.exe` and a source receipt.
The console executable includes its Python runtime and requires no user Python or developer PATH.
Its distribution folder also contains `THIRD-PARTY-NOTICES` for the bundled Python and Tcl/Tk.
The selected Atlas folder remains external. The installer saves the stock executable in a newly
created rollback folder outside both launcher and Atlas, then installs only `Bloodborne.exe` and
`_atlas_internal`; it does not rewrite `run.py`, the stock `_internal`, launcher settings, game
files, or saves.

```powershell
AtlasSetup.exe install `
  --launcher-root 'D:\Games\Bloodborne' `
  --adapter-root 'build\dist\Bloodborne' `
  --atlas-folder 'E:\Tools\Hunter''s Atlas' `
  --rollback-root '%TEMP%\Bloodborne Atlas rollback'
AtlasSetup.exe uninstall `
  --receipt 'D:\Games\Bloodborne\atlas-install-receipt.json'
```

Uninstall refuses if the adapter executable, any `_atlas_internal` file, `run.py`, or rollback
copy changed. It restores the stock executable, removes the exact receipt-owned dependency tree,
and leaves the rollback bundle plus an `uninstalled` receipt for recovery/audit. A fresh install
can reuse that receipt only when its launcher root, restored stock executable, `run.py`, and old
rollback copy all still match. The installer archives the verified prior receipt inside the new
rollback folder before reinstalling; installed, unknown, or tampered receipts are refused. Tests
use temporary folders and a test-only injected baseline hash; no live launcher installation was
performed.

`BB_LAUNCHER_SETTINGS_ROOT` redirects only the launcher's `settings.json` directory for isolated
profile tests. Normal Play and `--play` resolve `game_environment()` when launching. An in-game
restart inherits the validated environment of the current game session; changing the launcher's
Atlas toggle affects the next launch. Disabled Atlas clears inherited map/probe overrides, writes
`BB_ATLAS_ENABLED=0`, and selects the ordinary packaged probe. Enabled Atlas writes
`BB_ATLAS_ENABLED=1` plus the validated package paths and `BB_ENTER_BUTTON` (`1` Cross/A or `0`
Circle/B) only in the game child environment.
