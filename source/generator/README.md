# Hunter's Atlas generator

This directory contains the source and build inputs for the Atlas map
generator. Atlas is product version **1.0**; the unchanged generator
algorithm reports its own internal version **1.0.0**. The frozen entry point is
`src/generate_atlas_lite.py`. It provides a bundle import self-test and then
delegates map generation to the original `generate_atlas.py` pipeline. The 13
algorithm and support scripts are byte-identical to the original generator
sources; Atlas changes packaging and orchestration, not the map algorithm.

## Shipped bundle

The release artifact `tools/generator.atlaslite` is a ZIP_LZMA bundle containing
only the frozen generator runtime. It is **42,584,212 bytes (40.61 MiB)**, with
**210 payload files** expanding to **134,963,536 bytes (128.71 MiB)**. During
preparation, the launcher extracts it to package-owned temporary staging, runs
it against the selected game directory, and removes that expanded runtime when
the run ends. The package therefore needs temporary room for both the archive
and expanded runtime; the combined footprint is about **169.32 MiB**, before
generated maps and working files.

The bundle includes the required CPython 3.12 native extensions and GEOS,
SciPy, NumPy, and imaging libraries. The release launcher supplies the ordinary
Python runtime; no global Python installation or separate dependency download
is required. SciPy's cKDTree and the existing geometry operations are retained
to preserve the established output behavior.

The bundle contains no generated maps, game files, save data, or extracted
native font. Preparation reads the user's selected Bloodborne installation,
checks the exact supported Bloodborne 1.09 executable fingerprint, and writes
fresh maps and native-font data into the package asset pack. It does not write
to game files or saves.

## Source and build

The relative PyInstaller spec is `generate_atlas.spec`; `BUILD-GUIDE.md`
documents the pinned Windows x64 / CPython 3.12 build and bundle verification
commands. `generator-build-inputs.json` records source, spec, dependency-lock,
and shipped-bundle hashes plus the tested dependency versions. The expected
internal bundle version is `1.0.0`.

The preparation entry point lives in `source/lite/generator/prepare.py` and is
invoked by the verified frozen launcher with `--script`. See the Atlas source
README and preparation QA for its package-root, cancellation, and rollback
contract. The generator bundle itself remains independent of the old Atlas
installation at runtime.
