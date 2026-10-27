"""
State helpers + the snapshot logger (Instructions.md #18).

update_state / get_field are conveniences. log_state_snapshot dumps the state to
logs/<run_id>/ at every gate - that file trail is the audit log. Every field is
there; the CV tree goes through scrub_cv_tree first (bug#72 item 4).
Pure plumbing, no agent logic here.
"""

from __future__ import annotations

import itertools
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config
from state.state import GraphState

# Tie-breaker for snapshots written inside the same microsecond. itertools.count
# is advanced under the GIL, so concurrent gates get distinct numbers without a lock.
_snapshot_seq = itertools.count()

# Everything a run id may NOT put in a folder name. A dot is allowed (ids may carry
# one) but "." and ".." are rejected whole, below.
_UNSAFE_IN_DIRNAME = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_dirname(run_id: str) -> str:
    """One path component, never a climb out of the logs folder (bug#72.3, bug#36).

    `logs_dir / run_id` joined whatever the id held, so a CLI `--thread ../../x`
    wrote outside `logs/`. Today's ids are generated hex, so this is hardening -
    but `GraphState.run_id` takes any string and the drivers take it from argv.

    Mapped, not refused: the pinned test asks for a path inside the logs folder,
    not an exception, and a snapshot is an audit record - losing one to a bad id
    is the wrong trade. The id itself is still in the file, under `run_id`.
    """
    name = _UNSAFE_IN_DIRNAME.sub("_", run_id)[:120]
    return "no_run_id" if name in ("", ".", "..") else name


def scrub_cv_tree(tree: dict) -> dict:
    """A dumped `cv_tree` with what the CV-privacy rule forbids removed.

    `frontend/design.md` "Privacy": the CV text never goes into SSE events, run
    logs or URLs. Out go the header section outright (name, email, phone -
    `SectionType` "header") and `raw_text` at every depth; the structure, the
    node ids and the repaired `text` stay, so the audit trail still reads.

    The canonical copy of the rule lives here because both writers need it and
    `state/` is the one package both can import: `backend/runs/worker.py` has
    scrubbed the `cv_link` artifact since 2026-10-09 and now delegates here,
    while the gate snapshot did not scrub at all (bug#72 item 4). One rule in
    two implementations is what let them drift in the first place.
    """
    def scrub(node: dict) -> dict:
        return {**node, "raw_text": "", "children": [scrub(c) for c in node.get("children", [])]}

    root = tree.get("root")
    if not root:
        return tree
    root = scrub(root)
    root["children"] = [c for c in root["children"] if c.get("section_type") != "header"]
    return {**tree, "root": root}


def update_state(state: GraphState, **changes: Any) -> GraphState:
    """A NEW state with `changes` applied and re-validated.

    LangGraph merges the dict a node returns on its own. This is for when you
    want an updated GraphState outside the graph: tests, gates, scripts.

    The graph's REDUCERS ARE NOT APPLIED here: every change overwrites its field.
    `gate_feedback=[fb]` replaces the audit trail rather than appending to it,
    and `evidence=[...]` replaces rather than merging. Pass the whole intended
    value, not the delta.

    model_validate, not model_copy(update=...): Pydantic never validates a copy's
    update dict, so `stage="profile"` used to store a bare str where every reader
    expects a Stage, and the copy was shallow — appending to the new state's
    `evidence` also appended to the old one's (bugs_audit_fixed.md #56).
    Re-validation builds fresh containers; nested models are reused as-is, which
    is safe because nothing in the pipeline mutates one in place.
    """
    return GraphState.model_validate({**dict(state), **changes})


def get_field(state: GraphState, name: str, default: Any = None) -> Any:
    """Read a field by name. `default` if missing or None."""
    return getattr(state, name, default) if getattr(state, name, None) is not None else default


def log_state_snapshot(
    state: GraphState, label: str, logs_dir: Path | None = None
) -> Path:
    """Full state -> logs/<run_id>/<timestamp>_<label>.json, returns the path.

    Called at every gate so each pause leaves a record of what state held.
    """
    base = logs_dir or (config.BASE_DIR / "logs")
    out_dir = base / _safe_dirname(state.run_id or "no_run_id")
    if not out_dir.resolve().is_relative_to(base.resolve()):
        # Unreachable after _safe_dirname; kept so a future change to it cannot
        # quietly reopen the hole.
        raise ValueError(f"snapshot folder {out_dir} is outside {base}")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Second-resolution names collided: a gate reopening inside the same second
    # (an offline reject -> redo -> same gate) overwrote the snapshot the reject
    # was made against, losing it from the audit trail (#56). Microseconds plus a
    # per-process counter — the counter covers two writes that a coarse clock
    # reports at the same microsecond, and both parts sort in write order, so the
    # directory still reads chronologically.
    now = datetime.now(timezone.utc)
    stamp = f"{now:%Y%m%dT%H%M%S}.{now.microsecond:06d}Z-{next(_snapshot_seq):04d}"
    path = out_dir / f"{stamp}_{label}.json"

    # mode="python" keeps nested models, default=str catches whatever isn't
    # JSON-serializable (langchain message objects, mostly).
    data = state.model_dump(mode="python")

    # bug#72 item 4. Every UI run with an uploaded CV left the candidate's name,
    # email, phone and the raw PDF text on disk once per gate, in a folder with
    # none of the CV store's ownership or deletion rules - while the same tree
    # was being scrubbed on its way to the run log. Same rule, both paths now.
    # Note what this does NOT do: `document.content` is the generated CV and
    # `line_links[].text` are its lines, and both stay, exactly as they do on the
    # wire. Making a snapshot CV-free is the other half of bug#72.4 and is the
    # owner's call - snapshots would have to become CV storage, owned and deleted
    # with the CV.
    if isinstance(data.get("cv_tree"), dict):
        data["cv_tree"] = scrub_cv_tree(data["cv_tree"])

    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return path
