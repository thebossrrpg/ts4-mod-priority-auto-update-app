# ============================================================
# TS4 Mod Analyzer — Phase 1 → Phase 2 (Notion Integration)
# Version: v3.3.2
#
# Status:
# - Phase 1: Stable (ironclad)
# - Phase 2: Functional (creator-neutral)
#
# Notes:
# - Creator NÃO participa do matching
# - Notion é a base canônica
# - Escrita ocorre apenas sob ação humana
# ============================================================

import streamlit as st
import requests
import re
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from notion_client import Client

# =========================
# SESSION STATE
# =========================

if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None

# =========================
# CONFIG
# =========================

st.set_page_config(
    page_title="TS4 Mod Analyzer — Phases 1–2 · v3.3.2",
    layout="centered"
)

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
# FETCH
# =========================

def fetch_page(url: str) -> str:
    try:
        r = requests.get(url, headers=REQUEST_HEADERS, timeout=25)
        return r.text or ""
    except Exception:
        return ""

# =========================
# EXTRAÇÃO DE IDENTIDADE (FASE 1 — INTACTA)
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
        "is_blocked": is_blocked,
        "domain": parsed.netloc.replace("www.", "")
    }

# =========================
# NORMALIZAÇÃO
# =========================

def normalize_name(raw: str) -> str:
    if not raw:
        return "—"
    cleaned = re.sub(r"\s+", " ", raw).strip()
    cleaned = re.sub(r"(by\s+[\w\s]+)$", "", cleaned, flags=re.I).strip()
    return cleaned

def normalize_identity(identity: dict) -> dict:
    raw_name = (
        identity["og_title"]
        or identity["page_title"]
        or identity["url_slug"]
        or "Desconhecido"
    )
    return {
        "mod_name": normalize_name(raw_name),
        "creator": identity["og_site"] or identity["domain"]
    }

# =========================
# ANÁLISE
# =========================

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

# =========================
# NOTION — BUSCA DUPLICATA (CREATOR REMOVIDO)
# =========================

def search_notion_duplicate(url: str, mod_name: str):
    try:
        # 1. URL exata (match determinístico)
        r = notion.databases.query(
            database_id=NOTION_DATABASE_ID,
            filter={"property": "URL", "url": {"equals": url}}
        )
        if r["results"]:
            return r["results"][0]

        # 2. Filename (title)
        r = notion.databases.query(
            database_id=NOTION_DATABASE_ID,
            filter={
                "property": "Filename",
                "title": {"contains": mod_name}
            }
        )
        if r["results"]:
            return r["results"][0]

        # 3. Slug (fallback fraco)
        slug = urlparse(url).path.strip("/").replace("-", " ").lower()
        r = notion.databases.query(
            database_id=NOTION_DATABASE_ID,
            filter={
                "property": "Slug",
                "rich_text": {"contains": slug}
            }
        )
        if r["results"]:
            return r["results"][0]

        return None

    except Exception as e:
        st.error(f"Erro ao buscar no Notion: {e}")
        return None

# =========================
# NOTION — CRIAR ENTRADA
# =========================

def create_notion_entry(mod_name: str, creator: str, url: str):
    slug = urlparse(url).path.strip("/").replace("-", " ").lower()[:50]

    notion.pages.create(
        parent={"database_id": NOTION_DATABASE_ID},
        properties={
            "Filename": {"title": [{"text": {"content": mod_name}}]},
            "Creator": {"multi_select": [{"name": creator}]},
            "URL": {"url": url},
            "Slug": {"rich_text": [{"text": {"content": slug}}]},
            "Status": {"select": {"name": "Pendente"}}
        }
    )
    st.success(f"Entrada criada no Notion: **{mod_name}**")

# =========================
# UI
# =========================

st.title("TS4 Mod Analyzer — Phase 2")

url_input = st.text_input("URL do mod")

if st.button("Analisar") and url_input.strip():
    st.session_state.analysis_result = analyze_url(url_input.strip())

result = st.session_state.analysis_result
if result:
    st.subheader("📦 Mod")
    st.write(result["mod_name"])
    st.subheader("👤 Criador (informativo)")
    st.write(result["creator"])

    if result["debug"]["is_blocked"]:
        st.warning("⚠️ Bloqueio detectado. Fallback aplicado.")

    st.markdown("---")
    st.subheader("Notion")

    existing = search_notion_duplicate(
        result["url"], result["mod_name"]
    )

    if existing:
        page_url = f"https://www.notion.so/{existing['id'].replace('-', '')}"
        st.info("Duplicata encontrada.")
        st.markdown(f"[Abrir no Notion]({page_url})")
    else:
        st.info("Nenhuma duplicata encontrada.")
        if st.button("Criar entrada no Notion"):
            create_notion_entry(
                result["mod_name"], result["creator"], result["url"]
            )

# Footer
st.markdown(
    """
    <div style="text-align: center; padding: 1rem 0; font-size: 0.9rem; color: #6b7280;">
        Criado por Akin (@UnpaidSimmer)<br/>
        <span style="font-size: 0.75rem; opacity: 0.6;">
            v3.3.2 · Phase 2 funcional · Creator neutro
        </span>
    </div>
    """,
    unsafe_allow_html=True
)
