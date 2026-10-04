import unittest
from unittest.mock import patch
from datetime import date
from pathlib import Path
from streamlit.testing.v1 import AppTest

class AppTests(unittest.TestCase):
    def test_completion_updates_all_views_in_same_run(self):
        from datetime import datetime, timedelta
        from schedule import TZ
        a=self.app()
        tomorrow=datetime.now(TZ).date()+timedelta(days=1)
        next(t for t in a.text_input if t.label=='Что нужно сделать?').set_value('Проверить прогресс')
        next(d for d in a.date_input if d.label=='Срок').set_value(tomorrow)
        next(b for b in a.button if b.label=='Добавить вручную в план').click().run()
        task=a.session_state.tasks[0]
        self.assertTrue(task['blocks'])
        next(d for d in a.date_input if d.label=='Любая дата нужной недели').set_value(tomorrow).run()
        block_ids=[block['id'] for block in task['blocks']]
        for block_id in block_ids:
            a.checkbox(key='plan_block_'+block_id).check().run()
        self.assertTrue(all(block['done'] for block in a.session_state.tasks[0]['blocks']))
        self.assertEqual(next(m.value for m in a.metric if m.label=='Блоков подготовки'),f'{len(block_ids)} / {len(block_ids)}')
        self.assertEqual(a.get('progress')[0].value,100)
        self.assertTrue(any('study-block completed' in m.value for m in a.markdown))
        a.checkbox(key='task_'+task['id']).check().run()
        self.assertEqual(next(m.value for m in a.metric if m.label=='Завершено'),'1')
        for block_id in block_ids:
            a.checkbox(key='plan_block_'+block_id).uncheck().run()
        self.assertEqual(next(m.value for m in a.metric if m.label=='Блоков подготовки'),f'0 / {len(block_ids)}')
        self.assertEqual(a.get('progress')[0].value,0)
        self.assertFalse(any('study-block completed' in m.value for m in a.markdown))
        self.assertFalse(a.exception)

    def test_schedule_conflict_is_visible_and_replan_requires_confirmation(self):
        from datetime import datetime, timedelta
        from schedule import TZ
        from group_profiles import split_group_schedules
        a=self.app()
        tomorrow=(datetime.now(TZ).date()+timedelta(days=1)).isoformat()
        raw=(
            'date,group,start_time,end_time,subject,teacher,room,coverage_start,coverage_end\n'
            f'{tomorrow},A,08:00,09:00,Class A,T,1,{tomorrow},{tomorrow}\n'
            f'{tomorrow},B,10:00,11:00,Class B,T,2,{tomorrow},{tomorrow}\n').encode()
        block={'id':'a'*20,'date':tomorrow,'start_time':'10:10','end_time':'10:50',
               'minutes':40,'done':False}
        task={'id':'conflict_task','title':'Conflict test','due':tomorrow,'done':False,
              'minutes':40,'subject':'X','requirements':'','evidence':'','steps':'',
              'blocks':[dict(block)],'unplaced_minutes':0,'coverage_unknown':False}
        profiles=split_group_schedules(raw,'QA conflict fixture',False,tasks_by_group={'B':[task]})
        a.session_state.group_profiles={**a.session_state.group_profiles,**profiles}
        a.session_state._requested_group_key='A'
        a.run()
        self.assertEqual(next(s.value for s in a.selectbox if s.label=='Моя группа'),'A')
        self.assertEqual(a.session_state.tasks,[])
        self.assertFalse(any('Найдено сохранённых блоков' in error.value for error in a.error))
        next(s for s in a.selectbox if s.label=='Моя группа').select('B').run()
        self.assertTrue(any('конфликт' in error.value.lower() for error in a.error))
        next(b for b in a.button if b.key=='prepare_schedule_replan').click().run()
        self.assertEqual(a.session_state.tasks[0]['blocks'],[block])
        proposal=a.session_state['_schedule_replan_preview']['tasks'][0]['blocks']
        self.assertNotEqual(proposal[0]['start_time'],block['start_time'])
        next(b for b in a.button if b.key=='confirm_schedule_replan').click().run()
        replanned=a.session_state.tasks[0]['blocks']
        self.assertEqual(len(replanned),1)
        self.assertFalse(replanned[0]['done'])
        self.assertFalse(any('Найдено сохранённых блоков' in error.value for error in a.error))
        self.assertFalse(a.exception)

    def test_restored_profile_blocks_are_checked_against_restored_schedule(self):
        from datetime import datetime, timedelta
        import json
        from schedule import TZ
        from user_profile import decode_profile
        a=self.app()
        tomorrow=(datetime.now(TZ).date()+timedelta(days=1)).isoformat()
        schedule=(
            'date,group,start_time,end_time,subject,teacher,room,coverage_start,coverage_end\n'
            f'{tomorrow},X,10:00,11:00,Class,T,1,{tomorrow},{tomorrow}\n')
        task={'id':'restored_conflict','title':'Restored test','due':tomorrow,'done':False,
              'minutes':40,'subject':'X','requirements':'','evidence':'','steps':'',
              'blocks':[{'id':'b'*20,'date':tomorrow,'start_time':'10:10','end_time':'10:50',
                         'minutes':40,'done':False}]}
        profile={'version':1,'tasks':[task],'schedule':schedule,'source_name':'Restored QA fixture',
                 'is_demo':False,'preferences':{'theme':'Светлая','group':'X','begin':9,'end':20,'limit':120}}
        a.session_state['_profile_pending']=decode_profile(json.dumps(profile))
        a.run()
        self.assertEqual(a.session_state.tasks[0]['blocks'],task['blocks'])
        self.assertTrue(any('конфликт' in error.value.lower() for error in a.error))
        self.assertFalse(a.exception)

    def app(self):
        a=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
        self.assertFalse(a.exception)
        return a

    def test_themes_group_and_table(self):
        a=self.app()
        for theme in ['Тёмная','Тёплая','Светлая']:
            next(s for s in a.selectbox if s.label=='Тема оформления').select(theme).run()
            self.assertFalse(a.exception)
        next(s for s in a.selectbox if s.label=='Моя группа').select('ИС-101').run()
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

    def test_directory_and_week_grid(self):
        a=self.app()
        a.radio[0].set_value('Сетка недели').run()
        self.assertFalse(a.exception)
        self.assertTrue(any('week-grid' in m.value and '<table' in m.value for m in a.markdown))
        a.radio(key='directory_mode').set_value('Аудитории').run()
        self.assertFalse(a.exception)
        self.assertTrue(any('По загруженным данным' in d.value.columns for d in a.dataframe))

    def test_literal_search(self):
        a=self.app()
        next(t for t in a.text_input if t.label.startswith('Предмет, преподаватель')).set_value('[').run()
        self.assertFalse(a.exception)
        self.assertTrue(any('Найдено: 0' in c.value for c in a.caption))

    def test_tasks_and_isolation(self):
        a=self.app()
        next(t for t in a.text_input if t.label=='Что нужно сделать?').set_value('Подготовить демо')
        next(b for b in a.button if b.label=='Добавить вручную в план').click().run()
        self.assertEqual(len(a.session_state.tasks),1)
        self.assertEqual(len(self.app().session_state.tasks),0)

    def test_group_switching_keeps_separate_task_plans(self):
        from datetime import datetime, timedelta
        from schedule import TZ
        from group_profiles import split_group_schedules
        a=self.app()
        tomorrow=(datetime.now(TZ).date()+timedelta(days=1)).isoformat()
        raw=(
            'date,group,start_time,end_time,subject,teacher,room,coverage_start,coverage_end\n'
            f'{tomorrow},A,08:00,09:00,Class A,T,1,{tomorrow},{tomorrow}\n'
            f'{tomorrow},B,10:00,11:00,Class B,T,2,{tomorrow},{tomorrow}\n').encode()
        def task(ident,title):
            return {'id':ident,'title':title,'due':tomorrow,'done':False,'minutes':50,'subject':'X',
                    'requirements':'','evidence':'','steps':'','blocks':[],
                    'unplaced_minutes':50,'coverage_unknown':False}
        profiles=split_group_schedules(raw,'Two-group fixture',False,
                                       tasks_by_group={'A':[task('a_task','A plan')],
                                                       'B':[task('b_task','B plan')]})
        a.session_state.group_profiles={**a.session_state.group_profiles,**profiles}
        a.session_state._requested_group_key='A'
        a.run()
        self.assertEqual([t['title'] for t in a.session_state.tasks],['A plan'])
        next(s for s in a.selectbox if s.label=='Моя группа').select('B').run()
        self.assertEqual([t['title'] for t in a.session_state.tasks],['B plan'])
        next(s for s in a.selectbox if s.label=='Моя группа').select('A').run()
        self.assertEqual([t['title'] for t in a.session_state.tasks],['A plan'])

    def test_empty_week_search(self):
        a=self.app()
        a.session_state.schedule_raw=b'date,group,start_time,end_time,subject,teacher,room\n2020-01-01,X,09:00,10:00,Test,T,1\n'
        a.run()
        next(t for t in a.text_input if t.label.startswith('Предмет, преподаватель')).set_value('Test').run()
        self.assertFalse(a.exception)

    def test_real_schedule_and_task_edit(self):
        a=self.app()
        next(b for b in a.button if b.label=='Импортировать архивный снимок ИСР-242уск').click().run()
        self.assertFalse(a.session_state.is_demo)
        self.assertEqual(next(s.value for s in a.selectbox if s.label=='Моя группа'),'ИСР-242уск')
        next(t for t in a.text_input if t.label=='Что нужно сделать?').set_value('Проверка')
        next(b for b in a.button if b.label=='Добавить вручную в план').click().run()
        next(t for t in a.text_input if t.label=='Название задания').set_value('Исправлено')
        next(b for b in a.button if b.label=='Сохранить изменения').click().run()
        self.assertEqual(a.session_state.tasks[0]['title'],'Исправлено')
        self.assertFalse(a.exception)

    def test_ai_without_key_makes_no_requests(self):
        with patch('ai_ui.setting',side_effect=lambda name,default='': default), patch('ai_service.urlopen') as network:
            a=self.app()
            self.assertTrue(next(b for b in a.button if b.label=='Распознать расписание').disabled)
            self.assertTrue(any('готов к подключению' in info.value for info in a.info))
            network.assert_not_called()

    def test_assignment_draft_needs_confirmation(self):
        from datetime import datetime, timedelta
        from schedule import TZ
        tomorrow=datetime.now(TZ).date()+timedelta(days=1)
        response={'title':'Лабораторная SQL','subject':'Базы данных','due':tomorrow.isoformat(),'evidence':'Сдать SQL','requirements':['Сдать SQL-файл','Показать результаты запроса'],'steps':['Изучить условие','Проверить запросы']}
        with patch('assignment_ui.setting',side_effect=lambda name,default='': 'test-key' if name=='GEMINI_API_KEY' else default), patch('assignment_ui.generate',return_value=response):
            a=self.app()
            a.text_area(key='assignment_source').set_value(f'Сдать SQL к {tomorrow:%d.%m.%Y}.')
            a.checkbox(key='assignment_consent').check().run()
            next(b for b in a.button if b.label=='Разобрать задание с ИИ').click().run()
            self.assertEqual(len(a.session_state.tasks),0)
            schedule_before=a.session_state.schedule_raw
            revision=a.session_state.assignment_draft['revision']
            self.assertTrue(any('Предпросмотр плана' in m.value for m in a.markdown))
            next(b for b in a.button if b.label=='Отмена' and b.key=='cancel_assignment_'+revision).click().run()
            self.assertEqual(len(a.session_state.tasks),0)
            self.assertEqual(a.session_state.schedule_raw,schedule_before)
            self.assertNotIn('assignment_draft',a.session_state)
            a.session_state.ai_last_call=0
            next(b for b in a.button if b.label=='Разобрать задание с ИИ').click().run()
            revision=a.session_state.assignment_draft['revision']
            next(t for t in a.text_input if t.key=='assignment_subject_'+revision).set_value('Базы данных · проверено').run()
            next(t for t in a.text_area if t.key=='assignment_requirements_'+revision).set_value('Сдать SQL-файл\nПояснить результат').run()
            editor=next(d for d in a.dataframe if d.key=='assignment_blocks_'+revision)
            self.assertTrue(len(editor.value))
            next(c for c in a.checkbox if c.key=='assignment_checked_'+revision).check().run()
            self.assertEqual(len(a.session_state.tasks),0)
            next(b for b in a.button if b.label=='Подтвердить и добавить').click().run()
            self.assertEqual(len(a.session_state.tasks),1)
            task=a.session_state.tasks[0]
            self.assertEqual(task['subject'],'Базы данных · проверено')
            self.assertEqual(task['requirements'],'Сдать SQL-файл\nПояснить результат')
            self.assertEqual(task['evidence'],'Сдать SQL')
            self.assertTrue(task['blocks'])
            self.assertFalse(a.exception)
            block=task['blocks'][0]
            next(c for c in a.checkbox if c.key=='plan_block_'+block['id']).check().run()
            self.assertTrue(a.session_state.tasks[0]['blocks'][0]['done'])

    def test_malformed_ai_deadline_is_rejected_without_app_exception(self):
        response={'title':'Лабораторная SQL','subject':'Базы данных','due':'2026-1-1',
                  'evidence':'Сдать SQL','requirements':['Сдать SQL-файл'],
                  'steps':['Проверить решение']}
        with patch('assignment_ui.setting',side_effect=lambda name,default='': 'test-key' if name=='GEMINI_API_KEY' else default), \
             patch('assignment_ui.generate',return_value=response):
            a=self.app()
            a.text_area(key='assignment_source').set_value('Сдать SQL к 1 января 2026 года.')
            a.checkbox(key='assignment_consent').check().run()
            next(b for b in a.button if b.label=='Разобрать задание с ИИ').click().run()

            self.assertNotIn('assignment_draft',a.session_state)
            self.assertTrue(any('YYYY-MM-DD' in e.value for e in a.error))
            self.assertFalse(a.exception)

if __name__=='__main__':unittest.main()
