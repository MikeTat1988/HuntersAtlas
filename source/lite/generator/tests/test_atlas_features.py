"""Feature parsing and launch settings contracts without game files."""
import importlib.util
import json
from pathlib import Path
import struct
import unittest

REPO = Path(__file__).resolve().parents[4]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


extract = load('feature_extraction', REPO / 'source/generator/src/extract_atlas_features.py')
settings = load('feature_configuration', REPO / 'source/lite/integration/ui/atlas_feature_config.py')


class Features(unittest.TestCase):
    def test_ezl_menu_arithmetic(self):
        # Native menu expression: 10,000,000 + 241 * 10,000 + 7810 + 20 * slot.
        integer = lambda n: b'\x82' + struct.pack('<i', n)
        expr = integer(10000000) + integer(241) + integer(10000) + b'\x8f\x8c' + integer(7810) + b'\x8c' + b'\x54\x41\x8f\x8c\xa1'
        self.assertEqual(extract.constant(expr), 12417830)
        self.assertIsNone(extract.constant(b'\x4f\x82\x01\x00\x00\x00\x85\xa1'))

    def test_ezl_flag_is_data(self):
        expr = b'\x4f\x82' + struct.pack('<i', 12417830) + b'\x85\x41\x95\xa1'
        self.assertEqual(extract.expression(expr), ['==', ['flag', 12417830], 1])
        with self.assertRaises(ValueError):
            extract.expression(b'\xff')

    def test_settings_defaults_and_invalid_input(self):
        for value in ('bad json', '[]', '{"atlas_npc_mode":"bogus","atlas_travel_enabled":"false"}', 'x' * 4097):
            parsed = settings.decode(value)
            self.assertFalse(parsed['atlas_travel_enabled'])
            self.assertEqual(parsed['atlas_npc_mode'], 'all')
        self.assertEqual(settings.decode('null'), settings.normalize({}))

    def test_every_feature_round_trips_restart_contract(self):
        source = {k: not v if isinstance(v, bool) else 'new_dialogue' for k, v in settings.DEFAULTS.items()}
        env = settings.environment(source)
        self.assertEqual(settings.decode(env['BB_ATLAS_FEATURES']), settings.normalize(source))
        self.assertEqual(env['BB_MAP_TRAVEL_ENABLED'], '1')
        self.assertEqual(env['BB_MAP_FOG_ENABLED'], '1')
        self.assertEqual(env['BB_MAP_ITEM_CATEGORIES'], '')
        self.assertEqual(env['BB_MAP_NPC_MODE'], 'new_dialogue')

if __name__ == '__main__':
    unittest.main()
