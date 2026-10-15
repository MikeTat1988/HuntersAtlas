"""Prove the frozen launcher contains the owned sources used for this build."""
import ast
import hashlib
import importlib.util
import json
import marshal
import os
from pathlib import Path
import subprocess
import struct
import tempfile
import sys
import types
import zlib


ROOT = Path(os.environ.get('ATLAS_PORT_ROOT', Path(__file__).resolve().parents[3]))
SOURCE = Path(__file__).resolve().parent
FROZEN = SOURCE / 'build' / 'dist' / 'Bloodborne' / 'Bloodborne.exe'
BASELINE_ROOT = Path(os.environ.get('ATLAS_BASELINE_SOURCE', ROOT / 'working' / 'atlas-root-audit' / 'windows-v1.7.2'))
ORIGINAL_SOURCE = BASELINE_ROOT / 'bbport_launcher_win.py'
ORIGINAL_RUN = BASELINE_ROOT / 'run.py'
INSTALLED_EXE = Path(os.environ.get('ATLAS_STOCK_EXE', ROOT / 'launcher-v1.7' / 'Bloodborne.exe'))
BASELINE_EXE_SHA256 = '4a8e67ce5c2a5e4d8f8add8b0e606caecd5a3389756aef683f3ded793d4f6a59'
EXPECTED_HELPERS = (
    'atlas_addon', 'bbport_input_config', 'bbport_lang', 'bbport_lang_more',
    'bbport_steam', 'bbport_trophies',
)
STDLIB_ROOT = Path(importlib.util.find_spec('tkinter').origin).resolve().parent
EXPECTED_TK_MODULES = {
    'tkinter': STDLIB_ROOT / '__init__.py',
    'tkinter.ttk': STDLIB_ROOT / 'ttk.py',
    'tkinter.filedialog': STDLIB_ROOT / 'filedialog.py',
    'tkinter.messagebox': STDLIB_ROOT / 'messagebox.py',
}
COOP_FUNCTIONS = (
    'bridge_folder', 'bridge_config', 'bridge_cli', 'bridge_accounts', 'server_check_hunters_dream',
)


def digest(path):
    hasher = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(block)
    return hasher.hexdigest()


def inventory(root):
    return {
        path.relative_to(root).as_posix(): digest(path)
        for path in sorted(root.rglob('*')) if path.is_file()
    }


def normalized(code):
    return {
        'name': code.co_name,
        'bytecode': code.co_code.hex(),
        'names': code.co_names,
        'varnames': code.co_varnames,
        'constants': [normalized(value) if isinstance(value, types.CodeType)
                      else sorted(repr(item) for item in value) if isinstance(value, frozenset)
                      else repr(value) for value in code.co_consts],
    }


def extract_archive(data):
    cookie_magic = b'MEI\x0c\x0b\x0a\x0b\x0e'
    cookie = data.rfind(cookie_magic)
    if cookie < 0:
        raise RuntimeError('PyInstaller archive cookie was not found.')
    _magic, length, toc_offset, toc_length, _python_version, _library = struct.unpack(
        '!8sIIII64s', data[cookie:cookie + 88])
    archive_start = cookie + 88 - length
    toc = data[archive_start + toc_offset:archive_start + toc_offset + toc_length]
    entries, offset = {}, 0
    while offset < len(toc):
        size, start, compressed_size, _raw_size, compressed, kind = struct.unpack('!IIII BB', toc[offset:offset + 18])
        name = toc[offset + 18:offset + size].rstrip(b'\0').decode('utf-8')
        payload = data[archive_start + start:archive_start + start + compressed_size]
        entries[name] = zlib.decompress(payload) if compressed else payload
        offset += size
    return entries


def verify_coop_functions():
    before = ast.parse(ORIGINAL_SOURCE.read_text(encoding='utf-8'))
    after = ast.parse((SOURCE / 'bbport_launcher_win.py').read_text(encoding='utf-8'))
    before_functions = {node.name: ast.dump(node, include_attributes=False)
                        for node in before.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    after_functions = {node.name: ast.dump(node, include_attributes=False)
                       for node in after.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    changed = [name for name in COOP_FUNCTIONS if before_functions.get(name) != after_functions.get(name)]
    if changed:
        raise RuntimeError(f'Co-op bridge source changed unexpectedly: {", ".join(changed)}')


def main():
    baseline_exe_checked = bool(os.environ.get('ATLAS_STOCK_EXE'))
    baseline_source_checked = ORIGINAL_SOURCE.is_file() and ORIGINAL_RUN.is_file()
    if baseline_exe_checked and digest(INSTALLED_EXE) != BASELINE_EXE_SHA256:
        raise RuntimeError('Installed launcher hash changed since the source audit.')
    if os.environ.get('ATLAS_BASELINE_SOURCE') and not baseline_source_checked:
        raise RuntimeError('Explicit baseline source directory is incomplete.')
    if baseline_source_checked:
        verify_coop_functions()
    data = FROZEN.read_bytes()
    entries = extract_archive(data)
    main_name = next((name for name in entries if name.endswith('bbport_launcher_win')), None)
    if not main_name or normalized(marshal.loads(entries[main_name])) != normalized(
            compile((SOURCE / 'bbport_launcher_win.py').read_text(encoding='utf-8'),
                    str(SOURCE / 'bbport_launcher_win.py'), 'exec', optimize=0)):
        raise RuntimeError('The new frozen launcher does not match the owned launcher source.')

    pyz_name = next((name for name in entries if name.endswith('PYZ.pyz')), None)
    if not pyz_name:
        raise RuntimeError('Frozen package has no Python module archive.')
    pyz = entries[pyz_name]
    pyz_index = struct.unpack('!I', pyz[8:12])[0]
    toc = marshal.loads(pyz[pyz_index:])
    module_records = dict(toc.items() if isinstance(toc, dict) else toc)
    for module in ('xml', 'xml.etree', 'xml.etree.ElementTree', 'xml.parsers.expat'):
        if module not in module_records:
            raise RuntimeError(f'Frozen preparation runtime omitted required XML module {module}.')
    for module in EXPECTED_HELPERS:
        if module not in module_records:
            raise RuntimeError(f'Frozen package omitted required module {module}.')
        _kind, start, size = module_records[module]
        code = marshal.loads(zlib.decompress(pyz[start:start + size]))
        source = SOURCE / f'{module}.py'
        expected = compile(source.read_text(encoding='utf-8'), str(source), 'exec', optimize=0)
        if normalized(code) != normalized(expected):
            raise RuntimeError(f'Frozen module {module} does not match its source file.')

    for module, source in EXPECTED_TK_MODULES.items():
        if module not in module_records:
            raise RuntimeError(f'Frozen package omitted required GUI module {module}.')
        _kind, start, size = module_records[module]
        code = marshal.loads(zlib.decompress(pyz[start:start + size]))
        expected = compile(source.read_text(encoding='utf-8'), str(source), 'exec', optimize=0)
        if normalized(code) != normalized(expected):
            raise RuntimeError(f'Frozen GUI module {module} does not match this Python runtime.')

    frozen_dependencies = inventory(FROZEN.parent / '_atlas_internal')
    frozen_dependency_hashes = {name.casefold(): value for name, value in frozen_dependencies.items()}
    dependency_names = {Path(name).name.casefold() for name in frozen_dependencies}
    if not any(name.startswith('pyexpat') and name.endswith('.pyd') for name in dependency_names):
        raise RuntimeError('Frozen preparation runtime is missing native pyexpat.')
    if not any(name.startswith('_tkinter') and name.endswith('.pyd') for name in dependency_names):
        raise RuntimeError('Frozen package is missing the native _tkinter extension.')
    if not any(name.startswith('tcl') and name.endswith('.dll') for name in dependency_names):
        raise RuntimeError('Frozen package is missing the Tcl runtime DLL.')
    if not any(name.startswith('tk') and name.endswith('.dll') for name in dependency_names):
        raise RuntimeError('Frozen package is missing the Tk runtime DLL.')
    if not any(name.casefold().endswith('/init.tcl') for name in frozen_dependencies):
        raise RuntimeError('Frozen package is missing the Tcl initialization scripts.')
    notice_names = {name.casefold() for name in frozen_dependencies}
    required_notices = {
        'third-party-notices/python-psf-2.0.txt',
        'third-party-notices/tcl-tk-license.terms',
    }
    if not required_notices.issubset(notice_names):
        raise RuntimeError('Frozen package is missing the Python and Tcl/Tk license notices.')

    scripts_root = Path(os.environ.get('ATLAS_PREPARATION_SCRIPTS', SOURCE.parent / 'native' / 'scripts'))
    # Only runtime preparation modules belong in this import smoke check.
    # The source checkout also contains developer tools with command-line side effects.
    preparation_modules = ('content_profile', 'cpu_compat', 'link_libc', 'link_modules',
                           'mods', 'patches', 'prepare')
    preparation_sources = [SOURCE / 'run.py', *(scripts_root / f'{name}.py' for name in preparation_modules)]
    local_modules = {source.stem for source in preparation_sources}
    external_imports = set()
    for source in preparation_sources:
        for node in ast.walk(ast.parse(source.read_text(encoding='utf-8'))):
            names = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                     else [node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
            external_imports.update(name for name in names if name.split('.')[0] not in local_modules
                                    and name != '__future__')
    with tempfile.TemporaryDirectory(prefix='atlas-gui-smoke-') as isolated_profile:
        smoke_env = os.environ.copy()
        for key in list(smoke_env):
            if key.startswith('PYTHON'):
                smoke_env.pop(key)
        smoke_env['PATH'] = os.environ.get('SystemRoot', r'C:\Windows') + r'\System32'
        smoke_env['BB_LAUNCHER_SETTINGS_ROOT'] = isolated_profile
        smoke = subprocess.run([str(FROZEN), '--atlas-gui-smoke'], env=smoke_env,
                               timeout=30, check=False)
        if smoke.returncode != 0:
            raise RuntimeError(f'Frozen Tk GUI smoke check failed with exit code {smoke.returncode}.')
        import_smoke = Path(isolated_profile) / 'preparation_import_smoke.py'
        import_smoke.write_text(
            'import importlib, importlib.util, sys\n'
            f'sys.path.insert(0, {str(scripts_root)!r})\n'
            f'for name in {sorted(external_imports)!r}: importlib.import_module(name)\n'
            f'for name in {sorted(local_modules - {"run"})!r}: importlib.import_module(name)\n'
            'from xml.etree import ElementTree as ET\n'
            'assert ET.fromstring("<PatchList><Patch/></PatchList>").tag == "PatchList"\n',
            encoding='utf-8')
        import_result = subprocess.run([str(FROZEN), '--script', str(import_smoke)], env=smoke_env,
                                       capture_output=True, text=True, timeout=30, check=False)
        if import_result.returncode != 0:
            raise RuntimeError(f'Frozen preparation imports failed: {import_result.stdout}\n{import_result.stderr}')

    receipt = {
        'frozen_executable': str(FROZEN),
        'frozen_sha256': hashlib.sha256(data).hexdigest(),
        'frozen_dependency_sha256': frozen_dependencies,
        'installed_baseline_executable': str(INSTALLED_EXE) if baseline_exe_checked else None,
        'stock_baseline_checked': baseline_exe_checked,
        'installed_baseline_sha256': BASELINE_EXE_SHA256,
        'base_launcher_source_sha256': digest(ORIGINAL_SOURCE) if baseline_source_checked else None,
        'base_run_source_sha256': digest(ORIGINAL_RUN) if baseline_source_checked else None,
        'atlas_game_eboot_sha256': 'd65f0b4f01d59166aed16f8604196d8b7dd805abbf0758b356e8f1354c9429f9',
        'launcher_build': 'windows-v1.7.2-atlas1',
        'runtime_build': 'hunters-atlas-runtime-1.0',
        'verified_frozen_modules': [main_name, *EXPECTED_HELPERS],
        'verified_tkinter_modules': list(EXPECTED_TK_MODULES),
        'bundled_runtime_notices': {name: frozen_dependency_hashes[name] for name in sorted(required_notices)},
        'frozen_tk_gui_smoke_exit_code': smoke.returncode,
        'frozen_tk_gui_smoke_isolated_profile': True,
        'frozen_preparation_import_smoke_exit_code': import_result.returncode,
        'frozen_preparation_import_smoke_without_developer_path': True,
        'preparation_external_imports': sorted(external_imports),
        'preparation_source_sha256': {str(source): digest(source) for source in preparation_sources},
        'frozen_module_source_sha256': {
            name: digest(SOURCE / f'{name}.py') for name in ('bbport_launcher_win', *EXPECTED_HELPERS)
        },
        'tkinter_module_source_sha256': {name: digest(source) for name, source in EXPECTED_TK_MODULES.items()},
        'co_op_bridge_functions_unchanged': list(COOP_FUNCTIONS) if baseline_source_checked else [],
        'python_version': sys.version,
        'pyinstaller_version': '6.22.3',
    }
    destination = SOURCE / 'build' / 'source-receipt.json'
    destination.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
