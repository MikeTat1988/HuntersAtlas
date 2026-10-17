# Official Windows launcher 1.9 adapter

This profile binds the launcher UI and runner to official upstream commit
`652f9a494c47cc8c1ab16f28b456372eaa8103f8`. Its native integration is recorded in
`native-integration.diff`; the complete expanded native source is shipped in the
simultaneous corresponding-source ZIP and the automatic rebuild seed.

The UI retains upstream frame-generation controls and mod diagnostics. The runner
retains upstream optional-layer recovery. Atlas settings, map input and travel
hooks are carried forward. The overlay retains 1.9 FPS timing and frame-generation
controls and precise-readback backing access; Atlas polling runs after
initialization on presented frames.

Release assembly selects these files only for the authenticated `windows-v1.9`
adapter. The existing 1.7.2, 1.8.1 and 1.8.2 adapters keep their own runner and
launcher behavior. Runtime version checks still use the package identity and
exact file hashes.
