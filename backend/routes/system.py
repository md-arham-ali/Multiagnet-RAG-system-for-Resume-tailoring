"""Liveness + a secret-free config view."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

import config
from backend.deps import Identity

router = APIRouter()

# When THIS process started. A server that predates the code on disk is the one a smoke run
# must not grade (bug #85 item 4): compare this with the newest source file's mtime. A start
# time and not a git hash, so an open route says nothing about the repo.
_STARTED = datetime.now(timezone.utc).isoformat(timespec="seconds")


@router.get("/health")
def health():
    """The ONE unauthenticated route — the sidebar polls it every 15s to show
    'backend connected', which has to work before anyone has a token."""
    return {"ok": True, "test_mode": config.TEST_MODE, "offline_default": True, "started": _STARTED}


@router.get("/config")
def config_view(identity: Identity):
    """Behind auth: it exposes which provider keys are present."""
    return {
        "test_mode": config.TEST_MODE,
        "models": config.MODEL_CONFIG,
        # Every provider MODEL_CONFIG / FALLBACK_CHAINS can route to, so the
        # Settings screen doesn't show cerebras/openrouter agents as unbacked.
        "keys_present": {
            "groq": bool(config.GROQ_API_KEY),
            "google": bool(config.GOOGLE_API_KEY),
            "cerebras": bool(config.CEREBRAS_API_KEY),
            "openrouter": bool(config.OPENROUTER_API_KEY),
            "openai": bool(config.OPENAI_API_KEY),
        },
    }
