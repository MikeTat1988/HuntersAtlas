# Hunter’s Atlas 1.1 source and build guide

This guide describes the source available in this repository. Players use the prepared Atlas ZIP and do not need Python, a compiler, or the developer dependencies below. A rebuild is not guaranteed to produce byte-identical executables.

## Source layout

- `native/` contains the Windows native host and Atlas changes, with the required upstream vendor source and patches.
- `generator/src/` contains the original map-generation algorithms. The Atlas generator code under `lite/generator/` wraps, packages, and prepares that source for the first-install workflow; it does not replace the original algorithms.
- `lite/bootstrap/` contains the isolated package and launch checks.
- `lite/integration/ui/` and `lite/integration/` contain the launcher integration and its C wrapper source.
- `licenses/` contains project and third-party notices and source receipts. Runtime dependency source is supplied in this repository under `source/runtime-dependencies/`, not the player package.

Keep `native/gpu/third_party/`, `native/third_party/`, and the shader inputs in `native/gpu/shadps4/video_core/host_shaders/`. They include required host shaders, FSR-Vulkan source and patches, LibAtrac9, and other vendored code used by the build. Generated headers, object files, caches, and output directories are build products, not corresponding source.

## Build the Windows release assets

The combined release assembly entry point is `lite/build_auto_update_release.py` with `--release --version 1.2`; it reuses the verified 1.7.2, 1.8.1, 1.8.2 and 1.9 runtimes and the reviewed rebuild seed. See `docs/releases/RELEASE-PROCESS.md` for the publication procedure. Pass each additional verified package with `--additional-package` and its exact native source archive with `--additional-source`. The assembler includes these adapters in the authenticated bundled catalog. `lite/build_release.py` assembles an individual adapter. It takes explicit build inputs and writes to a new output directory:

```powershell
python source/lite/build_release.py `
  --runtime-dir <native-build-output-with-required-dlls> `
  --generator-bundle <generator.atlaslite> `
  --launcher-root <pristine-windows-v1.8.1-tree> `
  --wrapper <AtlasLauncher.exe> `
  --dependency-source <runtime-dependency-source.zip> `
  --catalog-signing-key <private-maintainer-key.json> `
  --output <new-output-directory>
```

Build the wrapper from `lite/integration/launcher_wrapper.c` with `lite/integration/Build-Wrapper.ps1`. This source build requires Visual Studio C++ Build Tools and the Windows SDK; players do not need them. Build the native runtime and frozen generator from their corresponding source before running the release assembler. `--launcher-root` must be a pristine official Windows v1.8.1 tree. The assembler checks its declared inputs. `--player-only` is available for intermediate validation; delivery requires both player and corresponding-source archives.

The native source is rebased on upstream commit `bee7ec16213022f15bf34084b5587f1ff09e0e65`. `runtime_atlas_build.h` embeds the protocol, feature schema and upstream identity. After stripping debug sections with `lite/strip_runtime.py`, place `native-build.json` beside the executable with those fields and its actual SHA-256. The assembler rejects a mismatch. `bb-probe.exe --atlas-build-info` prints the compiled identity without loading the game.

The compatibility catalog is RSA-3072/SHA-256 authenticated. Its public key is `lite/updates/trusted-key.json`; private signing material is deliberately absent from the source and player archives. Maintainers rebuilding independently must generate their own RSA key, update the public trust key and sign their build. Such a build is a separate trust identity and cannot impersonate the release catalog. The release bundles its signed catalog and adapter. Releases absent from the catalog use the shipped rebuild seed and authenticated official source. Catalog records contain fixed identities and artifact URLs, never executable commands.

The repository includes runtime dependency source under `source/runtime-dependencies/`. To rebuild the release archive, ZIP that directory as `runtime-dependency-source.zip` and pass it to `--dependency-source`. It is not required by the player, and the player package does not install a global Python runtime or compiler. Map generation for a release test requires the user’s own supported game copy; game files, generated maps, and the game font are not source-build inputs or player downloads.

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

The original algorithms are under `generator/src/`. The Atlas wrapper, bundle packer, and headless preparation entry points are under `lite/generator/`. Build the frozen generator with the CPython 3.12 toolchain and pinned dependencies described by the generator requirements and source receipts. The corresponding source archive includes the required project-only source and the optional dependency-source material referenced by those receipts.

The prepared player uses the frozen generator through the verified launcher’s private runtime. It prepares 16 maps and the required font from the compatible game files chosen by the user. Keep generated output outside the source tree and do not add game-derived maps or fonts to the release asset.

## Source and license records

The native host and its Atlas changes retain their GPL notices and complete corresponding source, including required vendors and patches. Third-party binaries and source components retain their own license terms. See [the license and source guide](licenses/README.md), the license files shipped beside each component, and the machine-readable runtime indices. These records describe the indexed components; they do not make a general legal determination or broaden a component’s license coverage.

The 1.9 adapter uses `lite/compatibility/profiles/windows-v1.9/`. The source release stores shared dependency and vendor files once. Reconstruct its exact expanded native source with `python source/lite/extract_corresponding_source.py Hunters-Atlas-Source-1.2.zip corresponding-source/windows-v1.9-source.json native-1.9`. Equivalent recipes cover 1.7.2, 1.8.2 and the automatic rebuild seed. Each reconstructed file is verified against its original SHA-256. The repository root native tree remains the 1.8.1 source for that retained adapter. The current automatic rebuild seed uses a 1.9 baseline; future source conflicts still require review.
