import unittest
from datetime import date
from pathlib import Path
from schedule import parse_csv, expand, conflicts, ics_export, csv_export

HEADER = 'weekday,date,group,start_time,end_time,subject,teacher,room\n'
ROW = 'Понедельник,,ИС-101,09:00,10:30,Алгоритмы,Преподаватель,101\n'

class ScheduleTests(unittest.TestCase):
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

if __name__=='__main__':unittest.main()
