import json
import unittest
from pathlib import Path
from datetime import date
from user_profile import decode_profile, clean_tasks
from schedule import parse_csv, expand, conflicts, clock_minutes

ROOT=Path(__file__).resolve().parents[1]

class ProfileTests(unittest.TestCase):
    def profile(self):
        return dict(version=1,tasks=[dict(id='abc',title='Задание',due='2026-10-02',done=False,minutes=50)],schedule=(ROOT/'data/isr242_2026-09-28.csv').read_text(encoding='utf-8'),source_name='ИСР-242уск',is_demo=False,preferences=dict(theme='Тёмная',group='ИСР-242уск',begin=9,end=20,limit=120))

    def test_roundtrip_and_backward_task_defaults(self):
        p=decode_profile(json.dumps(self.profile()))
        self.assertEqual(p,decode_profile(json.dumps(p)))
        self.assertEqual(p['tasks'][0]['steps'],'')
        self.assertEqual(p['preferences']['theme'],'Тёмная')

    def test_invalid_profile_is_rejected(self):
        for key,value in [('tasks',[{}]),('schedule','broken'),('is_demo','false'),('preferences',{'begin':22,'end':9}),('version',2)]:
            with self.subTest(key=key):
                p=self.profile();p[key]=value
                with self.assertRaises(ValueError):decode_profile(json.dumps(p))
        for raw in ['{','[]','x'*3_000_001]:
            with self.assertRaises(ValueError):decode_profile(raw)

    def test_duplicate_ids_and_boolean_minutes_rejected(self):
        task=self.profile()['tasks'][0]
        with self.assertRaises(ValueError):clean_tasks([task,task])
        with self.assertRaises(ValueError):clean_tasks([{**task,'minutes':True}])
        with self.assertRaises(ValueError):clean_tasks([{**task,'due':'2026-02-30'}])

    def test_real_week_not_repeated(self):
        frame=parse_csv(self.profile()['schedule'].encode())
        self.assertEqual(len(frame),23)
        self.assertEqual(set(frame.group),{'ИСР-242уск'})
        self.assertTrue(all(clock_minutes(r.end_time)-clock_minutes(r.start_time)==50 for r in frame.itertuples()))
        self.assertFalse(conflicts(expand(frame,date(2026,9,28))))
        self.assertTrue(expand(frame,date(2026,10,5)).empty)
