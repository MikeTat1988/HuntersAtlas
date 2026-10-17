# Release procedure

Releases use version tags (`v1.0`, `v1.2`, …), a short changelog, a player ZIP,
corresponding source ZIP and SHA-256 checksums. GitHub retains older releases.
The main README links to `/releases/latest`; the 1.2 release is marked Latest
when published. Existing tags/assets are never replaced.

## Prepare locally

1. Update product version, changelog, installation/compatibility docs and release notes.
2. Assemble verified native adapters with `source/lite/build_auto_update_release.py
   --release --version 1.2`, the exact native build receipts, corresponding sources,
   reviewed rebuild seed and private catalog signing key. Never include the key.
3. Check package versions, signatures, archive CRCs, source correspondence,
   unchanged native runtime hashes and absence of saves/game data/private files.
4. Exercise installation and the launcher Ready state on a disposable copy.
   Reuse existing gameplay/update evidence when runtime and relevant program
   files have not changed. Repeat affected checks after functional changes.
5. Keep generated binaries, tools, local paths and QA copies outside Git.
   Show the owner the exact release notes and publication layout for approval.

## Publish after owner approval

1. Verify remote `main` still has the expected reviewed parent. Commit the reviewed
   changes, push that commit to `main`, and create/push annotated tag `v1.2`.
2. Create release **Hunter’s Atlas 1.2 — installation fixes and reliable rebuild progress** from that tag. Use `docs/releases/v1.2.md` as its body.
3. Attach `Hunters-Atlas-1.2.zip`, `Hunters-Atlas-Source-1.2.zip` and
   `SHA256SUMS.txt`. Mark the release Latest and publish it as a normal release.
4. Verify the public Latest link, both downloads, their digests, screenshot and
   preserved v1.0 release. The new screenshot is stored in `examples/launcher-settings.png`
   and the release notes reference its immutable `v1.2` URL.

No GitHub writes, commits, tags or pushes are part of local preparation.
