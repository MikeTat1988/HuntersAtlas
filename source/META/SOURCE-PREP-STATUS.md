# Corresponding-source snapshot status

This source tree corresponds to the frozen native probe SHA-256 `f3d185f096afcc10a7ebb94a729da40b884cae00d41fd762e59e17ea7caf9761` and matching launcher executable SHA-256 `8427703e5c76aa37a36ab5f382155a357b0c6e720a59c19408f9d13af59e548f`. The native source includes the frozen renderer publication-order fix, map rendering and interaction updates, and opt-in QA event path; the launcher tree contains the matching Atlas-integrated sources and receipts.

The native source tree matches the active source under the exclusion policy recorded in the repository’s `docs/SOURCE_PROVENANCE.json`; the launcher source tree matches its authoritative source under the recorded build-receipt exclusion. The native baseline is `e699fdf76ff001df159dab049dfdac1a3446f13d`; the launcher baseline is `e5d04e2ba4864ccf40de6c3cf6aa532855320b0d`. All 17 generator source/build pins match `generator/generator-source-sha256.json`.

The tree includes build and vendor source, matching launcher sources and sanitized receipts, generator source/build inputs/tests/notices, the filtered Soulstruct Python/project source with provenance, runtime license notices, and original Atlas artwork/provenance. Exact runtime dependency sources are distributed separately in `releases/runtime-dependency-source.zip`.

This is a beta corresponding-source snapshot. Source identity does not establish broad compatibility, visual acceptance, or release acceptance. Consult the release QA and compatibility documents for the current tested scope and limitations.
