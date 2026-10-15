# Portable local Atlas generator

The frozen `dist/generate_atlas/` directory contains `generate_atlas.exe` and its `_internal` dependencies. Package its contents under the Atlas root's `tools/` directory. Keep the whole directory together; the executable uses no developer PATH, globally installed Python, game executable, copied save or precomputed map data.

Run the executable (or let the compatible launcher invoke it using the configured game folder):

```
tools\generate_atlas.exe --game-dir "C:\Games\Bloodborne\Image0" --output-dir "C:\Mods\Hunter's Atlas"
```

`--game-dir` accepts the folder containing `eboot.bin`, `sce_sys/param.sfo` and `dvdroot_ps4`, or its parent with an `Image0` subfolder. `--output-dir` is the selected Atlas package root and must be separate from the game. `--staging-dir` optionally supplies an empty temporary folder; otherwise a fresh subfolder is created under the package's `.generation-staging`. Use `--replace` to repair or regenerate previous generated assets. The generator refuses an existing successful generated-assets manifest without that flag, an unsupported executable or a source missing the 16 supported ordinary maps. It never writes game files or saves.

Supported tested source: SFO CUSA00207, version 01.09, eboot SHA-256 `d65f0b4f01d59166aed16f8604196d8b7dd805abbf0758b356e8f1354c9429f9`. Region labels alone are insufficient; the exact hash is checked. The two protected input fingerprints are rechecked before success. Runtime coverage and broader game-build compatibility remain separate acceptance gates.

Stdout includes JSON progress records with `stage`, map/index/total where applicable, and a final `complete` record. Underlying copied algorithms also print extraction details. Exit 0 confirms successful generation; exit 1 reports a JSON `error` plus a stderr traceback. The launcher should retain a user-readable log and display stage progress. Initial extraction takes several minutes; do not treat a quiet individual geometry operation as a hang.

Final generated outputs only:
- `maps/atlas.json`, 16 `maps/m*.json` collision maps, `maps/catalog.json`.
- `art/native-font.ttf`, extracted from the user's own local menu font.
- `maps/generated-assets.json`, written last: schema 1, version 1, `generator_version`, `game_eboot_sha256`, `game_version`, `title_id`, `protected_inputs`, `counts`, and a `files` object mapping relative generated paths to SHA-256. The manifest itself is excluded from that hash list.

The launcher declaration is `generated: {"manifest":"maps/generated-assets.json","required":["maps/atlas.json","maps/catalog.json"],"generator":"tools/generate_atlas.exe"}`. Native font is optional to the launcher's generic schema; this generator currently requires extraction to succeed. The launcher may choose the licensed fallback font when another valid generator manifest omits native font. It must verify every declared file, containment and the selected game's executable fingerprint before using generated output.

Stages: original collision/base map generation; verified static ladder/NPC evidence; vector floorplans; verified gates from ObjectAct/resolved opening events; explicit gate merge preserving all earlier markers; native localized names/ReturnPointParam joins; continuous original vertex heights and named collision footprints; native font; finite geometry/marker checks; input recheck; atomic generated JSON installation and final manifest. No older stage output is assumed. Catalog evidence contains portable relative paths and binder entry basenames. Font timestamps are fixed for reproducibility. The known original Dream `h000020` unsupported collision entry remains listed as an omission.

Replacement touches only those fixed owned outputs. Existing targets are copied into staging's `previous-generated/`; a commit failure restores every changed original and removes newly created owned files. Output containment also checks existing symlinks/junctions. Keep that rollback copy until the new prepared package passes launcher validation. The pure rollback test deliberately injects a commit failure and verifies originals are preserved.

The library uses `soulstruct_local_config.py`, an in-memory read-only configuration adapter. It disables global editor settings and log writes; the frozen bundle excludes the original machine-specific Soulstruct config and unused Oodle/Lua/Havok/texture helper executables/DLLs. Only generic Binder/DCX/FMG readers plus required Python/numeric native libraries are used. Unicode progress and pipe output explicitly use UTF-8.

Source under `src/` is the complete copied/parameterized chain plus the orchestrator and context module. `source-copy-manifest.json` records exact original/modified hashes. `copy_pipeline.py` is a development-only one-time copy trace and must never be rerun over later edits. Source and pinned runtime/build requirements accompany the executable; build receipts and dependency notices must accompany public release. This directory includes development logs and locally generated test output that must be excluded from public archives.

Build on Windows with CPython 3.12 and the pinned runtime/build/frozen requirements, then run PyInstaller with the included relative `generate_atlas.spec`. It excludes the library's editor configuration and unrelated helper resources. `requirements-frozen.txt` pins actual frozen optional modules (including lxml, charset-normalizer, CFFI and its parser); `frozen-dependency-inventory.json` maps frozen modules to distributions. The freeze-build logs record exact build options. Python 3.10/3.14 cannot load the tested cp312 native dependencies.
