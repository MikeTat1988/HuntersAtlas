"""Validated feature settings shared by the launcher and Atlas bootstrap."""
from __future__ import annotations
import json

DEFAULTS = {
    'atlas_npc_mode': 'all', 'atlas_items_enabled': False,
    'atlas_item_healing': True, 'atlas_item_insight': True,
    'atlas_item_equipment': True, 'atlas_item_echoes': True,
    'atlas_travel_enabled': False, 'atlas_fog_enabled': False,
}


def boolean(value):
    return value is True or value == 1 or (isinstance(value, str) and value.lower() in ('1', 'true', 'yes', 'on'))


def normalize(settings):
    if not isinstance(settings, dict):
        settings = {}
    result = {k: boolean(settings.get(k, v)) for k, v in DEFAULTS.items() if k != 'atlas_npc_mode'}
    mode = settings.get('atlas_npc_mode', 'all')
    result['atlas_npc_mode'] = mode if mode in ('all', 'new_dialogue', 'hidden') else 'all'
    return result


def decode(value):
    try:
        data = json.loads(value) if isinstance(value, str) and len(value) <= 4096 else {}
    except (ValueError, TypeError):
        data = {}
    return normalize(data)


def environment(settings):
    s = normalize(settings)
    return {
        'BB_ATLAS_FEATURES': json.dumps(s, sort_keys=True, separators=(',', ':')),
        'BB_MAP_NPC_MODE': s['atlas_npc_mode'],
        'BB_MAP_ITEMS_ENABLED': str(int(s['atlas_items_enabled'])),
        'BB_MAP_ITEM_CATEGORIES': ','.join(k for k in ('healing', 'insight', 'equipment', 'echoes') if s['atlas_item_' + k]),
        'BB_MAP_TRAVEL_ENABLED': str(int(s['atlas_travel_enabled'])),
        'BB_MAP_FOG_ENABLED': str(int(s['atlas_fog_enabled'])),
    }
