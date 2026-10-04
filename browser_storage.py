"""Opt-in browser-local persistence with validation and multi-tab conflict guard."""
import hashlib
import json
from pathlib import Path
import streamlit as st
from user_profile import decode_profile
from group_profiles import split_group_schedules, load_group_profile, remember_active_profile


def restore_pending(state=None):
    state=st.session_state if state is None else state
    p=state.pop('_profile_pending',None)
    if p:
        if p['version']==2:
            state.group_profiles=p['profiles']
            active=p['active_group']
        else:
            group=p['preferences']['group']
            profiles=split_group_schedules(
                p['schedule'].encode('utf-8'),p['source_name'],p['is_demo'],tasks_by_group={group:p['tasks']})
            active=group if group in profiles else next(iter(profiles))
            state.group_profiles=profiles
        state.active_group_selector=active
        state._active_group_key=''
        state._requested_group_key=active
        for key in list(state):
            if key.startswith(('task_','edit_','assignment_','ai_draft','plan_block_')):
                del state[key]
        prefs=p['preferences']
        for key,value in [('plan_begin',prefs['begin']),('plan_end',prefs['end']),('plan_limit',prefs['limit'])]:
            state[key]=value
        query_params=state.get('query_params')
        if query_params is None:
            query_params=st.query_params
        query_params['theme']=prefs.get('theme','Светлая')
        query_params['group']=active if p['version']==2 else prefs['group']
        if state.pop('_enable_storage_after_load',False):
            state.persist_enabled=True

def snapshot(theme,group,state=None):
    from schedule import parse_csv,csv_export
    state=st.session_state if state is None else state
    remember_active_profile(state)
    profiles=state.get('group_profiles',{})
    return dict(version=2,profiles=profiles,active_group=state.get('_active_group_key',group),
                preferences=dict(theme=theme,begin=state.get('plan_begin',9),
                                 end=state.get('plan_end',20),limit=state.get('plan_limit',120)))

def profile_validation_error(payload):
    try:
        decode_profile(payload)
    except ValueError as exc:
        return str(exc) or 'Копия не прошла проверку.'
    return ''

def sync_browser(theme,group):
    component=st.components.v2.component('shoqan_profile_storage',html='<span role="status" aria-live="polite"></span>',js=(Path(__file__).parent/'storage.js').read_text(encoding='utf-8'))
    loaded=st.session_state.get('_storage_loaded',False)
    payload=json.dumps(snapshot(theme,group),ensure_ascii=False,sort_keys=True)
    invalid=profile_validation_error(payload)
    revision=hashlib.sha256(payload.encode()).hexdigest()
    enabled=st.session_state.get('persist_enabled',False)
    error=st.session_state.get('_storage_error','') or invalid
    result=component(key='profile_bridge',data=dict(mode=('blocked' if error else 'sync') if loaded else 'load',error=error,enabled=enabled,payload=payload,revision=revision,expected=st.session_state.get('_storage_revision','')),on_loaded_change=lambda:None,on_receipt_change=lambda:None)
    initial=result.get('loaded')
    if not loaded and initial is not None:
        st.session_state._storage_loaded=True
        st.session_state._storage_revision=initial.get('revision','')
        if initial.get('error'):
            st.session_state._storage_error=initial['error']
        elif initial.get('payload'):
            try:
                st.session_state._profile_pending=decode_profile(initial['payload'])
                st.session_state._enable_storage_after_load=True
            except ValueError:
                st.session_state._storage_error='Сохранённая копия повреждена. Автосохранение отключено; скачайте текущие данные.'
        st.rerun()
    receipt=result.get('receipt')
    if receipt:
        if receipt.get('ok'):
            st.session_state._storage_revision=receipt['revision']
        elif receipt.get('error'):
            st.session_state._storage_error=receipt['error']
    if st.session_state.get('_storage_error'):
        st.warning(st.session_state._storage_error)

def render_controls(theme,group):
    st.subheader('Мои данные на этом устройстве')
    st.checkbox('Сохранять расписание и задания в этом браузере',key='persist_enabled')
    st.caption('Включайте только на личном устройстве. Копия доступна пользователям этого браузера. Очистка данных браузера или приватный режим могут удалить её. Между устройствами переносите файл копии; облачной синхронизации нет.')
    raw=json.dumps(snapshot(theme,group),ensure_ascii=False,indent=2)
    st.download_button('Скачать полную копию',raw.encode('utf-8'),'shoqan-profile.json','application/json')
    uploaded=st.file_uploader('Перенести полную копию с другого устройства',type=['json'],key='profile_upload',max_upload_size=3)
    if uploaded:
        try:
            p=decode_profile(uploaded.getvalue().decode('utf-8-sig'))
            if p['version']==2:
                task_count=sum(len(item['tasks']) for item in p['profiles'].values())
                st.caption(f"В копии {len(p['profiles'])} групп и {task_count} заданий.")
            else:
                st.caption(f"В копии {len(p['tasks'])} заданий. Источник: {p['source_name']}")
            if st.button('Восстановить полную копию'):
                st.session_state._profile_pending=p
                st.rerun()
        except (ValueError,UnicodeError) as exc:
            st.error(str(exc))
