# ============================================================
# TS4 Mod Analyzer — Phase 1 → Phase 4
# Version: v1.6.1 — Priority Classification
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
# PAGE CONFIG (sempre primeiro)
# =========================

st.set_page_config(
    page_title="TS4 Mod Analyzer — Phase 4 · v1.6.1",
    layout="centered"
)

# =========================
# GLOBAL STYLE
# =========================

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
    .block-container {
        padding-bottom: 4rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================
# SESSION STATE
# =========================

DEFAULT_KEYS = {
    "analysis_result": None,
    "ai_logs": [],
    "decision_log": [],
    "matchcache": {},
    "notfoundcache": {},
    "notioncache": {},
    "notioncache_loaded": False,
    "snapshot_loaded": False,
    "notion_fingerprint": None,
    "phase4_cache": {},
}

for k, v in DEFAULT_KEYS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# =========================
# CONFIG
# =========================

REQUEST_HEADERS = {
    "User-Agent": "TS4-Mod-Analyzer/1.6.1"
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

def now() -> str:
    return datetime.now(timezone.utc).isoformat()

def compute_notion_fingerprint() -> str:
    pages = st.session_state.notioncache.get("pages", {})
    if not pages:
        return "empty"
    return sha256(",".join(sorted(pages.keys())))

# =========================
# SNAPSHOT / HYDRATE
# =========================

def hydrate_session_state(snapshot: dict):
    st.session_state.notioncache = snapshot.get("phase_2_cache", {})
    st.session_state.matchcache = snapshot.get("phase_3_cache", {})
    st.session_state.phase4_cache = snapshot.get("phase_4_cache", {})
    st.session_state.decision_log = snapshot.get("canonical_log", [])
    st.session_state.notioncache_loaded = bool(st.session_state.notioncache)
    st.session_state.notion_fingerprint = compute_notion_fingerprint()
    st.session_state.snapshot_loaded = True

def build_snapshot():
    return {
        "meta": {
            "app": "TS4 Mod Analyzer",
            "version": "v1.6.1",
            "created_at": now(),
            "phase_2_fingerprint": st.session_state.notion_fingerprint,
        },
        "phase_2_cache": st.session_state.notioncache,
        "phase_3_cache": st.session_state.matchcache,
        "phase_4_cache": st.session_state.phase4_cache,
        "canonical_log": st.session_state.decision_log,
    }

# =========================
# PHASE 1 — IDENTITY
# =========================

def fetch_page(url: str) -> str:
    try:
        return requests.get(url, headers=REQUEST_HEADERS, timeout=20).text
    except Exception:
        return ""

def extract_identity(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    parsed = urlparse(url)

    title = soup.title.get_text(strip=True) if soup.title else None
    slug = parsed.path.strip("/").replace("-", " ")

    blocked = bool(re.search(r"(cloudflare|access denied|just a moment)", html.lower()))

    return {
        "url": url,
        "mod_name": title or slug or "—",
        "debug": {
            "domain": parsed.netloc.replace("www.", ""),
            "url_slug": slug,
            "is_blocked": blocked,
        },
    }

def build_identity_hash(identity: dict) -> str:
    return sha256(json.dumps(identity, sort_keys=True))

# =========================
# PHASE 4 — PRIORITY CLASSIFICATION (REAL)
# =========================

def fetch_notion_priority(notion_id: str) -> dict:
    page = notion.pages.retrieve(notion_id)
    props = page["properties"]
    return {
        "priority": props["Priority"]["select"]["name"],
        "sub": props["Subcategory"]["select"]["name"],
    }

def call_priority_model(context: dict) -> dict:
    prompt = f"""
You are classifying update priority for a Sims 4 mod.

Rules:
- Return JSON only
- priority must be 1–5
- subcategory must be consistent
- Suggest only, never enforce

Context:
{json.dumps(context, indent=2)}
"""
    r = requests.post(
        HF_MODEL,
        headers=HF_HEADERS,
        json={"inputs": prompt, "parameters": {"temperature": 0}},
    )
    data = r.json()
    text = data[0]["generated_text"]
    return json.loads(text)

def phase4_process(identity_hash: str, notion_id: str):
    current = fetch_notion_priority(notion_id)

    ai_result = call_priority_model(current)

    suggested = {
        "priority": str(ai_result["priority"]),
        "sub_category": ai_result["subcategory"],
    }

    source = "AUTO" if suggested == current else "MANUAL"

    result = {
        "current": current,
        "suggested": suggested,
        "source": source,
        "timestamp": now(),
    }

    st.session_state.phase4_cache[identity_hash] = result
    st.session_state.ai_logs.append({
        "stage": "PHASE_4",
        "input": current,
        "output": suggested,
        "source": source,
    })

    return result

# =========================
# UI
# =========================

st.title("TS4 Mod Analyzer — Phase 4")
st.caption("Auditável · Sugestivo · Sem decisão automática")

# Snapshot / Cache loaders omitidos aqui por brevidade (inalterados)

# =========================
# RESULT
# =========================

result = st.session_state.analysis_result
if result and result.get("decision") == "FOUND":
    identity_hash = result["identity_hash"]
    notion_id = result["notion_id"]

    with st.expander("🔢 Phase 4 — Priority Suggestion"):
        if identity_hash in st.session_state.phase4_cache:
            cached = st.session_state.phase4_cache[identity_hash]
            st.markdown(f"**Atual:** {cached['current']}")
            st.markdown(f"**Sugestão:** {cached['suggested']}")
            st.markdown(f"**Modo:** {cached['source']}")
        else:
            if st.button("Rodar classificação"):
                out = phase4_process(identity_hash, notion_id)
                st.success("Sugestão gerada")
                st.json(out)
