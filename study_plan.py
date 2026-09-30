"""Deterministic placement of confirmed study tasks around classes."""
from datetime import datetime, timedelta, time
from schedule import expand, TZ, clock_minutes

def allocate(tasks, schedule, now, start_hour=9, end_hour=20, daily_limit=120, horizon=14):
    if not 0<=start_hour<end_hour<=24 or not 15<=daily_limit<=480 or not 1<=horizon<=30:
        raise ValueError('Некорректные границы планирования.')
    rows=expand(schedule,now.date(),horizon)
    # Date-only imports are finite snapshots. Within their bounds, missing
    # dates are known to be free; dates beyond them have unknown coverage.
    dated = schedule[schedule["date"].notna()]
    recurring = schedule["weekday_num"].notna().any()
    coverage_start = dated["date"].min() if not dated.empty else None
    coverage_end = dated["date"].max() if not dated.empty else None
    slots=[]
    for offset in range(horizon):
        day=now.date()+timedelta(days=offset)
        if not recurring and coverage_start is not None and not coverage_start <= day <= coverage_end:
            continue
        cursor=start_hour*60
        if offset==0:
            cursor=max(cursor,now.hour*60+now.minute+(1 if now.second or now.microsecond else 0))
        blocked=sorted((max(0,clock_minutes(r.start_time)-10),min(1440,clock_minutes(r.end_time)+10))
                       for r in rows[rows.lesson_date==day].itertuples())
        for begin,end in blocked+[(end_hour*60,end_hour*60)]:
            stop=min(begin,end_hour*60)
            if stop>cursor:
                slots.append([day,cursor,stop])
            cursor=max(cursor,end)
            if cursor>=end_hour*60:
                break
    placed,unplaced,used=[],[],{}
    for task in sorted((t for t in tasks if not t['done']),key=lambda t:(t['due'],t['id'])):
        deadline=datetime.fromisoformat(task['due']).date()
        coverage_unknown = (not recurring and coverage_start is not None and
                            (deadline > coverage_end or (now.date() < coverage_start and deadline >= now.date())))
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
            unplaced.append({'Задание':task['title'],'Не размещено, мин':remaining,'Срок':task['due'],
                             'coverage_unknown': coverage_unknown})
    return placed,unplaced

def validate_assignment(result, source=None):
    if not isinstance(result,dict):
        raise ValueError('Неподдерживаемый ответ ИИ.')
    for field in ['title','subject','due','evidence']:
        if not isinstance(result.get(field),str) or len(result[field])>1500:
            raise ValueError('Некорректное поле задания.')
    if not result['title'].strip() or len(result['title'])>160 or len(result['subject'])>100:
        raise ValueError('Не удалось определить название задания.')
    if result['due']:
        datetime.strptime(result['due'],'%Y-%m-%d')
    if source is not None and (not result['evidence'].strip() or result['evidence'] not in source):
        raise ValueError('ИИ не привёл точную цитату из задания. Уточните текст и повторите.')
    steps=result.get('steps')
    if not isinstance(steps,list) or not 1<=len(steps)<=8 or any(not isinstance(s,str) or not 1<=len(s)<=160 for s in steps):
        raise ValueError('ИИ вернул некорректные этапы.')
    return result
