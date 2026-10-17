# Building the independent in-game edition

Hunter’s Atlas 1.3 packages the tested Windows 1.9 Atlas native runtime with a
private CPython 3.10/Tk installation and a pinned ordinary-port file closure.
Players run Install.cmd; these instructions are for maintainers.

## Corresponding source

The versioned Source ZIP contains the current owned installer, frontdoor,
bootstrap, UI and generator sources, documentation and tests. It also contains:

- `corresponding/native-atlas-1.2/`: the corresponding Atlas native source tree used by this unchanged native runtime.
- `corresponding/upstream-windows-v1.9-source.zip`: exact upstream source matching `native-build.json`.
- `corresponding/runtime-dependency-source.zip`: corresponding dependency sources and licenses.
- `proof/`: native identity, runtime dependency pins, adapter identity and the player manifest.

The unchanged native probe SHA-256 is
`887f5baf7e149ea7604e4e037fd5eef43a0ad483a8dcb649a6122636d906c557`.
The upstream commit is `652f9a494c47cc8c1ab16f28b456372eaa8103f8`.
For native compilation and generator details, follow the corresponding native
tree's build instructions and the historical `source/SOURCE-BUILD.md`. Its
launcher-wrapper installation and updater instructions describe the older edition.

## Owned frontdoor and package

Build `source/owned/owned_launcher.c` as an x64 Windows GUI executable using a
Unicode entry point (`-municode -mwindows` with MinGW/LLVM). Link user32 and embed
`source/lite/integration/bloodborne.ico` as the executable icon. The frontdoor
runs `runtime/python/pythonw.exe -I -B owned/app.py` from its own package.

`source/owned/build_package.py` has `stage` and `seal` phases. Supply explicit
input paths; its local QA defaults are conveniences for the maintainer workspace.
The candidate must be under the repository's `.local/owned-integration-qa` directory.
Stage requires:

1. A verified Windows 1.9 Atlas edition seed, including its manifest, native build proof and dependency pins. Build or extract the matching 1.9 adapter using the corresponding 1.2 source workflow.
2. The authenticated official Windows 1.9 ZIP, SHA-256 `d2df6aa37530f0d21f577c5cc05bd3366b1f95e8f402b96cab89bbd8c8a219e5`.
3. A complete x64 CPython 3.10 installation including Tk/Tcl and its VC runtime DLLs.
4. An unprepared art-only `assets.atlaslite`, such as the seed in the player package. Never use a prepared personal pack for release packaging.

```text
python source/owned/build_package.py stage --candidate .local/owned-integration-qa/candidate --backup "ATLAS_1_9_SEED" --official-zip "WINDOWS_1_9_ZIP" --python-home "CPYTHON_3_10" --art-pack "ART_ONLY_PACK"
python source/owned/build_package.py seal --candidate .local/owned-integration-qa/candidate --backup "ATLAS_1_9_SEED" --official-zip "WINDOWS_1_9_ZIP" --art-pack "ART_ONLY_PACK" --launcher-exe "OWNED_FRONTDOOR_EXE"
```

Seal overlays the canonical owned app, installer, bootstrap, UI and public docs,
then writes all immutable hashes. The package contains private Python and port
files; it does not launch an external Bloodborne executable or private interpreter.
Mutable profile/configuration, generated compilation files and caches live under
`state`. Prepared map identity is independent of the ordinary launcher version.

## Checks and release packaging

```text
python -B -m unittest discover -s source/owned/tests -p test_*.py
python -B -m unittest discover -s source/lite/tests/bootstrap -p test_*.py
python -B -m unittest discover -s source/lite -p test_assets.py
```

Use the candidate's private Python with `-I -B` to verify the package, open its
launcher UI, and prepare maps in disposable fixtures. Test real in-game Map tile
opening and travel with independently copied saves. Keep original save hashes.
`source/owned/tests/drive_game.py` is an opt-in native input/capture QA harness;
it is not a player entrypoint.

Package with `source/owned/runtime_tools/build_review_release.py`, supplying
`--candidate`, `--release`, `--base-source`, `--upstream-source` and
`--runtime-source` as needed. It checks the native source proof and player hashes,
includes corresponding source/licenses, and excludes personal state, saves,
generated maps, native font and game files. Validate both ZIP CRCs and every
manifest hash before uploading the versioned Windows/Source ZIPs and SHA256SUMS.
