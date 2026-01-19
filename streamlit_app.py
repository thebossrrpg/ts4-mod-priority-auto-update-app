# ============================================================
# TS4 Mod Analyzer — Phase 1 + Phase 2 (Sandbox honesto)
# Phase 1: v3.3 (INTACTA)
# Phase 2: v3.5 (URL-first, sem mock, até 3 candidatos)
# ============================================================

import streamlit as st
import requests
import re
from urllib.parse import urlparse
from bs4 import BeautifulSoup

# =========================
# SESSION STATE
# =========================

if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None

# =========================
# CONFIG
# =========================

st.set_page_config(
    page_title="TS4 Mod Analyzer — Phase 2",
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

STOPWORDS = {
    "mod", "mods", "the", "and", "or", "for", "with", "by"
}

# =========================
# FETCH (Fase 1 — intacta)
# =========================

def fetch_page(url: str) -> str:
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    if response.status_code in (403, 429):
        return response.text
    response.raise_for_status()
    return response.text

# =========================
# FASE 1 — IDENTIDADE
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
# FASE 2 — MATCH REAL (URL FIRST)
# =========================

def clean_tokens(text: str) -> set:
    text = text.lower()
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    tokens = {
        t for t in text.split()
        if t not in STOPWORDS and len(t) > 2
    }
    return tokens

def normalize_url(u: str) -> str:
    p = urlparse(u)
    return f"{p.netloc}{p.path}".rstrip("/").lower()

def phase2(identity: dict, notion_urls: list[str]) -> dict:
    input_url_norm = normalize_url(identity["url"])
    input_tokens = clean_tokens(identity["mod_name"])

    candidates = []

    for n_url in notion_urls:
        n_url_norm = normalize_url(n_url)

        score = 0.0
        reasons = []

        if input_url_norm == n_url_norm:
            score += 0.7
            reasons.append("URL idêntica")

        name_from_url = urlparse(n_url).path.replace("-", " ")
        notion_tokens = clean_tokens(name_from_url)

        common = input_tokens & notion_tokens
        if common:
            score += 0.1 * len(common)
            reasons.append(f"tokens em comum: {sorted(common)}")

        if score > 0:
            candidates.append({
                "url": n_url,
                "score": round(min(score, 1.0), 2),
                "reasons": reasons
            })

    candidates.sort(key=lambda x: x["score"], reverse=True)

    return {
        "status": "duplicate" if candidates else "new_entry",
        "candidates_found": len(candidates),
        "candidates": candidates[:3],
    }

# =========================
# UI
# =========================

st.title("🧪 TS4 Mod Analyzer — Phase 2 (Sandbox)")
st.caption("Fase 1 intacta · Fase 2 honesta · Sem mock")

url_input = st.text_input("URL do mod")

notion_input = st.text_area(
    "Cole URLs do Notion (uma por linha)",
    placeholder="https://...\nhttps://..."
)

if st.button("Analisar") and url_input.strip():
    with st.spinner("Analisando..."):
        identity = analyze_url(url_input.strip())
        notion_urls = [u.strip() for u in notion_input.splitlines() if u.strip()]
        phase2_result = phase2(identity, notion_urls)

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
                f"- **Score {c['score']}** → "
                f"[Abrir no Notion]({c['url']})  \n"
                f"  _{', '.join(c['reasons'])}_"
            )
    else:
        st.success("Nenhuma entrada correspondente encontrada no Notion.")

    with st.expander("🔍 Debug completo"):
        st.json({
            "identity": identity,
            "phase2": phase2_result
        })

# =========================
# FOOTER (INTACTO)
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
