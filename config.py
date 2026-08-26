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
KB_AUTH_DIR = KB_DIR / "auth"                  # access requests + issued tokens (git-ignored)
VECTORDB_DIR = KB_DIR / "chroma"               # Chroma persistent vector index (git-ignored)

STATE_DIR = BASE_DIR / "state"
RUNS_DIR = BASE_DIR / "logs" / "frontend_runs"  # one JSON event log per pipeline run
CHECKPOINT_DB = BASE_DIR / "logs" / "checkpoints.sqlite"  # durable graph state for interrupt()/resume
LEARNING_DIR = BASE_DIR / "learning"
EVALUATION_DIR = BASE_DIR / "evaluation"
OUTPUTS_DIR = BASE_DIR / "outputs"             # generated documents / run artifacts

# -----------------------------------------------------------------------------
# Test / cost mode (Instructions Part 1: "Wiring it as one flag")
#   dev  -> every agent on Groq Llama (graph/behaviour testing, cheap)
#   eval -> Document + Critic on Gemini Flash (output-quality testing only)
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


# -----------------------------------------------------------------------------
# Frontend access control (scripts/frontend_api.py -> backend/)
# -----------------------------------------------------------------------------
# Bootstrap admin credential. Empty means no one can administer the bridge: no
# access request can ever be approved, so no user token can ever be issued.
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
# Pipeline runs granted per issued user token. Admin is never decremented.
DEFAULT_RUN_ALLOWANCE = int(os.getenv("DEFAULT_RUN_ALLOWANCE", "2"))

# Canonical model identifiers (provider-agnostic names).
GROQ_LLAMA = "llama-3.3-70b-versatile"
GEMINI_FLASH = "gemini-2.5-flash"
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Single-flag provider override (same one-flag pattern as USE_FAKE_LLM / TEST_MODE):
#   USE_OPENAI=1 -> route EVERY agent to OpenAI (OPENAI_MODEL), ignoring the
#   Groq/Gemini per-mode assignment below. USE_FAKE_LLM still wins over this
#   (offline structure testing stays free). Lets the whole system run on just an
#   OpenAI key when Groq/Gemini aren't set up.
USE_OPENAI = os.getenv("USE_OPENAI", "0").strip().lower() in {"1", "true", "yes", "on"}

# Per-agent model assignment. Document + Critic read the flag; everything else
# is pinned to Groq regardless of mode (Build.md + Instructions Part 1).
MODEL_CONFIG: dict[str, str] = {
    "supervisor":  GROQ_LLAMA,
    "jd_analysis": GROQ_LLAMA,
    "profile":     GROQ_LLAMA,
    "profile_enrich": GROQ_LLAMA,  # polishes raw gap-interview answers into KB text
    "matching":    GROQ_LLAMA,
    "document":    GROQ_LLAMA if DEV_MODE else GEMINI_FLASH,
    "critic":      GROQ_LLAMA if DEV_MODE else GEMINI_FLASH,
    "verifier":    GROQ_LLAMA,
    "evaluation":  GROQ_LLAMA,
    # Scratch/experiment agents (scripts/custom_retriever_test.py) — not part of
    # the 7-agent pipeline, no LangGraph node, no state graph.
    "query_refine": GROQ_LLAMA,
    "rerank_critic": GROQ_LLAMA,
    # Sandbox company-ranking agents (scripts/agentic_rank_test.py) — a mini
    # supervisor→refine→critic loop over the CV-vs-companies ranking.
    "rank_refiner": GROQ_LLAMA,
    "rank_verifier": GROQ_LLAMA,
}

# OpenAI override: repoint every agent at the single OpenAI model in one place.
if USE_OPENAI:
    MODEL_CONFIG = {agent: OPENAI_MODEL for agent in MODEL_CONFIG}

# -----------------------------------------------------------------------------
# Provider routing + LiteLLM fallback chains (Instructions Part 3)
#   Groq lane:   Groq -> Cerebras -> OpenRouter :free  (same model family)
#   Gemini lane: Gemini -> OpenRouter Gemini :free -> Groq 70B
# Values are LiteLLM model strings, usable directly with litellm.completion(...).
# -----------------------------------------------------------------------------
GROQ_LANE = [
    f"groq/{GROQ_LLAMA}",
    "cerebras/llama-3.3-70b",
    "openrouter/meta-llama/llama-3.3-70b-instruct:free",
]
GEMINI_LANE = [
    f"gemini/{GEMINI_FLASH}",
    "openrouter/google/gemini-2.0-flash-exp:free",
    f"groq/{GROQ_LLAMA}",  # quality degrades here, but the run completes
]
OPENAI_LANE = [
    f"openai/{OPENAI_MODEL}",
    f"groq/{GROQ_LLAMA}",  # last-resort degrade so a run still completes
]

# Map a canonical model name -> its full fallback chain (primary is element 0).
FALLBACK_CHAINS: dict[str, list[str]] = {
    GROQ_LLAMA: GROQ_LANE,
    GEMINI_FLASH: GEMINI_LANE,
    OPENAI_MODEL: OPENAI_LANE,
}

# Exponential-backoff-with-jitter settings applied on 429 before fallback fires
# (Instructions Part 3, item 17).
RETRY = {
    "max_retries": 4,
    "base_delay_seconds": 1.0,
    "max_delay_seconds": 30.0,
    "jitter": True,
}


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
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
LANGFUSE_ENABLED = bool(LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY)

# -----------------------------------------------------------------------------
# Durable checkpointer (Postgres — survives a paused human gate across restarts)
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
    required = ["GROQ_API_KEY"]  # the Groq lane backs every agent
    if not DEV_MODE:
        required.append("GOOGLE_API_KEY")  # eval mode pushes Document/Critic to Gemini
    return required


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

    provider = "OpenAI (USE_OPENAI)" if USE_OPENAI else ("fake/offline" if USE_FAKE_LLM else "Groq/Gemini")
    lines = [
        f"TEST_MODE          : {TEST_MODE} (DEV_MODE={DEV_MODE})",
        f"Active provider    : {provider}",
        "Model assignment   :",
        *[f"    {a:<12}-> {m}" for a, m in MODEL_CONFIG.items()],
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
