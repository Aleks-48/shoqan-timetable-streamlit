"""Validated portable personal profiles; no shared server database."""
import json
import re
from datetime import date
from schedule import parse_csv, csv_export, COLUMNS
from group_profiles import MAX_IMPORTED_GROUPS, MAX_DEMO_PROFILES

MAX_PROFILE_BYTES = 3_000_000

def clean_tasks(tasks):
    if not isinstance(tasks, list) or len(tasks) > 100:
        raise ValueError('В копии должно быть не более 100 заданий.')
    result, ids, block_ids = [], set(), set()
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
        requirements,evidence=task.get('requirements',''),task.get('evidence','')
        if (type(minutes) is not int or not 15 <= minutes <= 480 or not isinstance(subject,str) or len(subject)>100 or
                not isinstance(steps,str) or len(steps)>1500 or not isinstance(requirements,str) or len(requirements)>1500 or
                not isinstance(evidence,str) or len(evidence)>1500):
            raise ValueError('Некорректные параметры задания.')
        ident=task.get('id',f'restored_{i}')
        if not isinstance(ident,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',ident) or ident in ids:
            raise ValueError('Идентификаторы заданий повреждены или повторяются.')
        ids.add(ident)
        blocks=clean_blocks(task.get('blocks',[]))
        current_block_ids={block['id'] for block in blocks}
        if block_ids.intersection(current_block_ids):
            raise ValueError('Идентификаторы блоков подготовки повторяются между заданиями.')
        block_ids.update(current_block_ids)
        default_unplaced=max(0,minutes-sum(block['minutes'] for block in blocks))
        unplaced=task.get('unplaced_minutes',default_unplaced)
        coverage_unknown=task.get('coverage_unknown',False)
        if type(unplaced) is not int or not 0<=unplaced<=480 or type(coverage_unknown) is not bool:
            raise ValueError('Некорректный остаток плана задания.')
        result.append(dict(id=ident,title=title.strip(),due=due,done=task['done'],minutes=minutes,
                           subject=subject,requirements=requirements,evidence=evidence,steps=steps,
                           blocks=blocks,unplaced_minutes=unplaced,
                           coverage_unknown=coverage_unknown))
    return result


def clean_blocks(blocks):
    if not isinstance(blocks,list) or len(blocks)>120:
        raise ValueError('В задании слишком много блоков подготовки.')
    cleaned=[]
    ids=set()
    for block in blocks:
        if not isinstance(block,dict):
            raise ValueError('Некорректный блок подготовки.')
        ident=block.get('id')
        day=block.get('date')
        start=block.get('start_time')
        end=block.get('end_time')
        minutes=block.get('minutes')
        done=block.get('done')
        if (not isinstance(ident,str) or not re.fullmatch(r'[A-Fa-f0-9]{20}',ident) or ident in ids or
                not isinstance(day,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day) or
                not isinstance(start,str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',start) or
                not isinstance(end,str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',end) or
                type(minutes) is not int or not 15<=minutes<=50 or type(done) is not bool):
            raise ValueError('Некорректный блок подготовки.')
        date.fromisoformat(day)
        start_minute=int(start[:2])*60+int(start[3:])
        end_minute=int(end[:2])*60+int(end[3:])
        if end_minute-start_minute!=minutes:
            raise ValueError('Время блока не совпадает с его длительностью.')
        ids.add(ident)
        cleaned.append(dict(id=ident,date=day,start_time=start,end_time=end,minutes=minutes,done=done))
    return cleaned

def decode_profile(raw):
    if not isinstance(raw,str) or len(raw.encode('utf-8')) > MAX_PROFILE_BYTES:
        raise ValueError('Копия больше 3 МБ.')
    try:
        p=json.loads(raw)
        if not isinstance(p,dict) or p.get('version') not in (1,2):
            raise ValueError('Неподдерживаемая версия копии.')
        if p.get('version') == 2:
            profiles=clean_group_profiles(p.get('profiles'))
            preferences=p.get('preferences',{})
            begin,end,limit=(preferences.get(k,v) for k,v in [('begin',9),('end',20),('limit',120)])
            if any(type(v) is not int for v in [begin,end,limit]) or not 0<=begin<end<=23 or not 15<=limit<=480:
                raise ValueError('Некорректные часы подготовки.')
            theme=preferences.get('theme','Светлая')
            active=p.get('active_group')
            if theme not in ['Светлая','Тёмная','Тёплая'] or not isinstance(active,str) or active not in profiles:
                raise ValueError('Некорректные настройки групп.')
            return dict(version=2,profiles=profiles,active_group=active,
                        preferences=dict(begin=begin,end=end,limit=limit,theme=theme))
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
        return dict(version=1,tasks=tasks,schedule=csv_export(schedule).decode('utf-8-sig'),source_name=name,is_demo=p['is_demo'],preferences=dict(begin=begin,end=end,limit=limit,theme=theme,group=group))
    except (KeyError,TypeError,UnicodeError,json.JSONDecodeError,AttributeError) as exc:
        raise ValueError('Копия повреждена. Текущие данные не изменены.') from None


def clean_group_profiles(profiles):
    """Validate a version-2 collection; each schedule and plan belongs to one group."""
    if (not isinstance(profiles,dict) or not profiles or
            len(profiles)>MAX_IMPORTED_GROUPS+MAX_DEMO_PROFILES):
        raise ValueError('В копии допускается до 10 импортированных групп и до 2 встроенных демо-групп.')
    result={}
    real_groups=set()
    demos=0
    total_bytes=0
    for key,item in profiles.items():
        if (not isinstance(key,str) or not 1<=len(key)<=250 or not isinstance(item,dict) or
                item.get('key')!=key):
            raise ValueError('Некорректный профиль группы.')
        group=item.get('group')
        source=item.get('source_name')
        is_demo=item.get('is_demo')
        raw=item.get('schedule')
        if (not isinstance(group,str) or not 1<=len(group)<=200 or
                not isinstance(source,str) or len(source)>250 or type(is_demo) is not bool or
                not isinstance(raw,str)):
            raise ValueError('Некорректный источник расписания группы.')
        total_bytes+=len(raw.encode('utf-8'))
        frame=parse_csv(raw.encode('utf-8'))
        if set(frame.group.astype(str).unique())!={group}:
            raise ValueError('В каждом профиле должно быть расписание ровно одной группы.')
        if is_demo:
            demos+=1
            if demos>MAX_DEMO_PROFILES:
                raise ValueError('В копии допускается до 2 явно помеченных демо-профилей.')
        else:
            if group in real_groups:
                raise ValueError('Импортированные группы не должны повторяться.')
            real_groups.add(group)
        result[key]=dict(key=key,group=group,
                         schedule=csv_export(frame).decode('utf-8-sig'),
                         source_name=source,is_demo=is_demo,
                         tasks=clean_tasks(item.get('tasks',[])))
    if len(real_groups)>MAX_IMPORTED_GROUPS or total_bytes>MAX_PROFILE_BYTES:
        raise ValueError('Копия превышает лимит в 10 импортированных групп или 3 МБ.')
    return result
