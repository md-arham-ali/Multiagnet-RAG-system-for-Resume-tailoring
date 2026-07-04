"""
State helpers + audit-trail snapshot logger (Instructions.md #18).

- update_state / get_field : thin, safe conveniences over the typed GraphState.
- log_state_snapshot       : dumps the FULL state to logs/<run_id>/<...>.json at
                             each human gate. This file trail is your audit log.

These are pure plumbing — no agent logic lives here.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config
from state.state import GraphState


def update_state(state: GraphState, **changes: Any) -> GraphState:
    """Return a NEW state with `changes` applied and re-validated.

    LangGraph itself merges the dict a node returns; this helper is for when you
    want an updated GraphState object outside the graph (tests, gates, scripts).
    """
    return state.model_copy(update=changes)


def get_field(state: GraphState, name: str, default: Any = None) -> Any:
    """Read a state field by name, returning `default` if missing or None."""
    return getattr(state, name, default) if getattr(state, name, None) is not None else default


def log_state_snapshot(
    state: GraphState, label: str, logs_dir: Path | None = None
) -> Path:
    """Write the full state to logs/<run_id>/<timestamp>_<label>.json.

    Returns the path written. Called at every human gate so each pause leaves an
    inspectable record of exactly what the state held.
    """
    run_id = state.run_id or "no_run_id"
    out_dir = (logs_dir or (config.BASE_DIR / "logs")) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"{stamp}_{label}.json"

    # mode="python" keeps nested Pydantic models; default=str catches anything
    # not natively JSON-serializable (e.g. LangChain message objects).
    data = state.model_dump(mode="python")
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return path
