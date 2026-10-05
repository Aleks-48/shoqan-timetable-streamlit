"""Local, constraint-checked proposal builder for a synthetic academic timetable.

This is a bounded deterministic heuristic/search aid, not an official scheduler.
It has no network or LLM dependencies.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
from collections import defaultdict


MAX_GROUPS = 10
MAX_REQUEST_ROWS = 100
MAX_MEETINGS = 30
MAX_ROOMS = 12
MAX_UNAVAILABLE_ROWS = 100
MAX_INPUT_BYTES = 200_000
SEARCH_NODE_BUDGET = 800
LESSON_MINUTES = 50
BUFFER_MINUTES = 10
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
DAY_INDEX = {day: index for index, day in enumerate(DAYS)}
_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def _minutes(value: str, field: str) -> int:
    if not isinstance(value, str) or not _TIME_RE.fullmatch(value):
        raise ValueError(f"{field}: используйте время ЧЧ:ММ, например 09:00.")
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def _label(value: str, field: str, limit: int = 100) -> str:
    value = value.strip()
    if not value or len(value) > limit or any(ord(char) < 32 for char in value):
        raise ValueError(f"{field}: заполните короткое название (до {limit} символов).")
    return value


def _csv_rows(raw: str, label: str, required: tuple[str, ...], max_rows: int):
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_INPUT_BYTES:
        raise ValueError(f"{label}: размер CSV не должен превышать 200 КБ.")
    try:
        reader = csv.DictReader(io.StringIO(raw, newline=""), strict=True)
        headers = [str(item or "").strip().lower() for item in (reader.fieldnames or [])]
        if not headers or len(headers) != len(set(headers)):
            raise ValueError(f"{label}: укажите уникальные заголовки CSV.")
        missing = [item for item in required if item not in headers]
        extra = [item for item in headers if item not in required]
        if missing or extra:
            detail = []
            if missing:
                detail.append("нет колонок: " + ", ".join(missing))
            if extra:
                detail.append("неизвестные колонки: " + ", ".join(extra))
            raise ValueError(f"{label}: " + "; ".join(detail) + ".")
        rows = []
        for row in reader:
            if not row or not any(str(value or "").strip() for value in row.values()):
                continue
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"{label}, строка {reader.line_num}: число ячеек не совпадает с заголовком.")
            rows.append({str(key).strip().lower(): str(value).strip() for key, value in row.items()})
            if len(rows) > max_rows:
                raise ValueError(f"{label}: максимум {max_rows} строк.")
        return rows
    except csv.Error as exc:
        raise ValueError(f"{label}: проверьте кавычки и разделители CSV.") from exc


def parse_proposal_input(requests_csv: str, rooms_csv: str, unavailable_csv: str,
                         start_hour: int = 9, end_hour: int = 18) -> dict:
    """Validate editable CSV inputs and expand weekly session counts."""
    if type(start_hour) is not int or type(end_hour) is not int or not 6 <= start_hour < end_hour <= 20:
        raise ValueError("Период должен быть целым часовым интервалом от 06:00 до 20:00.")
    if end_hour - start_hour < 1:
        raise ValueError("Период должен включать хотя бы один часовой слот.")

    request_rows = _csv_rows(
        requests_csv, "Заявки на занятия",
        ("group", "subject", "teacher", "room_type", "students", "sessions_per_week"),
        MAX_REQUEST_ROWS,
    )
    room_rows = _csv_rows(rooms_csv, "Аудитории", ("room", "room_type", "capacity", "building"), MAX_ROOMS)
    unavailable_rows = _csv_rows(
        unavailable_csv, "Окна недоступности",
        ("resource_type", "resource", "day", "start_time", "end_time"), MAX_UNAVAILABLE_ROWS,
    )
    if not request_rows:
        raise ValueError("Добавьте хотя бы одну заявку на занятие.")
    if not room_rows:
        raise ValueError("Добавьте хотя бы одну аудиторию.")

    requests = []
    groups = set()
    total_meetings = 0
    for row_index, row in enumerate(request_rows, 1):
        group = _label(row["group"], f"Заявки, строка {row_index}, группа", 80)
        subject = _label(row["subject"], f"Заявки, строка {row_index}, предмет", 120)
        teacher = _label(row["teacher"], f"Заявки, строка {row_index}, преподаватель", 100)
        room_type = _label(row["room_type"], f"Заявки, строка {row_index}, тип аудитории", 40).casefold()
        if room_type != "any" and not re.fullmatch(r"[\w -]{1,40}", room_type, re.UNICODE):
            raise ValueError(f"Заявки, строка {row_index}: некорректный тип аудитории.")
        try:
            students = int(row["students"])
            sessions = int(row["sessions_per_week"])
        except ValueError as exc:
            raise ValueError(f"Заявки, строка {row_index}: число студентов и занятий должно быть целым.") from exc
        if not 1 <= students <= 500 or not 1 <= sessions <= 5:
            raise ValueError(f"Заявки, строка {row_index}: студентов 1–500, занятий в неделю 1–5.")
        groups.add(group.casefold())
        total_meetings += sessions
        requests.append(dict(group=group, subject=subject, teacher=teacher,
                             room_type=room_type, students=students, sessions_per_week=sessions,
                             row_index=row_index))
    if len(groups) > MAX_GROUPS:
        raise ValueError(f"В одном предложении допускается не более {MAX_GROUPS} разных групп.")
    if total_meetings > MAX_MEETINGS:
        raise ValueError(f"Суммарно допускается не более {MAX_MEETINGS} занятий в неделю.")

    rooms = []
    room_names = set()
    for row_index, row in enumerate(room_rows, 1):
        name = _label(row["room"], f"Аудитории, строка {row_index}, название", 80)
        key = name.casefold()
        if key in room_names:
            raise ValueError(f"Аудитории: название «{name}» повторяется.")
        room_names.add(key)
        room_type = _label(row["room_type"], f"Аудитории, строка {row_index}, тип", 40).casefold()
        try:
            capacity = int(row["capacity"])
        except ValueError as exc:
            raise ValueError(f"Аудитории, строка {row_index}: вместимость должна быть целым числом.") from exc
        if not 1 <= capacity <= 2_000:
            raise ValueError(f"Аудитории, строка {row_index}: вместимость должна быть от 1 до 2000.")
        building = _label(row["building"], f"Аудитории, строка {row_index}, корпус", 80)
        rooms.append(dict(room=name, key=key, room_type=room_type, capacity=capacity, building=building))

    unavailable = []
    resource_names = {"room": room_names}
    for request in requests:
        resource_names.setdefault("group", set()).add(request["group"].casefold())
        resource_names.setdefault("teacher", set()).add(request["teacher"].casefold())
    for row_index, row in enumerate(unavailable_rows, 1):
        resource_type = row["resource_type"].casefold()
        if resource_type not in ("group", "teacher", "room"):
            raise ValueError(f"Окна недоступности, строка {row_index}: тип ресурса — group, teacher или room.")
        resource = _label(row["resource"], f"Окна недоступности, строка {row_index}, ресурс", 100)
        if resource.casefold() not in resource_names[resource_type]:
            raise ValueError(f"Окна недоступности, строка {row_index}: ресурс «{resource}» не найден среди заявок/аудиторий.")
        day = next((item for item in DAYS if item.casefold() == row["day"].casefold()), None)
        if day is None:
            raise ValueError(f"Окна недоступности, строка {row_index}: используйте Monday–Friday.")
        start = _minutes(row["start_time"], f"Окна недоступности, строка {row_index}, начало")
        end = _minutes(row["end_time"], f"Окна недоступности, строка {row_index}, конец")
        if end <= start:
            raise ValueError(f"Окна недоступности, строка {row_index}: конец должен быть позже начала.")
        unavailable.append(dict(resource_type=resource_type, resource=resource,
                                key=resource.casefold(), day=day, start=start, end=end))

    slots = []
    for day in DAYS:
        for hour in range(start_hour, end_hour):
            start = hour * 60
            slots.append(dict(day=day, start=start, end=start + LESSON_MINUTES))
    occurrences = []
    for request in requests:
        for session_index in range(1, request["sessions_per_week"] + 1):
            occurrence = {key: request[key] for key in
                          ("group", "subject", "teacher", "room_type", "students", "row_index")}
            occurrence["id"] = f"r{request['row_index']:03}-s{session_index:02}"
            occurrence["session_index"] = session_index
            occurrences.append(occurrence)
    occurrences.sort(key=lambda item: item["id"])
    return dict(requests=requests, rooms=rooms, unavailable=unavailable,
                occurrences=occurrences, slots=slots, start_hour=start_hour, end_hour=end_hour)


def _matches(resource_type: str, resource: str, day: str, start: int, end: int,
             unavailable: list[dict]) -> bool:
    key = resource.casefold()
    return any(item["resource_type"] == resource_type and item["key"] == key and item["day"] == day
               and start < item["end"] + BUFFER_MINUTES and end + BUFFER_MINUTES > item["start"]
               for item in unavailable)


def _room_options(problem: dict, occurrence: dict) -> list[dict]:
    return [room for room in problem["rooms"]
            if (occurrence["room_type"] == "any" or room["room_type"] == occurrence["room_type"])
            and room["capacity"] >= occurrence["students"]]


def _fixed_options(problem: dict, occurrence: dict, room: dict,
                   templates: dict[str, list[dict]] | None = None) -> list[dict]:
    options = []
    source = (templates or {}).get(room["key"])
    if source is None:
        source = [dict(day=slot["day"], start=slot["start"], end=slot["end"], room=room)
                  for slot in problem["slots"]]
    for option in source:
        day, start, end = option["day"], option["start"], option["end"]
        if (_matches("group", occurrence["group"], day, start, end, problem["unavailable"])
                or _matches("teacher", occurrence["teacher"], day, start, end, problem["unavailable"])
                or _matches("room", room["room"], day, start, end, problem["unavailable"])):
            continue
        options.append(option)
    return options


def _interval_conflict(start: int, end: int, other_start: int, other_end: int) -> bool:
    return start < other_end + BUFFER_MINUTES and end + BUFFER_MINUTES > other_start


def _resource_key(occurrence: dict, option: dict) -> tuple[tuple[str, str, str], ...]:
    return (("group", occurrence["group"].casefold(), option["day"]),
            ("teacher", occurrence["teacher"].casefold(), option["day"]),
            ("room", option["room"]["key"], option["day"]))


def _available(occurrence: dict, option: dict, busy: dict) -> bool:
    for key in _resource_key(occurrence, option):
        for start, end in busy.get(key, ()):
            if _interval_conflict(option["start"], option["end"], start, end):
                return False
    return True


def _public_meeting(occurrence: dict, option: dict) -> dict:
    return dict(id=occurrence["id"], group=occurrence["group"], subject=occurrence["subject"],
                teacher=occurrence["teacher"], room_type=occurrence["room_type"],
                students=occurrence["students"], day=option["day"],
                start_time=f"{option['start']//60:02}:{option['start']%60:02}",
                end_time=f"{option['end']//60:02}:{option['end']%60:02}",
                room=option["room"]["room"], building=option["room"]["building"],
                status="placed")


def verify_proposal(problem: dict, meetings: list[dict]) -> dict:
    """Independently check every placement against demand and resource constraints."""
    issues = []
    expected = {item["id"]: item for item in problem["occurrences"]}
    rooms = {item["room"].casefold(): item for item in problem["rooms"]}
    seen = set()
    parsed = []
    for meeting in meetings:
        ident = meeting.get("id")
        if ident not in expected:
            issues.append(f"Неизвестный идентификатор занятия: {ident}.")
            continue
        if ident in seen:
            issues.append(f"Занятие {ident} размещено повторно.")
            continue
        seen.add(ident)
        request = expected[ident]
        if any(meeting.get(field) != request[field] for field in
               ("group", "subject", "teacher", "room_type", "students")):
            issues.append(f"Данные размещения {ident} не совпадают с заявкой.")
        room = rooms.get(str(meeting.get("room", "")).casefold())
        day = meeting.get("day")
        try:
            start = _minutes(meeting.get("start_time"), f"Занятие {ident}, начало")
            end = _minutes(meeting.get("end_time"), f"Занятие {ident}, конец")
        except ValueError as exc:
            issues.append(str(exc))
            continue
        if day not in DAYS or end - start != LESSON_MINUTES:
            issues.append(f"Занятие {ident}: неверный день или длительность; ожидалось 50 минут.")
            continue
        if not any(slot["day"] == day and slot["start"] == start and slot["end"] == end
                   for slot in problem["slots"]):
            issues.append(f"Занятие {ident}: время вне заданной сетки.")
        if room is None:
            issues.append(f"Занятие {ident}: аудитория не найдена.")
        elif ((request["room_type"] != "any" and room["room_type"] != request["room_type"])
              or room["capacity"] < request["students"]):
            issues.append(f"Занятие {ident}: аудитория не подходит по типу или вместимости.")
        if (_matches("group", request["group"], day, start, end, problem["unavailable"])
                or _matches("teacher", request["teacher"], day, start, end, problem["unavailable"])
                or (room is not None and _matches("room", room["room"], day, start, end, problem["unavailable"]))):
            issues.append(f"Занятие {ident}: пересечение с заданным окном недоступности.")
        parsed.append((meeting, request, room, day, start, end))

    for index, left in enumerate(parsed):
        lm, lr, lroom, lday, ls, le = left
        for rm, rr, rroom, rday, rs, re_ in parsed[index + 1:]:
            if lday != rday or not _interval_conflict(ls, le, rs, re_):
                continue
            shared = []
            if lr["group"].casefold() == rr["group"].casefold():
                shared.append("группа")
            if lr["teacher"].casefold() == rr["teacher"].casefold():
                shared.append("преподаватель")
            if lroom and rroom and lroom["key"] == rroom["key"]:
                shared.append("аудитория")
            if shared:
                issues.append(f"Пересечение {lm['id']} и {rm['id']}: совпадает ресурс — {', '.join(shared)}.")
    return dict(valid=not issues, issues=issues, placed_count=len(seen),
                expected_count=len(expected), complete=(len(seen) == len(expected)))


def _availability_index(problem: dict) -> dict:
    busy = defaultdict(list)
    for item in problem["unavailable"]:
        busy[(item["resource_type"], item["key"], item["day"])].append((item["start"], item["end"]))
    return busy


def _place(busy: dict, occurrence: dict, option: dict):
    keys = _resource_key(occurrence, option)
    for key in keys:
        busy[key].append((option["start"], option["end"]))
    return keys


def _unplace(busy: dict, keys: tuple, option: dict):
    for key in keys:
        busy[key].remove((option["start"], option["end"]))


def generate_proposal(problem: dict, node_budget: int = SEARCH_NODE_BUDGET) -> dict:
    """Try a bounded full search, then return the best deterministic partial draft found."""
    if type(node_budget) is not int or node_budget < 1:
        raise ValueError("Лимит поиска должен быть положительным целым числом.")
    occurrences = problem["occurrences"]
    templates = {room["key"]: [dict(day=slot["day"], start=slot["start"],
                                    end=slot["end"], room=room)
                                for slot in problem["slots"]]
                 for room in problem["rooms"]}
    rooms_by_occurrence = {item["id"]: _room_options(problem, item) for item in occurrences}
    domains = {item["id"]: [option for room in rooms_by_occurrence[item["id"]]
                           for option in _fixed_options(problem, item, room, templates)] for item in occurrences}
    order = sorted(occurrences, key=lambda item: (len(domains[item["id"]]), item["group"].casefold(),
                                                   item["teacher"].casefold(), item["id"]))
    busy = _availability_index(problem)
    assignment = {}
    nodes = 0
    budget_hit = False

    def search(index: int) -> bool:
        nonlocal nodes, budget_hit
        if index == len(order):
            return True
        if nodes >= node_budget:
            budget_hit = True
            return False
        nodes += 1
        occurrence = order[index]
        for option in domains[occurrence["id"]]:
            if not _available(occurrence, option, busy):
                continue
            assignment[occurrence["id"]] = option
            keys = _place(busy, occurrence, option)
            if search(index + 1):
                return True
            _unplace(busy, keys, option)
            assignment.pop(occurrence["id"], None)
            if budget_hit:
                return False
        return False

    full_found = search(0)
    if full_found:
        selected = dict(assignment)
    else:
        # Multiple deterministic greedy orders improve coverage, but a partial
        # result is never described as proof that a full plan cannot exist.
        trials = [list(occurrences), list(reversed(occurrences)), list(order), list(reversed(order))]
        best = {}
        for trial_index, trial in enumerate(trials):
            trial_busy = _availability_index(problem)
            placed = {}
            for occurrence in trial:
                options = domains[occurrence["id"]]
                if trial_index % 2:
                    options = list(reversed(options))
                for option in options:
                    if _available(occurrence, option, trial_busy):
                        placed[occurrence["id"]] = option
                        _place(trial_busy, occurrence, option)
                        break
            if (len(placed) > len(best) or
                    (len(placed) == len(best) and tuple(sorted(placed)) < tuple(sorted(best)))):
                best = placed
        selected = best

    meetings = [_public_meeting(item, selected[item["id"]]) for item in occurrences if item["id"] in selected]
    meetings.sort(key=lambda item: (DAY_INDEX[item["day"]], item["start_time"], item["group"].casefold(), item["subject"].casefold()))
    verification = verify_proposal(problem, meetings)
    unplaced = []
    for occurrence in occurrences:
        if occurrence["id"] in selected:
            continue
        if not rooms_by_occurrence[occurrence["id"]]:
            reason = "Нет аудитории нужного типа или вместимости."
        elif not domains[occurrence["id"]]:
            reason = "Все окна периода закрыты заданной доступностью ресурсов."
        else:
            reason = "Место не найдено в этом поиске. Это не доказывает невозможность полного плана; пересмотрите ограничения или повторите генерацию."
        unplaced.append({**{key: occurrence[key] for key in
                            ("id", "group", "subject", "teacher", "room_type", "students")},
                         "reason": reason})
    status = "complete" if verification["valid"] and verification["complete"] else "partial"
    return dict(status=status, meetings=meetings, unplaced=unplaced,
                search_nodes=nodes, search_limited=budget_hit,
                verification=verification, problem_fingerprint=problem_fingerprint(problem))


def problem_fingerprint(problem: dict) -> str:
    payload = repr((problem["requests"], problem["rooms"], problem["unavailable"],
                    problem["start_hour"], problem["end_hour"])).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def export_proposal_csv(problem: dict, proposal: dict) -> bytes:
    """Export only an independently validated draft; partial rows are explicit."""
    checked = verify_proposal(problem, proposal.get("meetings", []))
    if not checked["valid"]:
        raise ValueError("Экспорт остановлен: независимая проверка нашла конфликт в черновике.")
    placed = {item["id"]: item for item in proposal.get("meetings", [])}
    waiting = {item["id"]: item for item in proposal.get("unplaced", [])}
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(["group", "subject", "teacher", "room_type", "students", "day",
                     "start_time", "end_time", "room", "building", "status", "note"])
    for occurrence in problem["occurrences"]:
        if occurrence["id"] in placed:
            meeting = placed[occurrence["id"]]
            row = [meeting["group"], meeting["subject"], meeting["teacher"], meeting["room_type"],
                   meeting["students"], meeting["day"], meeting["start_time"], meeting["end_time"],
                   meeting["room"], meeting["building"], "placed", ""]
        else:
            missing = waiting.get(occurrence["id"], {})
            row = [occurrence["group"], occurrence["subject"], occurrence["teacher"],
                   occurrence["room_type"], occurrence["students"], "", "", "", "", "",
                   "not_placed", missing.get("reason", "Нет размещения в черновике.")]
        safe = ["'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")) else value
                for value in row]
        writer.writerow(safe)
    return output.getvalue().encode("utf-8-sig")
