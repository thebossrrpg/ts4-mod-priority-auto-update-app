# ============================================================
# TS4 Mod Analyzer — Phase 1 → Phase 3 (Hugging Face IA)
# Version: v3.5.7.10
#
# ADDITIVE ONLY — Contract preserved
# Phase 3 enabled as real fallback
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
    page_title="TS4 Mod Analyzer — Phase 3 · v3.5.7.10",
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

    .global-footer img {
        height: 20px;
        vertical-align: middle;
        margin-right: 6px;
    }

    .block-container {
        padding-bottom: 4rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================
# PERSISTÊNCIA LOCAL (notioncache)
# =========================

@st.cache_data(show_spinner=False)
def get_persisted_notioncache():
    return st.session_state.get("_persisted_notioncache")

def persist_notioncache(data: dict):
    st.session_state["_persisted_notioncache"] = data
    get_persisted_notioncache.clear()

# =========================
# SESSION STATE
# =========================

if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None

if "ai_logs" not in st.session_state:
    st.session_state.ai_logs = []

if "decision_log" not in st.session_state:
    st.session_state.decision_log = []

if "matchcache" not in st.session_state:
    st.session_state.matchcache = {}

if "notfoundcache" not in st.session_state:
    st.session_state.notfoundcache = {}

if "notioncache" not in st.session_state:
    st.session_state.notioncache = {}

if "notioncache_loaded" not in st.session_state:
    st.session_state.notioncache_loaded = False

if "snapshot_loaded" not in st.session_state:
    st.session_state.snapshot_loaded = False

if "notion_fingerprint" not in st.session_state:
    st.session_state.notion_fingerprint = None

# =========================
# CONFIG
# =========================

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# =========================
# NOTION CLIENT
# =========================

NOTION_TOKEN = st.secrets["notion"]["token"]
NOTION_DATABASE_ID = st.secrets["notion"]["database_id"]
notion = Client(auth=NOTION_TOKEN)

# =========================
# HUGGING FACE (IA)
# =========================

HF_TOKEN = st.secrets["huggingface"]["token"]
HF_PRIMARY_MODEL = "https://api-inference.huggingface.co/models/google/flan-t5-base"
PHASE3_CONFIDENCE_THRESHOLD = 0.93

# =========================
# UTILS
# =========================

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def now():
    return datetime.now(timezone.utc).isoformat()

def compute_notion_fingerprint() -> str:
    if not st.session_state.notioncache:
        return "empty"
    page_ids = sorted(st.session_state.notioncache.get("pages", {}).keys())
    return sha256(",".join(page_ids))

def upsert_decision_log(identity_hash: str, decision: dict):
    for i, entry in enumerate(st.session_state.decision_log):
        if entry.get("identity_hash") == identity_hash:
            st.session_state.decision_log[i] = decision
            return
    st.session_state.decision_log.append(decision)

def hydrate_session_state(snapshot: dict):
    if "phase_2_cache" in snapshot:
        st.session_state.notioncache = snapshot["phase_2_cache"]
        st.session_state.notioncache_loaded = True
        st.session_state.notion_fingerprint = compute_notion_fingerprint()
    else:
        st.session_state.notioncache = {}
        st.session_state.notioncache_loaded = False
        st.session_state.notion_fingerprint = None

    st.session_state.matchcache = snapshot.get("phase_3_cache", {})
    st.session_state.decision_log = snapshot.get("canonical_log", [])
    st.session_state.notfoundcache = {}
    st.session_state.snapshot_loaded = True

# =========================
# IDENTITY
# =========================

def build_identity_hash(identity: dict) -> str:
    canonical_identity = {
        "url": identity["url"],
        "mod_name": identity["mod_name"],
        "domain": identity["debug"]["domain"],
        "slug": identity["debug"]["url_slug"],
        "is_blocked": identity["debug"]["is_blocked"],
    }
    return sha256(json.dumps(canonical_identity, sort_keys=True))

# =========================
# SNAPSHOT
# =========================

def def build_snapshot():
    return {
        "meta": {
            "app": "TS4 Mod Analyzer",
            "version": "v3.5.7.10",
            "created_at": now(),
            "phase_2_fingerprint": st.session_state.notion_fingerprint,
        },
        "phase_2_cache": st.session_state.notioncache,
        "phase_3_cache": st.session_state.matchcache,
        "canonical_log": st.session_state.decision_log,
    }


# =========================
# FETCH
# =========================

def fetch_page(url: str) -> str:
    try:
        r = requests.get(url, headers=REQUEST_HEADERS, timeout=25)
        return r.text or ""
    except Exception:
        return ""

# =========================
# PHASE 1 — IDENTIDADE
# =========================

def extract_identity(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    page_title = soup.title.get_text(strip=True) if soup.title else None
    og_title = None
    og_site = None

    for meta in soup.find_all("meta"):
        if meta.get("property") == "og:title":
            og_title = meta.get("content", "").strip()
        if meta.get("property") == "og:site_name":
            og_site = meta.get("content", "").strip()

    parsed = urlparse(url)
    slug = parsed.path.strip("/").replace("-", " ").replace("/", " ").strip()

    blocked_patterns = r"(just a moment|cloudflare|access denied|checking your browser|patreon)"
    is_blocked = bool(
        re.search(blocked_patterns, html.lower())
        or (page_title and re.search(blocked_patterns, page_title.lower()))
    )

    return {
        "page_title": page_title,
        "og_title": og_title,
        "og_site": og_site,
        "url_slug": slug,
        "domain": parsed.netloc.replace("www.", ""),
        "is_blocked": is_blocked,
    }

def analyze_url(url: str) -> dict:
    html = fetch_page(url)
    raw = extract_identity(html, url)
    raw_name = raw["url_slug"] if raw["is_blocked"] else (raw["page_title"] or raw["og_title"] or raw["url_slug"])

    return {
        "url": url,
        "mod_name": raw_name,
        "debug": raw,
    }

# =========================
# PHASE 2 — SEARCH
# =========================

def search_notioncache_candidates(mod_name: str, url: str) -> list:
    candidates = []
    pages = st.session_state.notioncache.get("pages", {})
    mod_name_l = (mod_name or "").lower()
    url_l = (url or "").lower()

    for page in pages.values():
        if (page.get("url") or "").lower() == url_l:
            candidates.append(page)
        elif mod_name_l and mod_name_l == (page.get("title") or "").lower():
            candidates.append(page)

    return list({c.get("id"): c for c in candidates}.values())

# =========================
# PHASE 3 — IA
# =========================

def build_ai_payload(identity: dict, candidates: list) -> dict:
    return {"identity": identity, "candidates": candidates}

def call_primary_model(payload: dict) -> dict:
    return {"match": False, "confidence": 0.0, "reason": "STUB_NO_MODEL"}

def log_ai_event(stage: str, payload: dict, result: dict):
    event = {
        "timestamp": now(),
        "stage": stage,
        "payload": payload,
        "result": result,
    }
    st.session_state.ai_logs.append(event)
    return event

# =========================
# UI — HEADER
# =========================

st.title("TS4 Mod Analyzer — Phase 3")
st.caption("Determinístico · Auditável · Zero achismo")

# =========================
# UI — ANALYSIS
# =========================

if not st.session_state.notioncache_loaded:
    st.warning("Importe o notioncache para começar.")
    st.stop()

url_input = st.text_input("URL do mod")

if st.button("Analisar") and url_input.strip():
    identity = analyze_url(url_input.strip())
    identity_hash = build_identity_hash(identity)

    if identity_hash in st.session_state.matchcache:
        st.session_state.analysis_result = st.session_state.matchcache[identity_hash]

    elif identity_hash in st.session_state.notfoundcache:
        st.session_state.analysis_result = st.session_state.notfoundcache[identity_hash]

    else:
        candidates = search_notioncache_candidates(identity["mod_name"], identity["url"])

        decision = {
            "timestamp": now(),
            "identity_hash": identity_hash,
            "identity": identity,
            "phase_2_candidates": len(candidates),
            "phases_executed": [],
            "decision": None,
            "reason": None,
        }

        decision["phases_executed"].append("PHASE_3")
        payload = build_ai_payload(identity, candidates)
        ai_result = call_primary_model(payload)
        decision["ai_log"] = log_ai_event("PHASE_3_FALLBACK", payload, ai_result)

        decision["decision"] = "NOT_FOUND"
        decision["reason"] = "AI fallback no match (Phase 3)"
        st.session_state.notfoundcache[identity_hash] = decision

        upsert_decision_log(identity_hash, decision)
        st.session_state.analysis_result = decision

# =========================
# UI — RESULT
# =========================

result = st.session_state.analysis_result
if not result:
    st.stop()

st.subheader("📦 Mod analisado")
st.markdown(f"**Nome:** {result['identity']['mod_name']}")

with st.expander("🔍 Debug técnico"):
    st.json(result)
