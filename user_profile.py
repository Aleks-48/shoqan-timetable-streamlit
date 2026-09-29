"""Validated portable personal profiles; no shared server database."""
import json
import re
from datetime import date
from schedule import parse_csv, csv_export, COLUMNS

MAX_PROFILE_BYTES = 3_000_000

def clean_tasks(tasks):
    if not isinstance(tasks, list) or len(tasks) > 100:
        raise ValueError('В копии должно быть не более 100 заданий.')
    result, ids = [], set()
    for i, task in enumerate(tasks):
        if not isinstance(task, dict):
            raise ValueError('Некорректное задание.')
        title, due = task.get('title'), task.get('due')
        if not isinstance(title,str) or not 1 <= len(title.strip()) <= 160 or type(task.get('done')) is not bool:
            raise ValueError('Некорректное название или статус задания.')
        if not isinstance(due,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',due):
            raise ValueError('Нужна дата ГГГГ-ММ-ДД.')
        date.fromisoformat(due)
        minutes, subject, steps = task.get('minutes',50),task.get('subject',''),task.get('steps','')
        if type(minutes) is not int or not 15 <= minutes <= 480 or not isinstance(subject,str) or len(subject)>100 or not isinstance(steps,str) or len(steps)>1500:
            raise ValueError('Некорректные параметры задания.')
        ident=task.get('id',f'restored_{i}')
        if not isinstance(ident,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',ident) or ident in ids:
            raise ValueError('Идентификаторы заданий повреждены или повторяются.')
        ids.add(ident)
        result.append(dict(id=ident,title=title.strip(),due=due,done=task['done'],minutes=minutes,subject=subject,steps=steps))
    return result

def decode_profile(raw):
    if not isinstance(raw,str) or len(raw.encode('utf-8')) > MAX_PROFILE_BYTES:
        raise ValueError('Копия больше 3 МБ.')
    try:
        p=json.loads(raw)
        if not isinstance(p,dict) or p.get('version') != 1:
            raise ValueError('Неподдерживаемая версия копии.')
        tasks=clean_tasks(p['tasks'])
        schedule=parse_csv(p['schedule'].encode('utf-8'))
        preferences=p.get('preferences',{})
        begin,end,limit=(preferences.get(k,v) for k,v in [('begin',9),('end',20),('limit',120)])
        if any(type(v) is not int for v in [begin,end,limit]) or not 0<=begin<end<=23 or not 15<=limit<=480:
            raise ValueError('Некорректные часы подготовки.')
        name=p.get('source_name','Моя копия')
        if not isinstance(name,str) or len(name)>250 or type(p.get('is_demo')) is not bool:
            raise ValueError('Некорректный источник расписания.')
        theme=preferences.get('theme','Светлая')
        group=preferences.get('group','')
        if theme not in ['Светлая','Тёмная','Тёплая'] or not isinstance(group,str) or len(group)>200:
            raise ValueError('Некорректные настройки.')
        return dict(version=1,tasks=tasks,schedule=csv_export(schedule[COLUMNS]).decode('utf-8-sig'),source_name=name,is_demo=p['is_demo'],preferences=dict(begin=begin,end=end,limit=limit,theme=theme,group=group))
    except (KeyError,TypeError,UnicodeError,json.JSONDecodeError,AttributeError) as exc:
        raise ValueError('Копия повреждена. Текущие данные не изменены.') from None
