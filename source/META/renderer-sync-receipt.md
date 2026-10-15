# GPU submission synchronization source receipt

The corresponding repair is present in `native/gpu/shadps4/core/libraries/gnmdriver/gnmdriver.cpp`, `native/gpu/shadps4/video_core/amdgpu/liverpool.cpp`, and `native/gpu/shadps4/video_core/amdgpu/liverpool.h`. The focused source regression is `native/tests/test_submission_sync.py` (SHA-256 `355485cebc1519eb056a7c38111d909130fcd675b9a071216b59fdd373f03e2b`); it exercises stale drain, deferred and completed retirement, idle submit completion, and queue-visible accounting, with negative controls.

`META/renderer-sync.patch` is a source-relative review diff against the earlier native source. The changes already exist in `native/`; do not apply it on top of the archive tree. Root's reported candidate QA is summarized in `META/FROZEN-CANDIDATE-SOURCE.md`; that report does not isolate this synchronization repair.
