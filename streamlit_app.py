# ============================================================
# TS4 Mod Analyzer
# Version: v3.1
# ============================================================

import streamlit as st
import requests
import re
from urllib.parse import urlparse
from bs4 import BeautifulSoup

st.set_page_config(
    page_title="TS4 Mod Analyzer — Phase 1 (v3.1)",
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
            return response.text  # Continua para detectar bloqueio
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

    is_blocked = bool(re.search(r"(Just a moment|403 Forbidden|Access Denied|cloudflare)", html.lower()))

    return {
        "page_title": page_title,
        "og_title": og_title,
        "og_site": og_site,
        "url_slug": slug,
        "is_blocked": is_blocked,
        "domain": parsed.netloc.replace("www.", "")
    }

def normalize_identity(identity: dict) -> dict:
    raw_name = (
        identity["og_title"]
        or identity["page_title"]
        or identity["url_slug"]
        or "Desconhecido"
    )

    mod_name = re.sub(r'\s+', ' ', raw_name).strip()
    mod_name = re.sub(r'(by\s+[\w\s]+)$', '', mod_name, flags=re.I).strip()
    mod_name = mod_name.title() if mod_name.islower() else mod_name

    creator = identity["og_site"]
    if not creator or creator.lower() in ["itch.io", "curseforge.com", "patreon.com"]:
        if "by " in raw_name.lower():
            creator_part = re.search(r'by\s+([\w\s]+)', raw_name, re.I)
            if creator_part:
                creator = creator_part.group(1).strip()
            else:
                creator = identity["domain"]
        else:
            creator = identity["domain"]

    return {
        "mod_name": mod_name or "—",
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

# Footer com créditos às ferramentas
def add_credits_footer():
    footer_html = """
    <div style="
        text-align: center;
        padding: 1.2rem 0;
        font-size: 0.85rem;
        color: #6b7280;
        margin-top: 1.5rem;
        border-top: 1px solid #e5e7eb;
    ">
        <div style="margin-bottom: 0.6rem; font-weight: 500;">
            Criado por Akin (@UnpaidSimmer)
        </div>
        <div style="display: flex; justify-content: center; align-items: center; gap: 1.2rem; flex-wrap: wrap;">
            <span>Com:</span>
            <a href="https://lovable.dev" target="_blank" style="text-decoration: none;">
                <img src="https://lobehub.com/icons/lovable?type=color" alt="Lovable" style="height: 24px; vertical-align: middle;">
            </a>
            <a href="https://chatgpt.com" target="_blank" style="text-decoration: none;">
                <img src="https://lobehub.com/icons/openai?type=color" alt="ChatGPT" style="height: 24px; vertical-align: middle;">
            </a>
            <a href="https://x.ai" target="_blank" style="text-decoration: none;">
                <img src="https://lobehub.com/icons/grok?type=color" alt="Grok" style="height: 24px; vertical-align: middle;">
            </a>
            <a href="https://www.notion.so" target="_blank" style="text-decoration: none;">
                <img src="https://lobehub.com/icons/notion?type=color" alt="Notion" style="height: 24px; vertical-align: middle;">
            </a>
        </div>
    </div>
    """
    st.markdown(footer_html, unsafe_allow_html=True)

# ==============================================
# INTERFACE PRINCIPAL
# ==============================================

st.title("TS4 Mod Analyzer — Phase 1 (v3.1)")

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

                if result["identity_debug"]["is_blocked"]:
                    st.warning("⚠️ Página possivelmente bloqueada (ex: Cloudflare). Usando fallback.")
                if not result["identity_debug"]["og_title"]:
                    st.info("ℹ️ og:title não encontrado (comum em itch.io). Usando título da página.")

                st.success("Identidade extraída!")

                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("📦 Mod")
                    st.write(result["mod_name"])

                with col2:
                    st.subheader("👤 Criador")
                    st.write(result["creator"])

                with st.expander("🔍 Debug técnico"):
                    st.json(result["identity_debug"])

            except Exception as e:
                st.error(f"Erro: {str(e)}")

# Footer com créditos
add_credits_footer()

# O footer padrão do Streamlit aparece automaticamente abaixo
