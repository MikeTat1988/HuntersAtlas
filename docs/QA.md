# Validation record — 1.4.0-beta2

- Native runtime rebuilt after the navigation, local cursor-audio and native-label cover fixes. Final runtime SHA-256: `782f6b4f3bb6b22a0545e9d292fde022f7cf90a4f5c6ecf05e7e4acd6e91c022`.
- Frozen launcher source/import/Tcl-Tk verification passed. Launcher/installer suite: 41 tests, 39 passes and two Windows symlink-permission skips; the real frozen installer fixtures passed installation, uninstall and reinstall.
- Actual installed normal Play loaded a copied save in Cathedral Ward. A 16-step logical-input sequence passed left/right wrapping through Map, both exits, Confirm and Back, without player movement. Queued SDL mouse tile click and Back passed.
- Actual runtime decoded the local move/select clips (3,072/4,096 PCM frames) and completed 9 move and 2 select clips through SDL's dummy backend. No sound was sent to hardware. The fully muted backend also passed navigation and counted suppressed audio requests.
- Standalone real-audio-path tests confirmed nonzero mixed PCM, main-port volume zero producing silence, `BB_AUDIO=none` suppressing requests, and malformed sound-bank rejection. The game's internal FMOD-only SFX slider is not tracked by the added cursor clips.
- Frozen installed package resolver verified beta2 and the automatic receipt-owned folder. Original save files, launcher profile and game executable hashes remained unchanged. An initial isolated test omitted the external patch directory and displayed the missing-DLC warning; restoring the existing selected patch directory in the test profile fixed it, without changing game files or the real profile.
- External window capture timed out. Runtime swapchain captures were used to inspect the menu and map. Human visual approval and physical-device certification remain pending. Runtime tests used the bounded preparation-worker override; they are not a broad renderer or performance certification.

## Earlier beta1 baseline

The framing and colour revisions have actual in-game captures for review. Human visual approval remains pending. Checks below distinguish the packaged runtime, internal widget invocation and physical-device acceptance.

| Check | Result and scope |
| --- | --- |
| Native build | Final runtime SHA-256 f3d185f096afcc10a7ebb94a729da40b884cae00d41fd762e59e17ea7caf9761. Build passed with assertions enabled. |
| Map revisions | Actual Great Bridge captures show faded other storeys, descender-safe headings, dark scratched tower interiors, side rules, preserved city painting/tree, textured soft edge fades and the colour key below High/Low. |
| Primary entry | Actual 1080p copied-save quick menu with FPS/settings overlay off: Right from System focuses Atlas; Confirm opens it and retains native focus. |
| Confirm mapping | Native Cross mode and the existing Circle-confirm tweak both passed. Circle mode displayed Circle OK/Cross Back in the native menu. Atlas follows the verified applied game predicate, not a second selector. Unknown predicates fail closed. |
| Controller path | Four-direction pan, zoom, recenter and Back/Confirm passed through logical runtime input injection without player movement. Twelve cycles each in Great Bridge and Dream had zero post-warm private-memory growth under a 32 MiB budget. Physical gamepad certification is not claimed. |
| Mouse path | Actual final runtime SDL events: tile down/up, drag, wheel zoom, clickable recenter and Back passed without player movement; native focus and capture restored. Invalid/out-of-bounds events were rejected. These were queued SDL events, not physical desktop mouse input. |
| Geometry | 88,645 storey-specific interior-fill triangles; independent GEOS audit found zero same-storey floor intersection. One pathological candidate was omitted conservatively. Other-height floors remain faded above interior fill. |
| Layout harness | Downscaled design, 720p, 1080p, 4K and ultrawide transforms, actual ImGui draw order and Back click passed. Cached CPU draw measured 0.871 ms. 4K/ultrawide were harness checks, not actual game captures. |
| Frozen launcher | Final adapter SHA-256 8427703e5c76aa37a36ab5f382155a357b0c6e720a59c19408f9d13af59e548f, built from matching v1.7.2 source. Frozen source/Tk/XML preparation imports passed without developer PATH or PYTHONPATH. |
| Launcher controls | Real frozen Browse callback, enable checkbox, persisted selection, normal Play and Stop widget invocation passed. Only the directory-dialog result was stubbed. |
| Enable/disable | Enabled normal Play selected Atlas; disabled normal Play selected stock and removed Atlas/pad overrides. Parent environment stayed unchanged. All game tests used child-process BB_AUDIO=none. |
| Restart | --play and replay of the exact runtime restart command passed with the validated session environment. Clicking in-game Apply/restart remains untested. |
| Launcher contracts | 40 tests run: 38 passed, two expected Windows symlink-permission skips. Missing/moved/corrupt/incompatible packages, Unicode/spaces and path containment covered. |
| Named scenes | Actual 1080p captures: Great Bridge layer29, y=-27.02 m; Clinic layer21, y=-50.81 m; Hunter's Nightmare DLC layer4, y=1490.38 m; Dream layer6, y=-1.66 m. Short Clinic/DLC walks updated tracked position. These do not establish every route in all 16 maps. |
| Performance | Bounded Great Bridge 30 FPS sample: median33.33 ms, p99 approximately37–44 ms; zoom/cache outliers retained. No uncapped performance or full-playthrough claim. |
| Generator | Empty output, 16 maps, all19 generated payloads byte-identical between source/frozen; spaces/Unicode and UTF8/cp1251 passed. Injected commit failure restored prior output. No user Python required. |
| Install/rollback | Standalone fixture and actual usual-launcher install/uninstall/reinstall passed. Uninstall restored the exact original executable (4a8e67ce…), preserving original run.py, dependencies, saves and settings. Final adapter is installed with a retained rollback bundle. |
| Sources/notices | Complete corresponding native/launcher/generator source and dependency-source archives included. Public maps directory is empty; no extracted game font, game executable, saves or personal profiles are distributed. |
| Desktop acceptance | Native picker pixels, physical mouse/gamepad, alt-tab/focus loss and disconnect remain unverified. Desktop capture repeatedly timed out; widget invocation and SDL injection are explicitly scoped above. |
| Cleanup | Atlas source consolidated in this repository; obsolete work trees, copied test saves, SDK/build products and v1.3 shortcut/runtime retired with a retained source/history recovery folder and retained tested launcher rollback. Original game/save/settings/mod files are protected. |

Three renderer defects were repaired with production-code regression cases and old-code negative controls: pending-write length, mixed-queue video-out waits, and presentation completion published before the previous surface lock was retired. Prompt entry into Dream gameplay and repeated Atlas interaction passed after the fixes. Assertions and default renderer options remain enabled.

Known runtime limit: leaving the title screen idle until its attract movie starts can cause a guest read fault at offset 0x26c01c3. The same fault appeared with differing renderer settings; an occasional bad draw-buffer length is not sufficient to explain it. A safe fix and stock-versus-Atlas causality have not been established. Do not describe the runtime as generally crash-free.

Original save files, game executable, AppData launcher settings and unrelated mod edits remain unchanged. The launcher executable changed intentionally; patches.json had an external selection change before validation, and that latest selection was preserved. Retired development binaries and v1.3 files are explicit cleanup exceptions. Tests use copied saves and isolated profiles.

Repository/release publication is separate from runtime acceptance. No Reddit post or external contact was made. Outstanding desktop/state checks and the idle-movie fault remain beta limits; cleanup does not imply they passed.
