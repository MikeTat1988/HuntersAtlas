"""Collect the selected build interpreter's Python and Tcl/Tk notices."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


def first_file(candidates: list[Path], label: str) -> Path:
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError(f'{label} license was not found for the selected interpreter.')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prefix = Path(sys.base_prefix)
    python_license = first_file([
        prefix / 'LICENSE.txt',
        prefix / 'share' / 'licenses' / f'python{sys.version_info.major}.{sys.version_info.minor}' / 'LICENSE',
    ], 'Python')
    tcl = Path(os.environ.get('TCL_LIBRARY', prefix / 'lib' / 'tcl8.6'))
    tk = Path(os.environ.get('TK_LIBRARY', prefix / 'lib' / 'tk8.6'))
    tcl_license = first_file([tcl / 'license.terms', tcl.parent / 'license.terms',
                              prefix / 'lib' / 'tk8.6' / 'demos' / 'license.terms'], 'Tcl/Tk')
    tk_candidates = [tk / 'license.terms', tk / 'demos' / 'license.terms']
    tk_license = next((path for path in tk_candidates if path.is_file()), tcl_license)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'Python-PSF-2.0.txt').write_bytes(python_license.read_bytes())
    combined = tcl_license.read_text(encoding='utf-8')
    if tk_license.read_bytes() != tcl_license.read_bytes():
        combined += '\n\nTk license:\n\n' + tk_license.read_text(encoding='utf-8')
    (args.output / 'Tcl-Tk-license.terms').write_text(combined, encoding='utf-8')


if __name__ == '__main__':
    main()
