# ============================================================
# TS4 Mod Analyzer — Phase 1 → Phase 3 (Hugging Face IA)
# Version: v3.5.0
#
# Contract:
# - Phase 1 preserved (identity extraction)
# - Phase 2 preserved (deterministic Notion match)
# - Phase 3 preserved (IA last resort)
# - ADDITIVE ONLY:
#   • Deterministic cache
#   • Canonical decision log
#
# Rule: New version = SUM, never subtraction
# ============================================================

import streamlit as st
import requests
import re
import json
import hashlib
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from notion_client import Client
from datetime import datetime

# =========================
# PAGE CONFIG (UI FIRST)
# =========================

st.set_page_config(
    page_title="TS4 Mod Analyzer — Phase 2 · v3.5.0",
    layout="centered"
)

# =========================
# SESSION STATE
# =========================

if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None

if "ai_logs" not in st.session_state:
    st.session_state.ai_logs = []

if "decision_log" not in st.session_state:
    st.session_state.decision_log = []

if "cache" not in st.session_state:
    st.session_state.cache = {}

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
HF_HEADERS = {
    "Authorization": f"Bearer {HF_TOKEN}",
    "Content-Type": "application/json"
}

HF_PRIMARY_MODEL = "https://api-inference.huggingface.co/models/google/flan-t5-base"
HF_FALLBACK_MODEL = "https://api-inference.huggingface.co/models/facebook/bart-large-mnli"

# =========================
# PASSO 1 — NOTION FINGERPRINT
# =========================

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def compute_notion_fingerprint() -> str:
    page_ids = []
    has_more = True
    cursor = None

    while has_more:
        payload = {}
        if cursor:
            payload["start_cursor"] = cursor

        r = requests.post(
            f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query",
            headers={
                "Authorization": f"Bearer {NOTION_TOKEN}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )

        if r.status_code != 200:
            return "fingerprint_error"

        data = r.json()
        for page in data.get("results", []):
            if page.get("id"):
                page_ids.append(page["id"])

        has_more = data.get("has_more", False)
        cursor = data.get("next_cursor")

    page_ids.sort()
    return sha256(",".join(page_ids))

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

def normalize_name(raw: str) -> str:
    if not raw:
        return "—"
    cleaned = re.sub(r"\s+", " ", raw).strip()
    cleaned = re.sub(r"(by\s+[\w\s]+)$", "", cleaned, flags=re.I).strip()
    return cleaned.title() if cleaned.islower() else cleaned

def analyze_url(url: str) -> dict:
    html = fetch_page(url)
    raw = extract_identity(html, url)
    raw_name = raw["page_title"] or raw["og_title"] or raw["url_slug"]

    return {
        "url": url,
        "mod_name": normalize_name(raw_name),
        "debug": raw,
    }

# =========================
# PHASE 2 — NOTION MATCH
# =========================

def search_notion_candidates(mod_name: str, url: str) -> list:
    candidates = []

    try:
        r = notion.databases.query(
            database_id=NOTION_DATABASE_ID,
            filter={"property": "URL", "url": {"equals": url}},
        )
        candidates.extend(r["results"])
    except Exception:
        pass

    try:
        r = notion.databases.query(
            database_id=NOTION_DATABASE_ID,
            filter={"property": "Filename", "title": {"contains": mod_name}},
        )
        candidates.extend(r["results"])
    except Exception:
        pass

    return list({c["id"]: c for c in candidates}.values())

# =========================
# PHASE 3 — IA
# =========================

def slug_quality(slug: str) -> str:
    return "poor" if not slug or len(slug.split()) <= 2 else "good"

def build_ai_payload(identity, candidates):
    return {
        "identity": {
            "title": identity["mod_name"],
            "domain": identity["debug"]["domain"],
            "slug": identity["debug"]["url_slug"],
            "page_blocked": identity["debug"]["is_blocked"],
        },
        "candidates": [
            {
                "notion_id": c["id"],
                "title": c["properties"]["Filename"]["title"][0]["plain_text"],
            }
            for c in candidates
            if c["properties"]["Filename"]["title"]
        ],
    }

def safe_parse_hf_response(response):
    try:
        data = response.json()
        text = None
        if isinstance(data, list) and data:
            text = data[0].get("generated_text")
        elif isinstance(data, dict):
            text = data.get("generated_text")
        return json.loads(text) if text else None
    except Exception:
        return None

def call_primary_model(payload):
    prompt = f"""
Compare the mod identity with the candidates.

Rules:
- Return JSON only
- match=true only if EXACTLY ONE clear match exists
- Do not guess

Payload:
{json.dumps(payload, ensure_ascii=False)}
"""
    r = requests.post(
        HF_PRIMARY_MODEL,
        headers=HF_HEADERS,
        json={"inputs": prompt, "parameters": {"temperature": 0}},
    )
    return safe_parse_hf_response(r)

def log_ai_event(stage, payload, result):
    st.session_state.ai_logs.append(
        {
            "timestamp": datetime.utcnow().isoformat(),
            "stage": stage,
            "payload": payload,
            "result": result,
        }
    )

# =========================
# UI — HEADER
# =========================

st.title("TS4 Mod Analyzer — Phase 2")
st.caption("Determinístico · Auditável · Zero achismo")

# =========================
# FINGERPRINT UI
# =========================

current_fp = compute_notion_fingerprint()
if st.session_state.notion_fingerprint is None:
    st.session_state.notion_fingerprint = current_fp
    st.info("📌 Fingerprint inicial da database do Notion calculado.")
elif current_fp != st.session_state.notion_fingerprint:
    st.warning("🔄 A database do Notion foi alterada desde a última execução.")
    st.session_state.notion_fingerprint = current_fp
else:
    st.success("✅ Database do Notion inalterada.")

st.divider()

# =========================
# UI — ANALYSIS
# =========================

url_input = st.text_input("URL do mod")

if st.button("Analisar") and url_input.strip():
    with st.spinner("Analisando..."):
        identity = analyze_url(url_input.strip())
        identity_hash = sha256(json.dumps(identity, sort_keys=True))

        if identity_hash in st.session_state.cache:
            st.session_state.analysis_result = st.session_state.cache[identity_hash]
            st.info("⚡ Resultado recuperado do cache")
        else:
            st.session_state.analysis_result = identity
            st.session_state.cache[identity_hash] = identity

result = st.session_state.analysis_result

if result:
    st.subheader("📦 Mod")
    st.write(result["mod_name"])

    with st.expander("🔍 Debug técnico"):
        st.json(result["debug"])

    st.markdown("---")
    st.subheader("Notion")

    candidates = search_notion_candidates(result["mod_name"], result["url"])

    decision_record = {
        "timestamp": datetime.utcnow().isoformat(),
        "identity": result,
        "phase_2_candidates": len(candidates),
        "decision": None,
    }

    if candidates:
        decision_record["decision"] = "FOUND"
        st.success("Match encontrado no Notion.")
        for c in candidates:
            page_url = f"https://www.notion.so/{c['id'].replace('-', '')}"
            title = c["properties"]["Filename"]["title"][0]["plain_text"]
            st.markdown(f"- [{title}]({page_url})")
    else:
        if result["debug"]["is_blocked"] or slug_quality(result["debug"]["url_slug"]) == "poor":
            st.warning("Identidade fraca — acionando IA (Fase 3)")
            payload = build_ai_payload(result, [])
            primary = call_primary_model(payload)

            if primary and primary.get("match") is True:
                decision_record["decision"] = "FOUND"
                st.success("IA identificou um match inequívoco.")
            else:
                decision_record["decision"] = "NOT_FOUND"
                log_ai_event("PRIMARY_NO_COLLAPSE", payload, primary)
                st.info("IA não conseguiu colapsar o match.")
        else:
            decision_record["decision"] = "NOT_FOUND"
            st.info("Nenhuma duplicata encontrada.")

    st.session_state.decision_log.append(decision_record)

# =========================
# CACHE (UX CONTROLADA)
# =========================

with st.expander("🗃️ Cache em memória"):
    st.write(f"Itens em cache: {len(st.session_state.cache)}")
    st.json(list(st.session_state.cache.keys()))

# =========================
# LOG (UX CONTROLADA)
# =========================

with st.expander("📊 Log canônico de decisões"):
    st.write(f"Entradas registradas: {len(st.session_state.decision_log)}")
    for i, entry in enumerate(st.session_state.decision_log, 1):
        with st.expander(f"Decisão #{i} — {entry['decision']}"):
            st.json(entry)

# =========================
# FOOTER (CANÔNICO — PRESERVADO)
# =========================

st.markdown(
    """
    <div style="text-align:center;padding:1rem 0;font-size:0.85rem;color:#6b7280;">
        <img src="https://64.media.tumblr.com/05d22b63711d2c391482d6faad367ccb/675ea15a79446393-0d/s2048x3072/cc918dd94012fe16170f2526549f3a0b19ecbcf9.png"
             style="height:20px;vertical-align:middle;margin-right:6px;">
        Criado por Akin (@UnpaidSimmer)
        <div style="font-size:0.7rem;opacity:0.6;">v3.5.0 · Phase 3 (IA controlada)</div>
    </div>
    """,
    unsafe_allow_html=True,
)
