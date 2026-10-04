"""Deterministic placement of confirmed study tasks around classes."""
import copy
import hashlib
import re
from datetime import datetime, timedelta, date
from schedule import expand, TZ, clock_minutes, coverage_info, date_is_covered


def planning_horizon(tasks, now):
    """Look ahead at least 14 days and far enough for known deadlines, up to 30."""
    days=14
    for task in tasks:
        if task.get('done'):
            continue
        due=date.fromisoformat(task['due'])
        days=max(days,(due-now.date()).days+1)
    return min(30,days)


def allocate(tasks, schedule, now, start_hour=9, end_hour=20, daily_limit=120, horizon=14,
             blocked_blocks=None):
    if not 0<=start_hour<end_hour<=24 or not 15<=daily_limit<=480 or not 1<=horizon<=30:
        raise ValueError('Некорректные границы планирования.')
    rows=expand(schedule,now.date(),horizon)
    # Date-only files without a declared interval cover only dates with rows.
    # Explicit coverage metadata may confirm empty dates between its bounds.
    coverage = coverage_info(schedule)
    slots=[]
    for offset in range(horizon):
        day=now.date()+timedelta(days=offset)
        if not date_is_covered(schedule, day):
            continue
        cursor=start_hour*60
        if offset==0:
            cursor=max(cursor,now.hour*60+now.minute+(1 if now.second or now.microsecond else 0))
        blocked=sorted((max(0,clock_minutes(r.start_time)-10),min(1440,clock_minutes(r.end_time)+10))
                       for r in rows[rows.lesson_date==day].itertuples())
        for block in blocked_blocks or []:
            if date.fromisoformat(block['date']) == day:
                blocked.append((max(0, clock_minutes(block['start_time'])-10),
                                min(1440, clock_minutes(block['end_time'])+10)))
        blocked.sort()
        for begin,end in blocked+[(end_hour*60,end_hour*60)]:
            stop=min(begin,end_hour*60)
            if stop>cursor:
                slots.append([day,cursor,stop])
            cursor=max(cursor,end)
            if cursor>=end_hour*60:
                break
    placed,unplaced=[],[]
    used={}
    for block in blocked_blocks or []:
        day=date.fromisoformat(block['date'])
        used[day]=used.get(day,0)+int(block['minutes'])
    for task in sorted((t for t in tasks if not t['done']),key=lambda t:(t['due'],t['id'])):
        deadline=datetime.fromisoformat(task['due']).date()
        check_end = min(deadline, now.date()+timedelta(days=horizon-1))
        coverage_unknown = (coverage["kind"] != "recurring" and check_end >= now.date() and
                            any(not date_is_covered(schedule, now.date()+timedelta(days=day_offset))
                                for day_offset in range((check_end-now.date()).days+1)))
        remaining=int(task.get('minutes',50))
        for slot in slots:
            day,begin,end=slot
            if day>deadline or remaining<=0:
                break
            capacity=daily_limit-used.get(day,0)
            while end-slot[1]>=15 and capacity>=15 and remaining>0:
                duration=min(50,remaining,end-slot[1],capacity)
                # Avoid stranding a tail that cannot form a valid 15-minute block.
                tail=remaining-duration
                if 0 < tail < 15 and duration-(15-tail) >= 15:
                    duration -= 15-tail
                if duration<15:
                    break
                begin=slot[1]
                placed.append({'task_id':task['id'],'Дата':day,'Начало':f'{begin//60:02}:{begin%60:02}',
                               'Конец':f'{(begin+duration)//60:02}:{(begin+duration)%60:02}',
                               'Предмет':task.get('subject',''),'Задание':task['title'],'Минут':duration})
                remaining-=duration
                used[day]=used.get(day,0)+duration
                capacity-=duration
                slot[1]+=duration+10
        if remaining:
            unplaced.append({'task_id':task['id'],'Задание':task['title'],'Не размещено, мин':remaining,'Срок':task['due'],
                             'coverage_unknown': coverage_unknown})
    return placed,unplaced


def preview_assignment(tasks, candidate, schedule, now, start_hour=9, end_hour=20,
                       daily_limit=120, candidate_minutes=None, additional_blocked=None):
    """Calculate new blocks without mutating tasks or the supplied candidate."""
    candidate_id=candidate['id']
    if any(task['id']==candidate_id for task in tasks):
        raise ValueError('Это задание уже добавлено.')

    fixed=list(additional_blocked or [])
    work=[]
    for task in tasks:
        blocks=task.get('blocks', [])
        fixed.extend(blocks)
        if task.get('done'):
            continue
        scheduled=sum(int(block['minutes']) for block in blocks)
        default_remaining=max(0, int(task.get('minutes',50))-scheduled)
        remaining=int(task.get('unplaced_minutes', default_remaining))
        if remaining:
            work.append({**task, 'minutes':remaining})

    candidate_work=dict(candidate)
    if candidate_minutes is not None:
        candidate_work['minutes']=candidate_minutes
    work.append(candidate_work)
    horizon=planning_horizon(work,now)
    rows,missed=allocate(work,schedule,now,start_hour,end_hour,daily_limit,
                         horizon=horizon,blocked_blocks=fixed)
    blocks_by_task={task['id']:[] for task in work}
    for row in rows:
        task_id=row['task_id']
        day=row['Дата'].isoformat()
        start=row['Начало']
        end=row['Конец']
        block_id=hashlib.sha256(f'{task_id}|{day}|{start}|{end}'.encode()).hexdigest()[:20]
        blocks_by_task[task_id].append({
            'id':block_id, 'date':day, 'start_time':start, 'end_time':end,
            'minutes':row['Минут'], 'done':False,
        })
    for blocks in blocks_by_task.values():
        blocks.sort(key=lambda block:(block['date'],block['start_time']))
    unplaced_by_task={task['id']:0 for task in work}
    coverage_unknown_by_task={task['id']:False for task in work}
    for item in missed:
        task_id=item['task_id']
        unplaced_by_task[task_id]=item['Не размещено, мин']
        coverage_unknown_by_task[task_id]=item.get('coverage_unknown',False)
    return {
        'blocks_by_task':blocks_by_task,
        'unplaced_by_task':unplaced_by_task,
        'coverage_unknown_by_task':coverage_unknown_by_task,
        'horizon':horizon,
    }


def edit_candidate_blocks(preview, candidate, edited_rows, existing_tasks, schedule, now,
                          start_hour=9, end_hour=20, daily_limit=120):
    """Validate and apply a student's editable draft blocks to an uncommitted preview."""
    task_id = candidate['id']
    if not isinstance(edited_rows, list) or len(edited_rows) > 120:
        raise ValueError('В черновике допускается не более 120 блоков подготовки.')
    deadline = date.fromisoformat(candidate['due'])
    horizon=preview.get('horizon',14)
    if type(horizon) is not int or not 1<=horizon<=30:
        raise ValueError('Некорректный горизонт планирования.')
    horizon_end=now.date()+timedelta(days=horizon-1)
    start_bound, end_bound = int(start_hour) * 60, int(end_hour) * 60
    fixed = [block for task in existing_tasks for block in task.get('blocks', [])]
    for other_id, blocks in preview['blocks_by_task'].items():
        if other_id != task_id:
            fixed.extend(blocks)
    fixed_minutes_by_day = {}
    for block in fixed:
        day = date.fromisoformat(block['date'])
        fixed_minutes_by_day[day] = fixed_minutes_by_day.get(day, 0) + int(block['minutes'])

    rows = []
    total = 0
    for item in edited_rows:
        if not isinstance(item, dict):
            raise ValueError('Проверьте строки черновика плана.')
        raw_day = item.get('date')
        if isinstance(raw_day, datetime):
            day = raw_day.date()
        elif isinstance(raw_day, date):
            day = raw_day
        elif isinstance(raw_day, str):
            try:
                day = date.fromisoformat(raw_day)
            except ValueError:
                raise ValueError('Дата блока должна быть в формате ГГГГ-ММ-ДД.') from None
        else:
            raise ValueError('Укажите дату каждого блока.')
        raw_start = item.get('start_time')
        if hasattr(raw_start, 'strftime'):
            start_text = raw_start.strftime('%H:%M')
        elif isinstance(raw_start, str):
            start_text = raw_start.strip()
        else:
            raise ValueError('Укажите время начала каждого блока в формате ЧЧ:ММ.')
        if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', start_text):
            raise ValueError('Время начала должно быть в формате ЧЧ:ММ.')
        raw_minutes = item.get('minutes')
        if isinstance(raw_minutes, bool):
            raise ValueError('Длительность блока должна быть от 15 до 50 минут.')
        try:
            minutes = int(raw_minutes)
        except (TypeError, ValueError, OverflowError):
            raise ValueError('Длительность блока должна быть от 15 до 50 минут.') from None
        if minutes != raw_minutes or not 15 <= minutes <= 50:
            raise ValueError('Длительность блока должна быть от 15 до 50 минут.')
        start = clock_minutes(start_text)
        end = start + minutes
        if day < now.date() or day > deadline or day > horizon_end:
            raise ValueError('Блок должен быть в пределах текущего горизонта планирования и срока задания.')
        if not date_is_covered(schedule, day):
            raise ValueError(f'Дата {day.isoformat()} не покрыта источником расписания и не считается свободной.')
        if start < start_bound or end > end_bound:
            raise ValueError('Блок выходит за выбранные часы подготовки.')
        current_minute=now.hour*60+now.minute+(1 if now.second or now.microsecond else 0)
        if day == now.date() and start < current_minute:
            raise ValueError('Нельзя запланировать блок на уже прошедшее сегодня время.')
        day_classes = expand(schedule, day, 1)
        for lesson in day_classes.itertuples():
            lesson_start = clock_minutes(lesson.start_time)
            lesson_end = clock_minutes(lesson.end_time)
            if start < min(1440, lesson_end + 10) and end > max(0, lesson_start - 10):
                raise ValueError(f'Блок пересекается с занятием «{lesson.subject}» или десятиминутным переходом.')
        total += minutes
        rows.append({'date': day.isoformat(), 'start_time': start_text, 'end_time': f'{end//60:02}:{end%60:02}',
                     'minutes': minutes, 'done': False})

    if total > int(candidate.get('minutes', 0)):
        raise ValueError('Суммарное время блоков больше указанного объёма подготовки.')
    rows.sort(key=lambda block: (block['date'], block['start_time']))
    used_by_day = dict(fixed_minutes_by_day)
    previous = []
    for block in rows:
        day = date.fromisoformat(block['date'])
        begin = clock_minutes(block['start_time'])
        finish = clock_minutes(block['end_time'])
        for other in fixed:
            if other['date'] != block['date']:
                continue
            other_begin, other_end = clock_minutes(other['start_time']), clock_minutes(other['end_time'])
            if begin < other_end + 10 and finish > other_begin - 10:
                raise ValueError('Блок пересекается с уже сохранённым или предложенным блоком подготовки.')
        for other_day, other_begin, other_end in previous:
            if other_day == day and begin < other_end + 10 and finish > other_begin - 10:
                raise ValueError('Блоки должны быть разделены минимум десятью минутами.')
        used_by_day[day] = used_by_day.get(day, 0) + block['minutes']
        if used_by_day[day] > daily_limit:
            raise ValueError('Блоки превышают дневной лимит подготовки.')
        previous.append((day, begin, finish))
        block['id'] = hashlib.sha256(
            f"{task_id}|{block['date']}|{block['start_time']}|{block['end_time']}".encode()
        ).hexdigest()[:20]

    preview['blocks_by_task'][task_id] = rows
    preview['unplaced_by_task'][task_id] = int(candidate.get('minutes', 0)) - total
    return preview


def commit_assignment(tasks, candidate, preview):
    """Persist an accepted proposal and retain existing planned/completed blocks."""
    if any(task['id']==candidate['id'] for task in tasks):
        raise ValueError('Это задание уже добавлено.')
    committed=[]
    for original in tasks:
        task=copy.deepcopy(original)
        task_id=task['id']
        task.setdefault('blocks',[])
        task['blocks'].extend(preview['blocks_by_task'].get(task_id,[]))
        if task_id in preview['unplaced_by_task']:
            task['unplaced_minutes']=preview['unplaced_by_task'][task_id]
            task['coverage_unknown']=preview['coverage_unknown_by_task'][task_id]
        committed.append(task)
    task=copy.deepcopy(candidate)
    task['blocks']=copy.deepcopy(task.get('blocks',[]))+copy.deepcopy(
        preview['blocks_by_task'].get(task['id'],[]))
    task['unplaced_minutes']=preview['unplaced_by_task'].get(task['id'],task['minutes'])
    task['coverage_unknown']=preview['coverage_unknown_by_task'].get(task['id'],False)
    committed.append(task)
    return committed


def validate_saved_blocks(tasks, schedule, buffer_minutes=10):
    """Report saved blocks that no longer fit the selected schedule or coverage."""
    issues=[]
    for task in tasks:
        for block in task.get('blocks',[]):
            day=date.fromisoformat(block['date'])
            block_start=clock_minutes(block['start_time'])
            block_end=clock_minutes(block['end_time'])
            common={
                'task_id':task['id'], 'task_title':task['title'],
                'block_id':block['id'], 'date':block['date'],
                'start_time':block['start_time'], 'end_time':block['end_time'],
                'done':bool(block.get('done',False)),
            }
            if not date_is_covered(schedule,day):
                issues.append({**common,'kind':'coverage',
                    'reason':'Дата блока не входит в подтверждённое покрытие текущего расписания.'})
            rows=expand(schedule,day,1)
            for lesson in rows.to_dict('records'):
                lesson_start=clock_minutes(lesson['start_time'])
                lesson_end=clock_minutes(lesson['end_time'])
                guarded_start=max(0,lesson_start-buffer_minutes)
                guarded_end=min(1440,lesson_end+buffer_minutes)
                if block_start < lesson_end and block_end > lesson_start:
                    reason=(f"Пересекается с парой «{lesson['subject']}» "
                            f"{lesson['start_time']}–{lesson['end_time']}.")
                    issues.append({**common,'kind':'class_overlap','reason':reason,
                        'lesson_subject':lesson['subject'],'lesson_start':lesson['start_time'],
                        'lesson_end':lesson['end_time']})
                elif block_start < guarded_end and block_end > guarded_start:
                    reason=(f"Попадает в 10-минутный интервал рядом с парой «{lesson['subject']}» "
                            f"{lesson['start_time']}–{lesson['end_time']}.")
                    issues.append({**common,'kind':'class_buffer','reason':reason,
                        'lesson_subject':lesson['subject'],'lesson_start':lesson['start_time'],
                        'lesson_end':lesson['end_time']})
    return issues


def preview_replan(tasks, schedule, now, start_hour=9, end_hour=20,
                   daily_limit=120, horizon=None):
    """Build a replacement plan, preserving completed blocks and completed tasks."""
    working=copy.deepcopy(tasks)
    fixed=[]
    work=[]
    for task in working:
        original_blocks=task.get('blocks',[])
        keep=(original_blocks if task.get('done') else
              [block for block in original_blocks if block.get('done')])
        task['blocks']=copy.deepcopy(keep)
        fixed.extend(copy.deepcopy(keep))
        if task.get('done'):
            continue
        remaining=max(0,int(task.get('minutes',50))-
                      sum(int(block['minutes']) for block in keep))
        if remaining:
            work.append({**task,'minutes':remaining})

    if horizon is None:
        horizon=planning_horizon(work,now)
    placed,missed=allocate(work,schedule,now,start_hour,end_hour,daily_limit,
                           horizon,blocked_blocks=fixed)
    blocks_by_task={task['id']:[] for task in work}
    for row in placed:
        task_id=row['task_id']
        day=row['Дата'].isoformat()
        start=row['Начало']
        end=row['Конец']
        block_id=hashlib.sha256(f'{task_id}|{day}|{start}|{end}'.encode()).hexdigest()[:20]
        blocks_by_task[task_id].append({
            'id':block_id,'date':day,'start_time':start,'end_time':end,
            'minutes':row['Минут'],'done':False,
        })
    unplaced_by_task={task['id']:0 for task in work}
    coverage_unknown_by_task={task['id']:False for task in work}
    for item in missed:
        task_id=item['task_id']
        unplaced_by_task[task_id]=item['Не размещено, мин']
        coverage_unknown_by_task[task_id]=item.get('coverage_unknown',False)

    for task in working:
        task_id=task['id']
        if task.get('done'):
            continue
        task['blocks'].extend(blocks_by_task.get(task_id,[]))
        task['blocks'].sort(key=lambda block:(block['date'],block['start_time']))
        task['unplaced_minutes']=unplaced_by_task.get(task_id,0)
        task['coverage_unknown']=coverage_unknown_by_task.get(task_id,False)
    return {'tasks':working,'blocks_by_task':blocks_by_task,
            'unplaced_by_task':unplaced_by_task,
            'coverage_unknown_by_task':coverage_unknown_by_task,'horizon':horizon}

def validate_assignment(result, source=None):
    if not isinstance(result,dict):
        raise ValueError('Неподдерживаемый ответ ИИ.')
    for field in ['title','subject','due','evidence']:
        if not isinstance(result.get(field),str) or len(result[field])>1500:
            raise ValueError('Некорректное поле задания.')
    if not result['title'].strip() or len(result['title'])>160 or len(result['subject'])>100:
        raise ValueError('Не удалось определить название задания.')
    if result['due']:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',result['due']):
            raise ValueError('Дедлайн ИИ должен быть в формате YYYY-MM-DD.')
        try:
            date.fromisoformat(result['due'])
        except ValueError:
            raise ValueError('Дедлайн ИИ должен быть существующей датой YYYY-MM-DD.') from None
    if source is not None and (not result['evidence'].strip() or result['evidence'] not in source):
        raise ValueError('ИИ не привёл точную цитату из задания. Уточните текст и повторите.')
    steps=result.get('steps')
    if not isinstance(steps,list) or not 1<=len(steps)<=8 or any(not isinstance(s,str) or not 1<=len(s)<=160 for s in steps):
        raise ValueError('ИИ вернул некорректные этапы.')
    requirements=result.get('requirements',[])
    if not isinstance(requirements,list) or len(requirements)>8 or any(
            not isinstance(item,str) or not 1<=len(item.strip())<=200 for item in requirements):
        raise ValueError('ИИ вернул некорректный список требований.')
    result['requirements']=[item.strip() for item in requirements]
    return result
