"""Views based exclusively on the current uploaded timetable."""
import html
from datetime import timedelta
import pandas as pd
import streamlit as st
from schedule import DAYS, expand, location, ics_export

def week_grid(rows, start):
    """Keep all lessons, including simultaneous and nonstandard intervals."""
    esc=lambda value: html.escape(str(value))
    intervals=sorted(set(zip(rows.start_time,rows.end_time)))
    out=['<div class="week-scroll"><table class="week-grid"><thead><tr><th>Время</th>']
    for i in range(7):
        day=start+timedelta(days=i)
        out.append(f'<th>{DAYS[i]}<br>{day:%d.%m}</th>')
    out.append('</tr></thead><tbody>')
    for begin,end in intervals:
        out.append(f'<tr><th>{esc(begin)}<br>{esc(end)}</th>')
        for i in range(7):
            block=rows[(rows.lesson_date==start+timedelta(days=i))&(rows.start_time==begin)&(rows.end_time==end)]
            out.append('<td>')
            if block.empty:
                out.append('<span class="meta">—</span>')
            for r in block.to_dict('records'):
                out.append(f'<div class="grid-lesson"><strong>{esc(r["subject"])}</strong><br>{esc(r["group"])} · {esc(r.get("lesson_type", ""))}<br>{esc(location(r))}<br><span class="meta">{esc(r["teacher"])}</span></div>')
            out.append('</td>')
        out.append('</tr>')
    out.append('</tbody></table></div>')
    return ''.join(out)

def room_snapshot(schedule, day, begin, end):
    rows=expand(schedule,day,1)
    inventory=schedule[schedule.room!=''][['building','room']].drop_duplicates().sort_values(['building','room'])
    result=[]
    for building,room in inventory.itertuples(index=False,name=None):
        hits=rows[(rows.building==building)&(rows.room==room)&(rows.start_time<end)&(rows.end_time>begin)]
        result.append({'Корпус':building or 'Не указан','Аудитория':room,
                       'По загруженным данным':'Есть занятия' if len(hits) else 'Нет записей на интервал',
                       'Занятия':'; '.join(f'{r.start_time}–{r.end_time} · {r.group} · {r.subject}' for r in hits.itertuples())})
    return pd.DataFrame(result,columns=['Корпус','Аудитория','По загруженным данным','Занятия'])

def render_directory(schedule, start, today, lessons, now):
    st.subheader('Преподаватели и аудитории')
    st.caption('По всем группам текущего источника. Неделя выбирается в разделе «Неделя».')
    mode=st.radio('Что посмотреть',['Преподаватель','Аудитории'],horizontal=True,key='directory_mode')
    if mode=='Преподаватель':
        names=sorted(x for x in schedule.teacher.unique() if x)
        if not names:
            st.info('В источнике не указаны преподаватели.')
            return
        teacher=st.selectbox('Преподаватель',names,key='directory_teacher')
        rows=expand(schedule[schedule.teacher==teacher],start)
        st.caption(f'{start:%d.%m} — {start+timedelta(days=6):%d.%m.%Y} · занятий: {len(rows)}')
        lessons(rows,now)
        st.download_button('Неделя преподавателя в календарь',ics_export(rows),'teacher-week.ics','text/calendar',disabled=rows.empty)
    else:
        st.info('Отсутствие записей не гарантирует, что аудитория свободна: источник может включать не все группы. Это просмотр расписания, не бронирование.')
        day=st.date_input('Дата проверки аудиторий',today,key='room_day')
        a,b=st.columns(2)
        from datetime import time
        begin=a.time_input('С',time(8,30),step=timedelta(minutes=10),key='room_begin')
        end=b.time_input('До',time(9,20),step=timedelta(minutes=10),key='room_end')
        if day is None or begin is None or end is None or end<=begin:
            st.warning('Укажите дату и интервал в пределах одного дня: конец позже начала.')
            return
        rooms=room_snapshot(schedule,day,begin.strftime('%H:%M'),end.strftime('%H:%M'))
        if rooms.empty:
            st.info('В источнике нет номеров аудиторий.')
            return
        building=st.selectbox('Корпус',['Все корпуса',*sorted(rooms['Корпус'].unique())],key='room_building')
        if building!='Все корпуса':
            rooms=rooms[rooms['Корпус']==building]
        st.dataframe(rooms,hide_index=True,width='stretch')
