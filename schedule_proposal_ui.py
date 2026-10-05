"""Streamlit interface for the review-only academic schedule proposal MVP."""
import hashlib
import json

import pandas as pd
import streamlit as st

from schedule_proposal import (
    DAYS, export_proposal_csv, generate_proposal, parse_proposal_input,
    verify_proposal,
)


DEMO_REQUESTS = """group,subject,teacher,room_type,students,sessions_per_week
DEMO-1,Algebra,Teacher A,lecture,22,2
DEMO-1,Physics lab,Teacher B,lab,18,1
DEMO-2,Algebra,Teacher A,lecture,18,2
DEMO-2,Academic writing,Teacher C,seminar,16,1
"""

DEMO_ROOMS = """room,room_type,capacity,building
A101,lecture,30,Demo campus A
A102,lecture,25,Demo campus A
B201,seminar,20,Demo campus B
LAB1,lab,20,Demo campus B
"""

DEMO_UNAVAILABLE = """resource_type,resource,day,start_time,end_time
teacher,Teacher A,Monday,09:00,10:00
room,A101,Tuesday,09:00,10:00
group,DEMO-1,Wednesday,11:00,12:00
"""


def _fingerprint(requests: str, rooms: str, unavailable: str, start_hour: int, end_hour: int) -> str:
    raw = json.dumps([requests, rooms, unavailable, start_hour, end_hour], ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _display_frame(rows: list[dict], empty: str) -> None:
    if not rows:
        st.info(empty)
        return
    frame = pd.DataFrame(rows).rename(columns={
        "group": "Группа", "subject": "Предмет", "teacher": "Преподаватель",
        "room_type": "Тип аудитории", "students": "Студентов", "day": "День",
        "start_time": "Начало", "end_time": "Конец", "room": "Аудитория",
        "building": "Корпус", "status": "Статус", "reason": "Причина",
    })
    st.dataframe(frame, hide_index=True, width="stretch")


def render_schedule_proposal() -> None:
    st.subheader("Предложение учебного расписания")
    st.info("Демонстрационный пример полностью синтетический. Здесь нет данных Platonus, официального расписания или отправки текста внешнему ИИ.")
    st.caption("Редактируйте заявки, аудитории и занятые окна; генератор создаёт локальный черновик для проверки эдвайзером. Он ничего не утверждает и не публикует.")

    requests_csv = st.text_area("Заявки · group, subject, teacher, room_type, students, sessions_per_week",
                                value=DEMO_REQUESTS, height=150, max_chars=20_000,
                                key="proposal_requests_csv")
    rooms_csv = st.text_area("Аудитории · room, room_type, capacity, building",
                             value=DEMO_ROOMS, height=125, max_chars=20_000,
                             key="proposal_rooms_csv")
    unavailable_csv = st.text_area("Занятые окна · resource_type (group/teacher/room), resource, day, start_time, end_time",
                                   value=DEMO_UNAVAILABLE, height=110, max_chars=20_000,
                                   key="proposal_unavailable_csv")
    left, right = st.columns(2)
    start_hour = left.number_input("Начало окна · час", min_value=6, max_value=19,
                                   value=9, step=1, key="proposal_start_hour")
    end_hour = right.number_input("Конец окна · час, не включая", min_value=7, max_value=20,
                                 value=18, step=1, key="proposal_end_hour")
    st.caption("Модель недели: Monday–Friday; занятия по 50 минут начинаются каждый час, с 10 минутами между слотами.")
    st.caption("Лимиты MVP: 10 групп, 30 встреч в неделю, 12 аудиторий, 100 занятых окон.")

    fingerprint = _fingerprint(requests_csv, rooms_csv, unavailable_csv, start_hour, end_hour)
    draft_key = "_academic_proposal_draft"
    draft = st.session_state.get(draft_key)
    stale = bool(draft and draft.get("input_fingerprint") != fingerprint)
    if stale:
        st.session_state.pop(draft_key, None)
        draft = None
        st.warning("Входные данные изменились. Старый черновик отменён; создайте новый после проверки ограничений.")

    build_col, cancel_col = st.columns([2, 1])
    build = build_col.button("Сформировать черновик", key="proposal_build", type="primary", width="stretch")
    cancel = cancel_col.button("Отменить черновик", key="proposal_cancel", disabled=draft is None,
                               width="stretch")
    if cancel:
        st.session_state.pop(draft_key, None)
        st.rerun()
    if build:
        st.session_state.pop(draft_key, None)
        try:
            problem = parse_proposal_input(requests_csv, rooms_csv, unavailable_csv,
                                           int(start_hour), int(end_hour))
            proposal = generate_proposal(problem)
            checked = verify_proposal(problem, proposal["meetings"])
            if not checked["valid"]:
                raise ValueError("Внутренняя проверка нашла конфликт; черновик не сохранён и не экспортируется.")
            st.session_state[draft_key] = dict(input_fingerprint=fingerprint,
                                                problem=problem, proposal=proposal)
            st.rerun()
        except (ValueError, TypeError, KeyError) as exc:
            st.error(str(exc))
        except TimeoutError:
            st.error("Поиск был прерван. Незавершённый вариант не сохранён; проверьте ограничения и запустите заново.")

    draft = st.session_state.get(draft_key)
    if not draft:
        st.caption("Черновика пока нет. Нажатие кнопки запускает только локальную проверку и поиск размещений.")
        return

    problem, proposal = draft["problem"], draft["proposal"]
    verification = verify_proposal(problem, proposal["meetings"])
    total = len(problem["occurrences"])
    placed = verification["placed_count"]
    if proposal["status"] == "complete" and verification["valid"] and verification["complete"]:
        st.success(f"Полный черновик: размещено {placed} из {total}. Независимая проверка не нашла конфликтов.")
    else:
        st.warning(f"Частичный черновик: размещено {placed} из {total}. Это не доказательство невозможности полного расписания.")
    st.caption(f"Поиск проверил {proposal['search_nodes']} узлов" +
               (" и достиг лимита; результат эвристический." if proposal["search_limited"] else "."))
    if verification["issues"]:
        st.error("В черновике есть конфликты, экспорт отключён.")
        st.dataframe(pd.DataFrame({"Проверка": verification["issues"]}), hide_index=True, width="stretch")
    else:
        st.success("Проверка групп, преподавателей, аудиторий, вместимости, типа и занятых окон пройдена.")
    _display_frame(proposal["meetings"], "Подходящих размещений пока нет.")
    if proposal["unplaced"]:
        st.markdown("**Не распределено · причины для ручного решения**")
        _display_frame(proposal["unplaced"], "Все занятия размещены.")
    if verification["valid"]:
        st.download_button("Скачать CSV для проверки эдвайзером",
                           export_proposal_csv(problem, proposal),
                           "schedule-proposal-review.csv", "text/csv", width="stretch")
    st.caption("Ограничения MVP: будни и сетка целых часов; по 50 минут на занятие. Корпус показан только как справка — время перехода между корпусами не рассчитывается. Не учитываются каникулы, нечётные недели, квалификации преподавателей и скрытая/официальная занятость. Полный поиск ограничен бюджетом; неполный результат не означает, что решения не существует.")
