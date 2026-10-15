# Generator and preparation QA

## Frozen generator

The shipped `generator.atlaslite` was independently run against a fresh output
directory using the supported Bloodborne 1.09 input. It generated all 16
supported maps in 542.52 seconds. The generated map JSON files, atlas, catalog,
native font, geometry layers, bounds, and marker semantics matched the retained
reference outputs; generated-file hashes passed. The artifact receipt records
the 42,584,212-byte ZIP_LZMA archive, 134,963,536-byte expanded runtime, 210
payload files, version probe `1.0.0`, import self-test pass, and expanded-runtime
cleanup pass. The algorithm scripts also match their original source hashes.

The import self-test covers the shipped NumPy, SciPy spatial cKDTree, SciPy
special, Shapely/GEOS, and Pillow/FreeType components. The build spec removes
only unused Pillow extensions and verified-unloaded duplicate OpenBLAS files;
it retains the numerical and geometry dependencies used by generation.

## Headless preparation

The package preparation entry point accepts:

```text
--game-dir <Image0-or-parent> --output-dir <Lite-package-root> --headless [--cancel-file <path>]
```

It loads the package's verified bootstrap contract, requires the output
directory to be the package root, and calls the unchanged frozen generator.
The generated maps and fresh native font are combined with release-owned art;
existing maps and fonts are ignored. The new asset pack and manifest are
committed together, with byte-for-byte rollback if validation fails or
cancellation arrives during commit. The expanded generator and work files are
kept under package-owned staging and cleaned after the run.

Run the focused headless preparation tests with the supported test Python:

```powershell
python -m unittest discover -s source/lite/generator/tests -p test_prepare.py -v
```

Current result: **7 passed**. The tests cover successful refresh, removal of
stale maps and fonts, generator failure, cancellation during generation,
cancellation between pack/manifest replacement, post-commit validation
rollback, output-root rejection, and cancellation of a child process with log
draining. They use disposable fixtures and do not alter an installed package
or a game directory.

The full frozen map-generation run is separate from the preparation-wrapper
tests. A full installer first run also passed in a fresh disposable package and an
independently extracted official launcher under Windows PowerShell 5.1. The
frozen generator completed in 567.91 seconds at BelowNormal priority, producing
16 maps, 602 layers, 742,315 triangles, 442,011 walls, 44 lamps, 48 ladders,
66 NPCs, 85 gates and 320 catalog regions. The installer exited with code 0.
The committed prepared pack is 21,870,216 bytes with SHA-256
`b889555f3aae436a3a59c05c14f863e8e8e56ac7ab70b45a78fd63c394efda19`.
This integration check is separate from the seven preparation unit tests.

## Scope

These checks establish deterministic output parity for the tested Bloodborne
1.09 input and the preparation transaction behavior. They do not establish
visual map approval, compatibility with other game builds, quest-state or
walk-through completeness, or clean-machine Windows installer acceptance.
