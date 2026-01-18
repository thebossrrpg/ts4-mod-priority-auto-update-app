import streamlit as st
import requests
import re
import json
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import google.generativeai as genai


# =========================
# CONFIG
# =========================

st.set_page_config(page_title="TS4 Mod Analyzer — Phase 1", layout="centered")

MAX_TEXT_CHARS = 12000
GEMINI_MODEL = "gemini-1.5-flash"


# =========================
# UTILS
# =========================

def detect_source(url: str) -> str:
    domain = urlparse(url).netloc.lower()

    if "patreon.com" in domain:
        return "patreon"
    if "tumblr.com" in domain:
        return "tumblr"
    if domain:
        return "website"
    return "unknown"


def clean_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def fetch_page(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    return response.text


# =========================
# GEMINI READER (FASE 1)
# =========================

def lm_read_mod(source: str, url: str, raw_text: str) -> dict:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

    model = genai.GenerativeModel(GEMINI_MODEL)

    prompt = f"""
You are a parser. You DO NOT classify mods.
You ONLY extract factual information.

Return ONLY valid JSON with the following fields:
- mod_name
- creator
- functional_summary
- confidence ("high", "medium", "low")
- notes (array of short strings)

Rules:
- If information is unclear, use null.
- Do NOT invent data.
- Focus only on what the mod DOES in-game.

Source: {source}
URL: {url}

TEXT:
\"\"\"
{raw_text[:MAX_TEXT_CHARS]}
\"\"\"
"""

    response = model.generate_content(
        prompt,
        generation_config={"temperature": 0}
    )

    return json.loads(response.text)


# =========================
# FASE 1 ORCHESTRATOR
# =========================

def phase1_analyze_url(url: str) -> dict:
    source = detect_source(url)
    html = fetch_page(url)
    raw_text = clean_text(html)

    lm_data = lm_read_mod(
        source=source,
        url=url,
        raw_text=raw_text
    )

    result = {
        "source": source,
        "url": url,
        "mod_name": lm_data.get("mod_name"),
        "creator": lm_data.get("creator"),
        "raw_text": raw_text,
        "functional_summary": lm_data.get("functional_summary"),
        "confidence": lm_data.get("confidence"),
        "notes": lm_data.get("notes", [])
    }

    assert_phase1_output(result)
    return result


def assert_phase1_output(data: dict):
    required_keys = {
        "source",
        "url",
        "mod_name",
        "creator",
        "raw_text",
        "functional_summary",
        "confidence",
        "notes"
    }

    assert set(data.keys()) == required_keys
    assert data["confidence"] in {"high", "medium", "low"}
    assert isinstance(data["notes"], list)


# =========================
# STREAMLIT UI
# =========================

st.title("TS4 Mod Analyzer — Phase 1")
st.markdown(
    "Cole uma **URL de mod** (Patreon, Tumblr ou site). "
    "O app **apenas lê e descreve** o mod."
)

url_input = st.text_input("URL do mod")

if st.button("Analisar"):
    if not url_input:
        st.error("Por favor, insira uma URL.")
    else:
        with st.spinner("Lendo a página e analisando..."):
            try:
                result = phase1_analyze_url(url_input)

                st.success("Análise concluída (Fase 1)")

                st.subheader("Resultado estruturado")
                st.json({
                    "source": result["source"],
                    "url": result["url"],
                    "mod_name": result["mod_name"],
                    "creator": result["creator"],
                    "functional_summary": result["functional_summary"],
                    "confidence": result["confidence"],
                    "notes": result["notes"]
                })

                with st.expander("Texto bruto extraído (raw_text)"):
                    st.text(result["raw_text"][:5000])

            except Exception as e:
                st.error(f"Erro durante a análise: {e}")
