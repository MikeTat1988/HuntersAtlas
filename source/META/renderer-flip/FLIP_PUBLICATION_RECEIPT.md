# Flip-publication regression source

The frozen native source in `native/gpu/shadps4/core/libraries/videoout/driver.cpp` retires the prior presentation label and updates the previous buffer index while holding `port_mutex`, before publishing completion status. This closes the ordering window where a guest can reuse the announced-complete surface before its old label is retired.

`META/renderer-flip/test_flip_publish.py` extracts the exact production `VideoOutDriver::Flip` tail from a supplied native source tree, then compiles it with scheduling stubs. It exercises status polling, event callbacks, label notifications, initial presentation, blank presentation, and repeated-buffer cases. The unchanged pre-fix tail is included as `driver-before-flip-publish.cpp` for negative controls.

Run with explicit inputs: `python test_flip_publish.py --native-source <native-source-directory> --baseline <driver-before-flip-publish.cpp> --tools <compiler-bin-directory>`.

Source hashes: production driver `703a49991b770c317eace6a4f650eb0b190090e021e34fc2aba7fb92ec9228b1`, archived portable test `de7949265573e9c1803b35d559cd05a0d5ff6e1c0565e11c54dbd0add097906a`, baseline `1955a90fd62ecc41ec2f0a58b12ad286921cac122c6975951b7fb830a6b4c393`, archived patch `d27360285bc10fcb536fa6e47075f96b67cac837169c475e609b779ae775a6a3`. Candidate GUI/Play QA is summarized in `META/FROZEN-CANDIDATE-SOURCE.md`; the source harness itself makes no runtime claim.
