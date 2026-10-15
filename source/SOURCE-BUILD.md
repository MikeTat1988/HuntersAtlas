# Hunter's Atlas corresponding-source build guide

This guide applies to the corresponding-source archive. It describes native, launcher, and map-generator builds from the included source. It does not claim that a freshly built binary is byte-for-byte identical to the release binary.

## Source tree and inputs

The archive root contains `native/`, `launcher/`, `generator/`, `licenses/`, and `art-originals/`. The `native/` subtree is the upstream bbport source with the Atlas renderer changes. Its required vendored source is expanded under `native/gpu/third_party/` and `native/third_party/`; no `.git` metadata is shipped. In particular, the host shader GLSL files, the FSR-Vulkan source and local patches, `LibAtrac9`, and the licensed DejaVu Sans fallback are build/runtime inputs. Do not remove these directories when pruning unused documentation or tests.

The `runtime-dependencies/` directory inside the separate `Hunters-Atlas-Source-1.0.zip` is compliance source for selected system runtime packages and build tools; it is not a compiler SDK or a replacement for the system development packages listed below. `licenses/runtime-source-index.json` maps each covered runtime library to its source recipe and notices. GEOS 3.13.1 source and its SHA-256 receipt are included there for the generator's pinned Shapely 2.1.2 dependency. Exact PyInstaller 6.16.0 and 6.22.3 source distributions are included there with PyPI URL/hash receipts. The generator's included Soulstruct source is the reviewed Python/project-only extraction; the upstream sdist containing unrelated executable and DLL resources is intentionally omitted.

## Native Windows build

Use 64-bit Windows 10 1903 or Windows 11 and an MSYS2 **CLANG64** shell. The source README's dependency inventory is:

```text
git, patch
mingw-w64-clang-x86_64-{toolchain,cmake,ninja,pkgconf,python}
mingw-w64-clang-x86_64-{vulkan-headers,vulkan-loader,vulkan-memory-allocator,glslang}
mingw-w64-clang-x86_64-{sdl3,fmt,boost,robin-map,xxhash,ffmpeg,zydis}
mingw-w64-clang-x86_64-{spirv-tools,spirv-headers,spirv-cross}
mingw-w64-clang-x86_64-{protobuf,openssl,zlib,miniupnpc,nlohmann-json}
```

These provide CMake's required Vulkan, fmt, Boost, robin-map, Vulkan Memory Allocator, xxhash, SDL3, FFmpeg, Zydis, protobuf, nlohmann-json, OpenSSL, zlib, miniupnpc, and glslang dependencies. `magic_enum`, `miniz`, `xbyak`, ImGui, SPIRV-Tools/headers, sirit, FSR-Vulkan, and LibAtrac9 source are present in the native source tree. That README is the package-name authority. MSYS2 package repositories are rolling; the package list is not an immutable repository snapshot.

The production build used these observed tool versions: Clang 23.1.3, CMake 4.4.4, Ninja 1.13.2, pkgconf 3.0.7, glslang 16.6.0, and MSYS2 Python 3.14.8. `native/gpu/CMakeLists.txt` requires CMake 3.24 or newer and C++23. Host shaders are generated with glslang targeting Vulkan 1.3. The installed MSYS2 versions are a reference inventory, not hard minimums beyond constraints stated in source.

The `native/build.sh` Windows path configures CMake with:

```text
-S gpu -B out/gpu -G Ninja
-DCMAKE_BUILD_TYPE=RelWithDebInfo
-DBB_PGO=off
-DBB_LTO=${BB_LTO:-OFF}
-DCMAKE_C_COMPILER=clang
-DCMAKE_CXX_COMPILER=clang++
```

From an MSYS2 CLANG64 shell, set `MSYS2_ROOT` if MSYS2 is not installed at the script's default location. Then run:

```bash
cd native
export MSYS2_ROOT=/c/msys64
export BB_LTO=OFF
bash build.sh
```

`MSYS2_ROOT` and `BB_LTO` are explicit toolchain/options inputs. The script builds `out/bb-probe.exe`, `out/bb-gpu-capabilities.exe`, and `out/bb-play.exe`; the GPU build targets are `bb-probe`, `bb-gpu-capabilities`, and `bb-play`. To enable link-time optimization, set `BB_LTO=ON`; the Windows path keeps profile-guided optimization off. The Linux path has separate defaults and is not the Windows release configuration.

The required shader source inputs remain in `native/gpu/shadps4/video_core/host_shaders/`. CMake generates their C++ headers in `out/gpu/include/`; generated headers and object files are not source. The archived `native/build.sh` checks for the expanded vendor source before considering submodule initialization, then applies the included FSR-Vulkan patches. A full Git clone is therefore not needed when building from this complete archive. If using a partial checkout, initialize the submodules named in `native/.gitmodules` before building.

## Launcher build and tests

The matching Atlas-integrated launcher source is in `launcher/`; the older native `native/launcher/` code is part of bbport, not this Windows UI adapter. Launcher build-receipt paths are sanitized and relative to the launcher source tree.

The 1.0 launcher and installer are frozen with CPython 3.12.14, PyInstaller 6.22.3, Pillow 12.3.0 and matching Tcl/Tk 8.6.12 data. These launcher builds are separate from the unchanged MSYS2 native runtime build. The frozen-source verifier uses the included native preparation scripts. Optional upstream comparison audits accept `ATLAS_BASELINE_SOURCE` (original launcher/run.py folder), `ATLAS_STOCK_EXE` (fingerprinted stock launcher), and `ATLAS_PREPARATION_SCRIPTS`; without these inputs it still verifies frozen code/imports/Tk, and records that the optional baseline comparison was not performed. Use a Python interpreter supplied explicitly to the build script; for example:

```powershell
$Python = (Resolve-Path $env:ATLAS_PYTHON).Path
$PyInstallerSdist = Join-Path $env:ATLAS_RUNTIME_SOURCE 'licenses/source/build-tools/pyinstaller-6.22.3.tar.gz'
$LauncherBuildReqs = Join-Path $env:TEMP 'atlas-launcher-build-requirements.txt'
Get-Content generator/requirements-build.txt | Where-Object { $_ -notmatch '^\s*pyinstaller==' } | Set-Content -Encoding ascii $LauncherBuildReqs
& $Python -m pip install -r $LauncherBuildReqs
& $Python -m pip install --no-deps --no-build-isolation $PyInstallerSdist
& $Python -m unittest discover -s launcher/tests -v
& .\launcher\build_frozen_launcher.ps1 -Python $Python
```

Set `ATLAS_PYTHON` to the full path of the intended CPython 3.12 interpreter and `ATLAS_RUNTIME_SOURCE` to the extracted `runtime-dependencies/` directory. Set `TCL_LIBRARY` and `TK_LIBRARY` to complete matching Tcl/Tk script folders; each must include its upstream `license.terms` for notice collection. The scripts used for 1.0 are recorded in `launcher/build-tool-inputs.json`. The PyInstaller source archive is used directly; the other launcher build requirements are pinned by the generator's `requirements-build.txt`. The build writes only under `launcher/build/`. The script collects Tcl/Tk and Python notices from the selected interpreter, then runs `launcher/verify_frozen_sources.py`. Re-run the source verifier after a successful freeze. `launcher/build/source-receipt.json` records the release executable hash and frozen-source checks; it is provenance, not a replacement for rebuilding and checking the executable.

## Map generator build and tests

The generator source is in `generator/src/`; `generate_atlas.spec` is a relative PyInstaller spec. The frozen generator was built with CPython 3.12.14, PyInstaller 6.16.0, and hooks-contrib 2026.8. Use CPython 3.12 for its pinned native dependencies. The package pins its runtime, frozen, and build Python distributions in `requirements-runtime.txt`, `requirements-frozen.txt`, and `requirements-build.txt`, and records frozen module mappings in `frozen-dependency-inventory.json`.

Create an isolated environment from an explicitly selected CPython 3.12 interpreter, install the pinned requirements, and use the included Soulstruct project source rather than downloading the upstream sdist:

```powershell
$Python = (Resolve-Path $env:ATLAS_PYTHON312).Path
& $Python -m venv generator/.venv
$VenvPython = (Resolve-Path generator/.venv/Scripts/python.exe).Path
$RuntimeReqs = Join-Path $env:TEMP 'atlas-runtime-requirements.txt'
$FrozenReqs = Join-Path $env:TEMP 'atlas-frozen-requirements.txt'
$BuildReqs = Join-Path $env:TEMP 'atlas-generator-build-requirements.txt'
$PyInstallerSdist = Join-Path $env:ATLAS_RUNTIME_SOURCE 'licenses/source/build-tools/pyinstaller-6.16.0.tar.gz'
Get-Content generator/requirements-runtime.txt | Where-Object { $_ -notmatch '^\s*soulstruct==' } | Set-Content -Encoding ascii $RuntimeReqs
Get-Content generator/requirements-frozen.txt | Where-Object { $_ -notmatch '^\s*soulstruct==' } | Set-Content -Encoding ascii $FrozenReqs
Get-Content generator/requirements-build.txt | Where-Object { $_ -notmatch '^\s*pyinstaller==' } | Set-Content -Encoding ascii $BuildReqs
& $VenvPython -m pip install -r $RuntimeReqs -r $FrozenReqs -r $BuildReqs
& $VenvPython -m pip install --no-deps --no-build-isolation generator/licenses/soulstruct-source
& $VenvPython -m pip install --no-deps --no-build-isolation $PyInstallerSdist
& $VenvPython -m unittest discover -s generator -p 'test_*.py' -v
& $VenvPython -m PyInstaller --noconfirm --clean --distpath generator/build/dist --workpath generator/build/work generator/generate_atlas.spec
```

Set `ATLAS_PYTHON312` to the full path of CPython 3.12.14 (or a compatible CPython 3.12 build), and `ATLAS_RUNTIME_SOURCE` to the extracted runtime-source archive root. Use the resulting `generator/build/dist/generate_atlas/` directory as the frozen output. A map-generation run separately requires the user's supported game folder and explicit output folder; pass them with `--game-dir` and `--output-dir` as documented in `generator/README.md`. No game files, game-derived map data, caches, or generated outputs are source-build inputs.

## Dependency and version limits

The package carries exact source for its expanded in-tree native vendors, the 33 indexed GPL/LGPL MSYS2 runtime package owners, three pinned upstream source trees, and GEOS 3.13.1. The MSYS2 Windows build still consumes system development packages; install the names in `native/packaging/windows/README.md` and consult `licenses/notices/installed/` for the recorded runtime package versions and notices. The exact compiler/system-package repository snapshot is not included, so system package resolution and resulting binaries can differ over time. Use the receipts and SHA manifests to compare source inputs and release outputs; successful compilation alone does not establish runtime or visual acceptance.

## Release packaging

Run `package_release.py --help` from a source checkout to build the two release assets. `Hunters-Atlas-1.0.zip` is the installable player package: verified native runtime, frozen generator, launcher adapter and installer, one user README and eight examples. `Hunters-Atlas-Source-1.0.zip` is the complete corresponding source with dependency source and the release entry-point scripts in `release-scripts/`. Both files are offered together on the same GitHub release; players need only the first file. Internal build reports and checksum lists are not user downloads.
