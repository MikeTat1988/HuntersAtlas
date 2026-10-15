import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import atlas_install


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AtlasInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='Atlas launcher test ü ')
        self.base = Path(self.temp.name)
        self.launcher = self.base / 'Game Root Ω'
        self.launcher.mkdir()
        self.stock = self.launcher / 'Bloodborne.exe'
        self.stock.write_bytes(b'exact synthetic stock launcher')
        self.stock_hash = digest(self.stock)
        (self.launcher / 'run.py').write_text('same-run-source', encoding='utf-8')
        (self.launcher / '_internal').mkdir()
        (self.launcher / '_internal' / 'stock.dll').write_bytes(b'preserve stock dependency')

        self.adapter = self.base / 'adapter build' / 'dist' / 'Bloodborne'
        self.adapter.mkdir(parents=True)
        (self.adapter / 'Bloodborne.exe').write_bytes(b'atlas adapter binary')
        (self.adapter / 'run.py').write_text('same-run-source', encoding='utf-8')
        (self.adapter / '_atlas_internal').mkdir()
        (self.adapter / '_atlas_internal' / 'python312.dll').write_bytes(b'owned adapter dependency')
        build_root = self.base / 'adapter build'
        build_root.mkdir(exist_ok=True)
        (build_root / 'source-receipt.json').write_text(json.dumps({
            'frozen_sha256': digest(self.adapter / 'Bloodborne.exe'),
            'frozen_dependency_sha256': {
                'python312.dll': digest(self.adapter / '_atlas_internal' / 'python312.dll'),
            },
            'launcher_build': 'windows-v1.7.2-atlas1',
            'runtime_build': 'hunters-atlas-runtime-1.4.0-beta1',
        }), encoding='utf-8')

        self.atlas = self.base / 'Atlas Package 名 with spaces'
        for folder in ('runtime', 'maps', 'settings', 'art', 'tools'):
            (self.atlas / folder).mkdir(parents=True, exist_ok=True)
        payloads = {
            'runtime/bb-probe.exe': b'probe',
            'art/font.ttf': b'font',
            'art/fallback.ttf': b'fallback font',
            'tools/generate_atlas.exe': b'generator',
        }
        for name, content in payloads.items():
            (self.atlas / name).write_bytes(content)
        (self.atlas / 'settings/settings.ini').write_text('[shortcuts]\n', encoding='utf-8')
        generated_payloads = {
            'maps/atlas.json': b'{"maps":[]}',
            'maps/catalog.json': b'{"areas":[]}',
        }
        for name, content in generated_payloads.items():
            (self.atlas / name).write_bytes(content)
        (self.atlas / 'maps/generated-assets.json').write_text(json.dumps({
            'schema': 1, 'version': 1,
            'game_eboot_sha256': 'd65f0b4f01d59166aed16f8604196d8b7dd805abbf0758b356e8f1354c9429f9',
            'game_version': 'fixture',
            'files': {name: digest(self.atlas / name) for name in generated_payloads},
        }), encoding='utf-8')
        manifest = {
            'id': 'hunters-atlas',
            'version': 'test',
            'launcher_builds': ['windows-v1.7.2-atlas1'],
            'runtime_build': 'hunters-atlas-runtime-1.4.0-beta1',
            'paths': {
                'probe': 'runtime/bb-probe.exe', 'maps': 'maps',
                'config': 'settings/settings.ini', 'art': 'art',
                'catalog': 'maps/catalog.json', 'font': 'art/font.ttf',
            },
            'generated': {
                'manifest': 'maps/generated-assets.json',
                'required': ['maps/atlas.json', 'maps/catalog.json'],
                'generator': 'tools/generate_atlas.exe',
            },
            'mutable_files': ['settings/settings.ini'],
            'files': {name: digest(self.atlas / name) for name in payloads},
        }
        (self.atlas / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        self.rollback = self.base / 'private rollback folder'

    def tearDown(self):
        self.temp.cleanup()

    def do_install(self):
        return atlas_install.install(
            self.launcher, self.adapter, self.atlas, self.rollback,
            expected_stock_sha256=self.stock_hash,
        )

    def test_install_uninstall_roundtrip_preserves_stock_tree_and_atlas(self):
        stock_internal = digest(self.launcher / '_internal' / 'stock.dll')
        settings = self.atlas / 'settings/settings.ini'
        settings.write_text('[shortcuts]\nmap=F9\n', encoding='utf-8')
        receipt_path = self.do_install()
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        self.assertEqual(receipt['state'], 'installed')
        self.assertNotEqual(digest(self.stock), self.stock_hash)
        self.assertEqual(digest(self.launcher / '_internal' / 'stock.dll'), stock_internal)
        self.assertEqual(settings.read_text(encoding='utf-8'), '[shortcuts]\nmap=F9\n')
        self.assertEqual((self.rollback / 'Bloodborne.exe').read_bytes(), b'exact synthetic stock launcher')

        atlas_install.uninstall(receipt_path)
        self.assertEqual(digest(self.stock), self.stock_hash)
        self.assertEqual(digest(self.launcher / '_internal' / 'stock.dll'), stock_internal)
        self.assertFalse((self.launcher / '_atlas_internal').exists())
        self.assertEqual(settings.read_text(encoding='utf-8'), '[shortcuts]\nmap=F9\n')
        self.assertEqual(json.loads(receipt_path.read_text(encoding='utf-8'))['state'], 'uninstalled')

    def test_actual_frozen_build_installs_and_uninstalls_in_fixture(self):
        source_root = Path(__file__).resolve().parents[1]
        built_adapter = source_root / 'build/dist/Bloodborne'
        source_receipt = source_root / 'build/source-receipt.json'
        if not built_adapter.is_dir() or not source_receipt.is_file():
            self.skipTest('Frozen launcher build is not present.')
        fixture_build = self.base / 'actual adapter'
        adapter_copy = fixture_build / 'dist/Bloodborne'
        shutil.copytree(built_adapter, adapter_copy)
        shutil.copy2(source_receipt, fixture_build / 'source-receipt.json')
        shutil.copy2(adapter_copy / 'run.py', self.launcher / 'run.py')
        receipt = atlas_install.install(
            self.launcher, adapter_copy, self.atlas, self.rollback,
            expected_stock_sha256=self.stock_hash,
        )
        atlas_install.uninstall(receipt)
        self.assertEqual(digest(self.stock), self.stock_hash)
        self.assertFalse((self.launcher / '_atlas_internal').exists())

    def test_frozen_public_installer_help_install_uninstall_without_python_path(self):
        source_root = Path(__file__).resolve().parents[1]
        installer = source_root / 'build/installer-dist/AtlasSetup.exe'
        stock_source = source_root.parents[2] / 'launcher-v1.7/Bloodborne.exe'
        if not installer.is_file():
            self.skipTest('Frozen standalone AtlasSetup.exe is not built.')
        if not stock_source.is_file():
            self.skipTest('Audited stock Bloodborne.exe is not available.')

        shutil.copy2(stock_source, self.stock)
        actual_stock_hash = digest(self.stock)
        (self.launcher / 'run.py').write_bytes((self.adapter / 'run.py').read_bytes())
        env = os.environ.copy()
        env['PATH'] = str(Path(os.environ.get('SYSTEMROOT', r'C:\Windows')) / 'System32')
        help_result = subprocess.run([str(installer), '--help'], capture_output=True, text=True,
                                     env=env, timeout=45, check=False)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn('install', help_result.stdout)
        self.assertIn('uninstall', help_result.stdout)

        install_result = subprocess.run([
            str(installer), 'install', '--launcher-root', str(self.launcher),
            '--adapter-root', str(self.adapter), '--atlas-folder', str(self.atlas),
            '--rollback-root', str(self.rollback),
        ], capture_output=True, text=True, env=env, timeout=90, check=False)
        self.assertEqual(install_result.returncode, 0, install_result.stderr)
        receipt = self.launcher / atlas_install.RECEIPT_NAME
        self.assertEqual(json.loads(receipt.read_text(encoding='utf-8'))['state'], 'installed')
        self.assertNotEqual(digest(self.stock), actual_stock_hash)
        self.assertEqual((self.launcher / '_internal' / 'stock.dll').read_bytes(), b'preserve stock dependency')
        uninstall_result = subprocess.run([
            str(installer), 'uninstall', '--receipt', str(receipt),
        ], capture_output=True, text=True, env=env, timeout=90, check=False)
        self.assertEqual(uninstall_result.returncode, 0, uninstall_result.stderr)
        self.assertEqual(digest(self.stock), actual_stock_hash)
        self.assertFalse((self.launcher / '_atlas_internal').exists())
        self.assertEqual((self.launcher / '_internal' / 'stock.dll').read_bytes(), b'preserve stock dependency')
        first_receipt = receipt.read_bytes()

        second_rollback = self.base / 'private rollback folder second install'
        reinstall_result = subprocess.run([
            str(installer), 'install', '--launcher-root', str(self.launcher),
            '--adapter-root', str(self.adapter), '--atlas-folder', str(self.atlas),
            '--rollback-root', str(second_rollback),
        ], capture_output=True, text=True, env=env, timeout=90, check=False)
        self.assertEqual(reinstall_result.returncode, 0, reinstall_result.stderr)
        self.assertEqual(json.loads(receipt.read_text(encoding='utf-8'))['state'], 'installed')
        archived = second_rollback / 'previous-atlas-install-receipt.json'
        self.assertEqual(archived.read_bytes(), first_receipt)
        self.assertEqual(digest(self.stock), digest(self.adapter / 'Bloodborne.exe'))

        final_uninstall = subprocess.run([
            str(installer), 'uninstall', '--receipt', str(receipt),
        ], capture_output=True, text=True, env=env, timeout=90, check=False)
        self.assertEqual(final_uninstall.returncode, 0, final_uninstall.stderr)
        self.assertEqual(digest(self.stock), actual_stock_hash)
        self.assertFalse((self.launcher / '_atlas_internal').exists())

    def test_reinstall_refuses_tampered_previous_rollback_backup(self):
        receipt = self.do_install()
        atlas_install.uninstall(receipt)
        (self.rollback / 'Bloodborne.exe').write_bytes(b'tampered prior stock backup')
        before = digest(self.stock)
        with self.assertRaisesRegex(atlas_install.InstallError, 'backup is missing or changed'):
            self.do_install()
        self.assertEqual(digest(self.stock), before)
        self.assertFalse((self.launcher / '_atlas_internal').exists())

    def test_reinstall_refuses_installed_or_unknown_receipt_states(self):
        receipt = self.do_install()
        atlas_install.uninstall(receipt)
        original = json.loads(receipt.read_text(encoding='utf-8'))
        for invalid_state in ('installed', 'legacy'):
            tampered = dict(original, state=invalid_state)
            receipt.write_text(json.dumps(tampered), encoding='utf-8')
            with self.subTest(state=invalid_state), self.assertRaisesRegex(
                    atlas_install.InstallError, 'completed uninstall'):
                self.do_install()
            receipt.write_text(json.dumps(original), encoding='utf-8')
        self.assertEqual(digest(self.stock), self.stock_hash)
        self.assertFalse((self.launcher / '_atlas_internal').exists())

    def test_refuses_changed_stock_executable_before_mutation(self):
        self.stock.write_bytes(b'updated launcher')
        before = digest(self.stock)
        with self.assertRaisesRegex(atlas_install.InstallError, 'SHA-256 mismatch'):
            self.do_install()
        self.assertEqual(digest(self.stock), before)
        self.assertFalse((self.launcher / '_atlas_internal').exists())

    def test_refuses_modified_adapter_executable_on_uninstall(self):
        receipt = self.do_install()
        self.stock.write_bytes(b'newer user launcher')
        with self.assertRaisesRegex(atlas_install.InstallError, 'changed since installation'):
            atlas_install.uninstall(receipt)
        self.assertEqual((self.launcher / '_atlas_internal' / 'python312.dll').read_bytes(), b'owned adapter dependency')

    def test_refuses_new_or_modified_adapter_dependency(self):
        receipt = self.do_install()
        (self.launcher / '_atlas_internal' / 'new.dll').write_bytes(b'user content')
        with self.assertRaisesRegex(atlas_install.InstallError, 'dependency files changed'):
            atlas_install.uninstall(receipt)
        self.assertNotEqual(digest(self.stock), self.stock_hash)

    def test_refuses_unlisted_atlas_file(self):
        (self.atlas / 'unexpected.bin').write_bytes(b'unlisted')
        with self.assertRaisesRegex(atlas_install.InstallError, 'unlisted files'):
            self.do_install()
        self.assertEqual(digest(self.stock), self.stock_hash)

    def test_mutable_config_is_only_manifest_exemption(self):
        (self.atlas / 'settings/settings.ini').write_text('user shortcut values', encoding='utf-8')
        atlas_install._validate_addon(self.atlas)
        manifest_path = self.atlas / 'manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest['files']['settings/settings.ini'] = digest(self.atlas / 'settings/settings.ini')
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaisesRegex(atlas_install.InstallError, 'Invalid immutable file record'):
            atlas_install._validate_addon(self.atlas)

    def test_rejects_package_traversal_and_symlinks(self):
        manifest_path = self.atlas / 'manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest['paths']['probe'] = '../outside.exe'
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaisesRegex(atlas_install.InstallError, 'stay inside'):
            atlas_install._validate_addon(self.atlas)

        manifest['paths']['probe'] = 'runtime/bb-probe.exe'
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        link = self.atlas / 'runtime/link-to-probe'
        try:
            link.symlink_to(self.atlas / 'runtime/bb-probe.exe')
        except (OSError, NotImplementedError):
            self.skipTest('symlink creation is unavailable on this Windows account')
        with self.assertRaisesRegex(atlas_install.InstallError, 'symlinks or junctions'):
            atlas_install._validate_addon(self.atlas)


if __name__ == '__main__':
    unittest.main()
