import importlib.util
from pathlib import Path
import unittest


SOURCE = Path(__file__).resolve().parents[2] / 'bootstrap' / 'integrated_play.py'
SPEC = importlib.util.spec_from_file_location('atlas_integrated_play_test', SOURCE)
integrated = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(integrated)


class IntegratedEnvironmentTests(unittest.TestCase):
    def test_serial_preparation_preserves_selected_user_data_and_graphics(self):
        root = Path('Atlas')
        contract = {'root': root, 'base_root': Path('port'),
                    'state_root': root / 'state', 'paths': {'config': root / 'settings.ini'}}
        paths = {key: root / key for key in ('probe', 'maps', 'art', 'catalog', 'font')}
        inherited = {'BB_PREP_WORKERS': '4', 'BB_USER_DIR': 'chosen-saves',
                     'BB_DLC_DIR': 'chosen-dlc', 'BB_CONFIG': 'chosen-graphics.ini',
                     'BB_FPS': 'uncap'}
        result = integrated.environment(None, contract, paths, inherited)
        self.assertEqual(result['BB_PREP_WORKERS'], '0')
        for key in ('BB_USER_DIR', 'BB_DLC_DIR', 'BB_CONFIG', 'BB_FPS'):
            self.assertEqual(result[key], inherited[key])
        self.assertEqual(inherited['BB_PREP_WORKERS'], '4')


if __name__ == '__main__':
    unittest.main()
