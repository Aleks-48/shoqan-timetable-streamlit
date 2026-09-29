"""Schedule validation and export independent of Streamlit."""
from __future__ import annotations
import csv
import hashlib
import re
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from zoneinfo import ZoneInfo
import pandas as pd

TZ = ZoneInfo("Asia/Almaty")
DAYS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
REQUIRED = ["group", "start_time", "end_time", "subject", "teacher", "room"]
COLUMNS = ["weekday", "date", *REQUIRED]
TEMPLATE = "weekday,date,group,start_time,end_time,subject,teacher,room\nПонедельник,,ИС-101,09:00,10:30,Пример предмета,Пример преподавателя,101\n"

def monday(day):
    return day - timedelta(days=day.weekday())

def parse_csv(raw: bytes) -> pd.DataFrame:
    if len(raw) > 2_000_000:
        raise ValueError("Файл больше 2 МБ. Разделите расписание на несколько файлов.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1251")
    if not text.strip():
        raise ValueError("CSV пуст. Скачайте шаблон и добавьте занятия.")
    header = text.splitlines()[0]
    reader = csv.reader(StringIO(text), delimiter=";" if header.count(";") > header.count(",") else ",")
    names = [s.strip().lower() for s in next(reader)]
    if len(names) != len(set(names)):
        raise ValueError("В заголовке повторяются названия колонок.")
    if any(x not in names for x in REQUIRED) or not ({"weekday", "date"} & set(names)):
        raise ValueError("Нужны колонки: " + ", ".join(REQUIRED) + ", а также weekday или date.")
    rows, errors = [], []
    for line, fields in enumerate(reader, 2):
        if not fields or not any(s.strip() for s in fields):
            continue
        if line > 10001:
            raise ValueError("Максимум 10 000 строк расписания.")
        if len(fields) != len(names):
            errors.append(f"Строка {line}: число ячеек не совпадает с заголовком.")
            continue
        r = {name: value.strip() for name, value in zip(names, fields)}
        reasons = []
        if not r["group"] or not r["subject"]:
            reasons.append("заполните group и subject")
        if any(len(v) > 300 for v in r.values()):
            reasons.append("значение длиннее 300 символов")
        for field in ["start_time", "end_time"]:
            if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", r[field]):
                reasons.append(f"{field}: используйте ЧЧ:ММ, например 09:00")
        if not reasons and r["end_time"] <= r["start_time"]:
            reasons.append("конец должен быть позже начала в тот же день")
        exact, weekday = r.get("date", ""), r.get("weekday", "").lower()
        day = None
        if exact:
            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", exact):
                    raise ValueError
                day = date.fromisoformat(exact)
            except ValueError:
                reasons.append("date: нужна существующая дата YYYY-MM-DD")
        elif weekday not in [x.lower() for x in DAYS]:
            reasons.append("укажите weekday по-русски или date")
        if exact and weekday:
            reasons.append("заполните только date или только weekday")
        if reasons:
            errors.append(f"Строка {line}: " + "; ".join(reasons))
        else:
            rows.append({**{c:r.get(c, "") for c in COLUMNS}, "date":day,
                         "weekday_num":DAYS.index(weekday.capitalize()) if weekday else None})
    if errors:
        suffix = f"\nИ ещё ошибок: {len(errors)-12}." if len(errors)>12 else ""
        raise ValueError("Файл не применён. Исправьте ошибки:\n" + "\n".join(errors[:12]) + suffix)
    if not rows:
        raise ValueError("В файле нет занятий.")
    result = pd.DataFrame(rows)
    if result.duplicated(subset=COLUMNS).any():
        raise ValueError("В файле есть полные дубликаты занятий. Удалите их.")
    return result

def expand(frame, start, days=7):
    rows = []
    end = start + timedelta(days=days)
    for r in frame.to_dict("records"):
        if r["date"] is not None and pd.notna(r["date"]):
            dates = [r["date"]] if start <= r["date"] < end else []
        else:
            dates = [start+timedelta(days=i) for i in range(days) if (start+timedelta(days=i)).weekday()==r["weekday_num"]]
        rows.extend({**r, "lesson_date":day} for day in dates)
    result = pd.DataFrame(rows, columns=[*frame.columns, "lesson_date"])
    return result.sort_values(["lesson_date", "start_time", "group", "subject"], kind="stable").reset_index(drop=True)

def conflicts(rows):
    messages = set()
    for (day, group), block in rows.groupby(["lesson_date", "group"]):
        active = []
        for r in block.sort_values("start_time").to_dict("records"):
            active = [a for a in active if a["end_time"] > r["start_time"]]
            for a in active:
                messages.add(f"{day:%d.%m} · {group}: «{a['subject']}» и «{r['subject']}» пересекаются.")
            active.append(r)
            if len(messages) >= 50:
                return sorted(messages) + ["Показаны первые 50 конфликтов."]
    return sorted(messages)

def csv_export(frame):
    out = frame.copy()
    for col in out.columns:
        out[col] = out[col].map(lambda v:"'"+v if isinstance(v,str) and v.startswith(("=","+","-","@","\t","\r")) else v)
    return out.to_csv(index=False).encode("utf-8-sig")

def ics_export(rows):
    def esc(v):
        return str(v).replace("\\","\\\\").replace("\r", "").replace("\n","\\n").replace(";","\\;").replace(",","\\,")
    def utc(day, clock):
        return datetime.combine(day,datetime.strptime(clock,"%H:%M").time(),TZ).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Shoqan Day//Timetable//RU","CALSCALE:GREGORIAN"]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for r in rows.to_dict("records"):
        uid=hashlib.sha256("|".join(str(r.get(k,"")) for k in ["lesson_date",*REQUIRED]).encode()).hexdigest()[:32]
        lines += ["BEGIN:VEVENT",f"UID:{uid}@shoqan-day",f"DTSTAMP:{stamp}",f"DTSTART:{utc(r['lesson_date'],r['start_time'])}",f"DTEND:{utc(r['lesson_date'],r['end_time'])}",f"SUMMARY:{esc(r['subject'])}",f"LOCATION:{esc(r['room'])}",f"DESCRIPTION:{esc(r['group']+' · '+r['teacher'])}","END:VEVENT"]
    lines.append("END:VCALENDAR")
    folded=[]
    for line in lines:
        part=""
        for char in line:
            if len((part+char).encode())>75:
                folded.append(part)
                part=" "
            part+=char
        folded.append(part)
    return ("\r\n".join(folded)+"\r\n").encode()
