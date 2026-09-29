import unittest
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
        self.assertEqual(len(a.dataframe[0].value),8)

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

if __name__=='__main__':unittest.main()
