import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1]


class FrozenUpdaterAtlasGuardTests(unittest.TestCase):
    def test_headless_stock_updater_refuses_enabled_atlas_without_touching_target(self):
        with tempfile.TemporaryDirectory(prefix='atlas-update-profile-') as folder:
            settings_root = Path(folder) / 'profile with spaces'
            settings_root.mkdir()
            settings_file = settings_root / 'settings.json'
            settings_file.write_text(json.dumps({'atlas_enabled': True, 'atlas_dir': 'E:/Hunter Atlas'}),
                                     encoding='utf-8')
            old_value = os.environ.get('BB_LAUNCHER_SETTINGS_ROOT')
            old_module = sys.modules.pop('bbport_launcher_win', None)
            sys.path.insert(0, str(SOURCE))
            os.environ['BB_LAUNCHER_SETTINGS_ROOT'] = str(settings_root)
            try:
                launcher = importlib.import_module('bbport_launcher_win')
                target = Path(folder) / 'installed port'
                target.mkdir()
                marker = target / 'Bloodborne.exe'
                marker.write_bytes(b'Atlas-aware launcher must remain untouched')
                messages = []
                user32 = types.SimpleNamespace(MessageBoxW=lambda *_args: messages.append(_args))
                fake_windll = types.SimpleNamespace(user32=user32)
                with mock.patch.object(launcher.ctypes, 'windll', fake_windll), \
                        mock.patch.object(launcher.shutil, 'copytree') as copytree, \
                        mock.patch.object(launcher.subprocess, 'Popen') as popen:
                    result = launcher.install_update(target, 4242)
                self.assertEqual(result, 1)
                self.assertEqual(marker.read_bytes(), b'Atlas-aware launcher must remain untouched')
                self.assertEqual(len(messages), 1)
                self.assertIn('Hunter', messages[0][1])
                copytree.assert_not_called()
                popen.assert_not_called()
            finally:
                sys.path.remove(str(SOURCE))
                if old_value is None:
                    os.environ.pop('BB_LAUNCHER_SETTINGS_ROOT', None)
                else:
                    os.environ['BB_LAUNCHER_SETTINGS_ROOT'] = old_value
                sys.modules.pop('bbport_launcher_win', None)
                if old_module is not None:
                    sys.modules['bbport_launcher_win'] = old_module


if __name__ == '__main__':
    unittest.main()
