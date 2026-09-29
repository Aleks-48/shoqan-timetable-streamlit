from __future__ import annotations

from datetime import date, datetime, time, timedelta
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st


APP_DIR = Path(__file__).parent
DEMO_FILE = APP_DIR / "data" / "schedule_demo.csv"
LOCAL_TZ = ZoneInfo("Asia/Qyzylorda")
WEEKDAYS = {
    "понедельник": 0,
    "вторник": 1,
    "среда": 2,
    "четверг": 3,
    "пятница": 4,
    "суббота": 5,
    "воскресенье": 6,
}
WEEKDAY_NAMES = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
REQUIRED_COLUMNS = ["group", "start_time", "end_time", "subject", "teacher", "room"]
CSV_TEMPLATE = "weekday,group,start_time,end_time,subject,teacher,room\nПонедельник,ИС-101,09:00,10:30,Пример предмета,Иванов И.И.,101\n"


st.set_page_config(page_title="Расписание Shoqan", page_icon="📅", layout="wide")


def local_today() -> date:
    return datetime.now(LOCAL_TZ).date()


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def read_csv_bytes(raw: bytes) -> pd.DataFrame:
    try:
        return pd.read_csv(BytesIO(raw), encoding="utf-8-sig")
    except UnicodeDecodeError:
        return pd.read_csv(BytesIO(raw), encoding="cp1251")


def load_schedule(uploaded_file) -> tuple[pd.DataFrame, bool, str | None]:
    is_demo = uploaded_file is None
    try:
        frame = pd.read_csv(DEMO_FILE) if is_demo else read_csv_bytes(uploaded_file.getvalue())
    except Exception as exc:
        return pd.DataFrame(), is_demo, f"Не удалось прочитать CSV: {exc}"

    frame.columns = [str(column).strip().lower() for column in frame.columns]
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        return pd.DataFrame(), is_demo, "В файле не хватает колонок: " + ", ".join(missing)

    if "weekday" not in frame.columns and "date" not in frame.columns:
        return pd.DataFrame(), is_demo, "Добавьте колонку weekday (день недели) или date (дата пары)."

    for column in REQUIRED_COLUMNS:
        frame[column] = frame[column].fillna("").astype(str).str.strip()
    frame["start_time"] = frame["start_time"].str.slice(0, 5)
    frame["end_time"] = frame["end_time"].str.slice(0, 5)
    frame = frame[(frame["group"] != "") & (frame["subject"] != "")]

    if "weekday" in frame.columns:
        frame["weekday"] = frame["weekday"].fillna("").astype(str).str.strip().str.lower()
        frame["weekday_num"] = frame["weekday"].map(WEEKDAYS)
    else:
        frame["weekday_num"] = pd.NA

    if "date" in frame.columns:
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.date
    else:
        frame["date"] = None

    invalid_time = frame["start_time"].map(lambda value: not is_time(value)) | frame["end_time"].map(lambda value: not is_time(value))
    invalid_day = frame["weekday_num"].isna() & frame["date"].isna()
    frame = frame[~invalid_time & ~invalid_day].copy()
    if frame.empty:
        return pd.DataFrame(), is_demo, "В файле нет строк с корректными днями и временем."
    return frame, is_demo, None


def is_time(value: str) -> bool:
    try:
        time.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False


def expand_week(frame: pd.DataFrame, week_start: date) -> pd.DataFrame:
    week_end = week_start + timedelta(days=6)
    rows: list[dict] = []
    for record in frame.to_dict("records"):
        exact_date = record.get("date")
        if pd.notna(exact_date) and isinstance(exact_date, date):
            dates = [exact_date] if week_start <= exact_date <= week_end else []
        elif pd.notna(record.get("weekday_num")):
            weekday_num = int(record["weekday_num"])
            dates = [week_start + timedelta(days=offset) for offset in range(7) if (week_start + timedelta(days=offset)).weekday() == weekday_num]
        else:
            dates = []
        for lesson_date in dates:
            rows.append({**record, "lesson_date": lesson_date})
    result = pd.DataFrame(rows, columns=[*frame.columns, "lesson_date"])
    if not result.empty:
        result = result.sort_values(["lesson_date", "start_time", "group", "room"], kind="stable")
    return result


def render_lessons(lessons: pd.DataFrame, today: date) -> None:
    if lessons.empty:
        st.info("На эту дату занятий не найдено.")
        return
    for lesson_date, day_rows in lessons.groupby("lesson_date", sort=True):
        day_name = WEEKDAY_NAMES[lesson_date.weekday()]
        st.markdown(f"### {day_name}, {lesson_date:%d.%m.%Y}" + (" · Сегодня" if lesson_date == today else ""))
        for _, lesson in day_rows.iterrows():
            st.markdown(
                f"**{lesson['start_time']}–{lesson['end_time']} · {lesson['subject']}**  \n"
                f"Группа: {lesson['group']} · Преподаватель: {lesson['teacher'] or 'не указан'} · Аудитория: {lesson['room'] or 'не указана'}"
            )
            st.divider()


st.title("📅 Расписание Shoqan")
st.caption("Простой просмотр расписания студентов — демонстрационная версия")

with st.sidebar:
    st.header("Данные расписания")
    uploaded = st.file_uploader("Загрузить CSV расписания", type=["csv"], help="Файл останется только в текущем сеансе браузера.")
    st.download_button(
        "Скачать шаблон CSV",
        data=CSV_TEMPLATE.encode("utf-8-sig"),
        file_name="schedule_template.csv",
        mime="text/csv",
        use_container_width=True,
    )
    st.caption("Поля: weekday или date, group, start_time, end_time, subject, teacher, room")

schedule, is_demo, error = load_schedule(uploaded)
if error:
    st.error(error)
    st.stop()

if is_demo:
    st.warning("Сейчас показаны вымышленные демонстрационные данные. Они не являются официальным расписанием университета.", icon="⚠️")

today = local_today()
with st.sidebar:
    groups = sorted(schedule["group"].dropna().unique().tolist())
    selected_group = st.selectbox("Группа", groups)
    selected_week = st.date_input("Неделя с", value=monday_of(today), help="Выберите любую дату нужной недели.")
    view = st.radio("Раздел", ["Сегодня", "Неделя", "Поиск"], horizontal=False)

week_start = monday_of(selected_week)
week_rows = expand_week(schedule, week_start)
group_rows = week_rows[week_rows["group"] == selected_group].copy()

if view == "Сегодня":
    st.subheader("Занятия сегодня")
    current_week_rows = expand_week(schedule, monday_of(today))
    today_rows = current_week_rows[(current_week_rows["group"] == selected_group) & (current_week_rows["lesson_date"] == today)]
    render_lessons(today_rows, today)
    st.caption(f"Часовой пояс: Asia/Qyzylorda · Дата: {today:%d.%m.%Y}")
elif view == "Неделя":
    st.subheader(f"Неделя {week_start:%d.%m} — {(week_start + timedelta(days=6)):%d.%m.%Y}")
    render_lessons(group_rows, today)
else:
    st.subheader("Поиск по расписанию")
    query = st.text_input("Предмет, преподаватель, аудитория или группа", placeholder="Например: базы данных или 203")
    search_every_group = st.checkbox("Искать по всем группам", value=False)
    searchable = week_rows if search_every_group else group_rows
    if query.strip() and searchable.empty:
        st.info("На выбранную неделю занятий не найдено.")
    elif query.strip():
        searchable_text = searchable[REQUIRED_COLUMNS].fillna("").astype(str).agg(" ".join, axis=1)
        matches = searchable[searchable_text.str.contains(query.strip(), case=False, regex=False)].copy()
        st.caption(f"Найдено занятий: {len(matches)}")
        render_lessons(matches, today)
    else:
        st.info("Введите поисковый запрос.")

st.markdown("---")
st.caption("Чтобы показать актуальное расписание, загрузите CSV из официального источника университета.")
