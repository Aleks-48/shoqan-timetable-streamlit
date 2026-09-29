"""Opt-in browser-local persistence with validation and multi-tab conflict guard."""
import hashlib
import json
from pathlib import Path
import streamlit as st
from user_profile import decode_profile


def restore_pending():
    p=st.session_state.pop('_profile_pending',None)
    if p:
        st.session_state.tasks=p['tasks']
        st.session_state.schedule_raw=p['schedule'].encode('utf-8')
        st.session_state.source_name=p['source_name']
        st.session_state.is_demo=p['is_demo']
        for key in list(st.session_state):
            if key.startswith(('task_','edit_','assignment_','ai_draft')):
                del st.session_state[key]
        prefs=p['preferences']
        for key,value in [('plan_begin',prefs['begin']),('plan_end',prefs['end']),('plan_limit',prefs['limit'])]:
            st.session_state[key]=value
        st.query_params['theme']=prefs['theme']
        st.query_params['group']=prefs['group']
        if st.session_state.pop('_enable_storage_after_load',False):
            st.session_state.persist_enabled=True

def snapshot(theme,group):
    from schedule import parse_csv,csv_export,COLUMNS
    state=st.session_state
    return dict(version=1,tasks=state.tasks,schedule=csv_export(parse_csv(state.schedule_raw)[COLUMNS]).decode('utf-8-sig'),source_name=state.source_name,is_demo=state.is_demo,preferences=dict(theme=theme,group=group,begin=state.get('plan_begin',9),end=state.get('plan_end',20),limit=state.get('plan_limit',120)))

def sync_browser(theme,group):
    component=st.components.v2.component('shoqan_profile_storage',html='<span role="status" aria-live="polite"></span>',js=(Path(__file__).parent/'storage.js').read_text(encoding='utf-8'))
    loaded=st.session_state.get('_storage_loaded',False)
    payload=json.dumps(snapshot(theme,group),ensure_ascii=False,sort_keys=True)
    invalid=''
    try:
        decode_profile(payload)
    except ValueError:
        invalid='Исправьте часы подготовки: начало должно быть раньше конца. Сохранённая копия пока не изменяется.'
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
            st.caption(f"В копии {len(p['tasks'])} заданий. Источник: {p['source_name']}")
            if st.button('Восстановить полную копию'):
                st.session_state._profile_pending=p
                st.rerun()
        except (ValueError,UnicodeError) as exc:
            st.error(str(exc))
