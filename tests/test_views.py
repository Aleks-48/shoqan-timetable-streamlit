import unittest
from datetime import date
from schedule import parse_csv, expand
from planner_views import room_snapshot, week_grid

HEADER='date,group,start_time,end_time,subject,teacher,room,building,lesson_type\n'
DATA=HEADER+'2026-09-28,A,08:30,09:20,<script>alert(1)</script>,T,101,East,Л\n2026-09-28,B,08:30,09:20,Second,T,101,West,Л\n2026-09-28,C,08:45,09:35,Third,T,101,East,ЛЗ\n'

class ViewsTests(unittest.TestCase):
    def test_room_boundaries_buildings_and_overlaps(self):
        f=parse_csv(DATA.encode())
        rooms=room_snapshot(f,date(2026,9,28),'09:20','10:10').set_index('Корпус')
        self.assertEqual(rooms.loc['West','По загруженным данным'],'Нет записей на интервал')
        self.assertEqual(rooms.loc['East','По загруженным данным'],'Есть занятия')
        self.assertIn('Third',rooms.loc['East','Занятия'])
        self.assertNotIn('alert',rooms.loc['East','Занятия'])

    def test_grid_escapes_and_keeps_each_lesson(self):
        rows=expand(parse_csv(DATA.encode()),date(2026,9,28))
        grid=week_grid(rows,date(2026,9,28))
        self.assertNotIn('<script>',grid)
        self.assertIn('&lt;script&gt;',grid)
        self.assertIn('08:45',grid)
        self.assertEqual(grid.count('class="grid-lesson"'),3)
        self.assertIn('Воскресенье',grid)

    def test_empty_day_does_not_claim_confirmed_availability(self):
        rooms=room_snapshot(parse_csv(DATA.encode()),date(2026,9,29),'08:30','09:20')
        self.assertEqual(len(rooms),2)
        self.assertTrue((rooms['По загруженным данным']=='Нет записей на интервал').all())
