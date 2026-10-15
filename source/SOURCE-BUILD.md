# Hunter’s Atlas Lite 2.0.0 source and build guide

This guide describes the corresponding source release. Players use the prepared Lite ZIP and do not need Python, a compiler, or the developer dependencies below. A rebuild is not guaranteed to produce byte-identical executables.

## Source layout

- `native/` contains the Windows native host and Atlas changes, with the required upstream vendor source and patches.
- `generator/src/` contains the original map-generation algorithms. The Lite generator code under `lite/generator/` wraps, packages, and prepares that source for the first-install workflow; it does not replace the original algorithms.
- `lite/bootstrap/` contains the isolated package and launch checks.
- `lite/integration/ui/` and `lite/integration/` contain the launcher integration and its C wrapper source.
- `licenses/` contains project and third-party notices and source receipts. Runtime dependency source is supplied under `runtime-dependencies/` in the corresponding source release, not the player package.

Keep `native/gpu/third_party/`, `native/third_party/`, and the shader inputs in `native/gpu/shadps4/video_core/host_shaders/`. They include required host shaders, FSR-Vulkan source and patches, LibAtrac9, and other vendored code used by the build. Generated headers, object files, caches, and output directories are build products, not corresponding source.

## Build the Windows release assets

The release assembly entry point is `lite/build_release.py`. It takes explicit build inputs and writes to a new output directory:

```powershell
python source/lite/build_release.py `
  --runtime-dir <native-build-output-with-required-dlls> `
  --generator-bundle <generator.atlaslite> `
  --launcher-root <pristine-windows-v1.7.2-tree> `
  --wrapper <AtlasLiteLauncher.exe> `
  --dependency-source <runtime-dependency-source.zip> `
  --output <new-output-directory>
```

Build the wrapper from `lite/integration/launcher_wrapper.c` with `lite/integration/Build-Wrapper.ps1`. This source build requires Visual Studio C++ Build Tools and the Windows SDK; players do not need them. Build the native runtime and frozen generator from their corresponding source before running the release assembler. `--launcher-root` must be an extracted, pristine copy of the supported official Windows v1.7.2 launcher. The assembler records and checks its declared inputs; use `python source/lite/build_release.py --help` for the exact options supported by the source archive.

The source release includes runtime dependency source under `runtime-dependencies/`. To rebuild the release archive, ZIP that directory as `runtime-dependency-source.zip` and pass it to `--dependency-source`. It is not required by the player, and the player package does not install a global Python runtime or compiler. Map generation for a release test requires the user’s own supported game copy; game files, generated maps, and the game font are not source-build inputs or player downloads.

## Build the native host

Use 64-bit Windows 10 or Windows 11 with MSYS2 and its **CLANG64** environment. The native CMake configuration requires CMake 3.24 or newer and C++23. Install the current CLANG64 toolchain and the packages listed in `native/packaging/windows/README.md`; that file is the package-name authority. The build requires the Vulkan headers/loader and shader tools, SDL3, FFmpeg, fmt, Boost, robin-map, xxhash, Zydis, protobuf, OpenSSL, zlib, miniupnpc, nlohmann-json, and related dependencies recorded there.

From an MSYS2 CLANG64 shell:

```bash
cd source/native
export MSYS2_ROOT=/c/msys64
export BB_LTO=OFF
bash build.sh
```

Set `MSYS2_ROOT` to the actual MSYS2 root if it is elsewhere. The Windows build uses Clang and Ninja, keeps PGO disabled, and writes build output beneath `native/out/`. The build script applies the included FSR-Vulkan patches after checking for the expanded vendor source. A complete corresponding-source archive does not require Git submodule initialization.

## Build the generator

The original algorithms are under `generator/src/`. The Lite wrapper, bundle packer, and headless preparation entry points are under `lite/generator/`. Build the frozen generator with the CPython 3.12 toolchain and pinned dependencies described by the generator requirements and source receipts. The corresponding source archive includes the required project-only source and the optional dependency-source material referenced by those receipts.

The prepared player uses the frozen generator through the verified launcher’s private runtime. It prepares 16 maps and the required font from the compatible game files chosen by the user. Keep generated output outside the source tree and do not add game-derived maps or fonts to the release asset.

## Source and license records

The native host and its Atlas changes retain their GPL notices and complete corresponding source, including required vendors and patches. Third-party binaries and source components retain their own license terms. See [the license and source guide](licenses/README.md), the license files shipped beside each component, and the machine-readable runtime indices. These records describe the indexed components; they do not make a general legal determination or broaden a component’s license coverage.
