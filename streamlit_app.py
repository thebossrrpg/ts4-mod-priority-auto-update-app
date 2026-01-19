# ============================================================
# TS4 Mod Analyzer — Phase 2 (Sandbox)
# Version: v3.4-sandbox (Notion secrets check + debug fix)
# ============================================================

import streamlit as st
import requests
import re
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from difflib import SequenceMatcher

# =========================
# SESSION STATE
# =========================

if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None

# =========================
# CONFIG
# =========================

st.set_page_config(
    page_title="TS4 Mod Analyzer — Phase 2 (Sandbox)",
    layout="centered"
)

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# =========================
# NOTION CONFIG (READ ONLY)
# =========================

NOTION_TOKEN = st.secrets.get("NOTION_TOKEN")
NOTION_DATABASE_ID = st.secrets.get("NOTION_DATABASE_ID")

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

# =========================
# FETCH PAGE
# =========================

def fetch_page(url: str) -> str:
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    if response.status_code in (403, 429):
        return response.text
    response.raise_for_status()
    return response.text

# =========================
# PHASE 1 — IDENTIDADE
# =========================

def extract_identity(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    page_title = soup.title.string.strip() if soup.title else None

    og_title = None
    og_site = None
    for meta in soup.find_all("meta"):
        if meta.get("property") == "og:title":
            og_title = meta.get("content", "").strip()
        if meta.get("property") == "og:site_name":
            og_site = meta.get("content", "").strip()

    parsed = urlparse(url)
    slug = parsed.path.strip("/").replace("-", " ").replace("/", " ").strip()

    blocked_patterns = (
        r"(just a moment|403 forbidden|access denied|cloudflare|"
        r"checking your browser|patreon login)"
    )

    is_blocked = bool(
        re.search(blocked_patterns, html.lower())
        or (page_title and re.search(blocked_patterns, page_title.lower()))
    )

    return {
        "page_title": page_title,
        "og_title": og_title,
        "og_site": og_site,
        "url_slug": slug,
        "is_blocked": is_blocked,
        "domain": parsed.netloc.replace("www.", ""),
    }

def normalize_name(raw: str) -> str:
    if not raw:
        return ""
    cleaned = re.sub(r"\s+", " ", raw).strip()
    cleaned = re.sub(r"(by\s+[\w\s]+)$", "", cleaned, flags=re.I).strip()
    return cleaned.lower()

def build_identity(identity_raw: dict) -> dict:
    if not identity_raw["is_blocked"] and identity_raw["page_title"]:
        name = identity_raw["page_title"]
    elif identity_raw["og_title"]:
        name = identity_raw["og_title"]
    else:
        name = identity_raw["url_slug"]

    return {
        "mod_name": name or "—",
        "creator": identity_raw["og_site"] or identity_raw["domain"],
        "normalized_name": normalize_name(name),
    }

# =========================
# NOTION — READ ONLY
# =========================

def query_notion_all() -> list:
    if not NOTION_TOKEN or not NOTION_DATABASE_ID:
        return []

    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    results = []
    payload = {}

    while True:
        res = requests.post(url, headers=NOTION_HEADERS, json=payload)
        res.raise_for_status()
        data = res.json()

        results.extend(data.get("results", []))

        if not data.get("has_more"):
            break

        payload["start_cursor"] = data["next_cursor"]

    return results

def extract_notion_name(page: dict) -> str:
    try:
        title_prop = page["properties"]["Name"]["title"]
        if title_prop:
            return title_prop[0]["plain_text"]
    except:
        pass
    return ""

# =========================
# DUPLICATE CHECK (LENIENT)
# =========================

def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()

def check_duplicates(identity: dict, notion_pages: list) -> dict:
    best_score = 0.0
    best_match = None
    reasons = []

    for page in notion_pages:
        notion_name = extract_notion_name(page)
        score = similarity(identity["normalized_name"], normalize_name(notion_name))

        if score > best_score:
            best_score = score
            best_match = notion_name

    if best_score > 0:
        reasons.append(f"Nome parecido ({best_score:.2f})")

    return {
        "score": round(best_score, 2),
        "best_match": best_match,
        "reasons": reasons,
    }

# =========================
# ORQUESTRADOR
# =========================

def analyze_url(url: str) -> dict:
    html = fetch_page(url)
    raw = extract_identity(html, url)
    identity = build_identity(raw)

    notion_pages = query_notion_all()
    dup = check_duplicates(identity, notion_pages)

    return {
        "identity": identity,
        "identity_debug": raw,
        "duplicate_check": dup,
        "notion_connected": bool(NOTION_TOKEN and NOTION_DATABASE_ID),
    }

# =========================
# UI
# =========================

st.title("Fase 2 (Sandbox): detecção de duplicatas")
st.warning("⚠️ Não escreve no Notion.")

# -------- SECRETS STATUS --------

with st.expander("🔐 Status dos secrets (diagnóstico)", expanded=True):
    st.write("NOTION_TOKEN carregado:", bool(NOTION_TOKEN))
    st.write("NOTION_DATABASE_ID carregado:", bool(NOTION_DATABASE_ID))

url_input = st.text_input("URL do mod")

if st.button("Analisar"):
    if not url_input.strip():
        st.warning("Cole uma URL válida.")
    else:
        with st.spinner("Analisando..."):
            st.session_state.analysis_result = analyze_url(url_input.strip())

# -------- RESULTADO --------

result = st.session_state.analysis_result

if result:
    st.subheader("📦 Identidade")
    st.write("Mod:", result["identity"]["mod_name"])
    st.write("Criador:", result["identity"]["creator"])

    st.subheader("🔍 Verificação de duplicata")

    score = result["duplicate_check"]["score"]

    if score >= 0.6:
        st.error("🚨 Alta chance de duplicata")
    elif score >= 0.3:
        st.warning("⚠️ Zona cinza — revisar")
    else:
        st.success("✅ Provavelmente novo mod")

    st.write("Score:", score)

    if result["duplicate_check"]["best_match"]:
        st.write("Possível match:", result["duplicate_check"]["best_match"])

    if result["duplicate_check"]["reasons"]:
        st.write("Razões:")
        for r in result["duplicate_check"]["reasons"]:
            st.write("•", r)

    with st.expander("🧪 Debug Fase 1"):
        st.json(result["identity_debug"])

# =========================
# FOOTER
# =========================


st.markdown(
    """
    <div style="text-align: center; padding: 1rem 0; font-size: 0.9rem; color: #6b7280;">
        <img src="https://64.media.tumblr.com/05d22b63711d2c391482d6faad367ccb/675ea15a79446393-0d/s2048x3072/cc918dd94012fe16170f2526549f3a0b19ecbcf9.png" 
             alt="Favicon" 
             style="height: 20px; vertical-align: middle; margin-right: 8px;">
        Criado por Akin (@UnpaidSimmer) · v3.4 · Sandbox
        <div style="margin-top: 0.5rem; font-size: 0.75rem; opacity: 0.6;">
            v3.3
        </div>
    </div>
    """,
    unsafe_allow_html=True
)
