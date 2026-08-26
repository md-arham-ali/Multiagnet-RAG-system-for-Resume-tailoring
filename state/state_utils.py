"""
State helpers + the snapshot logger (Instructions.md #18).

update_state / get_field are conveniences. log_state_snapshot dumps the FULL
state to logs/<run_id>/ at every gate - that file trail is the audit log.
Pure plumbing, no agent logic here.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config
from state.state import GraphState


def update_state(state: GraphState, **changes: Any) -> GraphState:
    """A NEW state with `changes` applied and re-validated.

    LangGraph merges the dict a node returns on its own. This is for when you
    want an updated GraphState outside the graph: tests, gates, scripts.
    """
    return state.model_copy(update=changes)


def get_field(state: GraphState, name: str, default: Any = None) -> Any:
    """Read a field by name. `default` if missing or None."""
    return getattr(state, name, default) if getattr(state, name, None) is not None else default


def log_state_snapshot(
    state: GraphState, label: str, logs_dir: Path | None = None
) -> Path:
    """Full state -> logs/<run_id>/<timestamp>_<label>.json, returns the path.

    Called at every gate so each pause leaves a record of what state held.
    """
    run_id = state.run_id or "no_run_id"
    out_dir = (logs_dir or (config.BASE_DIR / "logs")) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"{stamp}_{label}.json"

    # mode="python" keeps nested models, default=str catches whatever isn't
    # JSON-serializable (langchain message objects, mostly).
    data = state.model_dump(mode="python")
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return path
