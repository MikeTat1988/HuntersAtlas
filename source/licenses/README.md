# Hunter's Atlas launcher and generator license/source receipts

This scoped supplement contains two related receipts assembled on 2026-10-14. It does not alter the installed runtime, launcher, AppData settings, game files, or saves.

## Full runtime DLL owner and notice index

`runtime-owners-index.json` covers all 150 runtime dependencies inventoried by the root audit: 147 third-party DLLs are mapped to 81 distinct exact-version MSYS2 package owners, and all 147 are recorded as hash-matching the installed package binaries. The three unmapped files are separately identified in the root audit as the custom probe, custom MIT DLSS bridge, and NVIDIA SDK binary; this index does not claim their source or notice coverage.

`notices/installed/` preserves all 92 notice files declared by mapped owners' installed `share/licenses` records. Files are copied byte-for-byte and kept under package/version directories with their installed relative paths. Each file and owner-to-DLL association has a SHA-256 or root-audit exact-binary-match field in the index. Packages whose installed owner record has no notice file are left without a guessed replacement in this directory; the separate exact-source audit below supplies license texts where the original notices were absent.

## GPL/LGPL runtime corresponding source

`runtime-source-index.json` covers all 33 distinct GPL/LGPL-declared MSYS2 owners represented by 44 of the mapped runtime DLLs. For each owner it records the installed version, local package archive hash/build metadata where available, official MSYS2 package record, exact-version MSYS2 source-only tarball URL and SHA-256, exact extracted `PKGBUILD` and `.SRCINFO` hashes, and every source identifier/checksum from that recipe.

The 33 indexed source-only tarballs include the recipe and patch set and all 33 package entries resolve every declared source input. Exact pinned VCS inputs are also preserved as source archives under `source/upstream-archives/`: libsoxr commit `945b592b70470e29f917f4de89b4281fbbd540c0`, RTMPDump tag `v2.6` commit `138fdb258d9fc26f1843fd1b891180416c9dc575`, and zvbi tag `v0.2.45` commit `d3a5ee9f2b047bf16cd1ee5ccf6ec05ee75409d0`. The index lists the repository, exact revision, and archive hash for each VCS tree. Recipe-declared archive inputs are present in their source-only tarballs and listed with the recipe checksum and matching archive member; every non-SKIP recipe checksum was verified against the bundled bytes, while SKIP entries are covered by the outer source-only archive hash.

`source/` retains the 33 source archives referenced by that receipt, the previously recovered 16-package missing-notice archive set, exact extracted recipes, and the 3 pinned VCS source archives. Some legacy-named source archives remain because the earlier 16-package receipt references them; they have not been removed or rewritten. `license-audit.json` remains the original 16-package focused receipt, with its 40 notice texts and verification contract intact.

## Soulstruct 2.3.2 in the local generator

`source/soulstruct-2.3.2.tar.gz` is the exact PyPI source distribution, verified against PyPI's published SHA-256. Its `PKG-INFO` declares `GPL-3.0-or-later`, but the exact sdist contains no license file and does not identify a repository commit. `notices/soulstruct/COPYING` contains the canonical GPL version 3 text from GNU; the exact metadata and `soulstruct-license-receipt.json` make that provenance explicit and do not claim that the text was copied from an upstream Soulstruct file or commit.

## Verification

Run both receipts from the repository root:

```powershell
& 'python' working/atlas-dev/licenses/verify_license_audit.py
& 'python' working/atlas-dev/licenses/verify_runtime_license_receipts.py
```

The first verifies the original 16-package, 40-text receipt. The second rechecks the full DLL mapping, all copied installed notices, the 33 exact source-only archive hashes and recipes, cached installed package hashes, per-source recipe checksums, pinned Git-source archive hashes, compressed archive integrity, and Soulstruct's PyPI/GPL evidence. This is a source and notice inventory, not a general legal opinion or proof of source obligations for the separate custom/NVIDIA files.

