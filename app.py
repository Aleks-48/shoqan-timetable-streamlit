from __future__ import annotations
import hashlib
import html
import json
from datetime import date, datetime, timedelta
from pathlib import Path
import streamlit as st
from assignment_ui import render_assignment
from browser_storage import restore_pending, render_controls, sync_browser
from study_plan import allocate
from ai_ui import render as render_ai
from planner_views import week_grid, render_directory
from schedule import bell_schedule, clock_minutes, day_gaps, location, COLUMNS, DAYS, TEMPLATE, TZ, conflicts, csv_export, expand, ics_export, monday, parse_csv

ROOT = Path(__file__).parent
st.set_page_config(page_title="Shoqan Day · Расписание", page_icon="📘", layout="wide")
restore_pending()
if '_week_pending' in st.session_state:
    st.session_state.week_date=st.session_state.pop('_week_pending')
THEMES = {
    "Светлая": ("#F5F7FC", "#FFFFFF", "#17233D", "#52617C", "#DCE3F0", "#2258D6", "#EDF2FF"),
    "Тёмная": ("#101827", "#1B263B", "#EDF3FF", "#BBC8DF", "#34445F", "#9BBEFF", "#233653"),
    "Тёплая": ("#F7F3EC", "#FFFCF6", "#302C26", "#6F6251", "#E5D9C8", "#87602C", "#F1E7D7"),
}

def e(value):
    return html.escape(str(value))

def style(name):
    bg,panel,text,muted,border,accent,tint = THEMES[name]
    st.markdown(f"""<style>
    .stApp,[data-testid="stHeader"]{{background:{bg};color:{text}}}
    [data-testid="stSidebar"]{{background:{panel};color:{text}}}
    .stApp p,.stApp label,.stApp h1,.stApp h2,.stApp h3,.stApp h4,
    [data-testid="stWidgetLabel"] p,[data-testid="stMetricValue"]{{color:{text}}}
    [data-testid="stCaptionContainer"] p{{color:{muted}}}
    .block-container{{max-width:1180px;padding-top:2.4rem;padding-bottom:3rem}}
    .brand{{font-size:.8rem;letter-spacing:.18em;font-weight:800;color:{accent};margin-bottom:20px}}
    .hero{{background:{panel};border:1px solid {border};border-radius:22px;padding:28px 30px;margin:10px 0 24px}}
    .hero h2{{font-size:2rem;margin:5px 0 12px;line-height:1.25}}
    .eyebrow{{color:{accent};font-size:.8rem;font-weight:700;letter-spacing:.08em}}
    .meta{{color:{muted};font-size:.95rem}}
    .lesson{{display:grid;grid-template-columns:110px 1fr;gap:18px;background:{panel};border:1px solid {border};border-radius:14px;padding:18px 22px;margin:10px 0}}
    .lesson strong{{font-size:1.05rem;color:{text}}}
    .lesson .clock{{font-weight:750;color:{accent};font-size:1rem}}
    .lesson .details{{color:{muted};font-size:.9rem;margin-top:7px}}
    .current{{border-left:5px solid {accent};background:{tint}}}
    .day-label{{font-size:1.1rem;font-weight:750;margin:26px 0 8px}}
    .week-scroll{{overflow-x:auto;margin:16px 0;border:1px solid {border};border-radius:12px}}
    .week-grid{{border-collapse:collapse;min-width:1050px;width:100%;background:{panel};color:{text}}}
    .week-grid th,.week-grid td{{border:1px solid {border};padding:12px;vertical-align:top;min-width:130px}}
    .week-grid th{{background:{tint};font-size:.85rem}}
    .week-grid th:first-child{{min-width:75px}}
    .grid-lesson{{font-size:.85rem;line-height:1.55;padding:8px 0}}
    .stButton>button,.stDownloadButton>button{{border-color:{border};background:{panel};color:{text};border-radius:10px}}
    [data-baseweb="select"]>div,[data-baseweb="input"],[data-baseweb="input"] input,
    [data-baseweb="textarea"],textarea{{background:{panel}!important;color:{text}!important}}
    [data-baseweb="popover"] *,[role="listbox"]{{color:{text};background-color:{panel}}}
    [data-testid="stExpander"]{{background:{panel};border-color:{border}}}
    button[role="tab"] p{{color:{text}}}
    @media(max-width:640px){{.block-container{{padding:1rem}}.stApp h1{{font-size:2rem;line-height:1.2}}.hero{{padding:20px}}.hero h2{{font-size:1.5rem}}.lesson{{grid-template-columns:80px 1fr;padding:14px;gap:12px}}}}
    </style>""", unsafe_allow_html=True)

def lessons(rows,now):
    if rows.empty:
        st.info("Занятий нет. Проверьте группу и выбранную дату или выберите другую неделю.")
        return
    for day,items in rows.groupby("lesson_date",sort=True):
        st.markdown(f'<div class="day-label">{DAYS[day.weekday()]} · {day:%d.%m}' + (" · сегодня" if day==now.date() else "") + '</div>',unsafe_allow_html=True)
        for r in items.to_dict("records"):
            live = day==now.date() and r["start_time"]<=now.strftime("%H:%M")<r["end_time"]
            st.markdown(f'''<article class="lesson {'current' if live else ''}"><div class="clock">{e(r['start_time'])}<br><span class="meta">{e(r['end_time'])}</span></div><div><strong>{e(r['subject'])}</strong><div class="details">Место: {e(location(r))} · {e(r['teacher'] or 'Преподаватель не указан')}</div><div class="details">{e(r['group'])} · {e(r.get('lesson_type') or 'Тип не указан')} · {clock_minutes(r['end_time'])-clock_minutes(r['start_time'])} мин{' · Идёт сейчас' if live else ''}</div></div></article>''',unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### 📘 Shoqan Day")
    st.caption("Твой учебный день")
    choices=list(THEMES)
    initial=st.query_params.get("theme","Светлая")
    theme=st.selectbox("Тема оформления",choices,index=choices.index(initial) if initial in choices else 0)
    st.query_params["theme"]=theme
style(theme)
if "schedule_raw" not in st.session_state:
    st.session_state.schedule_raw=(ROOT/"data/schedule_demo.csv").read_bytes()
    st.session_state.source_name="Демонстрационный набор"
    st.session_state.is_demo=True
if "tasks" not in st.session_state:
    st.session_state.tasks=[]
schedule=parse_csv(st.session_state.schedule_raw)
now=datetime.now(TZ)
today=now.date()
groups=sorted(schedule.group.unique())
with st.sidebar:
    initial=st.query_params.get("group",groups[0])
    group=st.selectbox("Моя группа",groups,index=groups.index(initial) if initial in groups else 0)
    st.query_params["group"]=group
    st.caption("Группа и тема сохраняются в адресе. Добавь страницу в закладки.")
    st.divider()
    st.caption("Источник расписания")
    st.write(st.session_state.source_name)
    st.caption("Время Казахстана · UTC+5")
    st.link_button("Официальное расписание ↗", "https://timetable.kgu.kz/",width="stretch")
    if st.button("Обновить время",width="stretch"):
        st.rerun()
st.markdown('<div class="brand">SHOQAN DAY / STUDENT PLANNER</div>',unsafe_allow_html=True)
st.title("Учёба с понятным планом")
st.caption("Разбери задание с ИИ, проверь требования и найди время для подготовки.")
if st.session_state.is_demo:
    st.info("Демо: занятия и преподаватели вымышлены. Это студенческий проект, не официальное расписание университета.",icon="ℹ️")
else:
    st.caption("Личное расписание · сверьте изменения с официальным источником")
day_tab,task_tab,settings_tab=st.tabs(["Сегодня","Мой план","Настройки"])
with day_tab:
    day_tab,week_tab=st.tabs(["Учебный день","Расписание недели"])
with settings_tab:
    data_tab,ai_tab,search_tab,directory_tab=st.tabs(["Данные","ИИ-импорт","Поиск","Справочник"])
    st.caption("Сохранение на устройстве и перенос полной копии — в разделе «Данные».")
group_schedule=schedule[schedule.group==group]
with day_tab:
    upcoming=expand(group_schedule,today,35)
    snapshot_rows=group_schedule[group_schedule["date"].notna()]
    snapshot_only=not group_schedule["weekday_num"].notna().any() and not snapshot_rows.empty
    snapshot_start=snapshot_rows["date"].min() if snapshot_only else None
    snapshot_end=snapshot_rows["date"].max() if snapshot_only else None
    if snapshot_only:
        st.caption(f"Снимок расписания охватывает {snapshot_start:%d.%m.%Y}–{snapshot_end:%d.%m.%Y}; за пределами периода расписание неизвестно.")
    remaining=upcoming[(upcoming.lesson_date>today)|((upcoming.lesson_date==today)&(upcoming.end_time>now.strftime("%H:%M")))]
    if not remaining.empty:
        nxt=remaining.iloc[0]
        live=nxt.lesson_date==today and nxt.start_time<=now.strftime("%H:%M")
        label="ИДЁТ СЕЙЧАС" if live else "БЛИЖАЙШЕЕ ЗАНЯТИЕ"
        st.markdown(f'''<div class="hero"><div class="eyebrow">{label} · {nxt.lesson_date:%d.%m} · {e(nxt.start_time)}–{e(nxt.end_time)}</div><h2>{e(nxt.subject)}</h2><div class="meta">Место: {e(location(nxt))} · {e(nxt.teacher or 'Преподаватель не указан')}</div></div>''',unsafe_allow_html=True)
    elif snapshot_only and snapshot_end < today+timedelta(days=34):
        st.info(f"В загруженном снимке занятий дальше {snapshot_end:%d.%m.%Y} нет. После этой даты расписание неизвестно; проверьте источник.")
    else:
        st.success("На ближайшие 35 дней занятий нет. Проверьте группу и источник данных.")
    todays=upcoming[upcoming.lesson_date==today]
    a,b,c=st.columns(3)
    a.metric("Занятий сегодня",len(todays))
    minutes=sum((datetime.strptime(r.end_time,"%H:%M")-datetime.strptime(r.start_time,"%H:%M")).seconds//60 for r in todays.itertuples())
    b.metric("Учебное время",f"{minutes//60} ч {minutes%60:02} мин")
    c.metric("Группа",group)
    pending=sorted((t for t in st.session_state.tasks if not t['done']),key=lambda t:t['due'])
    if pending:
        st.subheader("Ближайшие задания")
        for task in pending[:3]:
            st.write(f"{task['title']} · до {task['due']} · {task.get('minutes',50)} мин")
        st.caption("План подготовки и отметка выполнения — в разделе «Мой план».")
    if snapshot_only and not snapshot_start<=today<=snapshot_end:
        st.info("Сегодня вне периода загруженного снимка; расписание на эту дату неизвестно.")
    else:
        lessons(todays,now)
    gaps=day_gaps(todays)
    if gaps:
        st.subheader("Перерывы и окна сегодня")
        for gap in gaps:
            label="Окно" if gap["Минут"]>=50 else "Перерыв"
            st.write(f"{label}: {gap['С']}–{gap['До']} · {gap['Минут']} мин")
        st.caption("Рассчитано между загруженными занятиями. Время на переход между корпусами не учитывается.")
    with st.expander("Расписание звонков · занятия по 50 минут"):
        st.dataframe(bell_schedule(),hide_index=True,width="stretch")
        st.caption("По скриншотам университетского расписания, переданным 29.09.2026. Это справочная сетка, не онлайн-синхронизация. В импортированном расписании сохраняется исходное время.")
    st.caption(f"Обновлено в {now:%H:%M} · {today:%d.%m.%Y}. Для актуального статуса нажмите «Обновить время».")
with week_tab:
    def shift_week(days):
        st.session_state.week_date=(st.session_state.get("week_date") or today)+timedelta(days=days)
    nav1,nav2,nav3=st.columns(3)
    nav1.button("← Предыдущая неделя",on_click=shift_week,args=(-7,),width="stretch")
    nav2.button("Текущая неделя",on_click=lambda: st.session_state.update(week_date=today),width="stretch")
    nav3.button("Следующая неделя →",on_click=shift_week,args=(7,),width="stretch")
    if "week_date" not in st.session_state:
        st.session_state.week_date=today
    selected=st.date_input("Любая дата нужной недели",value=None,key="week_date") or today
    start=monday(selected)
    weekly=expand(group_schedule,start)
    st.subheader(f"{start:%d.%m} — {start+timedelta(days=6):%d.%m.%Y}")
    issues=conflicts(weekly)
    if issues:
        st.warning("Есть пересечения. Уточните их у ответственного за расписание.")
        for issue in issues:
            st.write(issue)
    mode=st.radio("Вид расписания",["Карточки","Таблица","Сетка недели"],horizontal=True)
    if mode=="Карточки":
        lessons(weekly,now)
    elif mode=="Сетка недели":
        if weekly.empty:
            st.info("На выбранную неделю занятий нет.")
        else:
            st.markdown(week_grid(weekly,start),unsafe_allow_html=True)
            st.caption("На узком экране сетку можно прокручивать вбок. Каждая строка — точный интервал занятия; пересекающиеся занятия не скрываются.")
    else:
        st.dataframe(weekly[["lesson_date","start_time","end_time","subject","teacher","room","building","lesson_type"]].rename(columns={"lesson_date":"Дата","start_time":"Начало","end_time":"Конец","subject":"Предмет","teacher":"Преподаватель","room":"Аудитория","building":"Корпус","lesson_type":"Тип"}),hide_index=True,width="stretch")
    d1,d2=st.columns(2)
    d1.download_button("В календарь (.ics)",ics_export(weekly),"shoqan-week.ics","text/calendar",disabled=weekly.empty,width="stretch")
    d2.download_button("Скачать неделю CSV",csv_export(weekly[["lesson_date",*COLUMNS[2:]]].rename(columns={"lesson_date":"date"})),"shoqan-week.csv","text/csv",disabled=weekly.empty,width="stretch")
    st.caption("ICS переносит только выбранную неделю. Это разовый экспорт: изменения в приложении не обновляют календарь автоматически.")
with search_tab:
    st.subheader("Найди нужную пару")
    query=st.text_input("Предмет, преподаватель, аудитория, корпус или группа",placeholder="Например, Базы данных или 203")
    all_groups=st.checkbox("Искать по всем группам")
    st.caption(f"Поиск в неделе {start:%d.%m} — {start+timedelta(days=6):%d.%m}. Неделю можно сменить в разделе «Неделя».")
    source=expand(schedule if all_groups else group_schedule,start)
    if query.strip() and source.empty:
        st.info("На выбранную неделю занятий нет. Выберите другую дату в разделе «Неделя».")
    elif query.strip():
        mask=source[["group","subject","teacher","room","building","lesson_type"]].fillna("").astype(str).agg(" ".join,axis=1).str.contains(query.strip(),case=False,regex=False)
        found=source[mask]
        st.caption(f"Найдено: {len(found)}")
        lessons(found,now)
    else:
        st.info("Введите название предмета, фамилию преподавателя или номер аудитории.")
with task_tab:
    render_assignment(today)
    st.divider()
    st.subheader("Мои задания")
    st.caption("Автосохранение можно включить в Настройки → Данные. Полная копия переносит задания и расписание на другое устройство.")
    with st.form("add_task",clear_on_submit=True):
        title=st.text_input("Что нужно сделать?",max_chars=160)
        task_subject=st.text_input("Предмет задания",max_chars=100)
        task_minutes=st.number_input("Время подготовки, минут",min_value=15,max_value=480,value=50,step=5)
        due=st.date_input("Срок",today,key="task_due")
        added=st.form_submit_button("Добавить задачу")
    if added:
        if not title.strip() or due is None:
            st.warning("Введите название и срок задачи.")
        elif len(st.session_state.tasks)>=100:
            st.error("Максимум 100 задач. Сохраните копию и уберите завершённые.")
        else:
            st.session_state.tasks.append({"id":hashlib.sha256((title+datetime.now().isoformat()).encode()).hexdigest()[:12],"title":title.strip(),"due":due.isoformat(),"done":False,"subject":task_subject.strip(),"minutes":int(task_minutes)})
            st.rerun()
    for task in sorted(st.session_state.tasks,key=lambda x:(x["done"],x["due"])):
        overdue=not task["done"] and date.fromisoformat(task["due"])<today
        task["done"]=st.checkbox(f"{task['title']} · {task['due']}"+(" · просрочено" if overdue else ""),value=task["done"],key="task_"+task["id"])
        if task.get('steps'):
            with st.expander("Этапы: "+task['title']):
                st.text(task['steps'])
        with st.expander('Изменить: '+task['title']):
            with st.form('edit_'+task['id']):
                new_title=st.text_input('Название задания',task['title'],max_chars=160)
                new_subject=st.text_input('Учебный предмет',task.get('subject',''),max_chars=100)
                new_due=st.date_input('Новый срок',date.fromisoformat(task['due']))
                new_minutes=st.number_input('Минут на подготовку',min_value=15,max_value=480,value=task.get('minutes',50),step=5)
                new_steps=st.text_area('Этапы подготовки',task.get('steps',''),max_chars=1500)
                if st.form_submit_button('Сохранить изменения'):
                    if new_title.strip() and new_due:
                        task.update(title=new_title.strip(),subject=new_subject.strip(),due=new_due.isoformat(),minutes=int(new_minutes),steps=new_steps)
                        st.rerun()
                    else:
                        st.warning('Нужны название и срок.')
            if st.button('Удалить это задание',key='delete_'+task['id']):
                st.session_state.tasks=[t for t in st.session_state.tasks if t['id']!=task['id']]
                st.rerun()
    if not st.session_state.tasks:
        st.info("Пока задач нет. Добавьте первое задание или дедлайн.")
    st.subheader("Когда готовиться")
    st.caption("Предложение на 14 дней по срокам заданий. Только занятия выбранной группы; личные дела и работа здесь не учтены. Прошедшее время исключено.")
    pa,pb,pc=st.columns(3)
    begin=pa.number_input("Начинать не раньше, час",min_value=0,max_value=22,value=9,key="plan_begin")
    end=pb.number_input("Заканчивать до, час",min_value=1,max_value=23,value=20,key="plan_end")
    limit=pc.number_input("Подготовка в день, минут",min_value=15,max_value=480,value=120,step=15,key="plan_limit")
    if begin>=end:
        st.warning("Конец учебного дня должен быть позже начала.")
    elif st.session_state.tasks:
        blocks,unplaced=allocate(st.session_state.tasks,group_schedule,now,begin,end,limit)
        if blocks:
            st.dataframe([{k:v for k,v in row.items() if k!='task_id'} for row in blocks],hide_index=True,width="stretch")
            plan_rows=[]
            for row in blocks:
                plan_rows.append({'lesson_date':row['Дата'],'start_time':row['Начало'],'end_time':row['Конец'],'subject':'Подготовка: '+row['Задание'],'teacher':'','room':'','group':group})
            import pandas as pd
            st.download_button("Скачать предложенный план ICS",ics_export(pd.DataFrame(plan_rows)),"study-plan.ics","text/calendar")
        if unplaced:
            if any(item.get('coverage_unknown') for item in unplaced):
                st.warning("Часть задания не размещена: расписание после конца снимка неизвестно. Обновите расписание, чтобы планировать на эти даты.")
            else:
                st.warning("Часть задания не помещается в срок при заданных часах и дневном лимите. Увеличьте доступное время или сократите задачу.")
            st.dataframe([{**{k:v for k,v in item.items() if k!='coverage_unknown'},
                           'Расписание неизвестно':item.get('coverage_unknown',False)} for item in unplaced],
                          hide_index=True,width="stretch")
        st.caption("Блоки подготовки — от 15 до 50 минут; между блоками и занятиями остаётся 10 минут. Время задания задаёте вы; завершённым оно становится только по вашей отметке. Для снимка расписания планируются только даты внутри загруженного периода; дальше покрытие неизвестно.")
    st.download_button("Сохранить задачи JSON",json.dumps(st.session_state.tasks,ensure_ascii=False,indent=2).encode(),"shoqan-tasks.json","application/json")
    restore=st.file_uploader("Восстановить задачи из своей копии",type=["json"])
    if restore and st.button("Заменить список задач из копии"):
        try:
            if restore.size>200_000:
                raise ValueError
            tasks=json.loads(restore.getvalue())
            if not isinstance(tasks,list) or len(tasks)>100:
                raise ValueError
            clean=[]
            for i,t in enumerate(tasks):
                if not isinstance(t,dict) or not isinstance(t.get("title"),str) or not 1<=len(t["title"].strip())<=160 or not isinstance(t.get("done"),bool):
                    raise ValueError
                date.fromisoformat(t["due"])
                if type(t.get('minutes',50)) is not int or not 15<=t.get('minutes',50)<=480 or not isinstance(t.get('subject',''),str) or len(t.get('subject',''))>100 or not isinstance(t.get('steps',''),str) or len(t.get('steps',''))>1500:
                    raise ValueError
                clean.append({"id":f"import_{i}_{hashlib.sha256(restore.getvalue()).hexdigest()[:8]}","title":t["title"].strip(),"due":t["due"],"done":t["done"],"subject":t.get("subject",""),"minutes":t.get("minutes",50),"steps":t.get("steps","")})
            st.session_state.tasks=clean
            for k in list(st.session_state):
                if k.startswith("task_") and k!="task_due":
                    del st.session_state[k]
            st.rerun()
        except (ValueError,TypeError,KeyError,UnicodeDecodeError):
            st.error("Копия повреждена или имеет неподдерживаемый формат. Текущие задачи сохранены.")
    if st.button("Убрать завершённые задачи"):
        st.session_state.tasks=[t for t in st.session_state.tasks if not t["done"]]
        st.rerun()
with data_tab:
    render_controls(theme,group)
    st.divider()
    st.subheader('Расписание ИСР-242уск')
    st.caption('28 сентября — 3 октября 2026. Перенесено вручную из присланных снимков timetable.kgu.kz; группу указал студент. Это снимок одной недели, без автоматических обновлений. Уточняйте замены в официальном расписании.')
    with st.expander('Посмотреть 23 занятия перед загрузкой'):
        real_raw=(ROOT/'data/isr242_2026-09-28.csv').read_bytes()
        st.dataframe(parse_csv(real_raw)[COLUMNS],hide_index=True,width='stretch')
    if st.button('Использовать расписание ИСР-242уск'):
        st.session_state.schedule_raw=real_raw
        st.session_state.source_name='ИСР-242уск · снимок 28.09–03.10.2026'
        st.session_state.is_demo=False
        st.query_params['group']='ИСР-242уск'
        st.session_state._week_pending=date(2026,9,28)
        st.rerun()
    st.caption('Для других групп можно загрузить свой CSV. Доступ к их официальным данным требует авторизации университета; выдуманных расписаний здесь нет.')
    st.divider()
    st.subheader("Импорт расписания")
    st.write("Загрузите CSV из разрешённого источника. Проверьте предпросмотр, затем примените файл. Другие посетители не увидят вашу загрузку.")
    st.download_button("Скачать шаблон",TEMPLATE.encode("utf-8-sig"),"schedule-template.csv","text/csv")
    upload=st.file_uploader("CSV, до 2 МБ",type=["csv"],max_upload_size=2)
    if upload:
        try:
            candidate=parse_csv(upload.getvalue())
            st.success(f"Проверено: {len(candidate)} занятий, групп: {candidate.group.nunique()}")
            st.dataframe(candidate[COLUMNS],hide_index=True,width="stretch")
            for issue in conflicts(expand(candidate,monday(today))):
                st.warning(issue)
            if st.button("Применить расписание",type="primary"):
                st.session_state.schedule_raw=upload.getvalue()
                st.session_state.source_name=upload.name
                st.session_state.is_demo=False
                st.rerun()
        except (ValueError,UnicodeDecodeError) as exc:
            st.error(str(exc))
    st.download_button("Сохранить всё расписание CSV",csv_export(schedule[COLUMNS]),"shoqan-schedule.csv","text/csv")
    with st.expander("Формат файла и ограничения"):
        st.write("Необязательные колонки: building — корпус, lesson_type — тип занятия (например, Л, ЛЗ, СПЗ). Старые CSV без этих колонок тоже поддерживаются.")
        st.write("Одно занятие обычно длится 50 минут. Соседние занятия одного предмета сохраняйте отдельными строками: перерыв между ними не входит в учебное время.")
        st.write("Обязательные колонки: group, start_time, end_time, subject, teacher, room. Преподавателя и аудиторию можно оставить пустыми.")
        st.write("В строке заполните либо weekday (Понедельник…Воскресенье), либо date (YYYY-MM-DD). Время строго ЧЧ:ММ. Конец позже начала. UTF-8 или Windows-1251, разделитель запятая или точка с запятой.")
        st.write("weekday повторяется каждую неделю без каникул. Для точного учебного периода используйте date. Чётные/нечётные недели и автоматические замены пока не поддерживаются.")
        st.write("Пересечения проверяются для одной группы в выбранной неделе. Занятость аудиторий и общие лекции разных групп уточняйте у диспетчера.")
    if not st.session_state.is_demo and st.button("Вернуть демонстрационное расписание"):
        st.session_state.schedule_raw=(ROOT/"data/schedule_demo.csv").read_bytes()
        st.session_state.source_name="Демонстрационный набор"
        st.session_state.is_demo=True
        st.rerun()
    st.divider()
    st.subheader("О проекте")
    st.write("Shoqan Day — идея учебного ИИ-помощника для университета с работающей демонстрацией. ИИ помогает разобрать задание, студент проверяет требования, планировщик находит время вокруг занятий. Для университетской версии предлагаются согласованный источник расписания, казахский интерфейс и сопровождение. Решение о внедрении ещё не принято.")
st.caption("Shoqan Day · Источник и сохранение данных: Настройки → Данные")

with ai_tab:
    render_ai(group,today)
with directory_tab:
    render_directory(schedule,start,today,lessons,now)
sync_browser(theme,group)
