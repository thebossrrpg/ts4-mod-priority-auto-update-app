# ============================================================
# TS4 Mod Analyzer — Phase 1 → Phase 3 (Hugging Face IA)
# Version: v3.5.65  # Bump para update fixes de contrato (aditivo)
#
# Contract:
# - Phase 1 preserved (identity extraction)
# - Phase 2 preserved (deterministic Notion match via cache)
# - Phase 3 preserved (IA last resort, provides signals only)
# - Post-Phase 3: Interprets IA signals deterministically
# - ADDITIVE ONLY:
#   • Deterministic cache (stores FINAL decision)
#   • Canonical decision log (1 entry per mod, explains WHY)
#   • Fingerprints for invalidation
#   • Logs in HTML format
#   • Fallback IA model
#
# Rule: New version = SUM, never subtraction
# ============================================================

import streamlit as st
import requests
import re
import json
import hashlib
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from notion_client import Client
from datetime import datetime

# =========================
# PAGE CONFIG
# =========================

st.set_page_config(
    page_title="TS4 Mod Analyzer — Phase 3 · v3.5.65",
    layout="centered"
)

# =========================
# SESSION STATE
# =========================

if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None

if "ai_logs" not in st.session_state:
    st.session_state.ai_logs = []

if "decision_log" not in st.session_state:
    st.session_state.decision_log = []

if "cache" not in st.session_state:  # legado, preservado
    st.session_state.cache = {}

if "matchcache" not in st.session_state:
    st.session_state.matchcache = {}

if "notfoundcache" not in st.session_state:
    st.session_state.notfoundcache = {}

if "notioncache_loaded" not in st.session_state:
    st.session_state.notioncache_loaded = False

if "notioncache" not in st.session_state:
    st.session_state.notioncache = {}

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
# NOTION CLIENT (para fingerprint, se necessário; não usado em Phase 2)
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
HF_FALLBACK_MODEL = "https://api-inference.huggingface.co/models/facebook/bart-large-mnli"
PHASE3_CONFIDENCE_THRESHOLD = 0.93  # Alta confiança para interpretação

# =========================
# UTILS
# =========================

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def now():
    return datetime.utcnow().isoformat()

def upsert_decision_log(identity_hash: str, decision: dict):
    for i, entry in enumerate(st.session_state.decision_log):
        if entry.get("identity_hash") == identity_hash:
            st.session_state.decision_log[i] = decision
            return
    st.session_state.decision_log.append(decision)

def compute_notion_fingerprint() -> str:
    # Computa baseado em notioncache (determinístico)
    if not st.session_state.notioncache:
        return "empty"
    page_ids = sorted(st.session_state.notioncache.get("pages", {}).keys())
    return sha256(",".join(page_ids))

# =========================
# IDENTITY HASH CANÔNICO (expandido aditivamente)
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
+    # Validar schema mínimo (pages deve existir no nível raiz)
+    if "pages" not in data or not isinstance(data["pages"], dict):
+        raise ValueError("Schema inválido: 'pages' ausente ou inválido")
     st.session_state.notioncache = data
     st.session_state.matchcache = data.get("matchcache", {})
     st.session_state.notfoundcache = data.get("notfoundcache", {})
     st.session_state.decision_log = data.get("decision_log", [])
     st.session_state.notion_fingerprint = compute_notion_fingerprint()
     st.session_state.notioncache_loaded = True
     st.session_state.analysis_result = None

# =========================
# SNAPSHOT (alinhado com schema canônico)
# =========================

def build_snapshot():
    return {
        "meta": {
            "app": "TS4 Mod Analyzer",
            "version": "v3.5.65",
            "created_at": now(),
            "phase_2_fingerprint": st.session_state.notion_fingerprint,
        },
        # 🔧 FIX: phase_2_cache é APENAS o alias serializado do notioncache no snapshot
        # Não representa um cache distinto no runtime
        "phase_2_cache": st.session_state.notioncache,
        "phase_3_cache": st.session_state.matchcache,  # Apenas FOUND
        "canonical_log": st.session_state.decision_log,  # Indeterminações
    }

def hydrate_session_state(snapshot: dict):
    required_keys = {"meta", "phase_2_cache", "phase_3_cache", "canonical_log"}
    if not required_keys.issubset(snapshot.keys()):
        raise ValueError("Snapshot inválido ou incompleto")
    st.session_state.notioncache = snapshot["phase_2_cache"]
    st.session_state.matchcache = snapshot["phase_3_cache"]
    st.session_state.decision_log = snapshot["canonical_log"]
    st.session_state.notion_fingerprint = snapshot["meta"].get("phase_2_fingerprint")
    st.session_state.notioncache_loaded = True
    st.session_state.analysis_result = None

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
# PHASE 1 — IDENTIDADE (INALTERADA)
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
# PHASE 2 — NOTION MATCH (usando cache)
# =========================

def search_notioncache_candidates(mod_name: str, url: str) -> list:
    candidates = []
    pages = st.session_state.notioncache.get("pages", {})

    # Match por URL exata
    for page_id, page in pages.items():
        if page.get("url") == url:
            candidates.append(page)

    # Match por Filename contendo mod_name normalizado
    normalized_mod = mod_name.lower()
    for page_id, page in pages.items():
        filename = page.get("filename", "").lower()
        if normalized_mod in filename:
            candidates.append(page)

    # Limitar a ~35 plausíveis, únicos por ID
    unique_candidates = {c["notion_id"]: c for c in candidates}
    return list(unique_candidates.values())[:35]

# =========================
# PHASE 3 — IA (sinal apenas)
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
        # 🔧 FIX: IA pode raciocinar sobre MAIS de 5 candidatos
        # O limite de 5 é de exposição humana / auditabilidade, não cognitivo
        "candidates": [
            {
                "notion_id": c["notion_id"],
                "title": c["filename"],
            }
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
        json={"inputs": prompt, "parameters": {"temperature": 0, "top_p": 1}},
    )

    if r.status_code != 200:
        return call_fallback_model(payload)  # Fallback

    try:
        data = r.json()
        text = data[0].get("generated_text") if isinstance(data, list) else data.get("generated_text")
        return json.loads(text) if text else None
    except Exception:
        return call_fallback_model(payload)

def call_fallback_model(payload):
    # Similar ao primary, mas com BART MNLI para classificação
    prompt = f"Classify if there's a unique match: {json.dumps(payload)}"
    r = requests.post(
        HF_FALLBACK_MODEL,
        headers=HF_HEADERS,
        json={"inputs": prompt, "parameters": {"temperature": 0, "top_p": 1}},
    )
    try:
        data = r.json()
        # Assumir parsing similar; ajustar para MNLI output (labels, scores)
        if isinstance(data, list) and data[0].get("labels"):
            top_label = data[0]["labels"][0]
            confidence = data[0]["scores"][0]
            return {"match": top_label == "match", "confidence": confidence}
        return None
    except Exception:
        return None

def log_ai_event(stage, payload, result):
    st.session_state.ai_logs.append({
        "timestamp": now(),
        "stage": stage,
        "payload_summary": payload,  # Summary para evitar grandeza
        "raw_response_snippet": result,
        "parsed_result": result,
        "error": None if result else "Fallback usado ou erro",
    })

# Função para gerar HTML canônico
def generate_html_log(data: list, json_id: str) -> str:
    json_str = json.dumps(data, indent=2, ensure_ascii=False)
    return f"""
    <html>
    <body>
    <script type="application/json" id="{json_id}">
    {json_str}
    </script>
    </body>
    </html>
    """

# =========================
# UI — HEADER
# =========================

st.title("TS4 Mod Analyzer — Phase 3")
st.caption("Determinístico · Auditável · Zero achismo")

# =========================
# IMPORTAÇÃO OBRIGATÓRIA
# =========================

st.subheader("📥 Importar notioncache (obrigatório)")

uploaded_cache = st.file_uploader(
    "notioncache_YYYY-MM-DD_HH-MM.json",
    type="json",
    accept_multiple_files=False
)

if uploaded_cache:
    try:
        cache_data = json.load(uploaded_cache)
        load_notioncache(cache_data)
        st.success("Notioncache importado com sucesso.")
    except Exception:
        st.error("Arquivo de notioncache inválido.")

if not st.session_state.notioncache_loaded:
    st.warning("Importe o notioncache antes de analisar qualquer mod.")
    st.stop()

# =========================
# UI — ANALYSIS
# =========================

url_input = st.text_input("URL do mod")

if st.button("Analisar") and url_input.strip():
    with st.spinner("Analisando..."):
        identity = analyze_url(url_input.strip())
        identity_hash = build_identity_hash(identity)

        # Atualizar fingerprint
        current_fp = compute_notion_fingerprint()
        if st.session_state.notion_fingerprint != current_fp:
            st.warning("Notioncache alterado; fingerprints atualizados.")
            st.session_state.notion_fingerprint = current_fp

        # Cache hit (com validação de fingerprint)
        if identity_hash in st.session_state.matchcache and st.session_state.matchcache[identity_hash].get("notion_fingerprint") == current_fp:
            decision = st.session_state.matchcache[identity_hash]
            upsert_decision_log(identity_hash, decision)
            st.session_state.analysis_result = decision
            st.info("⚡ Resultado recuperado do cache (FOUND)")

        elif identity_hash in st.session_state.notfoundcache and st.session_state.notfoundcache[identity_hash].get("notion_fingerprint") == current_fp:
            decision = st.session_state.notfoundcache[identity_hash]
            upsert_decision_log(identity_hash, decision)
            st.session_state.analysis_result = decision
            st.info("⚡ Resultado recuperado do cache (NOT_FOUND)")

        else:
            candidates = search_notioncache_candidates(identity["mod_name"], identity["url"])

            decision = {
                "timestamp": now(),
                "identity_hash": identity_hash,
                "identity": identity,
                "notion_fingerprint": current_fp,
                "phase_2_candidates": len(candidates),
                "phase_2_status": None,
                "phase_3_signal": None,
                "decision": None,
                "decision_source": None,
                "decision_reason": None,
            }

            if len(candidates) == 1:
                decision["phase_2_status"] = "UNIQUE"
                decision["decision"] = "FOUND"
                decision["decision_source"] = "PHASE2_DETERMINISTIC"
                decision["decision_reason"] = "Unique deterministic match in Phase 2"
                st.session_state.matchcache[identity_hash] = decision

            elif len(candidates) > 1:
                decision["phase_2_status"] = "AMBIGUOUS"

                if identity["debug"]["is_blocked"] or slug_quality(identity["debug"]["url_slug"]) == "poor":
                    payload = build_ai_payload(identity, candidates)
                    ai_result = call_primary_model(payload)
                    log_ai_event("PHASE_3_CALLED", payload, ai_result)
                    decision["phase_3_signal"] = ai_result

                    # Pós-Phase 3: Interpretação determinística
                    if (
                        ai_result
                        and ai_result.get("match") is True
                        and ai_result.get("confidence", 0) >= PHASE3_CONFIDENCE_THRESHOLD
                        and len(candidates) <= 3  # Compatível com Phase 2
                    ):
                        decision["decision"] = "FOUND"
                        decision["decision_source"] = "PHASE3_IA_MATCH"
                        decision["decision_reason"] = f"IA signal confirmed unique match (confidence {ai_result['confidence']})"
                        st.session_state.matchcache[identity_hash] = decision
                    else:
                        decision["decision"] = "NOT_FOUND"
                        decision["decision_source"] = "PHASE3_IA_NO_MATCH"
                        decision["decision_reason"] = "Ambiguous; IA signal did not confirm unique match"
                        st.session_state.notfoundcache[identity_hash] = decision
                else:
                    decision["decision"] = "NOT_FOUND"
                    decision["decision_source"] = "PHASE2_DETERMINISTIC"
                    decision["decision_reason"] = "Ambiguous candidates with strong identity; IA skipped"
                    st.session_state.notfoundcache[identity_hash] = decision

            else:
                decision["phase_2_status"] = "NONE"
                decision["decision"] = "NOT_FOUND"
                decision["decision_source"] = "PHASE2_DETERMINISTIC"
                decision["decision_reason"] = "No deterministic candidates in Phase 2"
                st.session_state.notfoundcache[identity_hash] = decision

            upsert_decision_log(identity_hash, decision)
            st.session_state.analysis_result = decision

# =========================
# UI — RESULT
# =========================

result = st.session_state.analysis_result

if result:
    st.subheader("📦 Mod")
    st.write(result["identity"]["mod_name"])
    st.success(result["decision"])

    with st.expander("🔍 Debug técnico"):
        st.json(result)

# =========================
# DOWNLOADS — CACHE / LOG (alinhado com contrato)
# =========================

st.divider()
st.subheader("📁 Dados persistentes")

with st.expander("Downloads de cache"):
    st.download_button(
        "notioncache.json",
        data=json.dumps(st.session_state.notioncache, indent=2, ensure_ascii=False),
        file_name="notioncache.json",
        mime="application/json",
    )
    st.download_button(
        "matchcache.json",
        data=json.dumps(st.session_state.matchcache, indent=2, ensure_ascii=False),
        file_name="matchcache.json",
        mime="application/json",
    )
    st.download_button(
        "notfoundcache.json",
        data=json.dumps(st.session_state.notfoundcache, indent=2, ensure_ascii=False),
        file_name="notfoundcache.json",
        mime="application/json",
    )

with st.expander("Downloads de logs"):
    decision_html = generate_html_log(st.session_state.decision_log, "decisionlog-json")
    st.download_button(
        "decisionlog.html",
        data=decision_html,
        file_name="decisionlog.html",
        mime="text/html",
    )
    ialog_html = generate_html_log(st.session_state.ai_logs, "ialog-json")
    st.download_button(
        "ialog.html",
        data=ialog_html,
        file_name="ialog.html",
        mime="text/html",
    )

st.download_button(
    "📦 Baixar snapshot completo (JSON)",
    data=json.dumps(build_snapshot(), indent=2, ensure_ascii=False),
    file_name="ts4_mod_snapshot_v3.5.65.json",
    mime="application/json",
)

# =========================
# FOOTER (CANÔNICO — PRESERVADO)
# =========================

st.markdown(
    """
    <div style="text-align:center;padding:1rem 0;font-size:0.85rem;color:#6b7280;">
        <img src="https://64.media.tumblr.com/05d22b63711d2c391482d6faad367ccb/675ea15a79446393-0d/s2048x3072/cc918dd94012fe16170f2526549f3a0b19ecbcf9.png"
             style="height:20px;vertical-align:middle;margin-right:6px;">
        Criado por Akin (@UnpaidSimmer)
        <div style="font-size:0.7rem;opacity:0.6;">v3.5.65 · Phase 3 (IA controlada)</div>
    </div>
    """,
    unsafe_allow_html=True,
)
