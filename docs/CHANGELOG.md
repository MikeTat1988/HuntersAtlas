# Changelog

## 1.4.0-beta2

- Flattened the installable release: select the same folder that contains Install.ps1 and manifest.json.
- Launcher offers the receipt-owned Atlas folder when no folder is configured, without enabling Atlas or changing an existing selection.
- Fixed Left from the first quick-menu tile skipping Map; Map participates in navigation in both directions.
- Atlas selection and confirmation decode the existing cursor sounds from the player's local game bank and mix them through the main audio port. No game audio assets are distributed.

## 1.4.0-beta1 — unreleased

- Added the fourth Map tile with native quick-menu state guards, controller focus/Confirm/Back behavior, and mouse activation.
- Matched the supplied menu/map composition more closely: title, dividers, frame, compass, legend and control footer; added the supplied Atlas icon and deterministic scaled derivatives.
- Added conservative, cached, world-anchored scratched cut bands with floor and marker exclusions.
- Added separately selected Atlas folder activation in the matching frozen settings/mod launcher, including normal Play, persisted enable state, integrity checks and child-only runtime environment.
- Added a portable local map/font generator with exact game fingerprint checks, progress reporting and transactional replacement.
- Added a standalone adapter installer with checked installation receipts and restoration of the original launcher.
- Added complete source preparation, dependency notices, exact GPL/LGPL runtime package source receipts and a licensed fallback font.

This is a release candidate under validation. Runtime scene coverage, performance acceptance, final archive checks, scoped cleanup and human visual approval are not implied by this changelog.

- Faded context now includes all other storeys. Titles reserve a descender gutter.
- Storey-specific enclosed interiors receive sepia fill and scratches; same-storey floors are excluded.
- Central side framing protects the painted city and tree; textured fades soften all viewport edges. Colour explanations sit below High/Low.
- Frozen launcher includes XML modules required by the actual Mods and game-preparation path.
- GPU write-range sizing and video-out label wait ordering repaired with production-case negative-control regressions.

- Atlas observes the verified applied native Confirm layout. Launcher activation follows the existing Circle-confirm tweak, removing the duplicate independent selector. Unknown region predicate patches disable the menu bridge safely.
