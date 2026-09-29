import unittest
from unittest.mock import patch
from datetime import date
from pathlib import Path
from streamlit.testing.v1 import AppTest

class AppTests(unittest.TestCase):
    def app(self):
        a=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
        self.assertFalse(a.exception)
        return a

    def test_themes_group_and_table(self):
        a=self.app()
        for theme in ['Тёмная','Тёплая','Светлая']:
            a.selectbox[0].select(theme).run()
            self.assertFalse(a.exception)
        a.selectbox[1].select('ИС-101').run()
        a.radio[0].set_value('Таблица').run()
        self.assertFalse(a.exception)
        table=next(d.value for d in a.dataframe if 'Предмет' in d.value.columns)
        self.assertEqual(len(table),8)
        self.assertIn('Корпус',table.columns)

    def test_week_navigation(self):
        from datetime import timedelta
        a=self.app()
        before=a.session_state.week_date
        next(b for b in a.button if b.label=='Следующая неделя →').click().run()
        self.assertEqual(a.session_state.week_date,before+timedelta(days=7))
        next(b for b in a.button if b.label=='← Предыдущая неделя').click().run()
        self.assertEqual(a.session_state.week_date,before)
        self.assertFalse(a.exception)

    def test_literal_search(self):
        a=self.app()
        a.text_input[0].set_value('[').run()
        self.assertFalse(a.exception)
        self.assertTrue(any('Найдено: 0' in c.value for c in a.caption))

    def test_tasks_and_isolation(self):
        a=self.app()
        a.text_input[1].set_value('Подготовить демо')
        next(b for b in a.button if b.label=='Добавить задачу').click().run()
        self.assertEqual(len(a.session_state.tasks),1)
        self.assertEqual(len(self.app().session_state.tasks),0)

    def test_empty_week_search(self):
        a=self.app()
        a.session_state.schedule_raw=b'date,group,start_time,end_time,subject,teacher,room\n2020-01-01,X,09:00,10:00,Test,T,1\n'
        a.run()
        a.text_input[0].set_value('Test').run()
        self.assertFalse(a.exception)

    def test_ai_without_key_makes_no_requests(self):
        with patch('ai_ui.setting',side_effect=lambda name,default='': default), patch('ai_service.urlopen') as network:
            a=self.app()
            self.assertTrue(next(b for b in a.button if b.label=='Распознать расписание').disabled)
            self.assertTrue(any('готов к подключению' in info.value for info in a.info))
            network.assert_not_called()

if __name__=='__main__':unittest.main()
