import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from analyze_family_sessions import FAMILIES, summarize


def sheet(family):
    return dict(cohort_id='fixture', condition_id='lan', firmware='ct45', prototype_or_device='device',
                anonymous_id=family, evidence_kind='family_observation', parent_present=True, first_use=True, web_opened=True, first_action_completed=True,
                independent_stop=True, first_use_seconds=180, help_count=0, free_play_observed=True,
                repeat_plays=['登场'], modified_shows=['登场'])


class FamilyTests(unittest.TestCase):
    def test_same_play_and_theatre_are_different(self):
        rows = [sheet(i) for i in FAMILIES]
        for row, play in zip(rows, ['登场', '登场', '庆祝', '谢幕', '吹泡泡一秒']):
            row.update(repeat_plays=[play], modified_shows=[])
        rows[0]['help_count'] = 1
        r = summarize(rows)['groups'][0]
        self.assertEqual(r['same_play_repeated']['result'], 'missed')
        self.assertEqual(r['replayed_or_modified_show']['positive'], 4)
        self.assertEqual(r['independent_use']['positive'], 4)
        rows[1]['first_use_seconds'] = 180.01
        self.assertEqual(summarize(rows)['groups'][0]['independent_use']['result'], 'missed')

    def test_unknown_and_group_boundaries(self):
        rows = [sheet(i) for i in FAMILIES]
        rows[0].update(first_use=False, repeat_plays=None, modified_shows=[])
        rows[1]['free_play_observed'] = False
        rows.append({**rows[2], 'prototype_or_device':'prototype'})
        r = summarize([*rows, {**rows[0], 'evidence_kind':'dry_run'}, {'spontaneous_repeat':True}])
        self.assertEqual(r['dry_run_rows'], 1)
        self.assertEqual(r['unclassified_rows'], 1)
        device, proto = r['groups']
        self.assertEqual(proto['same_play_repeated']['scope'], 'prototype_only')
        self.assertEqual(device['same_play_repeated']['observed'], 3)
        self.assertEqual(device['replayed_or_modified_show']['observed'], 3)
        self.assertEqual(device['independent_use']['result'], 'pending')

    def test_duplicate_and_invalid_data(self):
        row = sheet('F01')
        for data in ([row, row], [{**row,'first_use_seconds':float('nan')}],
                     [{**row,'repeat_plays':['登场','登场']}], [{**row,'help_count':False}]):
            with self.assertRaises(ValueError):
                summarize(data)

    def test_templates_and_custom_stories_count_by_identity(self):
        rows = [sheet(i) for i in FAMILIES]
        for i, row in enumerate(rows):
            row['repeat_plays'] = [f'自编/B{i}']
            row['modified_shows'] = []
        self.assertEqual(summarize(rows)['groups'][0]['same_play_repeated']['positive'], 1)
        for row in rows[:3]:
            row['repeat_plays'] = ['自编/B1']
        r = summarize(rows)['groups'][0]
        self.assertEqual(r['same_play_repeated']['result'], 'met')
        self.assertEqual(r['replayed_or_modified_show']['positive'], 5)

    def test_voice_only_does_not_prove_web_onboarding(self):
        rows = [sheet(i) for i in FAMILIES]
        rows[0]['web_opened'] = False
        rows[1]['web_opened'] = None
        first = summarize(rows)['groups'][0]['independent_use']
        self.assertEqual((first['observed'], first['positive'], first['result']), (4, 3, 'pending'))
