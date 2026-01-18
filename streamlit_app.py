# ============================================================
# TS4 Mod Analyzer
# Version: v3.1.9 (persistência total via session_state + render fora do botão)
# ============================================================

import streamlit as st
import requests
import re
from urllib.parse import urlparse
from bs4 import BeautifulSoup

st.set_page_config(
    page_title="TS4 Mod Analyzer — Phase 1",
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

def fetch_page(url: str) -> str:
    try:
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
        if response.status_code in (403, 429):
            return response.text
        response.raise_for_status()
        return response.text
    except Exception as e:
        st.error(f"Erro ao buscar página: {str(e)}")
        return ""

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
    slug = parsed.path.strip('/').replace('-', ' ').replace('/', ' ').strip()

    blocked_patterns = r"(just a moment|just a moment\.\.\.|403 forbidden|access denied|cloudflare|checking your browser|patreon login)"
    is_blocked = bool(re.search(blocked_patterns, html.lower())) or \
                 (page_title and re.search(blocked_patterns, page_title.lower()))

    return {
        "page_title": page_title,
        "og_title": og_title,
        "og_site": og_site,
        "url_slug": slug,
        "is_blocked": is_blocked,
        "domain": parsed.netloc.replace("www.", "")
    }

def normalize_name(raw: str) -> str:
    try:
        if not raw:
            return "—"
        cleaned = re.sub(r'\s+', ' ', raw).strip()
        cleaned = re.sub(r'(\b\w+\b)(\s+\1)+$', r'\1', cleaned, flags=re.I)
        cleaned = re.sub(r'(by\s+[\w\s]+)$', '', cleaned, flags=re.I).strip()
        return cleaned.title() if cleaned.islower() else cleaned
    except:
        return raw or "— (erro na limpeza)"

def normalize_identity(identity: dict) -> dict:
    preferred_name = None
    if not identity["is_blocked"] and identity["page_title"] and "just a moment" not in (identity["page_title"] or "").lower():
        preferred_name = identity["page_title"]
    elif identity["og_title"]:
        preferred_name = identity["og_title"]
    else:
        preferred_name = identity["url_slug"]

    mod_name = normalize_name(preferred_name or "Desconhecido")

    creator = identity["og_site"] or identity["domain"]
    if "by " in (preferred_name or "").lower():
        try:
            creator_part = re.search(r'by\s+([\w\s]+)', preferred_name, re.I)
            if creator_part:
                creator = normalize_name(creator_part.group(1).strip())
        except:
            pass

    return {
        "mod_name": mod_name,
        "creator": creator or "—"
    }

def analyze_url(url: str) -> dict | None:
    try:
        html = fetch_page(url)
        if not html:
            return None
        raw = extract_identity(html, url)
        norm = normalize_identity(raw)
        return {
            "url": url,
            "mod_name": norm["mod_name"],
            "creator": norm["creator"],
            "identity_debug": raw
        }
    except Exception as e:
        st.error(f"Erro na análise: {str(e)}")
        return None

# ==============================================
# INTERFACE PRINCIPAL
# ==============================================

st.title("TS4 Mod Analyzer — Phase 1")

st.markdown("""
Cole a **URL de um mod**.  
Extrai identidade básica para evitar duplicatas no Notion (não lê conteúdo protegido).
""")

url_input = st.text_input("URL do mod", placeholder="Cole aqui a URL completa do mod", key="url_input")

if 'analysis_result' not in st.session_state:
    st.session_state.analysis_result = None

if st.button("Analisar"):
    if not url_input.strip():
        st.warning("Cole uma URL válida.")
    else:
        with st.spinner("Analisando..."):
            result = analyze_url(url_input.strip())
            if result:
                st.session_state.analysis_result = result
            else:
                st.session_state.analysis_result = None
                st.error("Análise falhou. Tente outra URL ou verifique a conexão.")

# Renderização persistente do resultado (fora do botão)
if st.session_state.analysis_result:
    result = st.session_state.analysis_result

    # 1. Mod / Criador
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📦 Mod")
        st.write(result["mod_name"])
    with col2:
        st.subheader("👤 Criador")
        st.write(result["creator"])

    # 2. Botão debug logo após
    if st.button("🔍 Ver debug técnico", help="Detalhes completos da extração", key="debug_btn"):
        with st.expander("Debug técnico (fonte completa)", expanded=True):
            st.json(result["identity_debug"])

    # 3. Success
    st.success("Identidade extraída!")

    # 4. Avisos
    if result["identity_debug"]["is_blocked"]:
        st.warning("⚠️ Bloqueio detectado (Cloudflare ou similar). Usando fallback do slug/domínio.")
    if not result["identity_debug"]["og_title"]:
        st.info("ℹ️ og:title não encontrado. Usando título da página ou slug.")

    # Botão limpar (opcional, discreto)
    if st.button("Limpar resultado", help="Voltar para tela inicial", key="clear_btn"):
        st.session_state.analysis_result = None
        st.rerun()

else:
    st.info("Cole uma URL e clique em Analisar para começar.")

add_credits_footer()
