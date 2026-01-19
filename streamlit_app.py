# ============================================================
# TS4 Mod Analyzer — Phase 2 (Sandbox)
# Version: v3.5
# Score cruzado por nome + URL + domínio (sem IA)
# ============================================================

import streamlit as st
import requests
import re
from urllib.parse import urlparse
from bs4 import BeautifulSoup

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
    )
}

STOPWORDS = {
    "mod", "mods", "post", "posts", "v", "v1", "v2", "version",
    "the", "and", "or", "for", "with", "by"
}

# =========================
# MOCK NOTION DATA (sandbox)
# =========================

NOTION_MODS = [
    "LGBTQIA+ / Gender & Orientation Overhaul",
    "Mini-mods: Tweaks & Changes",
    "Automatic Beard Shadows"
]

# =========================
# HELPERS
# =========================

def clean_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9+ ]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def tokenize(text: str) -> list[str]:
    tokens = clean_text(text).split()
    return [
        t for t in tokens
        if t not in STOPWORDS and len(t) > 2
    ]

def fetch_page(url: str) -> str:
    r = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    return r.text

# =========================
# IDENTIDADE (Fase 1 reaproveitada)
# =========================

def extract_identity(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    page_title = soup.title.string.strip() if soup.title else None

    og_title = None
    og_site = None
    for meta in soup.find_all("meta"):
        if meta.get("property") == "og:title":
            og_title = meta.get("content")
        if meta.get("property") == "og:site_name":
            og_site = meta.get("content")

    parsed = urlparse(url)
    slug = parsed.path.replace("-", " ").replace("/", " ")

    blocked = bool(
        page_title
        and "just a moment" in page_title.lower()
    )

    return {
        "mod_name": og_title or page_title or slug,
        "creator": og_site or parsed.netloc.replace("www.", ""),
        "url_slug": slug,
        "domain": parsed.netloc.replace("www.", ""),
        "is_blocked": blocked
    }

# =========================
# SCORE CRUZADO POR EIXOS
# =========================

def score_against_notion(identity: dict) -> dict:
    slug_tokens = tokenize(identity["url_slug"])
    name_tokens = tokenize(identity["mod_name"])

    all_input_tokens = set(slug_tokens + name_tokens)

    results = []

    for notion_name in NOTION_MODS:
        notion_tokens = tokenize(notion_name)

        common = set(notion_tokens) & all_input_tokens

        score = 0.0
        reasons = []

        # EIXO 1 — Token semântico direto
        if common:
            score += 0.30 + 0.05 * len(common)
            reasons.append(f"tokens em comum: {sorted(common)}")

        # EIXO 2 — Token raro (ex: lgbtqia)
        rare_tokens = [
            t for t in common
            if len(t) >= 6 or "+" in t
        ]
        if rare_tokens:
            score += 0.20
            reasons.append(f"tokens raros: {rare_tokens}")

        # EIXO 3 — URL confirma tema
        if any(t in slug_tokens for t in notion_tokens):
            score += 0.15
            reasons.append("URL confirma tema")

        # EIXO 4 — Penalidade por ruído
        noise = [t for t in slug_tokens if t.isdigit()]
        if noise:
            score -= 0.05

        score = round(min(score, 1.0), 2)

        results.append({
            "notion_name": notion_name,
            "score": score,
            "debug": {
                "slug_tokens": slug_tokens,
                "name_tokens": name_tokens,
                "notion_tokens": notion_tokens,
                "common_tokens": list(common),
                "reasons": reasons
            }
        })

    best = max(results, key=lambda r: r["score"])

    return {
        "scores": results,
        "best_match": best
    }

# =========================
# UI
# =========================

st.title("🧪 Fase 2 (Sandbox): detecção de duplicatas")
st.caption("⚠️ Não escreve no Notion. Apenas testes de score.")

url = st.text_input("URL do mod")

if st.button("Analisar") and url.strip():
    with st.spinner("Analisando..."):
        html = fetch_page(url)
        identity = extract_identity(html, url)
        scoring = score_against_notion(identity)

    st.subheader("📦 Identidade")
    st.write(f"**Mod:** {identity['mod_name']}")
    st.write(f"**Criador:** {identity['creator']}")

    st.subheader("🔎 Verificação de duplicata")

    score = scoring["best_match"]["score"]

    if score >= 0.6:
        st.error("🚨 Provável duplicata")
    elif score >= 0.35:
        st.warning("⚠️ Possível duplicata")
    else:
        st.success("✅ Provavelmente novo mod")

    st.write(f"**Score:** {score}")
    st.write(f"**Possível match:** {scoring['best_match']['notion_name']}")

    with st.expander("🔍 Debug detalhado"):
        st.json({
            "identity": identity,
            **scoring
        })


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
