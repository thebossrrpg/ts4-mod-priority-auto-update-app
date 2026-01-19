# ============================================================
# TS4 Mod Analyzer
# Version: v3.2.3 (fix ATS4 crash + debug funcional)
# ============================================================

import streamlit as st
import requests
import re
from urllib.parse import urlparse
from bs4 import BeautifulSoup

# --------------------
# SESSION STATE
# --------------------
if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None

st.set_page_config(
    page_title="TS4 Mod Analyzer — Phase 1",
    layout="centered"
)

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# --------------------
# FETCH
# --------------------
def fetch_page(url: str) -> str:
    try:
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=25)
        return response.text or ""
    except Exception as e:
        return ""

# --------------------
# EXTRACTION
# --------------------
def extract_identity(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    page_title = (
        soup.title.get_text(strip=True)
        if soup.title
        else None
    )

    og_title = None
    og_site = None
    for meta in soup.find_all("meta"):
        if meta.get("property") == "og:title":
            og_title = meta.get("content", "").strip()
        if meta.get("property") == "og:site_name":
            og_site = meta.get("content", "").strip()

    parsed = urlparse(url)
    slug = parsed.path.strip("/").replace("-", " ").replace("/", " ").strip()

    blocked_patterns = r"(just a moment|cloudflare|access denied|checking your browser|patreon login)"
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
        "domain": parsed.netloc.replace("www.", "")
    }

# --------------------
# NORMALIZATION
# --------------------
def normalize_identity(identity: dict) -> dict:
    raw_name = (
        identity["page_title"]
        or identity["og_title"]
        or identity["url_slug"]
        or "Desconhecido"
    )

    mod_name = re.sub(r"\s+", " ", raw_name).strip()

    creator = identity["og_site"] or identity["domain"]

    return {
        "mod_name": mod_name,
        "creator": creator or "—"
    }

# --------------------
# ANALYSIS
# --------------------
def analyze_url(url: str) -> dict:
    html = fetch_page(url)
    raw = extract_identity(html, url)
    norm = normalize_identity(raw)

    return {
        "url": url,
        "mod_name": norm["mod_name"],
        "creator": norm["creator"],
        "debug": raw
    }

# ====================
# UI
# ====================
st.title("TS4 Mod Analyzer — Phase 1")

st.markdown(
    "Cole a **URL de um mod** (CurseForge, Patreon, ATS4 etc). "
    "O app extrai identidade para evitar duplicatas no Notion."
)

url_input = st.text_input("URL do mod")

if st.button("Analisar"):
    if not url_input.strip():
        st.warning("Cole uma URL válida.")
    else:
        with st.spinner("Analisando..."):
            st.session_state.analysis_result = analyze_url(url_input.strip())

# --------------------
# RESULT
# --------------------
result = st.session_state.analysis_result

if result:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📦 Mod")
        st.write(result["mod_name"])

    with col2:
        st.subheader("👤 Criador")
        st.write(result["creator"])

    st.success("Identidade extraída com sucesso.")

    with st.expander("🔍 Debug técnico"):
        st.json(result["debug"])

    if result["debug"]["is_blocked"]:
        st.warning("⚠️ Bloqueio detectado (Cloudflare / Patreon). Fallback aplicado.")
