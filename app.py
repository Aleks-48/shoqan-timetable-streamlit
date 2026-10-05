from __future__ import annotations
import hashlib
import html
import json
from datetime import date, datetime, timedelta
from pathlib import Path
import pandas as pd
import streamlit as st
from assignment_ui import render_assignment
from browser_storage import restore_pending, render_controls, sync_browser
from study_plan import preview_assignment, commit_assignment, validate_saved_blocks, preview_replan
from ai_ui import render as render_ai
from planner_views import week_grid, render_directory, study_rows
from user_profile import clean_tasks
from schedule import bell_schedule, clock_minutes, day_gaps, location, COLUMNS, DAYS, TEMPLATE, TZ, conflicts, csv_export, expand, ics_export, monday, parse_csv, coverage_info, date_is_covered
from group_profiles import (initialize_group_profiles, remember_active_profile, load_group_profile,
                            set_active_tasks, split_group_schedules,
                            import_schedules_into_state,
                            add_demo_schedule, MAX_IMPORTED_GROUPS)
from schedule_proposal_ui import render_schedule_proposal

ROOT = Path(__file__).parent
st.set_page_config(page_title="Shoqan Day · Расписание", page_icon="📘", layout="wide")
restore_pending()
if '_week_pending' in st.session_state:
    st.session_state.week_date=st.session_state.pop('_week_pending')
THEMES = {
    "Светлая": ("#F6F9FC", "#FFFFFF", "#18324E", "#60748A", "#E0E8F0", "#246BC4", "#EDF5FE", "#DDF5EC"),
    "Тёмная": ("#101827", "#1B263B", "#EDF3FF", "#BBC8DF", "#34445F", "#9BBEFF", "#233653", "#24483F"),
    "Тёплая": ("#F7F3EC", "#FFFCF6", "#302C26", "#6F6251", "#E5D9C8", "#87602C", "#F1E7D7", "#E7F0DE"),
}

def e(value):
    return html.escape(str(value))

def style(name):
    bg,panel,text,muted,border,accent,tint,mint = THEMES[name]
    st.markdown(f"""<style>
    :root{{--sd-bg:{bg};--sd-panel:{panel};--sd-text:{text};--sd-muted:{muted};--sd-border:{border};--sd-blue:{accent};--sd-blue-soft:{tint};--sd-mint:{mint}}}
    .stApp,[data-testid="stHeader"]{{background:{bg};color:{text}}}
    [data-testid="stSidebar"]{{background:#164B7A;color:#F8FBFF}}
    [data-testid="stSidebar"] p,[data-testid="stSidebar"] label,[data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3,[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p{{color:#F3F8FF}}
    [data-testid="stSidebar"] [data-baseweb="select"]>div,[data-testid="stSidebar"] [data-baseweb="input"]{{background:#FFFFFF;color:#18324E}}
    .stApp p,.stApp label,.stApp h1,.stApp h2,.stApp h3,.stApp h4,
    [data-testid="stWidgetLabel"] p,[data-testid="stMetricValue"]{{color:{text}}}
    [data-testid="stCaptionContainer"] p{{color:{muted}}}
    .block-container{{max-width:1180px;padding:1.6rem 2rem 3rem}}
    .brand{{font-size:.74rem;letter-spacing:.16em;font-weight:800;color:{accent};margin:0 0 12px}}
    .hero{{background:{panel};border:1px solid {border};border-left:5px solid {accent};border-radius:16px;padding:24px 26px;margin:10px 0 22px;box-shadow:0 3px 14px rgba(23,55,88,.04)}}
    .hero h2{{font-size:1.8rem;margin:5px 0 10px;line-height:1.25}}
    .eyebrow{{color:{accent};font-size:.76rem;font-weight:750;letter-spacing:.07em}}
    .meta{{color:{muted};font-size:.95rem}}
    .lesson{{display:grid;grid-template-columns:96px 1fr;gap:16px;background:{panel};border:1px solid {border};border-left:4px solid #B9D8F4;border-radius:12px;padding:16px 18px;margin:9px 0;box-shadow:0 2px 8px rgba(23,55,88,.035)}}
    .lesson strong{{font-size:1.02rem;color:{text}}}
    .lesson .clock{{font-weight:750;color:{accent};font-size:.96rem}}
    .lesson .details{{color:{muted};font-size:.88rem;margin-top:6px}}
    .current,.class-block{{border-left-color:{accent};background:{tint}}}
    .study-block{{border-left-color:#28A883!important;background:{mint}!important}}
    .completed{{opacity:.72}}
    .day-label{{font-size:1rem;font-weight:750;margin:24px 0 7px;color:{text}}}
    .week-scroll{{overflow-x:auto;margin:14px 0;border:1px solid {border};border-radius:12px}}
    .week-grid{{border-collapse:collapse;min-width:1050px;width:100%;background:{panel};color:{text}}}
    .week-grid th,.week-grid td{{border:1px solid {border};padding:10px;vertical-align:top;min-width:130px}}
    .week-grid th{{background:{tint};font-size:.82rem}}
    .week-grid th:first-child{{min-width:75px}}
    .grid-lesson{{font-size:.82rem;line-height:1.5;padding:8px;border-left:3px solid #B9D8F4;background:{tint};border-radius:6px;margin:3px 0}}
    .grid-lesson.study-block{{border-left-color:#28A883;background:{mint}!important}}
    .week-mobile{{display:none}}
    .mobile-day{{background:{panel};border:1px solid {border};border-radius:12px;padding:12px;margin:9px 0}}
    .mobile-day h4{{font-size:.95rem;margin:0 0 8px}}
    .mobile-event{{display:grid;grid-template-columns:95px 1fr;gap:10px;border:1px solid {border};border-left:4px solid {accent};border-radius:9px;padding:10px;margin:7px 0;background:{tint}}}
    .mobile-event.study-block{{border-left-color:#28A883;background:{mint}!important}}
    .mobile-event time{{font-size:.83rem;font-weight:750;color:{accent}}}
    .mobile-event div span{{display:block;font-size:.78rem;color:{muted};margin-top:3px}}
    [data-testid="stMetric"]{{background:{panel};border:1px solid {border};border-radius:12px;padding:12px 14px}}
    .stButton>button,.stDownloadButton>button{{border:1px solid {border};background:{panel};color:{text};border-radius:9px;min-height:2.7rem}}
    .stButton>button:hover,.stDownloadButton>button:hover{{border-color:{accent};color:{accent}}}
    [data-testid="stBaseButton-primary"]{{background:{accent};border-color:{accent};color:#FFFFFF}}
    [data-baseweb="select"]>div,[data-baseweb="input"],[data-baseweb="input"] input,
    [data-baseweb="textarea"],textarea{{background:{panel}!important;color:{text}!important}}
    [data-baseweb="popover"] *,[role="listbox"]{{color:{text};background-color:{panel}}}
    [data-testid="stExpander"]{{background:{panel};border-color:{border}}}
    button[role="tab"] p{{color:{text}}}
    @media(max-width:760px){{.block-container{{padding:.9rem .85rem 2rem}}.stApp h1{{font-size:1.8rem;line-height:1.18}}.hero{{padding:18px;margin:8px 0 17px}}.hero h2{{font-size:1.35rem}}.lesson{{grid-template-columns:76px minmax(0,1fr);padding:12px;gap:10px}}.week-scroll{{display:none}}.week-mobile{{display:block}}.mobile-event{{grid-template-columns:82px minmax(0,1fr);gap:8px;padding:9px}}[data-testid="stHorizontalBlock"]{{gap:.5rem}}[data-testid="stMetric"]{{padding:9px}}}}
    </style>""", unsafe_allow_html=True)

def lessons(rows,now):
    if rows.empty:
        st.info("Занятий нет. Проверьте группу и выбранную дату или выберите другую неделю.")
        return
    for day,items in rows.groupby("lesson_date",sort=True):
        st.markdown(f'<div class="day-label">{DAYS[day.weekday()]} · {day:%d.%m}' + (" · сегодня" if day==now.date() else "") + '</div>',unsafe_allow_html=True)
        for r in items.to_dict("records"):
            live = day==now.date() and r["start_time"]<=now.strftime("%H:%M")<r["end_time"]
            study=bool(r.get('is_study',False))
            completed=bool(r.get('done',False))
            card_class='study-block' if study else 'current' if live else ''
            place='Блок подготовки' if study else f"Место: {e(location(r))} · {e(r['teacher'] or 'Преподаватель не указан')}"
            detail=f"{r['start_time']}–{r['end_time']} · {clock_minutes(r['end_time'])-clock_minutes(r['start_time'])} мин" if study else f"{e(r['group'])} · {e(r.get('lesson_type') or 'Тип не указан')} · {clock_minutes(r['end_time'])-clock_minutes(r['start_time'])} мин"
            state=' · Выполнено' if study and completed else ' · Идёт сейчас' if live else ''
            st.markdown(f'''<article class="lesson {card_class}{' completed' if completed else ''}"><div class="clock">{e(r['start_time'])}<br><span class="meta">{e(r['end_time'])}</span></div><div><strong>{e(r['subject'])}</strong><div class="details">{place}</div><div class="details">{detail}{state}</div></div></article>''',unsafe_allow_html=True)


def calendar_with_study(rows,tasks,group,start,days=7):
    events=rows.copy()
    events['is_study']=False
    events['done']=False
    prepared=study_rows(tasks,group,start,days)
    if not prepared.empty:
        events=pd.concat([events,prepared],ignore_index=True,sort=False)
    return events.sort_values(['lesson_date','start_time','end_time','is_study'],kind='stable').reset_index(drop=True)


def block_progress(task):
    blocks=task.get('blocks',[])
    total=sum(block['minutes'] for block in blocks)
    done=sum(block['minutes'] for block in blocks if block['done'])
    if total:
        st.progress(done/total,text=f'Блоки подготовки: выполнено {done} из {total} мин')
    if task.get('unplaced_minutes',0):
        note='; расписание не покрывает нужные даты' if task.get('coverage_unknown') else ''
        st.warning(f"Не размещено {task['unplaced_minutes']} мин до срока{note}.")


def update_task_completion(task_id):
    """Apply widget changes before the next full render, including its summaries."""
    for task in st.session_state.tasks:
        if task['id'] == task_id:
            task['done'] = st.session_state['task_' + task_id]
            return


def update_block_completion(task_id, block_id):
    """Keep the calendar, progress bar, and saved state current on one click."""
    for task in st.session_state.tasks:
        if task['id'] == task_id:
            for block in task.get('blocks', []):
                if block['id'] == block_id:
                    block['done'] = st.session_state['plan_block_' + block_id]
                    return


def saved_plan_revision(tasks, schedule_raw, group, start_hour, end_hour, daily_limit):
    payload={
        'tasks':tasks,
        'schedule_sha256':hashlib.sha256(schedule_raw).hexdigest(),
        'group':group,
        'start_hour':int(start_hour),
        'end_hour':int(end_hour),
        'daily_limit':int(daily_limit),
    }
    return hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def import_group_schedules(raw, source_name):
    """Store an explicit, previewed CSV import as isolated per-group profiles."""
    return import_schedules_into_state(st.session_state,raw,source_name)

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
initialize_group_profiles(
    st.session_state,(ROOT/"data/schedule_demo.csv").read_bytes(),
    preferred_group=st.query_params.get("group",""))
schedule=parse_csv(st.session_state.schedule_raw)
now=datetime.now(TZ)
today=now.date()
with st.sidebar:
    def profile_label(key):
        item=st.session_state.group_profiles[key]
        return item["group"] if key==item["group"] else f"{item['group']} · демо"
    profile_keys=sorted(st.session_state.group_profiles,key=profile_label)
    profile_key=st.selectbox("Моя группа",profile_keys,key="active_group_selector",format_func=profile_label)
    if profile_key!=st.session_state.get("_active_group_key"):
        remember_active_profile(st.session_state)
        load_group_profile(st.session_state,profile_key)
        schedule=parse_csv(st.session_state.schedule_raw)
    st.query_params["group"]=profile_key
    active_profile=st.session_state.group_profiles[profile_key]
    group=active_profile["group"]
    st.caption("Группа и тема сохраняются в адресе. Добавь страницу в закладки.")
    st.divider()
    st.caption("Источник расписания")
    st.write(st.session_state.source_name)
    if st.session_state.is_demo:
        st.caption("Синтетический демо-набор")
    else:
        st.caption(f"Импортировано групп: {sum(not p['is_demo'] for p in st.session_state.group_profiles.values())}/{MAX_IMPORTED_GROUPS}")
    st.caption("Время Казахстана · UTC+5")
    st.link_button("Официальное расписание ↗", "https://timetable.kgu.kz/",width="stretch")
    if st.button("Обновить время",width="stretch"):
        st.rerun()
st.markdown('<div class="brand">SHOQAN DAY / STUDENT PLANNER</div>',unsafe_allow_html=True)
st.title("Учёба с понятным планом")
st.caption("Разбери задание с ИИ, проверь требования и найди время для подготовки.")
if notice:=st.session_state.pop('_group_import_notice',None):
    st.success(notice)
if st.session_state.is_demo:
    st.info("Демо: занятия и преподаватели вымышлены. Это студенческий проект, не официальное расписание университета.",icon="ℹ️")
else:
    st.caption("Личное расписание · сверьте изменения с официальным источником")
calendar_tab,task_tab,settings_tab,proposal_tab=st.tabs(["Календарь","Мой план","Настройки","Предложение расписания"])
with calendar_tab:
    week_tab,day_tab=st.tabs(["Расписание недели","Учебный день"])
with settings_tab:
    data_tab,ai_tab,search_tab,directory_tab=st.tabs(["Данные","ИИ-импорт","Поиск","Справочник"])
    st.caption("Сохранение на устройстве и перенос полной копии — в разделе «Данные».")
group_schedule=schedule[schedule.group==group]
group_schedule.attrs.update(schedule.attrs)
plan_conflicts=validate_saved_blocks(st.session_state.tasks,group_schedule)
group_coverage=coverage_info(group_schedule)
if plan_conflicts:
    affected=len({(issue['task_id'],issue['block_id']) for issue in plan_conflicts})
    st.error(f'Сохранённый план содержит {affected} блоков с конфликтом текущей группы, расписания или покрытия. Блоки не перемещены; подробности и пересчёт — в разделе «Мой план».')
if group_coverage["kind"] == "interval":
    st.info(f"Покрытие расписания группы подтверждено: {group_coverage['start']:%d.%m.%Y}–{group_coverage['end']:%d.%m.%Y}.")
elif group_coverage["kind"] in ("listed_dates", "mixed"):
    st.warning("В CSV нет явного интервала покрытия. Даты без строк расписания считаются неизвестными, а не свободными.")
with day_tab:
    upcoming=expand(group_schedule,today,35)
    remaining=upcoming[(upcoming.lesson_date>today)|((upcoming.lesson_date==today)&(upcoming.end_time>now.strftime("%H:%M")))]
    if not remaining.empty:
        nxt=remaining.iloc[0]
        live=nxt.lesson_date==today and nxt.start_time<=now.strftime("%H:%M")
        gap_unknown=any(not date_is_covered(group_schedule,today+timedelta(days=i)) for i in range((nxt.lesson_date-today).days))
        label="ИДЁТ СЕЙЧАС" if live else "БЛИЖАЙШЕЕ ИЗВЕСТНОЕ ЗАНЯТИЕ" if gap_unknown else "БЛИЖАЙШЕЕ ЗАНЯТИЕ"
        st.markdown(f'''<div class="hero"><div class="eyebrow">{label} · {nxt.lesson_date:%d.%m} · {e(nxt.start_time)}–{e(nxt.end_time)}</div><h2>{e(nxt.subject)}</h2><div class="meta">Место: {e(location(nxt))} · {e(nxt.teacher or 'Преподаватель не указан')}</div></div>''',unsafe_allow_html=True)
    elif all(date_is_covered(group_schedule,today+timedelta(days=offset)) for offset in range(35)):
        st.success("На ближайшие 35 дней занятий нет. Проверьте группу и источник данных.")
    else:
        st.info("Ближайших занятий из файла не найдено; часть дат не входит в подтверждённое покрытие расписания.")
    todays=upcoming[upcoming.lesson_date==today]
    a,b,c=st.columns(3)
    a.metric("Записей о занятиях сегодня",len(todays))
    minutes=sum((datetime.strptime(r.end_time,"%H:%M")-datetime.strptime(r.start_time,"%H:%M")).seconds//60 for r in todays.itertuples())
    b.metric("Учебное время",f"{minutes//60} ч {minutes%60:02} мин")
    c.metric("Группа",group)
    pending=sorted((t for t in st.session_state.tasks if not t['done']),key=lambda t:t['due'])
    if pending:
        st.subheader("Ближайшие задания")
        for task in pending[:3]:
            st.write(f"{task['title']} · до {task['due']} · {task.get('minutes',50)} мин")
        st.caption("План подготовки и отметка выполнения — в разделе «Мой план».")
    if not date_is_covered(group_schedule,today):
        st.info("Сегодня нет данных о расписании: дата вне подтверждённого покрытия.")
    elif todays.empty:
        st.info("На сегодня в подтверждённом покрытии занятий нет.")
    else:
        lessons(todays,now)
    today_preparation=study_rows(st.session_state.tasks,group,today,1)
    if not today_preparation.empty:
        st.subheader("Подготовка сегодня")
        lessons(today_preparation,now)
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
    unknown_week=[start+timedelta(days=i) for i in range(7) if not date_is_covered(group_schedule,start+timedelta(days=i))]
    if unknown_week:
        st.warning("В расписании недели нет данных для: " + ", ".join(d.strftime("%d.%m") for d in unknown_week) + ". Пустые ячейки этих дат не подтверждают, что занятий нет.")
    st.subheader(f"{start:%d.%m} — {start+timedelta(days=6):%d.%m.%Y}")
    issues=conflicts(weekly)
    if issues:
        st.warning("Есть пересечения. Уточните их у ответственного за расписание.")
        for issue in issues:
            st.write(issue)
    calendar_events=calendar_with_study(weekly,st.session_state.tasks,group,start)
    covered_days={start+timedelta(days=i) for i in range(7)
                  if date_is_covered(group_schedule,start+timedelta(days=i))}
    mode=st.radio("Вид расписания",["Карточки","Таблица","Сетка недели"],horizontal=True,index=2)
    if mode=="Карточки":
        if calendar_events.empty:
            st.info("В файле нет записей на эту неделю; даты без покрытия отмечены выше как неизвестные." if unknown_week else "В подтверждённом периоде занятий на эту неделю нет.")
        else:
            lessons(calendar_events,now)
    elif mode=="Сетка недели":
        if calendar_events.empty:
            st.info("В файле нет записей на эту неделю; даты без покрытия отмечены выше как неизвестные." if unknown_week else "В подтверждённом периоде занятий на эту неделю нет.")
        else:
            st.markdown(week_grid(calendar_events,start,covered_days),unsafe_allow_html=True)
            st.caption("На широком экране показана недельная сетка, на телефоне — карточки дней. Пустая дата вне покрытия источника остаётся неизвестной.")
    else:
        st.dataframe(calendar_events[["lesson_date","start_time","end_time","subject","teacher","room","building","lesson_type","is_study","done"]].rename(columns={"lesson_date":"Дата","start_time":"Начало","end_time":"Конец","subject":"Предмет","teacher":"Преподаватель","room":"Аудитория","building":"Корпус","lesson_type":"Тип","is_study":"Блок подготовки","done":"Выполнено"}),hide_index=True,width="stretch")
    d1,d2=st.columns(2)
    d1.download_button("Занятия и подготовка · ICS",ics_export(calendar_events),"shoqan-week.ics","text/calendar",disabled=calendar_events.empty,width="stretch")
    d2.download_button("Скачать неделю CSV",csv_export(weekly[["lesson_date",*COLUMNS[2:]]].rename(columns={"lesson_date":"date"})),"shoqan-week.csv","text/csv",disabled=weekly.empty,width="stretch")
    st.caption("ICS включает занятия и сохранённые блоки подготовки выбранной недели. CSV содержит исходное расписание. Экспорт разовый и не синхронизируется автоматически.")
with search_tab:
    st.subheader("Найди нужную пару")
    query=st.text_input("Предмет, преподаватель, аудитория, корпус или группа",placeholder="Например, Базы данных или 203")
    all_groups=st.checkbox("Искать по всем группам")
    st.caption(f"Поиск в неделе {start:%d.%m} — {start+timedelta(days=6):%d.%m}. Неделю можно сменить в разделе «Неделя».")
    if all_groups:
        all_rows=[parse_csv(item['schedule'].encode('utf-8-sig')) for item in st.session_state.group_profiles.values()]
        source=expand(pd.concat(all_rows,ignore_index=True),start)
    else:
        source=expand(group_schedule,start)
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
    st.subheader("Задания и подготовка")
    task_count=len(st.session_state.tasks)
    complete_count=sum(bool(task['done']) for task in st.session_state.tasks)
    block_count=sum(len(task.get('blocks',[])) for task in st.session_state.tasks)
    done_block_count=sum(block['done'] for task in st.session_state.tasks for block in task.get('blocks',[]))
    m1,m2,m3=st.columns(3)
    m1.metric('Заданий',task_count)
    m2.metric('Завершено',complete_count)
    m3.metric('Блоков подготовки',f'{done_block_count} / {block_count}')
    st.caption("Задания и подтверждённые блоки сохраняются только в текущей сессии, пока вы явно не включили копию в Настройки → Данные.")
    st.session_state.setdefault('plan_begin',9)
    st.session_state.setdefault('plan_end',20)
    st.session_state.setdefault('plan_limit',120)
    pa,pb,pc=st.columns(3)
    begin=pa.number_input("Начинать не раньше, час",min_value=0,max_value=22,key="plan_begin")
    end=pb.number_input("Заканчивать до, час",min_value=1,max_value=23,key="plan_end")
    limit=pc.number_input("Подготовка в день, минут",min_value=15,max_value=480,step=15,key="plan_limit")
    if begin>=end:
        st.warning("Конец учебного дня должен быть позже начала. Проверьте часы перед добавлением задания.")
    revision=saved_plan_revision(st.session_state.tasks,st.session_state.schedule_raw,
                                 group,begin,end,limit)
    pending_replan=st.session_state.get('_schedule_replan_preview')
    if pending_replan and pending_replan['revision']!=revision:
        st.session_state.pop('_schedule_replan_preview',None)
        pending_replan=None
        st.warning('Расписание, группа или задания изменились. Старый вариант пересчёта отменён; подготовьте новый вариант.')
    if plan_conflicts:
        affected=len({(issue['task_id'],issue['block_id']) for issue in plan_conflicts})
        st.error(f'Найдено сохранённых блоков с конфликтом текущего расписания или покрытия: {affected}.')
        st.caption('Сохранённые блоки не перемещаются автоматически. Проверьте причины и подтвердите пересчёт отдельно.')
        conflict_rows=[{
            'Задание':issue['task_title'],
            'Блок':f"{issue['date']} · {issue['start_time']}–{issue['end_time']}",
            'Проблема':issue['reason'],
            'Выполнен':'Да' if issue['done'] else 'Нет',
        } for issue in plan_conflicts]
        st.dataframe(conflict_rows,hide_index=True,width='stretch')
    if pending_replan:
        st.subheader('Предложение пересчёта · проверьте перед применением')
        proposal_rows=[]
        for old,new in zip(st.session_state.tasks,pending_replan['tasks']):
            if old.get('done'):
                continue
            previous=[f"{b['date']} {b['start_time']}–{b['end_time']} ({b['minutes']} мин)"
                      for b in old.get('blocks',[]) if not b['done']]
            replacement=[f"{b['date']} {b['start_time']}–{b['end_time']} ({b['minutes']} мин)"
                         for b in new.get('blocks',[]) if not b['done']]
            if previous!=replacement or old.get('unplaced_minutes',0)!=new.get('unplaced_minutes',0):
                proposal_rows.append({
                    'Задание':old['title'],
                    'Было':'; '.join(previous) or '—',
                    'Станет':'; '.join(replacement) or '—',
                    'Не размещено, мин':new.get('unplaced_minutes',0),
                })
        if proposal_rows:
            st.dataframe(proposal_rows,hide_index=True,width='stretch')
        remaining_conflicts=validate_saved_blocks(pending_replan['tasks'],group_schedule)
        if remaining_conflicts:
            st.warning('После пересчёта останутся конфликты у выполненных или зафиксированных блоков. Они сохраняются без перемещения.')
        has_changes=pending_replan['tasks']!=st.session_state.tasks
        confirm_col,cancel_col=st.columns(2)
        if confirm_col.button('Подтвердить и применить пересчёт',type='primary',
                              key='confirm_schedule_replan',disabled=not has_changes):
            set_active_tasks(st.session_state,pending_replan['tasks'])
            st.session_state.pop('_schedule_replan_preview',None)
            st.rerun()
        if cancel_col.button('Отменить пересчёт',key='cancel_schedule_replan'):
            st.session_state.pop('_schedule_replan_preview',None)
            st.rerun()
    elif plan_conflicts and begin<end:
        if st.button('Подготовить вариант пересчёта',key='prepare_schedule_replan'):
            proposal=preview_replan(st.session_state.tasks,group_schedule,now,
                                    int(begin),int(end),int(limit))
            st.session_state._schedule_replan_preview={
                'revision':revision,'tasks':proposal['tasks']}
            st.rerun()
    render_assignment(today,group_schedule,now,begin,end,limit)
    st.divider()
    st.subheader("Добавить без ИИ")
    st.caption("Ручной ввод работает и без сетевого доступа к Gemini.")
    with st.form("add_task",clear_on_submit=True):
        title=st.text_input("Что нужно сделать?",max_chars=160)
        task_subject=st.text_input("Предмет задания",max_chars=100)
        task_minutes=st.number_input("Время подготовки, минут",min_value=15,max_value=480,value=50,step=5)
        due=st.date_input("Срок",today,key="task_due")
        added=st.form_submit_button("Добавить вручную в план")
    if added:
        if not title.strip() or due is None:
            st.warning("Введите название и срок задачи.")
        elif len(st.session_state.tasks)>=100:
            st.error("Максимум 100 задач. Сохраните копию и уберите завершённые.")
        elif begin>=end:
            st.error("Исправьте часы подготовки перед добавлением задания.")
        else:
            candidate={"id":hashlib.sha256((title+datetime.now().isoformat()).encode()).hexdigest()[:12],
                       "title":title.strip(),"due":due.isoformat(),"done":False,
                       "subject":task_subject.strip(),"minutes":int(task_minutes),"requirements":"",
                       "evidence":"","steps":"","blocks":[]}
            try:
                proposal=preview_assignment(st.session_state.tasks,candidate,group_schedule,now,begin,end,limit)
                set_active_tasks(st.session_state,commit_assignment(st.session_state.tasks,candidate,proposal))
            except ValueError as exc:
                st.error(str(exc))
                st.stop()
            st.rerun()
    for task in sorted(st.session_state.tasks,key=lambda x:(x["done"],x["due"])):
        overdue=not task["done"] and date.fromisoformat(task["due"])<today
        with st.container(border=True):
            st.checkbox(f"{task['title']} · срок {task['due']}"+(" · просрочено" if overdue else ""),value=task["done"],key="task_"+task["id"],on_change=update_task_completion,args=(task['id'],))
            block_progress(task)
            blocks=task.get('blocks',[])
            if blocks:
                with st.expander(f"Блоки подготовки · {len(blocks)}"):
                    for block in blocks:
                        label=f"{block['date'][8:10]}.{block['date'][5:7]} · {block['start_time']}–{block['end_time']} · {block['minutes']} мин"
                        st.checkbox(label,value=block['done'],key='plan_block_'+block['id'],on_change=update_block_completion,args=(task['id'],block['id']))
            elif not task['done']:
                st.info('Пока нет размещённых блоков. Добавьте расписание с покрытием и проверьте срок.')
        if task.get('steps'):
            with st.expander("Этапы: "+task['title']):
                st.text(task['steps'])
        if task.get('requirements') or task.get('evidence'):
            with st.expander("Требования: "+task['title']):
                if task.get('requirements'):
                    st.text(task['requirements'])
                if task.get('evidence'):
                    st.caption('Цитата из задания')
                    st.text(task['evidence'])
        with st.expander('Изменить: '+task['title']):
            with st.form('edit_'+task['id']):
                new_title=st.text_input('Название задания',task['title'],max_chars=160)
                new_subject=st.text_input('Учебный предмет',task.get('subject',''),max_chars=100)
                new_due=st.date_input('Новый срок',date.fromisoformat(task['due']))
                new_minutes=st.number_input('Минут на подготовку',min_value=15,max_value=480,value=task.get('minutes',50),step=5)
                new_requirements=st.text_area('Требования',task.get('requirements',''),max_chars=1500)
                new_steps=st.text_area('Этапы подготовки',task.get('steps',''),max_chars=1500)
                if st.form_submit_button('Сохранить изменения'):
                    if new_title.strip() and new_due:
                        completed_blocks=[dict(block) for block in task.get('blocks',[]) if block['done']]
                        completed_minutes=sum(block['minutes'] for block in completed_blocks)
                        if int(new_minutes)<completed_minutes:
                            st.error(f'Уже выполнено {completed_minutes} мин. Оценка времени не может быть меньше выполненного объёма.')
                        elif begin>=end:
                            st.error('Исправьте часы подготовки перед изменением задания.')
                        else:
                            updated={**task,'title':new_title.strip(),'subject':new_subject.strip(),
                                     'due':new_due.isoformat(),'minutes':int(new_minutes),'steps':new_steps,
                                     'requirements':new_requirements,
                                     'blocks':completed_blocks}
                            if new_due!=date.fromisoformat(task['due']) or int(new_minutes)!=task.get('minutes',50):
                                remaining=max(0,int(new_minutes)-completed_minutes)
                                others=[item for item in st.session_state.tasks if item['id']!=task['id']]
                                try:
                                    proposal=preview_assignment(others,updated,group_schedule,now,begin,end,limit,
                                                               candidate_minutes=remaining,additional_blocked=completed_blocks)
                                    st.session_state.tasks=commit_assignment(others,updated,proposal)
                                    st.rerun()
                                except ValueError as exc:
                                    st.error(str(exc))
                            else:
                                task.update(title=updated['title'],subject=updated['subject'],
                                            requirements=new_requirements,steps=new_steps)
                                st.rerun()
                    else:
                        st.warning('Нужны название и срок.')
            if st.button('Удалить это задание',key='delete_'+task['id']):
                st.session_state.tasks=[t for t in st.session_state.tasks if t['id']!=task['id']]
                st.rerun()
    if not st.session_state.tasks:
        st.info("Пока задач нет. Вставьте текст преподавателя для разбора или добавьте задание вручную.")
    st.subheader("Когда готовиться")
    st.caption("План покрывает минимум 14 дней и продлевается до более позднего срока, максимум на 30 дней. Доступные блоки зависят от покрытия расписания выбранной группы; личные дела, дорога и работа не учтены. Между занятиями заложено 10 минут.")
    if begin>=end:
        st.warning("Конец учебного дня должен быть позже начала.")
    elif st.session_state.tasks:
        blocks=[{'Дата':date.fromisoformat(block['date']),'Начало':block['start_time'],
                 'Конец':block['end_time'],'Предмет':task.get('subject',''),
                 'Задание':task['title'],'Минут':block['minutes'],
                 'Выполнено':'Да' if block['done'] else 'Нет'}
                for task in st.session_state.tasks for block in task.get('blocks',[])]
        blocks.sort(key=lambda item:(item['Дата'],item['Начало']))
        unplaced=[{'Задание':task['title'],'Не размещено, мин':task.get('unplaced_minutes',0),
                   'Срок':task['due'],'Расписание неизвестно':task.get('coverage_unknown',False)}
                  for task in st.session_state.tasks if task.get('unplaced_minutes',0)]
        if blocks:
            st.dataframe(blocks,hide_index=True,width="stretch")
        if unplaced:
            if any(item.get('Расписание неизвестно') for item in unplaced):
                st.warning("Часть задания не размещена: нужные даты не покрыты расписанием. Загрузите источник с явным периодом покрытия; неизвестные даты не считаются свободными.")
            else:
                st.warning("Часть времени не поместилась до срока в горизонте планирования до 30 дней с выбранным дневным лимитом. Проверьте срок, объём и доступные окна.")
            st.dataframe(unplaced,hide_index=True,width="stretch")
        if blocks:
            plan_rows=[{'lesson_date':item['Дата'],'start_time':item['Начало'],'end_time':item['Конец'],
                        'subject':'Подготовка: '+item['Задание'],'teacher':'','room':'','building':'',
                        'group':group,'lesson_type':'Подготовка'} for item in blocks]
            st.download_button("Скачать подтверждённые блоки ICS",ics_export(pd.DataFrame(plan_rows)),"study-plan.ics","text/calendar")
        st.caption("Блоки подготовки длятся 15–50 минут и отмечаются выполненными по отдельности. Снимок расписания используется только в пределах его объявленного периода.")
    st.download_button("Сохранить задачи JSON",json.dumps(st.session_state.tasks,ensure_ascii=False,indent=2).encode(),"shoqan-tasks.json","application/json")
    restore=st.file_uploader("Восстановить задачи из своей копии",type=["json"])
    if restore and st.button("Заменить список задач из копии"):
        try:
            if restore.size>200_000:
                raise ValueError
            tasks=clean_tasks(json.loads(restore.getvalue()))
            if not isinstance(tasks,list) or len(tasks)>100:
                raise ValueError
            digest=hashlib.sha256(restore.getvalue()).hexdigest()[:8]
            clean=[{**task,"id":f"import_{i}_{digest}"} for i,task in enumerate(tasks)]
            set_active_tasks(st.session_state,clean)
            for k in list(st.session_state):
                if k.startswith(("task_","plan_block_")) and k!="task_due":
                    del st.session_state[k]
            st.rerun()
        except (ValueError,TypeError,KeyError,UnicodeDecodeError):
            st.error("Копия повреждена или имеет неподдерживаемый формат. Текущие задачи сохранены.")
    if st.button("Убрать завершённые задачи"):
        set_active_tasks(st.session_state,[t for t in st.session_state.tasks if not t["done"]])
        st.rerun()
with data_tab:
    render_controls(theme,group)
    st.subheader('Источники по группам')
    source_rows=[]
    for key,item in st.session_state.group_profiles.items():
        item_frame=parse_csv(item['schedule'].encode('utf-8-sig'))
        item_coverage=coverage_info(item_frame)
        if item_coverage['kind']=='interval':
            coverage_text=f"{item_coverage['start']:%d.%m.%Y}–{item_coverage['end']:%d.%m.%Y}"
        elif item_coverage['kind']=='recurring':
            coverage_text='Повторяющееся расписание по дням недели'
        elif item_coverage['kind'] in ('listed_dates','mixed'):
            coverage_text='Только даты со строками расписания'
        else:
            coverage_text='Покрытие неизвестно'
        source_rows.append({'Группа':item['group']+(' · демо' if item['is_demo'] else ''),
                            'Источник':item['source_name'],'Покрытие':coverage_text,
                            'Заданий':len(item['tasks'])})
    st.dataframe(source_rows,hide_index=True,width='stretch')
    st.divider()
    st.subheader('Архивное расписание ИСР-242уск')
    st.warning('Архивный неофициальный снимок: срок покрытия завершился 3 октября 2026 года. Эти данные не являются актуальным расписанием и не обновляются автоматически.')
    st.caption('28 сентября — 3 октября 2026. Перенесено вручную из присланных снимков timetable.kgu.kz; группу указал студент. Это снимок одной недели, без автоматических обновлений. Уточняйте замены в официальном расписании.')
    with st.expander('Посмотреть 23 занятия перед загрузкой'):
        real_raw=(ROOT/'data/isr242_2026-09-28.csv').read_bytes()
        st.dataframe(parse_csv(real_raw)[COLUMNS],hide_index=True,width='stretch')
    if st.button('Импортировать архивный снимок ИСР-242уск'):
        try:
            import_group_schedules(real_raw,'ИСР-242уск · снимок 28.09–03.10.2026')
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state._week_pending=date(2026,9,28)
            st.rerun()
    st.caption('Для других групп можно загрузить свой CSV. Доступ к их официальным данным требует авторизации университета; выдуманных расписаний здесь нет.')
    st.divider()
    st.subheader("Импорт расписания")
    st.write(f"Загрузите проверенный CSV из разрешённого источника. Можно импортировать до {MAX_IMPORTED_GROUPS} групп; каждая получит своё расписание и отдельный план. Совпавшая группа обновит только расписание, сохранив задания.")
    st.download_button("Скачать шаблон",TEMPLATE.encode("utf-8-sig"),"schedule-template.csv","text/csv")
    st.caption("В шаблоне одна условная строка-пример. Замените её своими парами; это не реальное расписание университета.")
    upload=st.file_uploader("CSV, до 2 МБ",type=["csv"],max_upload_size=2)
    if upload:
        try:
            upload_raw=upload.getvalue()
            candidate=parse_csv(upload_raw)
            importable=split_group_schedules(upload_raw,upload.name,is_demo=False)
            incoming_names=set(importable)
            existing_names={profile['group'] for profile in st.session_state.group_profiles.values() if not profile['is_demo']}
            resulting_count=len(existing_names | incoming_names)
            if resulting_count>MAX_IMPORTED_GROUPS:
                raise ValueError(f"После импорта будет {resulting_count} групп; лимит — {MAX_IMPORTED_GROUPS}. Удалите или замените одну из существующих групп.")
            st.success(f"Проверено: {len(candidate)} занятий, групп: {candidate.group.nunique()}")
            st.caption(f"В копии будет {resulting_count}/{MAX_IMPORTED_GROUPS} импортированных групп. Совпадающие группы обновятся; их планы останутся на месте.")
            candidate_coverage=coverage_info(candidate)
            if candidate_coverage['kind']=='interval':
                st.info(f"Покрытие явно задано: {candidate_coverage['start']:%d.%m.%Y}–{candidate_coverage['end']:%d.%m.%Y}.")
            elif candidate_coverage['kind'] in ('listed_dates','mixed'):
                st.warning("Интервал покрытия не указан: даты без записей останутся неизвестными и не будут использоваться для свободных окон.")
            st.dataframe(candidate[COLUMNS],hide_index=True,width="stretch")
            for issue in conflicts(expand(candidate,monday(today))):
                st.warning(issue)
            if st.button("Добавить или обновить эти группы",type="primary"):
                try:
                    imported=import_group_schedules(upload_raw,upload.name)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.success(f"Добавлено или обновлено групп: {len(imported)}. Планы сохранены отдельно.")
                    st.rerun()
        except (ValueError,UnicodeDecodeError) as exc:
            st.error(str(exc))
    schedule_export=schedule[COLUMNS].copy()
    schedule_export.attrs.update(schedule.attrs)
    st.download_button("Сохранить расписание этой группы CSV",csv_export(schedule_export),"shoqan-schedule.csv","text/csv")
    st.caption(f"В этой копии сохранено {sum(not p['is_demo'] for p in st.session_state.group_profiles.values())} из {MAX_IMPORTED_GROUPS} импортированных групп. Демо-набор не занимает слот.")
    with st.expander("Формат файла и ограничения"):
        st.write("Необязательные колонки: building — корпус, lesson_type — тип занятия (например, Л, ЛЗ, СПЗ). Старые CSV без этих колонок тоже поддерживаются.")
        st.write("Одно занятие обычно длится 50 минут. Соседние занятия одного предмета сохраняйте отдельными строками: перерыв между ними не входит в учебное время.")
        st.write("Обязательные колонки: group, start_time, end_time, subject, teacher, room. Преподавателя и аудиторию можно оставить пустыми.")
        st.write("В строке заполните либо weekday (Понедельник…Воскресенье), либо date (YYYY-MM-DD). Время строго ЧЧ:ММ. Конец позже начала. UTF-8 или Windows-1251, разделитель запятая или точка с запятой.")
        st.write("weekday повторяется каждую неделю без каникул. Для точного учебного периода используйте date. Чётные/нечётные недели и автоматические замены пока не поддерживаются.")
        st.write("Для date-расписания можно явно указать одинаковые coverage_start и coverage_end (YYYY-MM-DD) в каждой строке. Только тогда дни без занятий между этими границами подтверждаются как свободные. Без метаданных учитываются лишь даты с записями; остальные даты неизвестны. Метаданные не применяются к weekday-расписаниям.")
        st.write("Пересечения проверяются для одной группы в выбранной неделе. Занятость аудиторий и общие лекции разных групп уточняйте у диспетчера.")
    if not st.session_state.is_demo and st.button("Добавить демонстрационное расписание"):
        try:
            remember_active_profile(st.session_state)
            demo_raw=(ROOT/"data/schedule_demo.csv").read_bytes()
            demos=add_demo_schedule(st.session_state.group_profiles,demo_raw)
            demo_key=next(key for key,item in demos.items() if item['is_demo'])
            st.session_state.group_profiles=demos
            st.session_state._active_group_key=""
            st.session_state._requested_group_key=demo_key
            st.session_state._group_import_notice='Демо-набор добавлен отдельно; импортированные планы сохранены.'
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    st.divider()
    st.subheader("О проекте")
    st.write("Shoqan Day — идея учебного ИИ-помощника для университета с работающей демонстрацией. ИИ помогает разобрать задание, студент проверяет требования, планировщик находит время вокруг занятий. Для университетской версии предлагаются согласованный источник расписания, казахский интерфейс и сопровождение. Решение о внедрении ещё не принято.")
st.caption("Shoqan Day · Источник и сохранение данных: Настройки → Данные")

with ai_tab:
    render_ai(group,today)
with directory_tab:
    render_directory(schedule,start,today,lessons,now)
with proposal_tab:
    render_schedule_proposal()
sync_browser(theme,group)
