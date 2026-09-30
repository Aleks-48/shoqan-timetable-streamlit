import unittest
from datetime import date
from pathlib import Path
from schedule import parse_csv, expand, conflicts, ics_export, csv_export, day_gaps, bell_schedule, clock_minutes, coverage_info, date_is_covered

HEADER = 'weekday,date,group,start_time,end_time,subject,teacher,room\n'
ROW = 'Понедельник,,ИС-101,09:00,10:30,Алгоритмы,Преподаватель,101\n'

class ScheduleTests(unittest.TestCase):
    def test_fifty_minute_demo_and_bells(self):
        f=parse_csv(Path('data/schedule_demo.csv').read_bytes())
        self.assertTrue(all(clock_minutes(r.end_time)-clock_minutes(r.start_time)==50 for r in f.itertuples()))
        bells=bell_schedule()
        self.assertEqual((bells[4]['Конец'],bells[5]['Начало']),('13:20','13:40'))
        self.assertEqual(bells[-1]['Конец'],'21:30')

    def test_gaps_merge_overlaps_and_stay_inside_day(self):
        raw=HEADER+ROW+ROW.replace('09:00,10:30,Алгоритмы','09:30,10:00,Вложенное')+ROW.replace('09:00,10:30,Алгоритмы','11:30,12:20,Позднее')
        gaps=day_gaps(expand(parse_csv(raw.encode()),date(2026,9,28)))
        self.assertEqual(len(gaps),1)
        self.assertEqual((gaps[0]['С'],gaps[0]['До'],gaps[0]['Минут']),('10:30','11:30',60))

    def test_optional_location_and_type_survive_export(self):
        raw=HEADER.rstrip()+',building,lesson_type\n'+ROW.rstrip()+',Корпус АТИ,ЛЗ\n'
        f=parse_csv(raw.encode())
        restored=parse_csv(csv_export(f.drop(columns='weekday_num')))
        self.assertEqual(restored.iloc[0].building,'Корпус АТИ')
        self.assertEqual(restored.iloc[0].lesson_type,'ЛЗ')
        self.assertIn('LOCATION:Корпус АТИ · 101',ics_export(expand(f,date(2026,9,28))).decode())
        self.assertEqual(parse_csv((HEADER+ROW).encode()).iloc[0].building,'')

    def test_demo_and_group_counts(self):
        f=parse_csv(Path('data/schedule_demo.csv').read_bytes())
        self.assertEqual(len(f),13)
        self.assertEqual(len(expand(f,date(2026,9,28))),13)

    def test_semicolon_cp1251_and_leading_zero_room(self):
        f=parse_csv((HEADER+ROW.replace(',101\n',',001\n')).replace(',',';').encode('cp1251'))
        self.assertEqual(f.iloc[0].room,'001')

    def test_rejects_invalid_rows_atomically(self):
        cases=[ROW.replace('09:00','9:00'),ROW.replace('10:30','08:59'),ROW.replace('09:00','25:00'),ROW.replace('Понедельник,',',2026-02-30'),ROW.replace('Понедельник','Someday'),ROW.replace('ИС-101',''),ROW.replace('09:00','09:00garbage')]
        for row in cases:
            with self.subTest(row=row),self.assertRaisesRegex(ValueError,'Строка 3'):
                parse_csv((HEADER+ROW+row).encode())

    def test_duplicate_and_empty_and_both_day_fields(self):
        for raw in ['',HEADER,HEADER+ROW+ROW,HEADER+ROW.replace('Понедельник,,','Понедельник,2026-09-28,')]:
            with self.assertRaises(ValueError):parse_csv(raw.encode())

    def test_exact_dates_do_not_repeat(self):
        f=parse_csv((HEADER+ROW.replace('Понедельник,,',',2026-09-28,')).encode())
        self.assertEqual(len(expand(f,date(2026,9,28))),1)
        self.assertTrue(expand(f,date(2026,10,5)).empty)

    def test_explicit_coverage_metadata_validates_and_round_trips(self):
        head=HEADER.rstrip()+',coverage_start,coverage_end\n'
        dated=ROW.replace('Понедельник,,',',2026-09-28,').rstrip()
        row=dated+',2026-09-28,2026-10-03\n'
        second=(dated.replace(',2026-09-28,',',2026-10-03,')
                .replace('09:00,10:30','11:00,12:30')+',2026-09-28,2026-10-03\n')
        frame=parse_csv((head+row+second).encode())
        self.assertEqual(frame.attrs['coverage_start'],date(2026,9,28))
        self.assertEqual(frame.attrs['coverage_end'],date(2026,10,3))
        restored=parse_csv(csv_export(frame.drop(columns='weekday_num')))
        self.assertEqual(restored.attrs,frame.attrs)
        inconsistent=(dated.replace(',2026-09-28,',',2026-10-03,')
                      .replace('09:00,10:30','11:00,12:30')+',2026-09-29,2026-10-03\n')
        invalid=[head+dated+',2026-10-03,2026-09-28\n',
                 head+dated+',2026-09-29,2026-10-03\n',
                 head+row+inconsistent,
                 HEADER.rstrip()+',coverage_start\n'+ROW.rstrip()+',2026-09-28\n']
        for content in invalid:
            with self.subTest(content=content),self.assertRaises(ValueError):
                parse_csv(content.encode())

    def test_mixed_weekday_and_exact_rows_do_not_imply_global_coverage(self):
        dated=ROW.replace('Понедельник,,',',2026-09-29,').replace('09:00,10:30','11:00,12:30')
        frame=parse_csv((HEADER+ROW+dated).encode())
        self.assertEqual(coverage_info(frame)['kind'],'mixed')
        self.assertTrue(date_is_covered(frame,date(2026,9,29)))
        self.assertFalse(date_is_covered(frame,date(2026,9,30)))

    def test_overlap_and_adjacent(self):
        f=parse_csv((HEADER+ROW+ROW.replace('09:00,10:30,Алгоритмы','10:00,11:00,Сети')).encode())
        self.assertEqual(len(conflicts(expand(f,date(2026,9,28)))),1)
        f=parse_csv((HEADER+ROW+ROW.replace('09:00,10:30,Алгоритмы','10:30,11:00,Сети')).encode())
        self.assertFalse(conflicts(expand(f,date(2026,9,28))))

    def test_ics_timezone_escaping_and_line_folding(self):
        raw=HEADER+ROW.replace('Алгоритмы','Я'*110+';END:VEVENT')
        f=parse_csv(raw.encode())
        calendar=ics_export(expand(f,date(2026,9,28))).decode()
        self.assertIn('DTSTART:20260928T040000Z',calendar)
        self.assertIn('DTEND:20260928T053000Z',calendar)
        self.assertEqual(calendar.count('\r\nBEGIN:VEVENT\r\n'),1)
        self.assertIn('\\;END:VEVENT',calendar.replace('\r\n ',''))
        self.assertTrue(all(len(x.encode())<=75 for x in calendar.split('\r\n')))

    def test_export_can_be_imported(self):
        f=parse_csv((HEADER+ROW).encode())
        self.assertEqual(len(parse_csv(csv_export(f.drop(columns='weekday_num')))),1)

    def test_malformed_csv_returns_useful_error(self):
        with self.assertRaisesRegex(ValueError,'структура CSV'):
            parse_csv((HEADER+'"unterminated').encode())

if __name__=='__main__':unittest.main()
