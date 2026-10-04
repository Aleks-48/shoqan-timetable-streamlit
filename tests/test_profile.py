import json
import unittest
from pathlib import Path
from datetime import date
from user_profile import decode_profile, clean_tasks
from schedule import parse_csv, expand, conflicts, clock_minutes, coverage_info
from group_profiles import merge_imported_schedules, MAX_IMPORTED_GROUPS

ROOT=Path(__file__).resolve().parents[1]

class ProfileTests(unittest.TestCase):
    def profile(self):
        return dict(version=1,tasks=[dict(id='abc',title='Задание',due='2026-10-02',done=False,minutes=50)],schedule=(ROOT/'data/isr242_2026-09-28.csv').read_text(encoding='utf-8'),source_name='ИСР-242уск',is_demo=False,preferences=dict(theme='Тёмная',group='ИСР-242уск',begin=9,end=20,limit=120))

    def test_roundtrip_and_backward_task_defaults(self):
        p=decode_profile(json.dumps(self.profile()))
        self.assertEqual(p,decode_profile(json.dumps(p)))
        self.assertEqual(p['tasks'][0]['steps'],'')
        self.assertEqual(p['tasks'][0]['blocks'],[])
        self.assertEqual(p['tasks'][0]['unplaced_minutes'],50)
        self.assertEqual(p['preferences']['theme'],'Тёмная')
    def test_saved_block_progress_survives_profile_roundtrip(self):
        profile=self.profile()
        profile['tasks'][0].update(blocks=[dict(id='a'*20,date='2026-10-01',start_time='09:00',
            end_time='09:50',minutes=50,done=True)],unplaced_minutes=0,coverage_unknown=False)
        restored=decode_profile(json.dumps(profile))
        self.assertTrue(restored['tasks'][0]['blocks'][0]['done'])
        self.assertEqual(restored,decode_profile(json.dumps(restored)))

    def test_duplicate_block_ids_across_tasks_are_rejected(self):
        from copy import deepcopy
        task=self.profile()['tasks'][0]
        task['blocks']=[dict(id='a'*20,date='2026-10-01',start_time='09:00',
                            end_time='09:50',minutes=50,done=False)]
        other=deepcopy(task)
        other['id']='another'
        with self.assertRaisesRegex(ValueError,'между заданиями'):
            clean_tasks([task,other])

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
        with self.assertRaises(ValueError):clean_tasks([{**task,'blocks':[dict(id='bad',date='2026-10-01',start_time='09:00',end_time='09:50',minutes=50,done=False)]}])
        with self.assertRaises(ValueError):clean_tasks([{**task,'blocks':[dict(id='a'*20,date='2026-10-01',start_time='10:00',end_time='09:50',minutes=50,done=False)]}])

    def test_real_week_not_repeated(self):
        frame=parse_csv(self.profile()['schedule'].encode())
        self.assertEqual(len(frame),23)
        self.assertEqual(set(frame.group),{'ИСР-242уск'})
        self.assertTrue(all(clock_minutes(r.end_time)-clock_minutes(r.start_time)==50 for r in frame.itertuples()))
        self.assertFalse(conflicts(expand(frame,date(2026,9,28))))
        self.assertTrue(expand(frame,date(2026,10,5)).empty)

    def group_csv(self,names,subject='Class'):
        lines=['date,group,start_time,end_time,subject,teacher,room,coverage_start,coverage_end']
        for i,name in enumerate(names):
            lines.append(f'2026-10-01,{name},{8+i:02}:00,{9+i:02}:00,{subject} {name},T,1,2026-09-28,2026-10-03')
        return ('\n'.join(lines)+'\n').encode()

    def test_ten_imported_groups_keep_individual_source_and_coverage(self):
        raw=self.group_csv([f'G{i:02}' for i in range(10)])
        profiles=merge_imported_schedules({},raw,'campus-week.csv')
        self.assertEqual(len(profiles),MAX_IMPORTED_GROUPS)
        for name,profile in profiles.items():
            self.assertEqual(profile['source_name'],'campus-week.csv')
            self.assertEqual(set(parse_csv(profile['schedule'].encode()).group),{name})
            info=coverage_info(parse_csv(profile['schedule'].encode()))
            self.assertEqual((info['start'].isoformat(),info['end'].isoformat()),('2026-09-28','2026-10-03'))

    def test_group_limit_rejects_import_atomically(self):
        existing=merge_imported_schedules({},self.group_csv([f'G{i:02}' for i in range(9)]),'nine.csv')
        before=json.dumps(existing,sort_keys=True)
        with self.assertRaisesRegex(ValueError,'не более 10'):
            merge_imported_schedules(existing,self.group_csv(['G09','G10']),'overflow.csv')
        self.assertEqual(json.dumps(existing,sort_keys=True),before)

    def test_group_names_outside_profile_safe_domain_rejected_atomically(self):
        existing=merge_imported_schedules({},self.group_csv(['Kept']),'kept.csv')
        before=json.dumps(existing,sort_keys=True)
        for name,expected in [('G'*201,'200'),('=G','Excel')]:
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError,expected):
                    merge_imported_schedules(existing,self.group_csv([name]),'unsafe.csv')
                self.assertEqual(json.dumps(existing,sort_keys=True),before)

    def test_excel_safe_csv_export_is_preserved_for_formula_subjects(self):
        raw=self.group_csv(['A'],subject='=cmd')
        profiles=merge_imported_schedules({},raw,'formula-subject.csv')
        profile_frame=parse_csv(profiles['A']['schedule'].encode('utf-8'))
        self.assertEqual(profile_frame.iloc[0].subject,"'=cmd A")

    def test_replacing_group_schedule_preserves_its_plan(self):
        existing=merge_imported_schedules({},self.group_csv(['A']),'first.csv')
        existing['A']['tasks']=[dict(id='a',title='My task',due='2026-10-02',done=False,minutes=50)]
        updated=merge_imported_schedules(existing,self.group_csv(['A'],subject='Updated'),'second.csv')
        self.assertEqual(updated['A']['tasks'],existing['A']['tasks'])
        self.assertEqual(updated['A']['source_name'],'second.csv')
        self.assertIn('Updated A',updated['A']['schedule'])

    def test_multi_group_profile_roundtrip_preserves_group_sources(self):
        profiles=merge_imported_schedules({},self.group_csv(['A','B']),'two-groups.csv')
        payload={'version':2,'profiles':profiles,'active_group':'B',
                 'preferences':{'theme':'Светлая','begin':9,'end':20,'limit':120}}
        restored=decode_profile(json.dumps(payload))
        self.assertEqual(set(restored['profiles']),{'A','B'})
        self.assertEqual(restored['profiles']['A']['source_name'],'two-groups.csv')
        self.assertEqual(restored['active_group'],'B')
        self.assertEqual(decode_profile(json.dumps(restored)),restored)
