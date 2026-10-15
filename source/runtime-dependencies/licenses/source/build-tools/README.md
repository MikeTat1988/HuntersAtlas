# PyInstaller build-tool source

This directory in the runtime-dependency source archive provides the exact PyInstaller source distributions used to freeze the included Atlas generator and matching Windows launcher.

| Build tool | Source archive | SHA-256 |
|---|---|---|
| PyInstaller 6.16.0 | `pyinstaller-6.16.0.tar.gz` | `53559fe1e041a234f2b4dcc3288ea8bdd57f7cad8a6644e422c27bb407f3edef` |
| PyInstaller 6.22.3 | `pyinstaller-6.22.3.tar.gz` | `05eb2f5615503e72939a7224d68b4aff572c6b0438ee4a17d0a4b481f399362d` |

`pyinstaller-source-receipts.json` records the official PyPI source-distribution URL, the corresponding version-specific PyPI JSON URL and response hash, the PyPI-published SHA-256, size, upload timestamp, and license declaration. Each downloaded archive's SHA-256 was checked against the official version JSON before it was accepted. The archives contain the upstream `COPYING.txt` and source tree.

PyInstaller declares GPL version 2 or later with a bootloader exception permitting its compiled bootloader and related files to be linked or embedded into programs without restrictions arising from those files. The exact release license text is in each source distribution and in the corresponding-source package's `generator/licenses/pyinstaller/COPYING.txt`.
