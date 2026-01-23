# ============================================================
# TS4 Mod Priority Auto Update App
# Version: v3.4.3
# Patch: PASSO 1 – Fingerprint da Database do Notion
# ============================================================

import streamlit as st
import requests
import hashlib
import json
import os

# ========================
# CONFIGURAÇÃO
# ========================

APP_VERSION = "v3.4.3"

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

NOTION_TOKEN = st.secrets.get("NOTION_TOKEN")
NOTION_DATABASE_ID = st.secrets.get("NOTION_DATABASE_ID")

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json",
}

# ========================
# UTILIDADES
# ========================

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

# ========================
# PASSO 1 – FINGERPRINT
# ========================

def compute_notion_fingerprint() -> str:
    """
    Gera um fingerprint determinístico da database do Notion
    baseado EXCLUSIVAMENTE nos IDs das páginas.
    """
    page_ids = []
    has_more = True
    start_cursor = None

    while has_more:
        payload = {}
        if start_cursor:
            payload["start_cursor"] = start_cursor

        r = requests.post(
            f"{NOTION_API_URL}/databases/{NOTION_DATABASE_ID}/query",
            headers=HEADERS,
            json=payload,
            timeout=30,
        )

        if r.status_code != 200:
            # Falha aqui NÃO quebra o app
            st.warning("⚠️ Não foi possível calcular fingerprint do Notion.")
            return "fingerprint_error"

        data = r.json()
        results = data.get("results", [])

        for page in results:
            page_id = page.get("id")
            if page_id:
                page_ids.append(page_id)

        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    page_ids.sort()
    joined_ids = ",".join(page_ids)

    return sha256(joined_ids)

# ========================
# INIT SESSION STATE
# ========================

if "notion_fingerprint" not in st.session_state:
    st.session_state.notion_fingerprint = None

# ========================
# APP INIT
# ========================

st.set_page_config(
    page_title="TS4 Mod Priority Auto Update App",
    layout="wide",
)

st.title("TS4 Mod Priority Auto Update App")
st.caption(f"Versão {APP_VERSION}")

# ========================
# FINGERPRINT CHECK
# ========================

current_fingerprint = compute_notion_fingerprint()

if st.session_state.notion_fingerprint is None:
    st.session_state.notion_fingerprint = current_fingerprint
    st.info("📌 Fingerprint inicial da database do Notion calculado.")
else:
    if current_fingerprint != st.session_state.notion_fingerprint:
        st.warning("🔄 A database do Notion foi alterada desde a última execução.")
        st.session_state.notion_fingerprint = current_fingerprint
    else:
        st.success("✅ Database do Notion inalterada.")

# ========================
# PLACEHOLDER DO APP REAL
# ========================

st.divider()

st.markdown(
    """
    ⚙️ **Status atual**
    
    - Phase 1: ativa  
    - Phase 2: ativa  
    - Phase 3 (IA): ativa  
    - Cache de páginas: ❌ (próximo passo)  
    - Cache de decisões: ❌ (passo seguinte)
    """
)

# ========================
# FOOTER
# ========================

st.divider()
st.caption("TS4 Mod Priority Auto Update App · Controle determinístico · Zero achismo")
