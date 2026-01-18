# ============================================================
# TS4 Mod Analyzer
# Version: v3.1.5 (UI: Mod/Criador > Success > Avisos > Debug)
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
        raise RuntimeError(f"Erro no fetch: {e}")

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
    if not raw:
        return "—"
    cleaned = re.sub(r'\s+', ' ', raw).strip()
    cleaned = re.sub(r'(\b\w+\b)(\s+\1)+$', r'\1', cleaned, flags=re.I)
    cleaned = re.sub(r'(by\s+[\w\s]+)$', '', cleaned, flags=re.I).strip()
    return cleaned.title() if cleaned.islower() else cleaned

def normalize_identity(identity: dict) -> dict:
    preferred_name = None
    if not identity["is_blocked"] and identity["page_title"] and "just a moment" not in identity["page_title"].lower():
        preferred_name = identity["page_title"]
    elif identity["og_title"]:
        preferred_name = identity["og_title"]
    else:
        preferred_name = identity["url_slug"]

    mod_name = normalize_name(preferred_name or "Desconhecido")

    creator = identity["og_site"] or identity["domain"]
    if "by " in (preferred_name or "").lower():
        creator_part = re.search(r'by\s+([\w\s]+)', preferred_name, re.I)
        if creator_part:
            creator = normalize_name(creator_part.group(1).strip())

    return {
        "mod_name": mod_name,
        "creator": creator or "—"
    }

def analyze_url(url: str) -> dict:
    html = fetch_page(url)
    raw = extract_identity(html, url)
    norm = normalize_identity(raw)
    return {
        "url": url,
        "mod_name": norm["mod_name"],
        "creator": norm["creator"],
        "identity_debug": raw
    }

def add_credits_footer():
    footer_html = """
    <div style="
        text-align: center;
        padding: 1.5rem 0 1rem;
        font-size: 0.9rem;
        color: #6b7280;
        margin-top: 2rem;
        border-top: 1px solid #e5e7eb;
    ">
        <div style="margin-bottom: 0.8rem; font-weight: bold; font-size: 1rem;">
            Criado por Akin (@UnpaidSimmer)
        </div>
        <div style="display: flex; justify-content: center; align-items: center; gap: 1.5rem; flex-wrap: wrap;">
            <span style="font-size: 0.85rem;">Com:</span>
            <a href="https://lovable.dev" target="_blank" style="text-decoration: none;">
                <img src="https://cdn.brandfetch.io/lovable.dev/logo" alt="Lovable" style="height: 20px; max-width: 80px; vertical-align: middle;">
            </a>
            <a href="https://chatgpt.com" target="_blank" style="text-decoration: none;">
                <img src="https://upload.wikimedia.org/wikipedia/commons/0/04/ChatGPT_logo.svg" alt="ChatGPT" style="height: 20px; max-width: 80px; vertical-align: middle;">
            </a>
            <a href="https://x.ai" target="_blank" style="text-decoration: none;">
                <img src="https://1000logos.net/wp-content/uploads/2024/05/Grok-Logo.png" alt="Grok" style="height: 20px; max-width: 80px; vertical-align: middle;">
            </a>
            <a href="https://www.notion.so" target="_blank" style="text-decoration: none;">
                <img src="https://www.notion.so/front-static/shared/notion-app-icon-3d.png" alt="Notion" style="height: 20px; max-width: 80px; vertical-align: middle;">
            </a>
        </div>
        <div style="margin-top: 0.8rem; font-size: 0.75rem; opacity: 0.7;">
            v3.1.5
        </div>
    </div>
    """
    st.markdown(footer_html, unsafe_allow_html=True)

# ==============================================
# INTERFACE PRINCIPAL
# ==============================================

st.title("TS4 Mod Analyzer — Phase 1")

st.markdown("""
Cole a **URL de um mod** (itch.io, CurseForge, Patreon, etc.).  
Extrai identidade básica para evitar duplicatas no Notion (não lê conteúdo protegido).
""")

url_input = st.text_input("URL do mod", placeholder="https://kuttoe.itch.io/mini-mods-bug-fixes")

if st.button("Analisar"):
    if not url_input.strip():
        st.warning("Cole uma URL válida.")
    else:
        with st.spinner("Analisando..."):
            try:
                result = analyze_url(url_input.strip())

                # Primeiro: Mod / Criador
                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("📦 Mod")
                    st.write(result["mod_name"])
                with col2:
                    st.subheader("👤 Criador")
                    st.write(result["creator"])

                # Depois: Success message
                st.success("Identidade extraída!")

                # Avisos/infos em seguida
                if result["identity_debug"]["is_blocked"]:
                    st.warning("⚠️ Bloqueio detectado (Cloudflare ou similar). Usando fallback do slug/domínio.")
                if not result["identity_debug"]["og_title"]:
                    st.info("ℹ️ og:title não encontrado. Usando título da página ou slug.")

                # Por último: Debug
                with st.expander("🔍 Debug técnico (fonte completa)"):
                    st.json(result["identity_debug"])

            except Exception as e:
                st.error(f"Erro: {str(e)}")

add_credits_footer()
