# ============================================================
# TS4 Mod Analyzer — Phase 1 → Phase 2 (Notion Integration)
# Version: v3.3.1
#
# Status:
# - Phase 1: Stable (ironclad)
# - Phase 2: Functional
#
# Notes:
# - Nenhuma decisão automática
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
    page_title="TS4 Mod Analyzer — Phases 1–2 · v3.3.1",
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
# NOTION CLIENT (secrets)
# =========================

NOTION_TOKEN = st.secrets["notion"]["token"]
NOTION_DATABASE_ID = st.secrets["notion"]["database_id"]
notion = Client(auth=NOTION_TOKEN)

# =========================
# FETCH
# =========================

def fetch_page(url: str) -> str:
    try:
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=25)
        return response.text or ""
    except Exception:
        return ""

# =========================
# EXTRAÇÃO DE IDENTIDADE
# =========================

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

# =========================
# NORMALIZAÇÃO
# =========================

def normalize_name(raw: str) -> str:
    if not raw:
        return "—"
    cleaned = re.sub(r"\s+", " ", raw).strip()
    cleaned = re.sub(r"(\b\w+\b)(\s+\1)+$", r"\1", cleaned, flags=re.I)
    cleaned = re.sub(r"(by\s+[\w\s]+)$", "", cleaned, flags=re.I).strip()
    return cleaned.title() if cleaned.islower() else cleaned

def normalize_identity(identity: dict) -> dict:
    raw_name = (
        identity["page_title"]
        or identity["og_title"]
        or identity["url_slug"]
        or "Desconhecido"
    )
    mod_name = normalize_name(raw_name)
    creator = identity["og_site"] or identity["domain"]
    return {
        "mod_name": mod_name,
        "creator": creator or "—"
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
# NOTION – BUSCA DUPLICATA
# =========================

# Busca duplicata (atualizado para compatibilidade 2.7.0+)
def search_notion_duplicate(url: str, mod_name: str, creator: str) -> dict | None:
    try:
        # 1. Busca por URL exata (prioridade máxima)
        response = notion.databases.query(
            database_id=NOTION_DATABASE_ID,
            filter={
                "property": "URL",
                "url": {"equals": url}
            }
        )
        if response["results"]:
            return response["results"][0]

        # 2. Busca por nome + criador (fallback mais confiável)
        response_name = notion.databases.query(
            database_id=NOTION_DATABASE_ID,
            filter={
                "and": [
                    {"property": "Filename", "title": {"contains": mod_name}},
                    {"property": "Creator", "rich_text": {"contains": creator}}
                ]
            }
        )
        if response_name["results"]:
            return response_name["results"][0]

        # 3. Busca por slug (opcional, só se a propriedade existir)
        try:
            slug = urlparse(url).path.strip('/').replace('-', ' ').lower()
            response_slug = notion.databases.query(
                database_id=NOTION_DATABASE_ID,
                filter={
                    "property": "Slug",  # Se não existir, pula sem crash
                    "rich_text": {"contains": slug}
                }
            )
            if response_slug["results"]:
                return response_slug["results"][0]
        except Exception as slug_err:
            # Ignora silenciosamente se propriedade "Slug" não existir
            pass

        return None
    except Exception as e:
        st.error(f"Erro ao buscar no Notion: {str(e)}")
        return None

# =========================
# NOTION – CRIAR ENTRADA
# =========================

# Criação de página (atualizado para compatibilidade)
def create_notion_entry(mod_name: str, creator: str, url: str):
    try:
        slug = urlparse(url).path.strip('/').replace('-', ' ').lower()[:50]

        notion.pages.create(
            parent={"database_id": NOTION_DATABASE_ID},
            properties={
                "Filename": {"title": [{"text": {"content": mod_name}}]},
                "Creator": {"rich_text": [{"text": {"content": creator}}]},
                "URL": {"url": url},
                "Slug": {"rich_text": [{"text": {"content": slug}}]},
                "Status": {"select": {"name": "Pendente"}},
                "Notes": {"rich_text": [{"text": {"content": "Adicionado via app – Fase 2"}}]}
            }
        )
        st.success(f"Entrada criada no Notion: **{mod_name}**")
    except Exception as e:
        st.error(f"Erro ao criar no Notion: {str(e)}")

# =========================
# UI
# =========================

st.title("TS4 Mod Analyzer — Phase 1")

st.markdown(
    "Cole a **URL de um mod**.  \n"
    "Extrai identidade básica para evitar duplicatas no Notion."
)

url_input = st.text_input("URL do mod", placeholder="Cole aqui a URL completa do mod")

if st.button("Analisar"):
    if not url_input.strip():
        st.warning("Cole uma URL válida.")
    else:
        with st.spinner("Analisando..."):
            st.session_state.analysis_result = analyze_url(url_input.strip())

# Resultado persistente
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

    # ====================
    # INTEGRAÇÃO NOTION
    # ====================
    st.markdown("---")
    st.subheader("Notion – Duplicatas e Criação")

    existing = search_notion_duplicate(result["url"], result["mod_name"], result["creator"])
    if existing:
        page_id = existing["id"].replace("-", "")
        page_url = f"https://www.notion.so/{page_id}"
        st.info("Este mod **já existe** no Notion!")
        st.markdown(f"[Abrir página existente]({page_url})")
    else:
        st.info("Nenhuma duplicata encontrada.")
        if st.button("Criar nova entrada no Notion"):
            create_notion_entry(result["mod_name"], result["creator"], result["url"])

# Footer
st.markdown(
    """
    <div style="text-align: center; padding: 1rem 0; font-size: 0.9rem; color: #6b7280;">
        <img src="https://64.media.tumblr.com/05d22b63711d2c391482d6faad367ccb/675ea15a79446393-0d/s2048x3072/cc918dd94012fe16170f2526549f3a0b19ecbcf9.png" 
             alt="Favicon" 
             style="height: 20px; vertical-align: middle; margin-right: 8px;">
        Criado por Akin (@UnpaidSimmer)
        <div style="margin-top: 0.5rem; font-size: 0.75rem; opacity: 0.6;">
            v3.3.1 · Phase 2 funcional · Notion real
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

