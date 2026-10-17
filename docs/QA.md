# Release validation — Hunter’s Atlas 1.2

## Installer fixes in 1.2

- The reported shader header is present in the published 1.1 seed. Its failing
  installation path reaches the traditional Windows 260-character boundary.
- A disposable copy of the official launcher was tested with long-path awareness
  explicitly disabled in its manifest. Direct access to a 346-character physical
  header path failed, while extraction through the owned short build drive passed
  at 205 characters. The Windows registry was not changed.
- A full forced source rebuild for official launcher 1.8.2 passed from a deeply
  nested workspace, including native identity and output-manifest verification.
- The 1.8.2 adapter reuses the exact previously tested runtime. The bundled 1.7.2
  and 1.8.1 runtimes are also unchanged.
- Update/rebuild tests: 34 passed, including live output, real child-process
  cancellation, idle timeout, cancellation refusing activation, archive traversal,
  signature verification and recovery. Bootstrap: 20; UI bridge: 10; dependency
  packaging: 3 passed.

Final package installation, update and owner gameplay checks are recorded with
the release preparation artifacts. Publication remains pending those checks.

## Prior gameplay evidence for unchanged native runtimes

The owner confirmed that installation and the launcher update worked on
October 16, 2026. Automated checks used disposable launchers and copied saves.

| Check | Result |
| --- | --- |
| Repair an installed Atlas on launcher 1.7.2 | Passed |
| Ordinary launcher Update callback, 1.7.2 → 1.8.2 | Passed: native rebuild, activation and automatic restart |
| Restarted launcher status | Ready; Atlas enabled |
| Map reuse | Verified pack reused without regeneration |
| In-game map and lamp selection on 1.8.2 | Passed |
| Travel to Tomb of Oedon | Completed; arrival verified |
| Undiscovered Grand Cathedral lamp | Hidden |
| Confirmation proportions | Passed at 1920×1080 and 3840×2160 |
| Travel/items disabled | Map still usable; optional controls removed |
| Build tools from an empty directory | Portable bootstrap and compilation passed |
| Injected Atlas build failure | Verified launcher activated; maps/settings retained; stock game route used |
| Uninstall from pending state | Restored new stock launcher |
| Python unit suites | Updates 27; UI bridge 10; bootstrap 20; dependency packaging 3 |
| Production protection | 17 recorded launcher/save hashes unchanged during update QA |

The initial gameplay harness attempted travel before the game menu was ready.
The normal travel guard rejected it. Retesting after the native menu became
available completed travel and the 1080p/4K/1080p resize sequence.

Desktop capture was unavailable during update QA. The button callback and Ready
status were checked through the actual Tk widgets. Map layout was inspected in
native render captures. The supplied launcher screenshot illustrates the setup;
it was captured before the 1.1 version label was prepared.

The 1.1 packaging changes version metadata, release status and documentation;
the verified bundled 1.7.2 and 1.8.1 native executables are retained byte-for-byte.
The release preparation report records the final archive checks and hashes.

## Coverage limits

These checks do not certify every destination, death/respawn sequence, story
restriction, pickup collection, NPC stage, reveal boundary, controller or GPU.
NPC filtering is limited to the stages in [controls and coverage](MAP-FEATURES.md).
Chalice Dungeons and unlisted game builds remain unsupported. Future upstream
source conflicts can require an Atlas integration repair.

## Launcher 1.9 integration

The overlay conflict with upstream FPS timing was reviewed. The new adapter and
rebuild seed use official 1.9 commit `652f9a494c47cc8c1ab16f28b456372eaa8103f8`.
Frame-generation controls, presented-frame timing, settings scrolling, Quit,
and precise-readback backing access are retained. Atlas polling runs after
initialization on presented frames. A full forced fallback build and native
identity verification passed. Exact source and seed hashes are recorded in
`SOURCE_PROVENANCE.json`.

Version-specific UI and runner files apply only to the 1.9 adapter. Existing
1.7.2, 1.8.1 and 1.8.2 native binaries are unchanged. Packaged-adapter checks,
recovery from pending status and gameplay results are recorded with the 1.9
release preparation artifacts. Owner gameplay verification is required before
publication of the new native integration.
