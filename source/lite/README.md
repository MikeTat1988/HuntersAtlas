# Atlas Lite implementation

`bootstrap/entry.py` validates the package and the exact supported ordinary
launcher dependencies. `bootstrap/integrated_play.py` receives the normal
launcher's selected game/save/DLC/patch settings, stages compressed Atlas assets
for the session, and runs the native host. The ordinary `run.py` is preserved.

`integration/launcher_wrapper.c` is the small Windows executable installed as
`Bloodborne.exe`. It delegates to the verified original executable under
`Bloodborne.stock.exe` and the external Python UI in `integration/ui/`. The
original launcher's bundled interpreter remains under `_internal`; no second
interpreter is installed for the UI. Build with `integration/Build-Wrapper.ps1`.

`generator/prepare.py` is shipped as `tools/prepare.py`. The installer calls it
through the ordinary launcher's `--script` role. It invokes the verified frozen
bundle, generates maps/font from the user's game, validates the new compressed
pack and manifest, and restores the previous pair on failure or cancellation.
`generator/atlas_lite_bundle.py` builds, verifies and extracts the temporary
generator bundle. See [the generator build guide](../generator/BUILD-GUIDE.md).

`build_release.py` creates the player and complete source downloads. Build
arguments are documented in [SOURCE-BUILD.md](../SOURCE-BUILD.md). The player
ZIP starts with owned art and the licensed fallback font only. Generated maps,
the game font, local profiles, saves and previous Atlas installations are not
build inputs. `packaging/dependency-template.json` records the immutable inputs
of the official supported launcher; mutable patches, shader downloads and
Python caches are deliberately excluded.

Focused tests use the standard library:

```powershell
python -m unittest discover -s source/lite/tests/bootstrap
python -m unittest discover -s source/lite/integration/tests
python -m unittest discover -s source/lite/generator/tests
python -m unittest discover -s source/lite/generator -p test_atlas_lite_bundle.py
python -m unittest discover -s source/lite/packaging -p test_build_dependencies.py
python -m unittest discover -s source/lite -p test_assets.py
```

Compatibility and release evidence are in [docs/COMPATIBILITY.md](../../../docs/COMPATIBILITY.md)
and [docs/QA.md](../../../docs/QA.md). Game/launcher input changes require a newly
verified dependency template and independent preparation/launch validation;
do not weaken fingerprint checks to make an unsupported build appear ready.
