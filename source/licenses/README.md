# Licenses, notices, and source receipts

Hunter’s Atlas combines project code with the native Bloodborne port and third-party components. Each component remains under its own license. Read the license and notice files shipped in the corresponding source tree; the root `LICENSE` does not replace those component notices.

## Native host and Atlas source

The native host is based on the GPL-licensed `bloodborne_pc` project. The corresponding source release retains the complete modified native source, required vendored source, shader inputs, and patches. Keep those files together when redistributing the corresponding source. License texts and component notices are retained alongside the native and vendor trees and in `notices/`.

## Windows runtime records

`runtime-owners-index.json` records the indexed launcher/runtime DLLs, their package owners, binary hashes, and notice-copy status. `runtime-source-index.json` records source-recipe and archive evidence for the runtime packages in its scope. `notices/` retains the copied license and notice files. Use each index’s file list and status fields to determine what a particular binary is covered by; an inventory entry is not a claim that every executable or vendor file has the same license.

The corresponding source release includes optional runtime dependency source material, identified by the release’s source receipt. That material supports source availability and rebuild work; it is not part of the player package and does not replace the native compiler and development libraries required by a source build. Some custom or separately licensed components may have distinct provenance and are identified in their own receipts.

## Generator dependencies

The generator includes source and license records for its Python dependencies, including the reviewed Soulstruct source and its license receipt. `soulstruct-license-receipt.json` records the exact source-distribution metadata and the source of the accompanying GPL text. It does not claim that the text came from an upstream file when the distribution did not contain one.

## Verification

Machine-readable receipts are evidence scoped to their listed files, versions, hashes, and source archives. Use the verifier named by each release receipt when available, and review its exact scope and result. The records are not a general legal opinion and do not extend one component’s license or source coverage to unrelated binaries.
