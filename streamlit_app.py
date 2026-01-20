# ============================================================
# TS4 Mod Analyzer — Phase 2 (Com Cruzamento Real)
# Version: v3.5 (Com Notion real, cruzamento total de dados)
# ============================================================

import os
import re
import requests
import streamlit as st
from urllib.parse import urlparse
from bs4 import BeautifulSoup

# =========================
# CONFIG
# =========================

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json",
}

# =========================
# HELPERS
# =========================

def normalize_url(url: str) -> str:
    if not url:
        return ""
    url = url.strip()
    url = re.sub(r"#.*$", "", url)
    url = re.sub(r"\?.*$", "", url)
    if url.endswith("/"):
        url = url[:-1]
    return url.lower()

def extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""

# =========================
# FASE 1 — IDENTIDADE (INTACTA)
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
        return "—"
    cleaned = re.sub(r"\s+", " ", raw).strip()
    cleaned = re.sub(r"(by\s+[\w\s]+)$", "", cleaned, flags=re.I).strip()
    return cleaned.title() if cleaned.islower() else cleaned

def normalize_identity(identity: dict) -> dict:
    if not identity["is_blocked"] and identity["page_title"]:
        preferred = identity["page_title"]
    elif identity["og_title"]:
        preferred = identity["og_title"]
    else:
        preferred = identity["url_slug"]

    return {
        "mod_name": normalize_name(preferred),
        "creator": identity["og_site"] or identity["domain"],
    }

def analyze_url(url: str) -> dict:
    html = fetch_page(url)
    raw = extract_identity(html, url)
    norm = normalize_identity(raw)

    return {
        "url": url,
        "mod_name": norm["mod_name"],
        "creator": norm["creator"],
        "identity_debug": raw,
    }

# =========================
# NOTION QUERY — FASE 2 (COM NOTION REAL)
# =========================

def fetch_all_notion_pages() -> list:
    url = f"{NOTION_API_URL}/databases/{NOTION_DATABASE_ID}/query"
    results = []
    payload = {}

    while True:
        r = requests.post(url, headers=NOTION_HEADERS, json=payload)
        if r.status_code != 200:
            return {"error": r.text}

        data = r.json()
        results.extend(data.get("results", []))

        if not data.get("has_more"):
            break

        payload["start_cursor"] = data["next_cursor"]

    return results


def extract_properties_from_page(page: dict) -> dict:
    properties = {}

    props = page.get("properties", {})
    properties["title"] = props.get("Name", {}).get("title", [{}])[0].get("plain_text", "")
    properties["category"] = props.get("Category", {}).get("select", {}).get("name", "—")
    properties["priority"] = props.get("Priority", {}).get("select", {}).get("name", "—")
    properties["url"] = next((v["url"] for v in props.values() if v.get("url")), "")

    return properties


def phase2(identity: dict) -> dict:
    target_url = normalize_url(identity["url"])

    pages = fetch_all_notion_pages()
    if isinstance(pages, dict) and "error" in pages:
        return {
            "status": "error",
            "error": pages["error"],
            "candidates": [],
        }

    matches = []

    for page in pages:
        props = extract_properties_from_page(page)

        notion_url = normalize_url(props["url"])

        # Verificação de correspondência de URL
        if notion_url == target_url:
            matches.append({
                "page_id": page["id"],
                "notion_url": notion_url,
                "mod_name": props["title"],
                "creator": props["category"],
                "priority": props["priority"],
                "reason": "URL idêntica"
            })

        # Verificação de correspondência de nome
        if identity["mod_name"].lower() in props["title"].lower():
            matches.append({
                "page_id": page["id"],
                "notion_url": notion_url,
                "mod_name": props["title"],
                "creator": props["category"],
                "priority": props["priority"],
                "reason": "Nome similar"
            })

    return {
        "status": "duplicate" if matches else "new_entry",
        "candidates_found": len(matches),
        "candidates": matches[:3],
    }

# =========================
# UI
# =========================

st.title("🧪 TS4 Mod Analyzer — Phase 2 (Sandbox)")
st.caption("Fase 1 intacta · Fase 2 honesta · Sem mock")

url_input = st.text_input("URL do mod")

if st.button("Analisar") and url_input.strip():
    with st.spinner("Analisando..."):
        identity = analyze_url(url_input.strip())
        phase2_result = phase2(identity)

    st.subheader("📦 Identidade detectada")
    st.write(f"**Mod:** {identity['mod_name']}")
    st.write(f"**Criador:** {identity['creator']}")
    st.write(f"**Domínio:** {urlparse(identity['url']).netloc}")

    if identity["identity_debug"]["is_blocked"]:
        st.warning("⚠️ Página bloqueou leitura automática. Identidade baseada na URL.")

    st.subheader("🔎 Resultado da Fase 2")
    st.write(f"**Status:** {phase2_result['status']}")
    st.write(f"**Candidatos encontrados:** {phase2_result['candidates_found']}")

    if phase2_result["candidates"]:
        for c in phase2_result["candidates"]:
            st.markdown(
                f"- **[Abrir no Notion]({c['notion_url']})**  \n"
                f"  _{c['mod_name']} · {c['creator']} · {c['priority']}_"
            )
    else:
        st.success("Nenhuma entrada correspondente encontrada no Notion.")

    with st.expander("🔍 Debug completo"):
        st.json({
            "identity": identity,
            "phase2": phase2_result
        })

# =========================
# FOOTER (INCLUÍDO)
# =========================

st.markdown(
    """
    <div style="text-align: center; padding: 1rem 0; font-size: 0.9rem; color: #6b7280;">
        <img src="https://64.media.tumblr.com/05d22b63711d2c391482d6faad367ccb/675ea15a79446393-0d/s2048x3072/cc918dd94012fe16170f2526549f3a0b19ecbcf9.png" 
             alt="Favicon" 
             style="height: 20px; vertical-align: middle; margin-right: 8px;">
        Criado por Akin (@UnpaidSimmer)
        <div style="margin-top: 0.5rem; font-size: 0.75rem; opacity: 0.6;">
            v3.5 · Sandbox
        </div>
    </div>
    """,
    unsafe_allow_html=True
)
