"""Per-group schedule profiles and safe CSV imports."""
from copy import deepcopy
import hashlib

from schedule import COLUMNS, csv_export, parse_csv

MAX_IMPORTED_GROUPS = 10
MAX_DEMO_PROFILES = 2


def split_group_schedules(raw, source_name, is_demo=False, tasks_by_group=None):
    """Build one isolated profile per group present in a validated CSV."""
    frame = parse_csv(raw)
    names = sorted(str(name) for name in frame.group.dropna().unique())
    if not names:
        raise ValueError("В расписании нет групп.")
    if not is_demo and len(names) > MAX_IMPORTED_GROUPS:
        raise ValueError(f"В одном импорте допускается не более {MAX_IMPORTED_GROUPS} групп.")
    if is_demo and len(names) > MAX_DEMO_PROFILES:
        raise ValueError(f"Во встроенном демонстрационном CSV допускается не более {MAX_DEMO_PROFILES} групп.")
    profiles = {}
    for name in names:
        subset = frame[frame.group == name].copy()
        subset.attrs.update(frame.attrs)
        key = name
        if key in profiles:
            raise ValueError("Названия групп должны быть уникальными.")
        profiles[key] = {
            "key": key,
            "group": name,
            "schedule": csv_export(subset[COLUMNS]).decode("utf-8-sig"),
            "source_name": str(source_name)[:250],
            "is_demo": bool(is_demo),
            "tasks": deepcopy((tasks_by_group or {}).get(name, [])),
        }
    return profiles


def merge_imported_schedules(profiles, raw, source_name):
    """Atomically add/replace imported groups while preserving their plans."""
    existing = deepcopy(profiles or {})
    incoming = split_group_schedules(raw, source_name, is_demo=False)
    real_names = {item["group"] for item in existing.values() if not item["is_demo"]}
    combined = real_names | {item["group"] for item in incoming.values()}
    if len(combined) > MAX_IMPORTED_GROUPS:
        raise ValueError(
            f"Можно хранить не более {MAX_IMPORTED_GROUPS} импортированных групп. "
            "Текущие данные не изменены."
        )

    for name, profile in incoming.items():
        old_key = next((key for key, item in existing.items()
                        if item["group"] == name and not item["is_demo"]), None)
        if old_key is not None:
            profile["tasks"] = deepcopy(existing[old_key].get("tasks", []))
            del existing[old_key]
        # Keep a same-named synthetic demo profile available as a separate choice.
        demo_key = next((key for key, item in existing.items()
                         if item["group"] == name and item["is_demo"]), None)
        if demo_key is not None:
            new_demo_key = f"Демо · {name}"
            suffix = 2
            while new_demo_key in existing:
                new_demo_key = f"Демо · {name} ({suffix})"
                suffix += 1
            existing[demo_key]["key"] = new_demo_key
            existing[new_demo_key] = existing.pop(demo_key)
        if name in existing:
            raise ValueError("Не удалось безопасно сопоставить импортированную группу.")
        existing[name] = profile
    return existing


def add_demo_schedule(profiles, raw, source_name="Демонстрационный набор"):
    """Add or restore bundled synthetic demo groups without losing their plans."""
    existing = deepcopy(profiles or {})
    incoming = split_group_schedules(raw, source_name, is_demo=True)
    for group, profile in incoming.items():
        current_demo = next((key for key, item in existing.items()
                             if item["group"] == group and item["is_demo"]), None)
        if current_demo is not None:
            profile["tasks"] = deepcopy(existing[current_demo].get("tasks", []))
            del existing[current_demo]
        key = group if group not in existing else f"Демо · {group}"
        suffix = 2
        while key in existing:
            key = f"Демо · {group} ({suffix})"
            suffix += 1
        profile["key"] = key
        existing[key] = profile
    return existing


def import_schedules_into_state(state, raw, source_name, preferred_group=""):
    """Commit an already-confirmed CSV into the isolated group registry."""
    remember_active_profile(state)
    frame = parse_csv(raw)
    names = sorted(str(name) for name in frame.group.unique())
    updated = merge_imported_schedules(state.get("group_profiles", {}), raw, source_name)
    target = preferred_group if preferred_group in names else names[0]
    state.group_profiles = updated
    state._active_group_key = ""
    state._requested_group_key = target
    state._group_import_notice = f"Групп добавлено или обновлено: {len(names)}. Сохранённые планы не перемещались."
    return names


def ensure_profile_keys(profiles):
    """Normalize keys after profile loading without changing schedule data."""
    result = {}
    for key, value in (profiles or {}).items():
        profile = deepcopy(value)
        profile["key"] = str(key)
        result[str(key)] = profile
    return result


def remember_active_profile(state):
    key = state.get("_active_group_key")
    profile = state.get("group_profiles", {}).get(key)
    if not profile:
        return
    try:
        frame = parse_csv(state.schedule_raw)
        if set(frame.group.astype(str).unique()) == {profile["group"]}:
            profile["schedule"] = csv_export(frame).decode("utf-8-sig")
    except (ValueError, TypeError, AttributeError):
        pass
    profile["source_name"] = state.get("source_name", profile["source_name"])
    profile["is_demo"] = bool(state.get("is_demo", profile["is_demo"]))
    profile["tasks"] = state.get("tasks", profile.get("tasks", []))


def load_group_profile(state, key):
    """Load one group as the legacy UI aliases used by the calendar and planner."""
    profile = state.group_profiles[key]
    state._active_group_key = key
    state.schedule_raw = profile["schedule"].encode("utf-8-sig")
    state.source_name = profile["source_name"]
    state.is_demo = profile["is_demo"]
    state.tasks = profile.setdefault("tasks", [])
    state._active_schedule_guard = hashlib.sha256(state.schedule_raw).hexdigest()
    for widget_key in list(state):
        if widget_key.startswith(("task_", "edit_", "assignment_", "ai_draft", "plan_block_")):
            del state[widget_key]


def set_active_tasks(state, tasks):
    state.tasks = tasks
    key = state.get("_active_group_key")
    if key in state.get("group_profiles", {}):
        state.group_profiles[key]["tasks"] = tasks


def initialize_group_profiles(state, default_raw, preferred_group=""):
    """Migrate legacy single-schedule state, then safely follow profile selection."""
    profiles = state.get("group_profiles")
    if not isinstance(profiles, dict) or not profiles:
        raw = state.get("schedule_raw", default_raw)
        source = state.get("source_name", "Демонстрационный набор")
        demo = state.get("is_demo", source.startswith("Демонстрационный"))
        old_tasks = state.get("tasks", [])
        profiles = split_group_schedules(raw, source, demo)
        groups = [item["group"] for item in profiles.values()]
        selected = preferred_group if preferred_group in groups else groups[0]
        profiles[selected]["tasks"] = old_tasks
        state.group_profiles = profiles
        state._active_group_key = ""
        state.active_group_selector = selected
        load_group_profile(state, selected)
    else:
        state.group_profiles = ensure_profile_keys(profiles)
        requested = state.pop("_requested_group_key", None)
        current = state.get("active_group_selector") or state.get("_active_group_key")
        if requested in state.group_profiles:
            current = requested
            state.active_group_selector = requested
        if current not in state.group_profiles:
            current = next(iter(state.group_profiles))
            state.active_group_selector = current
        loaded = state.get("_active_group_key")
        if loaded != current:
            remember_active_profile(state)
            load_group_profile(state, current)
        else:
            profile = state.group_profiles[current]
            desired_raw = profile["schedule"].encode("utf-8-sig")
            alias_changed = state.get("_active_schedule_guard") != hashlib.sha256(state.schedule_raw).hexdigest()
            profile_changed = state.schedule_raw != desired_raw
            if profile_changed and requested is not None:
                # The import has already captured the old profile; load its newly
                # confirmed source while preserving the profile's isolated tasks.
                load_group_profile(state, current)
            elif alias_changed:
                # Preserve compatibility with a restored v1 profile or callers that
                # replace schedule_raw directly: import it as isolated group profiles.
                tasks = state.get("tasks", [])
                imported = merge_imported_schedules(state.group_profiles, state.schedule_raw,
                                                    state.get("source_name", "Импорт расписания"))
                raw_frame = parse_csv(state.schedule_raw)
                target = profile["group"] if profile["group"] in raw_frame.group.astype(str).unique() else str(raw_frame.group.iloc[0])
                imported[target]["tasks"] = tasks
                state.group_profiles = imported
                state.active_group_selector = target
                state._active_group_key = ""
                load_group_profile(state, target)
            else:
                profile["tasks"] = state.get("tasks", profile.get("tasks", []))
    return state.group_profiles
