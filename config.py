"""
Central configuration for the multi-agent CV / Cover-Letter system.

This is the ONLY module that reads environment variables (Instructions.md step 3:
"loads all environment variables in one place. Never hardcode keys anywhere else").
Every other module imports its settings from here.

Layout
------
- Paths            : project / knowledge-base / prompt directories
- Test mode        : TEST_MODE flag -> DEV_MODE (Instructions Part 1)
- MODEL_CONFIG     : per-agent model assignment (Build.md "Per-agent model")
- Provider routing : LiteLLM model strings + fallback chains (Instructions Part 3)
- API keys         : every provider credential, read once, here
- Observability    : Langfuse
- Budget guard     : Gemini daily-cap thresholds (Instructions Part 4)
"""

from __future__ import annotations

import contextvars
import os
from pathlib import Path

from dotenv import load_dotenv

# -----------------------------------------------------------------------------
# Load .env (project root) exactly once, at import time.
# -----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# -----------------------------------------------------------------------------
# Filesystem paths
# -----------------------------------------------------------------------------
PROMPTS_DIR = BASE_DIR / "prompts"

KB_DIR = BASE_DIR / "knowledge_base"
KB_DOCUMENTS_DIR = KB_DIR / "documents"        # CV/CL examples + templates (vector)
KB_PROFILE_DIR = KB_DIR / "profile"            # projects/skills/achievements (vector)
KB_DO_NOT_CLAIM_DIR = KB_DIR / "do_not_claim"  # hard constraint list (plain JSON)
KB_LEARNING_DIR = KB_DIR / "learning"          # per-agent exemplars + scores
# Env-overridable (same default) so a throwaway server — scripts/dev.py smoke — can keep its
# test accounts out of the real folder (bug #86 item 3).
KB_AUTH_DIR = Path(os.getenv("KB_AUTH_DIR") or (KB_DIR / "auth"))  # access requests + issued tokens (git-ignored)
VECTORDB_DIR = KB_DIR / "chroma"               # Chroma persistent vector index (git-ignored)
CV_INPUT_DIR = KB_DIR / "input"                # CV PDFs read by utils/cv_handling; kept out of profile/ (git-ignored)
CV_SANDBOX_DIR = BASE_DIR / "test_work" / "test_vb"   # sandbox Chroma for the CLI test scripts only: pdf_documents (+ profile_bullets when a script passes it)
# The `profile_bullets` index the live cv_link node matches CV lines against. A derived cache
# (rebuilt from the KB JSON when its count drifts), kept in its own Chroma folder under the KB
# so a deploy needs no test_work/ at all and it rides on the knowledge_base volume.
CV_BULLET_INDEX_DIR = Path(os.getenv("CV_BULLET_INDEX_DIR") or (KB_DIR / "chroma_bullets"))
CV_MATCH_DIR = BASE_DIR / "test_work" / "cv_match"    # CV match outputs (tree + links JSON)
# Sample CV, used only as the admin/demo fallback once CV upload exists
# (design.md D-CV2: block non-admins with no CV; never the admin, who may have
# no profile of their own to upload against). Still read from server config,
# never from the request: a client-supplied path would let a caller point
# cv_link at any file on the host.
CV_DEFAULT_PATH = Path(os.getenv("CV_DEFAULT_PATH") or (CV_INPUT_DIR / "CV_test.pdf"))
# User-uploaded CV PDFs, one subtree per owner: uploads/{owner}/cv/{sha256[:12]}.pdf
# plus that owner's index.json (backend/cv_store.py). Git-ignored and on the
# persisted volume, same treatment as KB_AUTH_DIR. `owner` is token_id until
# Stage 0 §13.1's profile_id lands.
CV_UPLOADS_DIR = Path(os.getenv("CV_UPLOADS_DIR") or (BASE_DIR / "uploads"))

STATE_DIR = BASE_DIR / "state"
RUNS_DIR = Path(os.getenv("RUNS_DIR") or (BASE_DIR / "logs" / "frontend_runs"))  # one JSON event log per pipeline run
CHECKPOINT_DB = BASE_DIR / "logs" / "checkpoints.sqlite"  # durable graph state for interrupt()/resume
PLAN_CACHE_DIR = BASE_DIR / "logs" / "plan_cache"  # Document planner answers (LLM call 1), one JSON per call fingerprint
# PLAN_CACHE=0: never read or write that folder, so the planner is called every time.
PLAN_CACHE = os.getenv("PLAN_CACHE", "1").strip().lower() in {"1", "true", "yes", "on"}
LEARNING_DIR = BASE_DIR / "learning"
EVALUATION_DIR = BASE_DIR / "evaluation"
OUTPUTS_DIR = BASE_DIR / "outputs"             # generated documents / run artifacts

# -----------------------------------------------------------------------------
# Test / cost mode (Instructions Part 1: "Wiring it as one flag")
#   dev / eval. Since 2026-10-19 this no longer changes model routing: MODEL_CONFIG
#   below is the user's fixed per-agent assignment. Use USE_FAKE_LLM=1 (or
#   FAKE_CRITIC_VERDICT) for routine development so Gemini is not spent.
# -----------------------------------------------------------------------------
TEST_MODE = os.getenv("TEST_MODE", "dev").strip().lower()
DEV_MODE = TEST_MODE == "dev"
#Offline build mode: when on, every agent uses a local fake LLM (no network,
# lets us build and test the whole graph before any key exists
USE_FAKE_LLM = os.getenv("USE_FAKE_LLM", "0").strip().lower() in {"1", "true", "yes", "on"}

# Per-run override of the offline switch, for the frontend bridge: one process
# can now have several pipeline runs in flight (one per user), each started in
# "offline" or "live" mode independently. Mutating the USE_FAKE_LLM global from a
# run's worker thread — what the bridge used to do — lets a live run flip an
# in-flight offline run onto real, billed providers, and vice versa.
#
# A ContextVar and not a threading.local(): LangGraph runs a node inline on the
# calling thread only while it is the single runnable task for that step
# (langgraph/pregel/_runner.py). Any parallel step is submitted to a
# ContextThreadPoolExecutor via copy_context() (pregel/_executor.py), i.e. a
# DIFFERENT thread — where a thread-local set by the API worker is invisible and
# the switch would silently fail open. copy_context() carries ContextVars by
# design, so this works on both paths.
_fake_llm: contextvars.ContextVar[bool | None] = contextvars.ContextVar("fake_llm", default=None)


def set_fake_llm(value: bool) -> None:
    """Force offline (True) / live (False) for the current context only."""
    _fake_llm.set(bool(value))


def fake_llm_active() -> bool:
    """Is the fake LLM active here? Per-run override wins, else the env default."""
    override = _fake_llm.get()
    return USE_FAKE_LLM if override is None else override


# Whose data this run may touch (backend/bugs.md "2026-10-09 (design)" §3).
# Same carrier as _fake_llm above and for the same reason: a run's worker thread
# sets it, and every node — inline or on a copy_context() pool thread — reads the
# value its own run set, never another in-flight run's. A module global or a
# threading.local would make one user's collection, plan cache or export folder
# visible to another user's node the moment two runs overlap.
#
# Deliberately a bare profile_id string, not a Scope object: `backend/deps.Scope`
# carries a role as well, and nothing the graph does may depend on the caller
# being an admin — an admin's run reads the admin's own vault, exactly like
# everyone else's. Keeping the role out of the graph means there is no path for
# a privileged caller to widen what a node can see.
_profile_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("profile_id", default=None)


def set_profile_id(value: str | None) -> None:
    """Bind this run's account for the current context only. None clears it."""
    _profile_id.set(value or None)


def current_profile_id() -> str | None:
    """This run's account, or None outside a scoped run (a bare CLI driver)."""
    return _profile_id.get()


def require_profile_id() -> str:
    """This run's account, or raise. Use this at every door that reaches user
    data — a vault path, a per-profile collection, the plan cache, an export.

    Raising is the point (§3: "a missing scope raises"). The alternative to an
    unscoped read is not a harmless default; it is the shared, everyone's-data
    behaviour that §3 exists to end, and silently falling back to it is exactly
    how one account's evidence reached another's run.
    """
    value = _profile_id.get()
    if not value:
        raise RuntimeError(
            "No profile is in scope: this code reaches per-account data and must run "
            "inside a scoped run (config.set_profile_id, set by backend/runs/worker.py "
            "or a CLI driver's --profile)."
        )
    return value


# -----------------------------------------------------------------------------
# Frontend access control (scripts/frontend_api.py -> backend/)
# -----------------------------------------------------------------------------
# The one definition of the bridge API's port (bugs_audit_fixed.md #40: dev.py
# served 8002 while the Vite proxy, nginx and the smoke test all called 8000, so
# `dev.py up` showed a dashboard whose every call failed and `dev.py smoke`
# checked whatever stale server happened to hold 8000). Everything that needs
# the port reads the BACKEND_PORT env var, with this default:
#   - scripts/dev.py       reads the env/.env directly (it must stay runnable
#                          without the venv, so it cannot import config)
#   - scripts/smoke_backend.py  via SMOKE_BASE, which dev.py builds from it
#   - frontend/vite.config.js   via process.env.BACKEND_PORT
#   - frontend/nginx.conf.template   takes the backend address from the BACKEND_URL
#                          env var (default http://host.docker.internal:8000 in the
#                          Dockerfile), so a non-default port needs BACKEND_URL set,
#                          not a rebuild. It does not read BACKEND_PORT itself.
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))
# Bootstrap admin credential. Empty means no one can administer the bridge: no
# access request can ever be approved, so no user token can ever be issued.
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
# Pipeline runs granted per issued user token. Admin is never decremented.
DEFAULT_RUN_ALLOWANCE = int(os.getenv("DEFAULT_RUN_ALLOWANCE", "2"))

# Canonical model identifiers (provider-agnostic names).
# Set GROQ_MODEL in .env to a model your Groq key can list (GET /openai/v1/models).
GROQ_LLAMA = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
# Defaults moved 2026-10-24: gemini-2.5-flash is closed to new API users (404) and Cerebras no
# longer serves llama-3.3-70b to this key (its list: gpt-oss-120b, qwen-3.8-27b). The names stay.
GEMINI_FLASH = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
CEREBRAS_LLAMA = os.getenv("CEREBRAS_MODEL", "gpt-oss-120b").strip()
OPENROUTER_FREE = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free").strip()
OPENROUTER_GEMINI_FREE = os.getenv("OPENROUTER_GEMINI_MODEL", "google/gemini-2.0-flash-exp:free").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Single-flag provider override (same one-flag pattern as USE_FAKE_LLM / TEST_MODE):
#   USE_OPENAI=1 -> route EVERY agent to OpenAI (OPENAI_MODEL), ignoring the
#   Groq/Gemini per-mode assignment below. USE_FAKE_LLM still wins over this
#   (offline structure testing stays free). Lets the whole system run on just an
#   OpenAI key when Groq/Gemini aren't set up.
USE_OPENAI = os.getenv("USE_OPENAI", "0").strip().lower() in {"1", "true", "yes", "on"}

# Per-agent model assignment (the user's allocation, 2026-10-19). Four providers:
# Groq for routine structured work, Gemini Flash where output quality is the
# product, Cerebras as the second lane, OpenRouter free for occasional calls.
# A provider with no key is skipped and the agent's lane falls over (FALLBACK_CHAINS).
MODEL_CONFIG: dict[str, str] = {
    "supervisor":     GROQ_LLAMA,       # routing is deterministic (decide()); no LLM call today
    "jd_analysis":    GROQ_LLAMA,       # structured extraction
    "profile":        GROQ_LLAMA,       # retrieval-heavy, one grading call
    "profile_enrich": CEREBRAS_LLAMA,   # polishes gap answers into compact KB text
    "matching":       GROQ_LLAMA,       # requirement-to-evidence grading
    "document":       GEMINI_FLASH,     # LLM 2 of the CV patcher: writes the lines
    "document_plan":  GROQ_LLAMA,       # LLM 1 of the CV patcher: keep/refine/rewrite, no writing
    "critic":         GEMINI_FLASH,     # quality review; use FAKE_CRITIC_VERDICT in routine dev
    "verifier":       CEREBRAS_LLAMA,   # stub in Stage 0; real calls only for semantic checks
    "evaluation":     OPENROUTER_FREE,  # occasional evaluation / model comparison
    # Scratch/experiment agents: prompts exist, no pipeline node.
    "query_refine":   GROQ_LLAMA,
    "rerank_critic":  OPENROUTER_FREE,
    # Sandbox company-ranking agents (scripts/agentic_rank_test.py).
    "rank_refiner":   GROQ_LLAMA,
    "rank_verifier":  CEREBRAS_LLAMA,
}

# OpenAI override: repoint every agent at the single OpenAI model in one place.
if USE_OPENAI:
    MODEL_CONFIG = {agent: OPENAI_MODEL for agent in MODEL_CONFIG}

# -----------------------------------------------------------------------------
# Provider routing + fallback chains (agents/base.py _live_answer)
#   Each canonical model has a lane: element 0 is the primary, the rest are tried
#   in order once the primary's retries are used up. Entries are "provider/model";
#   a provider with no key is skipped.
# -----------------------------------------------------------------------------
GROQ_LANE = [
    f"groq/{GROQ_LLAMA}",
    f"cerebras/{CEREBRAS_LLAMA}",
    f"openrouter/{OPENROUTER_FREE}",
]
CEREBRAS_LANE = [
    f"cerebras/{CEREBRAS_LLAMA}",
    f"groq/{GROQ_LLAMA}",
    f"openrouter/{OPENROUTER_FREE}",
]
OPENROUTER_LANE = [
    f"openrouter/{OPENROUTER_FREE}",
    f"groq/{GROQ_LLAMA}",
    f"cerebras/{CEREBRAS_LLAMA}",
]
GEMINI_LANE = [
    f"gemini/{GEMINI_FLASH}",
    f"openrouter/{OPENROUTER_GEMINI_FREE}",
    f"groq/{GROQ_LLAMA}",  # quality degrades here, but the run completes
]
OPENAI_LANE = [
    f"openai/{OPENAI_MODEL}",
    f"groq/{GROQ_LLAMA}",  # last-resort degrade so a run still completes
]

# Map a canonical model name -> its full fallback chain (primary is element 0).
FALLBACK_CHAINS: dict[str, list[str]] = {
    GROQ_LLAMA: GROQ_LANE,
    CEREBRAS_LLAMA: CEREBRAS_LANE,
    OPENROUTER_FREE: OPENROUTER_LANE,
    GEMINI_FLASH: GEMINI_LANE,
    OPENAI_MODEL: OPENAI_LANE,
}
if len(FALLBACK_CHAINS) != 5:
    # Two providers configured with the same model string would share one lane.
    raise RuntimeError("config: two provider models have the same name; set distinct *_MODEL values.")

# Lane provider prefix -> the env var holding its key.
PROVIDER_KEY = {
    "groq": "GROQ_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "cerebras": "CEREBRAS_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
}

# The agents that are graph nodes (sandbox agents excluded from key checks).
PIPELINE_AGENTS = [
    "jd_analysis", "profile", "profile_enrich", "matching",
    "document_plan", "document", "critic", "verifier", "evaluation",
]

# LLM door settings (agents/base.py structured_call). Set fallback_offline
# False for Stage 0 production: a fallback answer is fake data.
RETRY = {
    "rate_limit_wait_seconds": 5.0,   # fixed wait after a 429, before trying again
    "rate_limit_attempts": 4,         # total tries on the provider when it keeps sending 429
    "none_attempts": 2,               # total tries when the model returns None
    "fallback_offline": False,         # 429 tries used up -> answer with the offline fake LLM
}

# LangGraph's step budget for ONE invoke/stream call. pregel/_loop.py recomputes
# it as (current step + recursion_limit + 1) at the start of every call, so each
# gate resume begins a fresh budget and only the longest single call matters:
# gate 3 -> gate 4, which holds the whole Critic/Verifier loop at ~6 steps a lap.
# The default 25 overruns as soon as max_revisions goes past its default 2
# (bugs_audit_fixed.md #78 item 1). A flat ceiling cannot under-provision at any
# cap, and decide() already bounds the loop by max_revisions, so this is only a
# backstop against a wiring bug that never terminates.
RECURSION_LIMIT = 100


def model_for(agent: str) -> str:
    """Canonical model name assigned to an agent (e.g. 'llama-3.3-70b-versatile')."""
    try:
        return MODEL_CONFIG[agent]
    except KeyError as exc:
        raise KeyError(
            f"Unknown agent '{agent}'. Known agents: {sorted(MODEL_CONFIG)}"
        ) from exc


def fallback_chain_for(agent: str) -> list[str]:
    """Ordered LiteLLM model strings (primary first) for an agent's lane."""
    return list(FALLBACK_CHAINS[model_for(agent)])


def primary_litellm_model(agent: str) -> str:
    """Primary LiteLLM model string for an agent (head of its fallback chain)."""
    return fallback_chain_for(agent)[0]


# -----------------------------------------------------------------------------
# API keys — read once, here, and nowhere else.
# -----------------------------------------------------------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# -----------------------------------------------------------------------------
# Observability (Langfuse)
# -----------------------------------------------------------------------------
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")
# The SDK's own name is LANGFUSE_BASE_URL; LANGFUSE_HOST is the older one. Keys are per region.
LANGFUSE_HOST = (os.getenv("LANGFUSE_BASE_URL") or os.getenv("LANGFUSE_HOST") or "https://cloud.langfuse.com").strip().strip('"')
LANGFUSE_ENABLED = bool(LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY)

# -----------------------------------------------------------------------------
# Durable checkpointer. What actually backs the gates today is CHECKPOINT_DB
# above (SqliteSaver, utils/checkpointer.py). DATABASE_URL is the Build.md
# Postgres target and has no reader yet - the swap is one function.
# -----------------------------------------------------------------------------
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/agentic"
)

# -----------------------------------------------------------------------------
# Embeddings / reranking (local, free — sentence-transformers)
# -----------------------------------------------------------------------------
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-base-en-v1.5")
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-base")

# -----------------------------------------------------------------------------
# Gemini daily-budget guard (Instructions Part 4, items 22-23)
# -----------------------------------------------------------------------------
GEMINI_DAILY_LIMIT = int(os.getenv("GEMINI_DAILY_LIMIT", "1500"))
GEMINI_ALERT_THRESHOLD = int(os.getenv("GEMINI_ALERT_THRESHOLD", "1200"))


# -----------------------------------------------------------------------------
# Validation — call from main.py / app startup, not at import time.
# -----------------------------------------------------------------------------
def required_keys_for_mode() -> list[str]:
    """Env var names that must be set for the current TEST_MODE to actually run."""
    if USE_FAKE_LLM:
        return []  # offline mode needs no provider keys at all
    if USE_OPENAI:
        return ["OPENAI_API_KEY"]  # override routes every agent to OpenAI
    # The primary provider of every pipeline agent. A missing one is not fatal at run
    # time (the lane falls over), but it means that agent never runs where assigned.
    return sorted({PROVIDER_KEY[primary_litellm_model(a).partition("/")[0]] for a in PIPELINE_AGENTS})


def validate(strict: bool = False) -> list[str]:
    """
    Return a list of human-readable config problems (empty == all good).

    Set strict=True to raise instead of returning, e.g. on production startup.
    """
    problems: list[str] = []

    if TEST_MODE not in {"dev", "eval"}:
        problems.append(f"TEST_MODE must be 'dev' or 'eval', got '{TEST_MODE}'.")

    for key in required_keys_for_mode():
        if not os.getenv(key):
            problems.append(f"Missing required env var: {key} (needed in '{TEST_MODE}' mode).")

    if strict and problems:
        raise RuntimeError("Configuration invalid:\n  - " + "\n  - ".join(problems))
    return problems


def summary() -> str:
    """One-glance, secret-free view of the active configuration."""
    def mask(v: str) -> str:
        return "set" if v else "—"

    provider = "OpenAI (USE_OPENAI)" if USE_OPENAI else ("fake/offline" if USE_FAKE_LLM else "per-agent (Groq/Gemini/Cerebras/OpenRouter)")
    lines = [
        f"TEST_MODE          : {TEST_MODE} (DEV_MODE={DEV_MODE})",
        f"Active provider    : {provider}",
        "Model assignment   :",
        *[f"    {a:<15}-> {primary_litellm_model(a)}" for a in MODEL_CONFIG],
        "Provider keys      :",
        f"    GROQ           : {mask(GROQ_API_KEY)}",
        f"    GOOGLE         : {mask(GOOGLE_API_KEY)}",
        f"    OPENAI         : {mask(OPENAI_API_KEY)}",
        f"    CEREBRAS       : {mask(CEREBRAS_API_KEY)}",
        f"    OPENROUTER     : {mask(OPENROUTER_API_KEY)}",
        f"Langfuse           : {'enabled' if LANGFUSE_ENABLED else 'disabled'}",
        f"Embeddings         : {EMBEDDING_MODEL}",
        f"Reranker           : {RERANKER_MODEL}",
        f"Gemini guard       : alert at {GEMINI_ALERT_THRESHOLD}/{GEMINI_DAILY_LIMIT} calls/day",
    ]
    return "\n".join(lines)
