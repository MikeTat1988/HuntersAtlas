"""Verify the self-contained installer contains the owned source and runs without Python PATH."""
import hashlib
import json
import marshal
import os
from pathlib import Path
import subprocess
import sys

from verify_frozen_sources import extract_archive, normalized


SOURCE = Path(__file__).resolve().parent
EXE = SOURCE / 'build' / 'installer-dist' / 'AtlasSetup.exe'
INSTALLER_SOURCE = SOURCE / 'atlas_install.py'


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(block)
    return hasher.hexdigest()


def main() -> None:
    entries = extract_archive(EXE.read_bytes())
    if 'atlas_install' not in entries:
        raise RuntimeError('Frozen installer omitted its atlas_install entry script.')
    frozen_entry_code = marshal.loads(entries['atlas_install'])
    expected_code = compile(INSTALLER_SOURCE.read_text(encoding='utf-8'), str(INSTALLER_SOURCE), 'exec', optimize=0)
    if normalized(frozen_entry_code) != normalized(expected_code):
        raise RuntimeError('Frozen installer entry code does not match atlas_install.py.')
    system_root = os.environ.get('SYSTEMROOT', r'C:\Windows')
    no_python_env = os.environ.copy()
    no_python_env['PATH'] = str(Path(system_root) / 'System32')
    help_result = subprocess.run([str(EXE), '--help'], env=no_python_env, capture_output=True,
                                 text=True, timeout=45, check=False)
    if help_result.returncode != 0 or 'install' not in help_result.stdout or 'uninstall' not in help_result.stdout:
        raise RuntimeError(f'Frozen installer --help failed without Python PATH: {help_result.stderr}')
    notice_root = EXE.parent / 'THIRD-PARTY-NOTICES'
    notice_paths = {
        'Python-PSF-2.0.txt': notice_root / 'Python-PSF-2.0.txt',
        'Tcl-Tk-license.terms': notice_root / 'Tcl-Tk-license.terms',
    }
    missing_notices = [name for name, path in notice_paths.items() if not path.is_file()]
    if missing_notices:
        raise RuntimeError(f'Public installer distribution is missing notices: {", ".join(missing_notices)}.')
    receipt = {
        'executable': str(EXE),
        'executable_sha256': digest(EXE),
        'source': str(INSTALLER_SOURCE),
        'source_sha256': digest(INSTALLER_SOURCE),
        'python_version': sys.version,
        'pyinstaller_version': '6.22.3',
        'verified_module': 'atlas_install',
        'help_without_python_path_exit_code': help_result.returncode,
        'bundled_runtime_notice_sha256': {name: digest(path) for name, path in notice_paths.items()},
        'cli_commands': ['install', 'uninstall'],
        'stock_launcher_sha256': '4a8e67ce5c2a5e4d8f8add8b0e606caecd5a3389756aef683f3ded793d4f6a59',
    }
    destination = SOURCE / 'build' / 'installer-source-receipt.json'
    destination.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
