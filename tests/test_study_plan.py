import unittest
from datetime import datetime
from schedule import parse_csv,TZ
from study_plan import allocate,validate_assignment
HEADER='date,group,start_time,end_time,subject,teacher,room\n'

class PlanTests(unittest.TestCase):
    def task(self,**kwargs):
        return {'id':'a','title':'Lab','due':'2026-09-29','done':False,'minutes':100,**kwargs}
    def test_class_buffer_past_time_daily_limit(self):
        schedule=parse_csv((HEADER+'2026-09-29,X,10:00,10:50,Class,T,1\n').encode())
        rows,left=allocate([self.task()],schedule,datetime(2026,9,29,9,40,tzinfo=TZ),9,20,60)
        self.assertEqual(rows[0]['Начало'],'11:00')
        self.assertEqual(sum(r['Минут'] for r in rows),50)
        self.assertEqual(left[0]['Не размещено, мин'],50)
    def test_two_tasks_never_overlap(self):
        schedule=parse_csv((HEADER+'2026-09-30,X,10:00,10:50,Class,T,1\n').encode())
        rows,left=allocate([self.task(minutes=50),self.task(id='b',minutes=50)],schedule,datetime(2026,9,29,8,tzinfo=TZ))
        self.assertFalse(left)
        self.assertEqual([(r['Начало'],r['Конец']) for r in rows],[('09:00','09:50'),('10:00','10:50')])
    def test_snapshot_unknown_dates_are_not_planned(self):
        raw=(HEADER+'2026-09-28,X,10:00,10:50,Class,T,1\n'
             '2026-10-03,X,10:00,10:50,Class,T,1\n')
        schedule=parse_csv(raw.encode())
        rows,left=allocate([self.task(due='2026-10-05',minutes=100)],schedule,
                           datetime(2026,9,29,8,tzinfo=TZ),daily_limit=15)
        self.assertTrue(rows)  # September 30 through October 2 are confirmed free.
        self.assertTrue(all(r['Дата']<=datetime(2026,10,3).date() for r in rows))
        self.assertEqual(left[0]['Не размещено, мин'],25)
        self.assertTrue(left[0]['coverage_unknown'])
    def test_confirmed_empty_date_is_available(self):
        raw=(HEADER+'2026-09-28,X,10:00,10:50,Class,T,1\n'
             '2026-09-30,X,10:00,10:50,Class,T,1\n')
        rows,left=allocate([self.task(due='2026-09-29',minutes=30)],parse_csv(raw.encode()),
                           datetime(2026,9,29,8,tzinfo=TZ))
        self.assertFalse(left)
        self.assertTrue(rows)
        self.assertTrue(all(r['Дата']==datetime(2026,9,29).date() for r in rows))
    def test_sixty_minutes_split_without_stranding_short_tail(self):
        raw=HEADER+'2026-09-29,X,12:00,12:50,Class,T,1\n'
        rows,left=allocate([self.task(minutes=60)],parse_csv(raw.encode()),
                           datetime(2026,9,29,9,tzinfo=TZ))
        self.assertFalse(left)
        self.assertEqual([r['Минут'] for r in rows],[45,15])
    def test_expired_and_done_tasks(self):
        schedule=parse_csv((HEADER+'2026-09-30,X,10:00,10:50,Class,T,1\n').encode())
        rows,left=allocate([self.task(due='2026-09-28'),self.task(id='b',done=True)],schedule,datetime(2026,9,29,8,tzinfo=TZ))
        self.assertFalse(rows)
        self.assertEqual(len(left),1)
    def test_assignment_requires_grounded_quote(self):
        draft={'title':'Lab','subject':'SQL','due':'','evidence':'SQL lab','steps':['Read task']}
        self.assertEqual(validate_assignment(draft,'Prepare SQL lab.'),draft)
        with self.assertRaises(ValueError):validate_assignment(draft,'Other homework')
        with self.assertRaises(ValueError):validate_assignment({**draft,'due':'2026-02-30'},'SQL lab')
