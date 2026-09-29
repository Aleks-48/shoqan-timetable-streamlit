import hashlib
import os
import time
import pandas as pd
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError
from ai_service import AIError, Budget, DEFAULT_MODEL, FALLBACK_MODEL, extract
from schedule import COLUMNS, csv_export, parse_csv, expand, conflicts

@st.cache_resource
def budget():
    return Budget()

def setting(name, default=""):
    try:
        return str(st.secrets.get(name, os.environ.get(name, default)))
    except StreamlitSecretNotFoundError:
        return os.environ.get(name, default)

def render(group, today):
    st.subheader("Из фото — в расписание")
    st.write("Загрузите одну страницу расписания. Gemini предложит таблицу, которую можно исправить перед импортом.")
    key, model = setting("GEMINI_API_KEY"), setting("GEMINI_MODEL", DEFAULT_MODEL)
    st.caption("Модель на сервере: " + model + " · резерв при временном отказе: " + FALLBACK_MODEL + ". Всего до трёх попыток.")
    if not key:
        st.info("ИИ готов к подключению: владелец должен добавить ключ Google AI Studio в Streamlit Secrets. CSV-импорт уже работает.")
        with st.expander("Как владельцу включить бесплатный Gemini"):
            st.markdown("1. Создайте ключ в [Google AI Studio](https://aistudio.google.com/apikey) для проекта без платёжного аккаунта.\n2. В Streamlit откройте Manage app → Settings → Secrets.\n3. Добавьте настройки ниже и сохраните. Ключ не публикуйте в GitHub и не отправляйте в чат.")
            st.code('GEMINI_API_KEY = "ваш_ключ"\nGEMINI_MODEL = "'+DEFAULT_MODEL+'"',language="toml")
            st.caption("Бесплатная квота зависит от проекта и региона. Приложение не переключается на другую модель при исчерпании квоты.")
    st.caption("Файл отправляется Google только по кнопке. На бесплатном тарифе данные могут использоваться для улучшения продуктов Google. Загружайте только разрешённое расписание, без списков студентов и оценок.")
    file = st.file_uploader("Фото или PDF · одна страница · до 4 МБ",type=["png","jpg","jpeg","pdf"],key="ai_file",max_upload_size=4)
    fallback = st.text_input("Группа, если не указана в документе",value=group,max_chars=100,key="ai_group")
    consent = st.checkbox("Разрешаю отправить этот файл Google для распознавания",key="ai_consent")
    fingerprint = hashlib.sha256(file.getvalue()+fallback.encode()).hexdigest() if file else None
    if st.session_state.get("ai_fingerprint") != fingerprint:
        st.session_state.pop("ai_draft",None)
        st.session_state.ai_fingerprint = fingerprint
    if st.button("Распознать расписание",type="primary",disabled=not(key and file and consent)):
        try:
            if time.time()-st.session_state.get("ai_last_call",0)<30:
                raise AIError("Между запросами должно пройти 30 секунд.")
            mime = "application/pdf" if file.name.lower().endswith(".pdf") else "image/png" if file.name.lower().endswith(".png") else "image/jpeg"
            budget().claim()
            st.session_state.ai_last_call=time.time()
            with st.spinner("Gemini читает таблицу…"):
                rows,warnings=extract(key,model,file.getvalue(),mime,fallback)
            st.session_state.ai_draft={"rows":rows,"warnings":warnings,"revision":str(time.time_ns())}
        except AIError as exc:
            st.error(str(exc))
    draft=st.session_state.get("ai_draft")
    if draft:
        st.warning("ИИ может ошибаться. Сверьте каждую строку с оригиналом, особенно время, даты и аудитории.")
        for warning in draft["warnings"]:
            st.text(warning)
        st.caption("Заполните weekday (день недели по-русски) ИЛИ date (ГГГГ-ММ-ДД). Время — ЧЧ:ММ. Строки можно добавлять и удалять.")
        edited=st.data_editor(pd.DataFrame(draft["rows"],columns=COLUMNS),hide_index=True,num_rows="dynamic",width="stretch",key="ai_editor_"+draft["revision"])
        try:
            raw=edited.fillna("").to_csv(index=False).encode("utf-8-sig")
            validated=parse_csv(raw)
            for issue in conflicts(expand(validated,today,35)):
                st.warning(issue)
            st.success(f"Формат проверен: {len(validated)} занятий. Содержание требует вашей проверки.")
            st.download_button("Сохранить распознанный CSV",csv_export(validated[COLUMNS]),"recognized-schedule.csv","text/csv")
            confirmed=st.checkbox("Сверил таблицу с оригиналом; заменить текущее расписание",key="ai_confirm_"+hashlib.sha256(raw).hexdigest())
            if st.button("Применить проверенную таблицу",disabled=not confirmed):
                st.session_state.schedule_raw=raw
                st.session_state.source_name="ИИ-импорт: "+file.name
                st.session_state.is_demo=False
                st.session_state.pop("ai_draft",None)
                st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    st.caption("Не более 80 занятий за одно распознавание. Файлы и результаты хранятся только в текущей сессии приложения. Сохраните CSV перед закрытием.")
