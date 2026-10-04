import json
import unittest
from pathlib import Path

from browser_storage import profile_validation_error, restore_pending, snapshot
from group_profiles import add_demo_schedule, initialize_group_profiles, load_group_profile, merge_imported_schedules
from user_profile import decode_profile


ROOT = Path(__file__).resolve().parents[1]


class SessionState(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc

    def __setattr__(self, key, value):
        self[key] = value


class BrowserStorageTests(unittest.TestCase):
    def setUp(self):
        self.demo_raw = (ROOT / 'data/schedule_demo.csv').read_bytes()

    def group_csv(self, names):
        lines = ['date,group,start_time,end_time,subject,teacher,room,coverage_start,coverage_end']
        for i, name in enumerate(names):
            lines.append(f'2026-10-01,{name},{8+i:02}:00,{9+i:02}:00,Class {name},T,1,2026-09-28,2026-10-03')
        return ('\n'.join(lines) + '\n').encode()

    def test_both_bundled_demo_profiles_survive_json_and_browser_restore(self):
        state = SessionState(query_params={})
        initialize_group_profiles(state, self.demo_raw)
        keys = sorted(state.group_profiles)
        self.assertEqual(len(keys), 2)
        for i, key in enumerate(keys):
            state.group_profiles[key]['tasks'] = [dict(
                id=f'demo_{i}', title=f'Demo task {i}', due='2026-10-07',
                done=False, minutes=50,
            )]

        active = keys[1]
        load_group_profile(state, active)
        state.plan_begin, state.plan_end, state.plan_limit = 9, 20, 120
        raw_payload = json.dumps(snapshot('Светлая', active, state), ensure_ascii=False)
        decoded = decode_profile(raw_payload)

        self.assertEqual(set(decoded['profiles']), set(keys))
        self.assertEqual([decoded['profiles'][key]['tasks'][0]['title'] for key in keys],
                         ['Demo task 0', 'Demo task 1'])
        self.assertEqual(profile_validation_error(raw_payload), '')

        restored = SessionState(_profile_pending=decoded,
                                 _enable_storage_after_load=True, query_params={})
        restore_pending(restored)
        initialize_group_profiles(restored, self.demo_raw,
                                  preferred_group=decoded['active_group'])

        self.assertEqual(set(restored.group_profiles), set(keys))
        self.assertEqual(restored.active_group_selector, active)
        self.assertEqual(restored.tasks, restored.group_profiles[active]['tasks'])
        self.assertEqual([restored.group_profiles[key]['tasks'][0]['title'] for key in keys],
                         ['Demo task 0', 'Demo task 1'])
        self.assertTrue(restored.persist_enabled)

    def test_ten_imported_groups_plus_two_demo_profiles_fit_backup_limit(self):
        profiles = add_demo_schedule({}, self.demo_raw, 'Встроенное демо')
        profiles = merge_imported_schedules(
            profiles, self.group_csv([f'R{i:02}' for i in range(10)]), 'ten-groups.csv')
        active = next(iter(profiles))
        payload = {
            'version': 2,
            'profiles': profiles,
            'active_group': active,
            'preferences': {'theme': 'Светлая', 'begin': 9, 'end': 20, 'limit': 120},
        }

        restored = decode_profile(json.dumps(payload, ensure_ascii=False))
        self.assertEqual(len(restored['profiles']), 12)
        self.assertEqual(sum(not item['is_demo'] for item in restored['profiles'].values()), 10)
        self.assertEqual(sum(item['is_demo'] for item in restored['profiles'].values()), 2)

    def test_browser_storage_reports_specific_profile_validation_error(self):
        state = SessionState(query_params={})
        initialize_group_profiles(state, self.demo_raw)
        key = state.active_group_selector
        payload = snapshot('Светлая', key, state)
        payload['preferences'].update(begin=22, end=9)

        error = profile_validation_error(json.dumps(payload, ensure_ascii=False))
        self.assertIn('часы подготовки', error)
        self.assertNotIn('лимит', error)


if __name__ == '__main__':
    unittest.main()
