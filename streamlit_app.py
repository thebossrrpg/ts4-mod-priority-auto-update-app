# ============================================================
# TS4 Mod Analyzer — Phase 1 → Phase 4 (Hugging Face IA)
# Version: v1.6 — Phase 4 Priority Classification (Closed)
#
# Contract:
# - Phase 1: Identity extraction (URL + HTML)
# - Phase 2: Deterministic Notion match (notioncache)
# - Phase 3: IA as SIGNAL only (never decides)
# - Phase 4: Priority classification (AUTO / MANUAL)
#
# ADDITIVE ONLY — Contract preserved
# ============================================================


import streamlit as st
import requests
import re
import json
import hashlib
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from notion_client import Client
from datetime import datetime, timezone

# =========================
# PAGE CONFIG
# =========================

st.set_page_config(
    page_title="TS4 Mod Analyzer — Phase 4 · v1.6",
    layout="centered"
)

st.markdown(
    """
    <style>
    .global-footer {
        position: fixed;
        bottom: 0;
        left: 0;
        width: 100%;
        background-color: rgba(17, 24, 39, 0.95);
        text-align: center;
        padding: 0.75rem 0;
        font-size: 0.8rem;
        color: #9ca3af;
        z-index: 999;
    }
    .block-container { padding-bottom: 4rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================
# SESSION STATE
# =========================

for key, default in {
    "analysis_result": None,
    "ai_logs": [],
    "decision_log": [],
    "matchcache": {},
    "notfoundcache": {},
    "notioncache": {},
    "phase_4_cache": {},
    "notioncache_loaded": False,
    "snapshot_loaded": False,
    "notion_fingerprint": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# =========================
# CONFIG
# =========================

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

NOTION_TOKEN = st.secrets["notion"]["token"]
NOTION_DATABASE_ID = st.secrets["notion"]["database_id"]
notion = Client(auth=NOTION_TOKEN)

HF_TOKEN = st.secrets["huggingface"]["token"]
HF_HEADERS = {
    "Authorization": f"Bearer {HF_TOKEN}",
    "Content-Type": "application/json"
}
HF_MODEL = "https://api-inference.huggingface.co/models/google/flan-t5-base"

# =========================
# UTILS
# =========================

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def now():
    return datetime.now(timezone.utc).isoformat()

def compute_notion_fingerprint() -> str:
    pages = st.session_state.notioncache.get("pages", {})
    return sha256(",".join(sorted(pages.keys()))) if pages else "empty"

# =========================
# SNAPSHOT
# =========================

def build_snapshot():
    return {
        "meta": {
            "app": "TS4 Mod Analyzer",
            "version": "v1.6",
            "created_at": now(),
            "phase_2_fingerprint": st.session_state.notion_fingerprint,
        },
        "phase_2_cache": st.session_state.notioncache,
        "phase_3_cache": st.session_state.matchcache,
        "phase_4_cache": st.session_state.phase_4_cache,
        "canonical_log": st.session_state.decision_log,
    }

# =========================
# PHASE 4 — CLASSIFICATION
# =========================

def build_phase4_prompt(notion_text: str):
    return f"""
You are classifying a The Sims 4 mod priority.

Scoring (0–8):
- Removal risk (0–2)
- Framework dependency (0–2)
- Essential gameplay impact (0–4)

Priority mapping:
0–1 → Priority 1
2–3 → Priority 2
4–5 → Priority 3
6–7 → Priority 4
8 → Priority 5

Return STRICT JSON:
{{
  "priority": int,
  "subcategory": "string or null",
  "score": int,
  "confidence": float
}}

Text:
\"\"\"
{notion_text}
\"\"\"
"""

def run_phase4_ai(notion_text: str):
    r = requests.post(
        HF_MODEL,
        headers=HF_HEADERS,
        json={"inputs": build_phase4_prompt(notion_text), "parameters": {"temperature": 0}},
        timeout=30,
    )
    data = r.json()
    text = data[0]["generated_text"] if isinstance(data, list) else data.get("generated_text")
    return json.loads(text)

def validate_phase4(result: dict):
    if not (0 <= result["score"] <= 8):
        raise ValueError("Invalid score")
    if not (1 <= result["priority"] <= 5):
        raise ValueError("Invalid priority")

def append_phase4_notes(page_id: str, subcategory: str | None):
    note = "[TS4 AUTO] Subcategoria: " + subcategory if subcategory else "[TS4 AUTO] Classificado automaticamente"
    notion.pages.update(
        page_id=page_id,
        properties={
            "Notes": {
                "rich_text": [{"type": "text", "text": {"content": note}}]
            }
        }
    )

# =========================
# UI
# =========================

st.title("TS4 Mod Analyzer — Phase 4")
st.caption("Classificação de prioridade · Auditável")

result = st.session_state.analysis_result
if result and result.get("decision") == "FOUND":
    identity_hash = result["identity_hash"]

    if identity_hash not in st.session_state.phase_4_cache:
        if st.button("Classificar prioridade (Phase 4)"):
            page_id = result["notion_id"]
            page = notion.pages.retrieve(page_id=page_id)

            text_blocks = [
                b["paragraph"]["rich_text"][0]["plain_text"]
                for b in page["properties"].values()
                if b["type"] == "rich_text" and b["rich_text"]
            ]
            notion_text = "\n".join(text_blocks)

            ai_result = run_phase4_ai(notion_text)
            validate_phase4(ai_result)

            st.session_state.phase_4_cache[identity_hash] = {
                "timestamp": now(),
                "priority": ai_result["priority"],
                "subcategory": ai_result.get("subcategory"),
                "score": ai_result["score"],
                "confidence": ai_result["confidence"],
                "source": "AUTO",
            }

            append_phase4_notes(page_id, ai_result.get("subcategory"))
            st.success("Phase 4 concluída")

# =========================
# FOOTER
# =========================

st.markdown(
    """
    <div class="global-footer">
        Criado por Akin (@UnpaidSimmer)
        <div style="font-size:0.7rem;">v1.6 · Phase 4</div>
    </div>
    """,
    unsafe_allow_html=True,
)
