# Frozen candidate source identity

Native probe SHA-256: `f3d185f096afcc10a7ebb94a729da40b884cae00d41fd762e59e17ea7caf9761`. The matching launcher executable SHA-256: `8427703e5c76aa37a36ab5f382155a357b0c6e720a59c19408f9d13af59e548f`.

This snapshot contains the native driver's flip-publication retirement ordering fix and its source-only regression harness under `META/renderer-flip/`. It also contains the applied-region confirmation guard in `native/src/runtime_map.c` and `native/src/map_confirm_guard.inc`, with `native/tests/test_map_location.c`.

Root-reported candidate QA: normal GUI Play reached Great Bridge; mouse click, drag, wheel, recenter, Back, and invalid-command checks passed with player pose unchanged. Circle-confirm Dream Map and 12 open/close cycles passed with zero post-warm memory growth. This is source-candidate evidence only; the beta documentation records the remaining limits; this source identity does not imply human visual acceptance.
