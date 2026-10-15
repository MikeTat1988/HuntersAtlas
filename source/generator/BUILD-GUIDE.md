# Atlas Lite generator build record

The official frozen entry point is `src/generate_atlas_lite.py`.
That thin wrapper adds `--self-test-imports`, then delegates ordinary generation
to `generate_atlas.main()`; the 13 algorithm/source scripts below it are copied
byte-for-byte from the original Hunter's Atlas generator. The archived wrapper
copy in this directory is SHA-256 identical to the frozen entry source. The
portable current PyInstaller spec is `generate_atlas.spec`; its
copy here is a reference snapshot, and the spec should be run beside the
`generator/src/` tree that it names.

`generator-build-inputs.json` pins the copied script hashes, spec, lock-file
hashes, build environment versions, and the already generated bundle's hash and
size. It contains no game-generated map or native-font data. The current bundle
is the frozen code runtime only (`generator.atlaslite`, 42,584,212 bytes; SHA-256
`621300c2660025db454b45e6152e14b5c18f6b93e24867e9cc1e661c68c2af36`).

## Pinned build environment

Build on Windows x64 with CPython 3.12.14 and the exact pins in
`requirements-runtime.txt`,
`requirements-frozen.txt`, and `requirements-build.txt`. The tested environment
uses PyInstaller 6.16.0 and pyinstaller-hooks-contrib 2026.8, with NumPy 2.5.4,
SciPy 1.16.3, Shapely 2.1.2, Pillow 12.3.0, Soulstruct 2.3.2, ConStrata 1.3.3,
fontTools 4.61.1, zstandard 0.25.0, lxml 6.1.1, CFFI 2.1.1, and
charset-normalizer 3.5.2. These pins matter because the frozen native extension
modules target CPython 3.12.

Set `ATLAS_GENERATOR_BUILD_DEPS` to a directory containing those installed
build/frozen dependencies. The PowerShell example below uses a locally available
CPython 3.12 executable and keeps all build products inside `generator/`:

```powershell
$GeneratorRoot = (Resolve-Path 'source/generator').Path
$Python312 = 'C:\Path\To\Python312\python.exe'
$env:PYTHONPATH = $env:ATLAS_GENERATOR_BUILD_DEPS
& $Python312 -m PyInstaller --noconfirm --clean `
  --distpath (Join-Path $GeneratorRoot 'dist') `
  --workpath (Join-Path $GeneratorRoot 'build') `
  (Join-Path $GeneratorRoot 'generate_atlas.spec')
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
```

The spec explicitly keeps SciPy sparse/linalg/spatial/special, drops unused
SciPy subpackages and only the confirmed-unloaded root OpenBLAS duplicates and
unused Pillow codec extensions. It does not alter generator algorithms. Before
packing, verify the real import closure and entry point; then package only the
frozen directory, never game input or generated maps:

```powershell
& $Python312 source/lite/generator/atlas_lite_bundle.py pack `
  --source-tools (Join-Path $GeneratorRoot 'dist/generate_atlas_lite') `
  --output 'path/to/generator.atlaslite' --compression lzma
& $Python312 source/lite/generator/atlas_lite_bundle.py verify `
  --bundle 'path/to/generator.atlaslite' --self-test-imports
```

The shipped bundle is `tools/generator.atlaslite` in the player ZIP. Its inputs
and exact artifact hashes are recorded in `generator-build-inputs.json`. The
source and dependency archive accompany the release. This record does not claim
bit-identical builds from an arbitrary newer toolchain.
