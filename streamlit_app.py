# ============================================================
# TS4 Mod Analyzer — Phase 1 → Phase 3 (Hugging Face IA)
# Version: v3.5.7.2 — Closed
#
# ADDITIVE ONLY — Contract preserved
# Phase 3 enabled as real fallback
# ============================================================


import streamlit as st
import requests
import re
import json
import hashlib
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from notion_client import Client
from datetime import datetime, timezone  # <--- Adicionado timezone

# =========================
# PAGE CONFIG (sempre primeiro)
# =========================

st.set_page_config(
    page_title="TS4 Mod Analyzer — Phase 3 · v3.5.7.2",
    layout="centered"
)

st.markdown(
    """
    <style>
    .global-footer {
        position: fixed;
        bottom: 0;
        left: 0;
        width: 100%;
        background-color: rgba(17, 24, 39, 0.95);
        text-align: center;
        padding: 0.75rem 0;
        font-size: 0.8rem;
        color: #9ca3af;
        z-index: 999;
    }

    .global-footer img {
        height: 20px;
        vertical-align: middle;
        margin-right: 6px;
    }

    /* Evita que o footer cubra o conteúdo */
    .block-container {
        padding-bottom: 4rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================
# PERSISTÊNCIA LOCAL (notioncache)
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

if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None

if "ai_logs" not in st.session_state:
    st.session_state.ai_logs = []

if "decision_log" not in st.session_state:
    st.session_state.decision_log = []

if "matchcache" not in st.session_state:
    st.session_state.matchcache = {}

if "notfoundcache" not in st.session_state:
    st.session_state.notfoundcache = {}

if "notioncache" not in st.session_state:
    st.session_state.notioncache = {}

if "notioncache_loaded" not in st.session_state:
    st.session_state.notioncache_loaded = False

if "snapshot_loaded" not in st.session_state:
    st.session_state.snapshot_loaded = False

if "notion_fingerprint" not in st.session_state:
    st.session_state.notion_fingerprint = None


# =========================
# CONFIG
# =========================

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# =========================
# NOTION CLIENT (apenas para contexto futuro)
# =========================

NOTION_TOKEN = st.secrets["notion"]["token"]
NOTION_DATABASE_ID = st.secrets["notion"]["database_id"]
notion = Client(auth=NOTION_TOKEN)

# =========================
# HUGGING FACE (IA)
# =========================

HF_TOKEN = st.secrets["huggingface"]["token"]
HF_HEADERS = {
    "Authorization": f"Bearer {HF_TOKEN}",
    "Content-Type": "application/json"
}

HF_PRIMARY_MODEL = "https://api-inference.huggingface.co/models/google/flan-t5-base"
PHASE3_CONFIDENCE_THRESHOLD = 0.93

# =========================
# UTILS (Atualizado)
# =========================

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def now():
    """Retorna timestamp ISO-8601 UTC-aware, compatível com Python 3.13+"""
    return datetime.now(timezone.utc).isoformat()  # <--- Correção canônica

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

def hydrate_session_state(snapshot: dict):
    """
    Restaura o estado do app a partir de um snapshot canônico.
    """

    # =========================
    # Phase 2 — Fonte de verdade
    # =========================
    if "phase_2_cache" in snapshot:
        st.session_state.notioncache = snapshot["phase_2_cache"]
        st.session_state.notioncache_loaded = True
        st.session_state.notion_fingerprint = compute_notion_fingerprint()
    else:
        st.session_state.notioncache = {}
        st.session_state.notioncache_loaded = False
        st.session_state.notion_fingerprint = None

    # =========================
    # Phase 3 — Cache FOUND only
    # =========================
    if "phase_3_cache" in snapshot:
        st.session_state.matchcache = snapshot["phase_3_cache"]
    else:
        st.session_state.matchcache = {}

    # =========================
    # Log canônico (auditável)
    # =========================
    if "canonical_log" in snapshot:
        st.session_state.decision_log = snapshot["canonical_log"]
    else:
        st.session_state.decision_log = []

    # =========================
    # Nunca restaurado por snapshot
    # =========================
    st.session_state.notfoundcache = {}

    # =========================
    # Flag de controle
    # =========================
    st.session_state.snapshot_loaded = True


# =========================
# IDENTITY HASH CANÔNICO
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
# NOTIONCACHE LOADER
# =========================

def load_notioncache(data: dict):
    if "pages" not in data or not isinstance(data["pages"], dict):
        raise ValueError("Schema inválido: 'pages' ausente ou inválido")

    # Phase 2 — fonte canônica
    st.session_state.notioncache = data
    st.session_state.notioncache_loaded = True
    st.session_state.notion_fingerprint = compute_notion_fingerprint()

    # Reset apenas da análise corrente
    st.session_state.analysis_result = None


# =========================
# SNAPSHOT (CANÔNICO)
# =========================

def build_snapshot():
    return {
        "meta": {
            "app": "TS4 Mod Analyzer",
            "version": "v3.5.7.2",
            "created_at": now(),
            "phase_2_fingerprint": st.session_state.notion_fingerprint,
        },
        "phase_2_cache": st.session_state.notioncache,
        "phase_3_cache": st.session_state.matchcache,
        "canonical_log": st.session_state.decision_log,
    }

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
# PHASE 1 — IDENTIDADE
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
        "domain": parsed.netloc.replace("www.", ""),
        "is_blocked": is_blocked,
    }

def normalize_name(raw: str) -> str:
    if not raw:
        return "—"
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
# PHASE 2 — MATCH VIA NOTIONCACHE
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
# PHASE 3 — IA (SINAL · FALLBACK REAL)
# =========================

def slug_quality(slug: str) -> str:
    return "poor" if not slug or len(slug.split()) <= 2 else "good"

def build_ai_payload(identity, candidates):
    return {
        "identity": {
            "title": identity["mod_name"],
            "domain": identity["debug"]["domain"],
            "slug": identity["debug"]["url_slug"],
            "page_blocked": identity["debug"]["is_blocked"],
        },
        "candidates": [
            {"notion_id": c["notion_id"], "title": c["filename"]}
            for c in candidates
        ],
    }

def call_primary_model(payload):
    prompt = f"""
Compare the mod identity with the candidates.

Rules:
- Return JSON only
- match=true only if EXACTLY ONE clear match exists
- Include confidence (0–1)
- Do not guess

Payload:
{json.dumps(payload, ensure_ascii=False)}
"""
    r = requests.post(
        HF_PRIMARY_MODEL,
        headers=HF_HEADERS,
        json={"inputs": prompt, "parameters": {"temperature": 0}},
    )
    try:
        data = r.json()
        text = data[0].get("generated_text") if isinstance(data, list) else data.get("generated_text")
        return json.loads(text) if text else None
    except Exception:
        return None

def log_ai_event(stage, payload, result):
    st.session_state.ai_logs.append({
        "timestamp": now(),
        "stage": stage,
        "payload": payload,
        "result": result,
    })


# =========================
# UI — HEADER
# =========================

st.title("TS4 Mod Analyzer — Phase 3")
st.caption("Determinístico · Auditável · Zero achismo")

persisted = get_persisted_notioncache()
if (
    persisted
    and not st.session_state.snapshot_loaded
    and not st.session_state.notioncache_loaded
):
    load_notioncache(persisted)


# =========================
# FOOTER (GLOBAL · ESTRUTURAL)
# =========================

def render_footer():
    st.markdown(
        """
        <div class="global-footer">
            <img src="https://64.media.tumblr.com/05d22b63711d2c391482d6faad367ccb/675ea15a79446393-0d/s2048x3072/cc918dd94012fe16170f2526549f3a0b19ecbcf9.png">
            Criado por Akin (@UnpaidSimmer)
            <div style="font-size:0.7rem;opacity:0.6;">
                v3.5.7.2 · Phase 3
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

render_footer()


# =========================
# UI — SIDEBAR
# =========================

with st.sidebar:
    with st.expander("📥 Importar Snapshot (estado completo)", expanded=False):
        if not st.session_state.snapshot_loaded:
            uploaded_snapshot = st.file_uploader(
                "Snapshot JSON",
                type="json",
                key="snapshot_uploader"
            )

            if uploaded_snapshot:
                try:
                    snapshot = json.load(uploaded_snapshot)
                    hydrate_session_state(snapshot)
                    st.session_state.snapshot_loaded = True
                    st.success("Snapshot importado com sucesso.")
                    st.experimental_rerun()
                except Exception as e:
                    st.error(f"Erro ao importar snapshot: {e}")
        else:
            st.info("Snapshot já carregado nesta sessão.")

    with st.expander("📥 Importar notioncache", expanded=False):
        uploaded_cache = st.file_uploader("Arquivo JSON", type="json")
        if uploaded_cache:
            try:
                data = json.load(uploaded_cache)
                load_notioncache(data)
                persist_notioncache(data)
                st.success("notioncache importado e salvo.")
            except Exception as e:
                st.error(f"Erro ao importar: {e}")

    with st.expander("🗃️ Cache", expanded=False):
        st.download_button(
            "matchcache.json",
            json.dumps(st.session_state.matchcache, indent=2),
            "matchcache.json",
        )
        st.download_button(
            "notfoundcache.json",
            json.dumps(st.session_state.notfoundcache, indent=2),
            "notfoundcache.json",
        )

    with st.expander("📊 Logs", expanded=False):
        st.download_button(
            "decision_log.json",
            json.dumps(st.session_state.decision_log, indent=2),
            "decision_log.json",
        )
        st.download_button(
            "ai_log.json",
            json.dumps(st.session_state.ai_logs, indent=2),
            "ai_log.json",
        )

    with st.expander("📸 Snapshot", expanded=False):
        st.download_button(
            "snapshot.json",
            json.dumps(build_snapshot(), indent=2),
            "snapshot.json",
        )
# =========================
# UI — ANALYSIS
# =========================

if not st.session_state.notioncache_loaded:
    st.warning("Importe o notioncache para começar.")
    st.stop()

url_input = st.text_input("URL do mod")

if st.button("Analisar") and url_input.strip():
    identity = analyze_url(url_input.strip())
    identity_hash = build_identity_hash(identity)
    fp = compute_notion_fingerprint()

    if identity_hash in st.session_state.matchcache:
        st.session_state.analysis_result = st.session_state.matchcache[identity_hash]

    elif identity_hash in st.session_state.notfoundcache:
        st.session_state.analysis_result = st.session_state.notfoundcache[identity_hash]

    else:
        candidates = search_notioncache_candidates(identity["mod_name"], identity["url"])

        decision = {
            "timestamp": now(),
            "identity_hash": identity_hash,
            "identity": identity,
            "notion_fingerprint": fp,
            "phase_2_candidates": len(candidates),
            "decision": None,
            "reason": None,
            "notion_id": None,
            "notion_url": None,
        }

        # =========================
        # PHASE 2 — determinística
        # =========================
        if len(candidates) == 1:
            matched = candidates[0]

            notion_id = matched.get("id") or matched.get("notion_id")
            notion_url = f"https://www.notion.so/{notion_id.replace('-', '')}" if notion_id else None

            display_name = (
                matched.get("title")
                or matched.get("filename")
            )

            decision.update({
                "decision": "FOUND",
                "reason": "Deterministic match (Phase 2)",
                "notion_id": notion_id,
                "notion_url": notion_url,
                "display_name": display_name,
            })

            st.session_state.matchcache[identity_hash] = decision

        # =========================
        # PHASE 3 — fallback real
        # =========================
        else:
            payload = build_ai_payload(identity, candidates)
            ai_result = call_primary_model(payload)

            log_ai_event("PHASE_3_FALLBACK", payload, ai_result)

            if (
                ai_result
                and ai_result.get("match") is True
                and ai_result.get("confidence", 0) >= PHASE3_CONFIDENCE_THRESHOLD
            ):
                notion_id = ai_result.get("notion_id")
                notion_url = f"https://www.notion.so/{notion_id.replace('-', '')}" if notion_id else None

                decision.update({
                    "decision": "FOUND",
                    "reason": "AI fallback match (Phase 3)",
                    "notion_id": notion_id,
                    "notion_url": notion_url,
                    "display_name": ai_result.get("title"),
                })

                st.session_state.matchcache[identity_hash] = decision

            else:
                decision.update({
                    "decision": "NOT_FOUND",
                    "reason": "AI fallback no match (Phase 3)",
                })

                st.session_state.notfoundcache[identity_hash] = decision

        upsert_decision_log(identity_hash, decision)
        st.session_state.analysis_result = decision


# =========================
# UI — RESULTADO (CANÔNICO · RECONSTRUÍDO)
# =========================

result = st.session_state.get("analysis_result")

# 🔒 PATCH CANÔNICO
# Nunca acessar `.get()` se não houver resultado ativo
if not result:
    st.info("ℹ️ Insira uma URL e clique em **Analisar** para iniciar.")
    st.stop()

st.divider()
st.subheader("📦 Mod analisado")

# Identidade (fallback em cascata conforme contrato)
identity = result.get("identity", {})

mod_name = (
    result.get("display_name")
    or identity.get("mod_name")
    or "—"
)

st.markdown(f"**Nome:** {mod_name}")


# =========================
# DECISÃO FINAL
# =========================

decision = result.get("decision")

if decision == "FOUND":
    st.success("✅ Mod encontrado no Notion")
    st.markdown(f"[🔗 Abrir no Notion]({result.get('notion_url')})")
    
elif decision == "NOT_FOUND":
    st.info("ℹ️ Nenhuma entrada correspondente encontrada")
    
else:
    st.warning("⚠️ Estado de decisão inválido")


# =========================
# DEBUG (COLAPSÁVEL)
# =========================

with st.expander("🔍 Debug técnico"):
    st.markdown(f"**{result.get('reason')}**")
    st.json(result.get("identity", {}).get("debug", {}))
