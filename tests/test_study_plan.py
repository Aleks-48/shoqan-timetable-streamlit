import unittest
from datetime import datetime, timedelta
from schedule import parse_csv,TZ
from study_plan import allocate,preview_assignment,commit_assignment,validate_assignment,validate_saved_blocks,preview_replan,edit_candidate_blocks
HEADER='date,group,start_time,end_time,subject,teacher,room\n'

class PlanTests(unittest.TestCase):
    def task(self,**kwargs):
        return {'id':'a','title':'Lab','due':'2026-09-29','done':False,'minutes':100,**kwargs}
    def with_coverage(self,raw,start,end):
        lines=raw.strip().splitlines()
        return '\n'.join([lines[0]+',coverage_start,coverage_end',
                           *(line+f',{start},{end}' for line in lines[1:])])+'\n'
    def test_class_buffer_past_time_daily_limit(self):
        schedule=parse_csv((HEADER+'2026-09-29,X,10:00,10:50,Class,T,1\n').encode())
        rows,left=allocate([self.task()],schedule,datetime(2026,9,29,9,40,tzinfo=TZ),9,20,60)
        self.assertEqual(rows[0]['Начало'],'11:00')
        self.assertEqual(sum(r['Минут'] for r in rows),50)
        self.assertEqual(left[0]['Не размещено, мин'],50)
    def test_two_tasks_never_overlap(self):
        raw=HEADER+'2026-09-30,X,10:00,10:50,Class,T,1\n'
        schedule=parse_csv(self.with_coverage(raw,'2026-09-29','2026-09-30').encode())
        rows,left=allocate([self.task(minutes=50),self.task(id='b',minutes=50)],schedule,datetime(2026,9,29,8,tzinfo=TZ))
        self.assertFalse(left)
        self.assertEqual([(r['Начало'],r['Конец']) for r in rows],[('09:00','09:50'),('10:00','10:50')])
    def test_preview_keeps_saved_block_and_respects_capacity_and_deadline(self):
        raw=HEADER+'2026-09-29,X,12:00,12:50,Class,T,1\n'
        schedule=parse_csv(self.with_coverage(raw,'2026-09-29','2026-09-29').encode())
        existing={'id':'old','title':'Реферат','due':'2026-09-29','done':False,'minutes':50,
                  'unplaced_minutes':0,'blocks':[{'id':'a'*20,'date':'2026-09-29',
                  'start_time':'09:00','end_time':'09:50','minutes':50,'done':False}]}
        candidate={'id':'new','title':'Лабораторная','due':'2026-09-29','done':False,'minutes':120,'blocks':[]}
        before_existing=dict(existing,blocks=[dict(existing['blocks'][0])])
        before_candidate=dict(candidate,blocks=[])
        plan=preview_assignment([existing],candidate,schedule,datetime(2026,9,29,8,tzinfo=TZ),9,20,120)
        new_blocks=plan['blocks_by_task']['new']
        self.assertEqual([(b['start_time'],b['end_time']) for b in new_blocks],
                         [('10:00','10:50'),('11:00','11:20')])
        self.assertEqual(plan['unplaced_by_task']['new'],50)
        self.assertTrue(plan['coverage_unknown_by_task']['new'] is False)
        self.assertEqual(existing,before_existing)
        self.assertEqual(candidate,before_candidate)
        saved=commit_assignment([existing],candidate,plan)
        self.assertEqual(saved[0]['blocks'],existing['blocks'])
        self.assertEqual(len(saved[1]['blocks']),2)
        self.assertEqual(saved[1]['unplaced_minutes'],50)
    def test_saved_completed_block_still_reserves_time(self):
        schedule=parse_csv(self.with_coverage(HEADER+'2026-09-29,X,12:00,12:50,Class,T,1\n',
                                              '2026-09-29','2026-09-29').encode())
        existing={'id':'old','title':'Реферат','due':'2026-09-29','done':False,'minutes':50,
                  'unplaced_minutes':0,'blocks':[{'id':'b'*20,'date':'2026-09-29',
                  'start_time':'09:00','end_time':'09:50','minutes':50,'done':True}]}
        candidate={'id':'new','title':'Лабораторная','due':'2026-09-29','done':False,'minutes':20,'blocks':[]}
        plan=preview_assignment([existing],candidate,schedule,datetime(2026,9,29,8,tzinfo=TZ),9,20,120)
        self.assertEqual(plan['blocks_by_task']['new'][0]['start_time'],'10:00')
        self.assertTrue(plan['blocks_by_task']['new'][0]['start_time']>existing['blocks'][0]['start_time'])
    def test_saved_blocks_are_checked_against_classes_and_coverage(self):
        raw=HEADER+'2026-09-29,X,10:00,11:00,Class,T,1\n'
        schedule=parse_csv(self.with_coverage(raw,'2026-09-29','2026-09-29').encode())
        task=self.task(due='2026-09-29',blocks=[
            {'id':'a'*20,'date':'2026-09-29','start_time':'10:10','end_time':'10:50','minutes':40,'done':False},
            {'id':'b'*20,'date':'2026-09-30','start_time':'09:00','end_time':'09:50','minutes':50,'done':False},
        ])
        issues=validate_saved_blocks([task],schedule)
        self.assertEqual({issue['kind'] for issue in issues},{'class_overlap','coverage'})
        self.assertTrue(any('Class' in issue['reason'] for issue in issues))
        self.assertTrue(any(issue['date']=='2026-09-30' for issue in issues))
    def test_replan_requires_caller_confirmation_and_preserves_done_blocks(self):
        raw=HEADER+'2026-09-29,X,10:00,11:00,Class,T,1\n'
        schedule=parse_csv(self.with_coverage(raw,'2026-09-29','2026-09-30').encode())
        done={'id':'a'*20,'date':'2026-09-29','start_time':'10:00','end_time':'10:50','minutes':50,'done':True}
        conflict={'id':'b'*20,'date':'2026-09-29','start_time':'10:00','end_time':'10:50','minutes':50,'done':False}
        task=self.task(due='2026-09-29',minutes=100,blocks=[dict(done),dict(conflict)])
        original={'id':task['id'],'blocks':[dict(done),dict(conflict)]}
        proposal=preview_replan([task],schedule,datetime(2026,9,29,8,tzinfo=TZ),8,20,120)
        planned=proposal['tasks'][0]
        kept=next(block for block in planned['blocks'] if block['done'])
        moved=next(block for block in planned['blocks'] if not block['done'])
        self.assertEqual(kept,done)
        self.assertNotEqual((moved['date'],moved['start_time']),(conflict['date'],conflict['start_time']))
        self.assertEqual(validate_saved_blocks(proposal['tasks'],schedule),[
            issue for issue in validate_saved_blocks([task],schedule) if issue['block_id']==done['id']])
        self.assertEqual(task,{'id':original['id'],'title':'Lab','due':'2026-09-29','done':False,
                               'minutes':100,'blocks':original['blocks']})
    def test_gap_between_min_max_is_unknown_without_metadata(self):
        raw=(HEADER+'2026-09-28,X,10:00,10:50,Class,T,1\n'
             '2026-10-03,X,10:00,10:50,Class,T,1\n')
        schedule=parse_csv(raw.encode())
        rows,left=allocate([self.task(due='2026-09-30',minutes=30)],schedule,
                           datetime(2026,9,29,8,tzinfo=TZ))
        self.assertFalse(rows)
        self.assertEqual(left[0]['Не размещено, мин'],30)
        self.assertTrue(left[0]['coverage_unknown'])
    def test_confirmed_empty_day_inside_explicit_interval_is_available(self):
        raw=(HEADER+'2026-09-28,X,10:00,10:50,Class,T,1\n'
             '2026-10-03,X,10:00,10:50,Class,T,1\n')
        schedule=parse_csv(self.with_coverage(raw,'2026-09-28','2026-10-03').encode())
        rows,left=allocate([self.task(due='2026-09-29',minutes=30)],schedule,
                           datetime(2026,9,29,8,tzinfo=TZ))
        self.assertFalse(left)
        self.assertTrue(rows)
        self.assertTrue(all(r['Дата']==datetime(2026,9,29).date() for r in rows))
    def test_explicit_interval_includes_both_boundaries(self):
        raw=(HEADER+'2026-09-29,X,10:00,10:50,Class,T,1\n'
             '2026-10-02,X,10:00,10:50,Class,T,1\n')
        schedule=parse_csv(self.with_coverage(raw,'2026-09-29','2026-10-02').encode())
        rows,left=allocate([self.task(due='2026-10-02',minutes=480)],schedule,
                           datetime(2026,9,28,8,tzinfo=TZ),daily_limit=120)
        self.assertFalse(left)
        days={row['Дата'] for row in rows}
        self.assertEqual(min(days),datetime(2026,9,29).date())
        self.assertEqual(max(days),datetime(2026,10,2).date())
    def test_empty_schedule_never_creates_free_slots(self):
        schedule=parse_csv((HEADER+'2026-09-29,X,10:00,10:50,Class,T,1\n').encode()).iloc[:0]
        rows,left=allocate([self.task(minutes=30)],schedule,datetime(2026,9,29,8,tzinfo=TZ))
        self.assertFalse(rows)
        self.assertEqual(left[0]['Не размещено, мин'],30)
        self.assertTrue(left[0]['coverage_unknown'])
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
        self.assertEqual(validate_assignment(draft,'Prepare SQL lab.'),{**draft,'requirements':[]})
        with self.assertRaises(ValueError):validate_assignment(draft,'Other homework')
        with self.assertRaises(ValueError):validate_assignment({**draft,'due':'2026-02-30'},'SQL lab')
        with self.assertRaisesRegex(ValueError,'YYYY-MM-DD'):
            validate_assignment({**draft,'due':'2026-1-1'},'SQL lab')
        with self.assertRaises(ValueError):validate_assignment({**draft,'requirements':['x'*201]},'SQL lab')

    def test_autoplan_preview_is_editable_and_reports_unplaced_minutes(self):
        raw=HEADER+'2026-09-29,X,12:00,13:00,Class,T,1\n'
        schedule=parse_csv(self.with_coverage(raw,'2026-09-29','2026-09-29').encode())
        candidate={'id':'draft','title':'Report','due':'2026-09-29','done':False,'minutes':60,'blocks':[]}
        now=datetime(2026,9,29,8,tzinfo=TZ)
        preview=preview_assignment([],candidate,schedule,now,9,20,120)
        self.assertTrue(preview['blocks_by_task']['draft'])
        first=preview['blocks_by_task']['draft'][0]
        self.assertEqual(first['start_time'],'09:00')
        edited=edit_candidate_blocks(preview,candidate,[{'date':'2026-09-29','start_time':'10:00','minutes':50}],
                                     [],schedule,now,9,20,120)
        self.assertEqual(edited['blocks_by_task']['draft'][0]['start_time'],'10:00')
        self.assertEqual(edited['unplaced_by_task']['draft'],10)
        with self.assertRaisesRegex(ValueError,'пересекается с занятием'):
            edit_candidate_blocks(preview,candidate,[{'date':'2026-09-29','start_time':'12:10','minutes':30}],
                                  [],schedule,now,9,20,120)
        two_day_schedule=parse_csv(self.with_coverage(raw,'2026-09-29','2026-09-30').encode())
        two_day_candidate={**candidate,'due':'2026-09-30','minutes':60}
        two_day_preview=preview_assignment([],two_day_candidate,two_day_schedule,now,9,20,120)
        edited=edit_candidate_blocks(
            two_day_preview,two_day_candidate,
            [{'date':'2026-09-29','start_time':'09:00','minutes':30},
             {'date':'2026-09-30','start_time':'09:00','minutes':30}],
            [],two_day_schedule,now,9,20,120)
        self.assertEqual(len(edited['blocks_by_task']['draft']),2)
        self.assertEqual(edited['unplaced_by_task']['draft'],0)

    def test_editor_cannot_place_outside_thirty_day_preview_horizon(self):
        start=datetime(2026,9,29,8,tzinfo=TZ)
        due=start.date()+timedelta(days=40)
        raw=(HEADER+f'{start.date()},X,12:00,12:50,First,T,1\n'
             +f'{due},X,12:00,12:50,Last,T,1\n')
        schedule=parse_csv(self.with_coverage(raw,start.date().isoformat(),due.isoformat()).encode())
        candidate={'id':'horizon','title':'Long task','due':due.isoformat(),
                   'done':False,'minutes':50,'blocks':[]}
        preview=preview_assignment([],candidate,schedule,start,9,20,120)
        self.assertEqual(preview['horizon'],30)
        outside=(start.date()+timedelta(days=40)).isoformat()
        with self.assertRaisesRegex(ValueError,'горизонт'):
            edit_candidate_blocks(preview,candidate,
                [{'date':outside,'start_time':'09:00','minutes':50}],[],schedule,start,9,20,120)

    def test_editor_matches_allocator_rounding_after_seconds(self):
        start=datetime(2026,9,29,9,0,1,tzinfo=TZ)
        raw=(HEADER+'2026-09-29,X,12:00,12:50,Class,T,1\n')
        schedule=parse_csv(self.with_coverage(raw,'2026-09-29','2026-09-29').encode())
        candidate={'id':'seconds','title':'Quick task','due':'2026-09-29',
                   'done':False,'minutes':15,'blocks':[]}
        preview=preview_assignment([],candidate,schedule,start,9,20,120)
        self.assertEqual(preview['blocks_by_task']['seconds'][0]['start_time'],'09:01')
        with self.assertRaisesRegex(ValueError,'прошедшее'):
            edit_candidate_blocks(preview,candidate,
                [{'date':'2026-09-29','start_time':'09:00','minutes':15}],[],schedule,start,9,20,120)

    def test_assignment_preview_reaches_deadlines_beyond_two_weeks(self):
        start=datetime(2026,9,29,8,tzinfo=TZ)
        due=start.date()+timedelta(days=20)
        lines=[HEADER.strip()]
        for offset in range(15):
            day=start.date()+timedelta(days=offset)
            lines.append(f'{day.isoformat()},X,09:00,20:00,Class,T,1')
        schedule=parse_csv(self.with_coverage('\n'.join(lines),'2026-09-29',due.isoformat()).encode())
        candidate={'id':'long-deadline','title':'Essay','due':due.isoformat(),
                   'done':False,'minutes':50,'blocks':[]}
        plan=preview_assignment([],candidate,schedule,start,9,20,120)
        self.assertEqual(plan['horizon'],21)
        self.assertEqual(plan['blocks_by_task']['long-deadline'][0]['date'],
                         (start.date()+timedelta(days=15)).isoformat())
        self.assertEqual(plan['unplaced_by_task']['long-deadline'],0)
