# ============================================================
# TS4 Mod Analyzer — Phase 1 → Phase 3 (Integrated)
# Version: v3.5.7.3 — Runtime Fixes & List Logic
#
# CHANGES:
# - Fix: datetime.now(timezone.utc) for Python 3.13+
# - Fix: candidates logic (AttributeError)
# - UI: Corrected Footer CSS and Structure
# ============================================================

import streamlit as st
import requests
import re
import json
import hashlib
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from notion_client import Client
from datetime import datetime, timezone  # <--- [FIX 1] Import timezone

# =========================
# PAGE CONFIG & CSS
# =========================
st.set_page_config(
    page_title="TS4 Mod Analyzer — Phase 3 · v3.5.7.3",
    layout="centered"
)

st.markdown(
    """
    <style>
    .stButton>button {width: 100%;}
    .reportview-container .main .block-container {padding-top: 2rem;}
    div[data-testid="stExpander"] div[role="button"] p {font-size: 1rem; font-weight: 600;}
    
    /* CSS DO FOOTER */
    .global-footer {
        position: fixed;
        bottom: 0;
        left: 0;
        width: 100%;
        background-color: #0e1117;
        text-align: center;
        padding: 10px;
        z-index: 999;
        font-size: 0.8em;
        color: #888;
        border-top: 1px solid #262730;
    }
    .global-footer img {
        height: 20px;
        vertical-align: middle;
        margin-right: 8px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================
# PERSISTÊNCIA LOCAL
# =========================
@st.cache_data(show_spinner=False)
def get_persisted_notioncache():
    return st.session_state.get("_persisted_notioncache")

def persist_notioncache(data: dict):
    st.session_state["_persisted_notioncache"] = data
    get_persisted_notioncache.clear()

# =========================
# SESSION STATE
# =========================
DEFAULT_KEYS = {
    "analysis_result": None,
    "ai_logs": [],
    "decision_log": [],
    "matchcache": {},
    "notfoundcache": {},
    "notioncache": {},
    "notioncache_loaded": False,
    "snapshot_loaded": False,
    "notion_fingerprint": None,
}

for k, v in DEFAULT_KEYS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# =========================
# CONFIG & CLIENTS
# =========================
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

NOTION_TOKEN = st.secrets["notion"]["token"]
NOTION_DATABASE_ID = st.secrets["notion"]["database_id"]
notion = Client(auth=NOTION_TOKEN)

HF_TOKEN = st.secrets["huggingface"]["token"]
HF_HEADERS = {
    "Authorization": f"Bearer {HF_TOKEN}",
    "Content-Type": "application/json"
}
HF_PRIMARY_MODEL = "https://api-inference.huggingface.co/models/google/flan-t5-base"

# =========================
# UTILS
# =========================
def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def now():
    """Retorna timestamp ISO-8601 UTC-aware, compatível com Python 3.13+"""
    # [FIX 2] Uso correto de timezone para evitar DeprecationWarning
    return datetime.now(timezone.utc).isoformat()

def compute_notion_fingerprint() -> str:
    if not st.session_state.notioncache:
        return "empty"
    page_ids = sorted(st.session_state.notioncache.get("pages", {}).keys())
    return sha256(",".join(page_ids))

def upsert_decision_log(identity_hash: str, decision: dict):
    for i, entry in enumerate(st.session_state.decision_log):
        if entry.get("identity_hash") == identity_hash:
            st.session_state.decision_log[i] = decision
            return
    st.session_state.decision_log.append(decision)

# =========================
# SNAPSHOT / HYDRATE
# =========================
def hydrate_session_state(snapshot: dict):
    if "phase_2_cache" in snapshot:
        st.session_state.notioncache = snapshot["phase_2_cache"]
        st.session_state.notioncache_loaded = True
        st.session_state.notion_fingerprint = compute_notion_fingerprint()
    else:
        st.session_state.notioncache = {}
        st.session_state.notioncache_loaded = False
        st.session_state.notion_fingerprint = None

    if "phase_3_cache" in snapshot:
        st.session_state.matchcache = snapshot["phase_3_cache"]
    else:
        st.session_state.matchcache = {}

    if "canonical_log" in snapshot:
        st.session_state.decision_log = snapshot["canonical_log"]
    else:
        st.session_state.decision_log = []

    st.session_state.notfoundcache = {}
    st.session_state.snapshot_loaded = True

def build_snapshot():
    return {
        "meta": {
            "app": "TS4 Mod Analyzer",
            "version": "v3.5.7.3",
            "created_at": now(),
            "phase_2_fingerprint": st.session_state.notion_fingerprint,
        },
        "phase_2_cache": st.session_state.notioncache,
        "phase_3_cache": st.session_state.matchcache,
        "canonical_log": st.session_state.decision_log,
    }

def load_notioncache(data: dict):
    if "pages" not in data or not isinstance(data["pages"], dict):
        raise ValueError("Schema inválido: 'pages' ausente ou inválido")
    st.session_state.notioncache = data
    st.session_state.notioncache_loaded = True
    st.session_state.notion_fingerprint = compute_notion_fingerprint()
    st.session_state.analysis_result = None

# =========================
# HASH BUILDER
# =========================
def build_identity_hash(identity: dict) -> str:
    canonical_identity = {
        "url": identity["url"],
        "mod_name": identity["mod_name"],
        "domain": identity["debug"]["domain"],
        "slug": identity["debug"]["url_slug"],
        "is_blocked": identity["debug"]["is_blocked"],
    }
    return sha256(json.dumps(canonical_identity, sort_keys=True))

# =========================
# PHASE 1 — IDENTIDADE
# =========================
def fetch_page(url: str) -> str:
    try:
        r = requests.get(url, headers=REQUEST_HEADERS, timeout=25)
        return r.text or ""
    except Exception:
        return ""

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
        "domain": parsed.netloc.replace("www.", ""),
        "is_blocked": is_blocked,
    }

def normalize_name(raw: str) -> str:
    if not raw: return "—"
    cleaned = re.sub(r"\s+", " ", raw).strip()
    cleaned = re.sub(r"(by\s+[\w\s]+)$", "", cleaned, flags=re.I).strip()
    return cleaned.title() if cleaned.islower() else cleaned

def analyze_url(url: str) -> dict:
    html = fetch_page(url)
    raw = extract_identity(html, url)
    raw_name = raw["page_title"] or raw["og_title"] or raw["url_slug"]
    return {
        "url": url,
        "mod_name": normalize_name(raw_name),
        "debug": raw,
    }

# =========================
# PHASE 2 — MATCHING DETERMINÍSTICO
# =========================
def search_notioncache_candidates(mod_name: str, url: str) -> list:
    candidates = []
    pages = st.session_state.notioncache.get("pages", {})
    
    for page in pages.values():
        if page.get("url") == url:
            candidates.append(page)
            
    normalized = mod_name.lower()
    for page in pages.values():
        if normalized in page.get("filename", "").lower():
            candidates.append(page)
            
    return list({c["notion_id"]: c for c in candidates}.values())[:35]

# =========================
# UI MAIN
# =========================
st.title("TS4 Mod Analyzer — Phase 3")
st.caption("Determinístico · Auditável · Zero achismo")

# Loader de persistência
persisted = get_persisted_notioncache()
if persisted and not st.session_state.snapshot_loaded and not st.session_state.notioncache_loaded:
    load_notioncache(persisted)

# =========================
# FOOTER
# =========================
def render_footer():
    # Certifique-se de substituir a URL da imagem se tiver uma
    img_tag = '<img src="https://raw.githubusercontent.com/thebossrrpg/ts4-mod-priority-auto-update/main/assets/logo_small.png" alt="Logo">' 
    st.markdown(
        f"""
        <div class="global-footer">
            {img_tag}
            Criado por Akin (@UnpaidSimmer) | v3.5.7.3
        </div>
        """,
        unsafe_allow_html=True,
    )
render_footer()

# =========================
# SIDEBAR
# =========================
with st.sidebar:
    with st.expander("📥 Importar Snapshot", expanded=False):
        if not st.session_state.snapshot_loaded:
            uploaded_snapshot = st.file_uploader("Snapshot JSON", type="json", key="snap_up")
            if uploaded_snapshot:
                try:
                    snapshot = json.load(uploaded_snapshot)
                    hydrate_session_state(snapshot)
                    st.success("Snapshot carregado.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro: {e}")
        else:
            st.info("Snapshot ativo.")

    with st.expander("📥 Importar notioncache", expanded=False):
        uploaded_cache = st.file_uploader("notioncache.json", type="json")
        if uploaded_cache:
            try:
                data = json.load(uploaded_cache)
                load_notioncache(data)
                persist_notioncache(data)
                st.success("Cache atualizado.")
            except Exception as e:
                st.error(f"Erro: {e}")

    with st.expander("🗃️ Downloads", expanded=False):
        st.download_button("matchcache.json", json.dumps(st.session_state.matchcache, indent=2), "matchcache.json")
        st.download_button("decision_log.json", json.dumps(st.session_state.decision_log, indent=2), "decision_log.json")
        st.download_button("snapshot.json", json.dumps(build_snapshot(), indent=2), "snapshot.json")

# =========================
# ANÁLISE (PHASE 1-3)
# =========================
if not st.session_state.notioncache_loaded:
    st.warning("⚠️ Importe o notioncache.json na barra lateral para começar.")
    st.stop()

url_input = st.text_input("URL do mod")

if st.button("Analisar") and url_input.strip():
    with st.spinner("Executando Fases 1, 2 e 3..."):
        # Phase 1
        identity = analyze_url(url_input.strip())
        identity_hash = build_identity_hash(identity)
        fp = compute_notion_fingerprint()

        # Cache Check
        if identity_hash in st.session_state.matchcache:
            st.session_state.analysis_result = st.session_state.matchcache[identity_hash]
        elif identity_hash in st.session_state.notfoundcache:
            st.session_state.analysis_result = st.session_state.notfoundcache[identity_hash]
        else:
            # Phase 2
            candidates = search_notioncache_candidates(identity["mod_name"], identity["url"])
            
            decision = {
                "timestamp": now(),
                "identity_hash": identity_hash,
                "identity": identity,
                "notion_fingerprint": fp,
                "phase_2_candidates": len(candidates),
                "decision": None,
                "notion_id": None,
                "notion_url": None
            }

            if candidates:
    # pega o melhor match determinístico (primeiro da lista)
    matched = candidates[0]

    notion_id = matched.get("id") or matched.get("notion_id")
    notion_url = f"https://www.notion.so/{notion_id.replace('-', '')}" if notion_id else None

    # Tratamento seguro de títulos aninhados
    props = matched.get("properties", {})
    title_prop = props.get("Filename") or props.get("Name")
    title_list = title_prop.get("title", []) if title_prop else []
    # title_list é lista de objetos; pegamos o primeiro item
    if title_list and isinstance(title_list, list):
        mod_title = title_list[0].get("plain_text", "Unknown")
    else:
        mod_title = "Unknown"

    decision.update({
        "decision": "FOUND",
        "reason": "Deterministic match (Phase 2)",
        "notion_id": notion_id,
        "notion_url": notion_url,
        "display_name": mod_title,
    })
    st.session_state.matchcache[identity_hash] = decision
else:
    decision.update({
        "decision": "NOT_FOUND",
        "reason": "No candidates found",
    })
    st.session_state.notfoundcache[identity_hash] = decision


                decision.update({
                    "decision": "FOUND",
                    "reason": "Deterministic match (Phase 2)",
                    "notion_id": notion_id,
                    "notion_url": notion_url,
                    "display_name": mod_title,
                })
                st.session_state.matchcache[identity_hash] = decision
            else:
                decision.update({
                    "decision": "NOT_FOUND",
                    "reason": "No candidates found",
                })
                st.session_state.notfoundcache[identity_hash] = decision
            
            upsert_decision_log(identity_hash, decision)
            st.session_state.analysis_result = decision

# =========================
# EXIBIÇÃO DE RESULTADO
# =========================
result = st.session_state.get("analysis_result")

if not result:
    st.info("Insira uma URL acima para iniciar.")
    st.stop()

st.divider()
st.subheader("📦 Resultado da Análise")

identity = result.get("identity", {})
mod_name = result.get("display_name") or identity.get("mod_name") or "—"
st.markdown(f"**Mod:** {mod_name}")

decision_val = result.get("decision")

if decision_val == "FOUND":
    st.success("✅ Mod encontrado no Notion")
    st.markdown(f"[🔗 Abrir página no Notion]({result.get('notion_url')})")

elif decision_val == "NOT_FOUND":
    st.warning("⚠️ Mod não encontrado na base.")

else:
    st.error(f"Estado inválido: {decision_val}")

# =========================
# DEBUG
# =========================
with st.expander("🔍 Debug Técnico"):
    st.json(result)
