# ============================================================
# TS4 Mod Analyzer — Phase 1 → Phase 4 (Integrated)
# Version: v3.6.0 — Priority Classification
#
# ADDITIVE UPDATE: Phase 4 added to stable v3.5.7.2 base.
# ============================================================

import streamlit as st
import requests
import re
import json
import hashlib
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from notion_client import Client
from datetime import datetime, timezone

# =========================
# PAGE CONFIG
# =========================
st.set_page_config(
    page_title="TS4 Mod Analyzer — Phase 4 · v3.6.0",
    layout="centered"
)

st.markdown(
    """
    <style>
    .stButton>button {width: 100%;}
    .reportview-container .main .block-container {padding-top: 2rem;}
    div[data-testid="stExpander"] div[role="button"] p {font-size: 1rem; font-weight: 600;}
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
# SESSION STATE INITIALIZATION
# =========================
DEFAULT_KEYS = {
    "analysis_result": None,
    "ai_logs": [],
    "decision_log": [],
    "matchcache": {},
    "notfoundcache": {},
    "phase4_cache": {},  # <--- FASE 4 (Novo Cache)
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

# Notion Credentials
NOTION_TOKEN = st.secrets["notion"]["token"]
NOTION_DATABASE_ID = st.secrets["notion"]["database_id"]
notion = Client(auth=NOTION_TOKEN)

# Hugging Face Credentials
HF_TOKEN = st.secrets["huggingface"]["token"]
HF_HEADERS = {
    "Authorization": f"Bearer {HF_TOKEN}",
    "Content-Type": "application/json"
}
HF_PRIMARY_MODEL = "https://api-inference.huggingface.co/models/google/flan-t5-base"
PHASE3_CONFIDENCE_THRESHOLD = 0.93

# =========================
# UTILS
# =========================
def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def now():
    """Retorna timestamp ISO-8601 UTC-aware (Python 3.13 safe)"""
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
# SNAPSHOT / HYDRATE (Atualizado para Fase 4)
# =========================
def hydrate_session_state(snapshot: dict):
    """Restaura caches e logs a partir do snapshot JSON."""
    
    # Phase 2
    if "phase_2_cache" in snapshot:
        st.session_state.notioncache = snapshot["phase_2_cache"]
        st.session_state.notioncache_loaded = True
        st.session_state.notion_fingerprint = compute_notion_fingerprint()
    else:
        st.session_state.notioncache = {}
        st.session_state.notioncache_loaded = False
        st.session_state.notion_fingerprint = None

    # Phase 3
    if "phase_3_cache" in snapshot:
        st.session_state.matchcache = snapshot["phase_3_cache"]
    else:
        st.session_state.matchcache = {}

    # Phase 4 (NOVO)
    if "phase_4_cache" in snapshot:
        st.session_state.phase4_cache = snapshot["phase_4_cache"]
    else:
        st.session_state.phase4_cache = {}

    # Logs
    if "canonical_log" in snapshot:
        st.session_state.decision_log = snapshot["canonical_log"]
    else:
        st.session_state.decision_log = []

    st.session_state.notfoundcache = {} # Nunca restaura notfound
    st.session_state.snapshot_loaded = True

def build_snapshot():
    return {
        "meta": {
            "app": "TS4 Mod Analyzer",
            "version": "v3.6.0",
            "created_at": now(),
            "phase_2_fingerprint": st.session_state.notion_fingerprint,
        },
        "phase_2_cache": st.session_state.notioncache,
        "phase_3_cache": st.session_state.matchcache,
        "phase_4_cache": st.session_state.phase4_cache, # Incluído
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
# PHASE 3 — IA MATCHING
# =========================
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
    try:
        r = requests.post(
            HF_PRIMARY_MODEL, 
            headers=HF_HEADERS, 
            json={"inputs": prompt, "parameters": {"temperature": 0}},
            timeout=10
        )
        data = r.json()
        # Tratamento robusto para lista ou dict
        if isinstance(data, list) and len(data) > 0:
            text = data.get("generated_text")
        elif isinstance(data, dict):
            text = data.get("generated_text")
        else:
            text = None
            
        return json.loads(text) if text else None
    except Exception:
        return None

# =========================
# PHASE 4 — PRIORITY CLASSIFICATION (INTEGRADA)
# =========================
def fetch_notion_page_context(notion_id: str) -> dict:
    """Busca dados da página no Notion para a Fase 4."""
    try:
        page = notion.pages.retrieve(notion_id)
        props = page.get("properties", {})
        
        # Extração segura de Prioridade (Select)
        p_select = props.get("Priority", {}).get("select")
        priority_val = p_select["name"] if p_select else "Pending"
        
        # Extração segura de Notes (Rich Text) - usado para Subclassificação
        notes_prop = props.get("Notes", {}).get("rich_text", [])
        notes_text = "".join([t["plain_text"] for t in notes_prop]) if notes_prop else ""
        
        return {
            "priority": priority_val,
            "notes_context": notes_text,
            "page_url": page.get("url"),
        }
    except Exception as e:
        return {"error": str(e)}

def call_priority_model(context: dict) -> dict:
    """Chama a IA para sugerir prioridade baseada no contexto."""
    prompt = f"""
    You are classifying update priority for a Sims 4 mod.
    Rules:
    - Return JSON only.
    - 'priority' must be an integer 0-5.
    - 'subcategory' (e.g. 3A, 4B) goes into text if applicable.
    - Suggest based on the provided context.
    
    Context:
    {json.dumps(context, indent=2)}
    """
    try:
        r = requests.post(
            HF_PRIMARY_MODEL,
            headers=HF_HEADERS,
            json={"inputs": prompt, "parameters": {"temperature": 0}},
            timeout=10
        )
        data = r.json()
        
        if isinstance(data, list) and len(data) > 0:
            text = data.get("generated_text")
        elif isinstance(data, dict):
            text = data.get("generated_text")
        else:
            return {"error": "Invalid AI response"}
            
        return json.loads(text) if text else {"error": "Empty response"}
    except Exception as e:
        return {"error": str(e)}

def phase4_process(identity_hash: str, notion_id: str):
    """Orquestrador da Fase 4."""
    current_data = fetch_notion_page_context(notion_id)
    
    if "error" in current_data:
        return {"error": current_data["error"]}
        
    ai_result = call_priority_model(current_data)
    
    suggested = {
        "priority": str(ai_result.get("priority", "?")),
        "sub_category": ai_result.get("subcategory", "None"),
    }
    
    source = "AUTO" if suggested.get("priority") == current_data.get("priority") else "MANUAL_CHECK"
    
    result = {
        "current": current_data,
        "suggested": suggested,
        "source": source,
        "timestamp": now(),
    }
    
    # Salva no cache da Fase 4 e no log de IA
    st.session_state.phase4_cache[identity_hash] = result
    
    st.session_state.ai_logs.append({
        "timestamp": now(),
        "stage": "PHASE_4",
        "input": current_data,
        "output": suggested,
        "source": source
    })
    
    return result

# =========================
# UI MAIN
# =========================
st.title("TS4 Mod Analyzer — Phase 3+4")
st.caption("Determinístico · Auditável · Classificação de Prioridade")

# Loader de persistência
persisted = get_persisted_notioncache()
if persisted and not st.session_state.snapshot_loaded and not st.session_state.notioncache_loaded:
    load_notioncache(persisted)

# =========================
# FOOTER
# =========================
def render_footer():
    st.markdown(
        """
        <div style="position: fixed; bottom: 0; width: 100%; text-align: center; color: #888; font-size: 0.8em; background-color: #0e1117; padding: 10px;">
        Criado por Akin (@UnpaidSimmer) | v3.6.0 · Integrated Phase 4
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

    with st.expander("🗃️ Downloads (Caches/Logs)", expanded=False):
        st.download_button("matchcache.json", json.dumps(st.session_state.matchcache, indent=2), "matchcache.json")
        st.download_button("phase4_cache.json", json.dumps(st.session_state.phase4_cache, indent=2), "phase4_cache.json") # Novo
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
                matched = candidates # Simplificação determinística Phase 2
                notion_id = matched.get("id") or matched.get("notion_id")
                notion_url = f"https://www.notion.so/{notion_id.replace('-', '')}" if notion_id else None
                
                # Retrieve title safely
                title_list = matched.get("properties", {}).get("Filename", {}).get("title", [])
                if not title_list: 
                     title_list = matched.get("properties", {}).get("Name", {}).get("title", [])
                
                mod_title = title_list.get("plain_text", "Unknown") if title_list else "Unknown"

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
    
    # =========================
    # PHASE 4 INTEGRATION (Só aparece se FOUND)
    # =========================
    identity_hash = result["identity_hash"]
    notion_id = result["notion_id"]
    
    st.markdown("---")
    with st.expander("🔢 Phase 4 — Classificação de Prioridade", expanded=True):
        if notion_id:
            # Check cache Phase 4
            if identity_hash in st.session_state.phase4_cache:
                p4_data = st.session_state.phase4_cache[identity_hash]
                curr = p4_data.get("current", {})
                sugg = p4_data.get("suggested", {})
                
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("#### Atual (Notion)")
                    st.write(f"Prioridade: **{curr.get('priority')}**")
                    st.text(f"Contexto: {curr.get('notes_context')[:50]}...")
                with col2:
                    st.markdown("#### Sugestão (IA)")
                    st.write(f"Prioridade: **{sugg.get('priority')}**")
                    st.write(f"Subclassificação: **{sugg.get('sub_category')}**")
                
                if st.button("🔄 Re-classificar"):
                    del st.session_state.phase4_cache[identity_hash]
                    st.rerun()
            else:
                st.info("Classificação de prioridade ainda não realizada para esta versão.")
                if st.button("🚀 Rodar Classificação de Prioridade"):
                    with st.spinner("Lendo Notion e consultando IA..."):
                        out = phase4_process(identity_hash, notion_id)
                        if "error" in out:
                            st.error(f"Erro na Fase 4: {out['error']}")
                        else:
                            st.success("Classificação concluída!")
                            st.rerun()
        else:
            st.error("Notion ID perdido. Não é possível rodar Fase 4.")

elif decision_val == "NOT_FOUND":
    st.warning("⚠️ Mod não encontrado na base atual.")
    st.markdown("A Fase 4 (Prioridade) requer que o mod já exista no Notion.")

else:
    st.error(f"Estado inválido: {decision_val}")

# =========================
# DEBUG
# =========================
with st.expander("🔍 Debug Técnico"):
    st.json(result)
