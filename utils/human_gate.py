"""
Reusable human gate (Instructions.md #26-28).

ONE node handles all four gates — it reads `gate_name` to know which state field
to surface. It (a) shows the relevant work to the user, (b) saves a state
snapshot (audit trail), and (c) collects structured feedback into the state.

In LangGraph this is paired with `interrupt()` so the graph pauses here and
resumes after the user responds. The surfacing + snapshot below is boilerplate;
collecting/applying the feedback is the block you write (it depends on your UI —
CLI prompt now, Streamlit form later).
"""

from __future__ import annotations

from state.state import GraphState, GateFeedback
from state.state_utils import log_state_snapshot

# Which state field each gate surfaces to the user (Instructions: 4 gates).
GATE_FIELDS: dict[str, str] = {
    "gate1_requirements": "requirements",   # after JD Analysis
    "gate2_evidence": "evidence",           # after Profile (also profile gaps)
    "gate3_fit": "fit_report",              # after Matching
    "gate4_document": "document",           # final verified draft
}


def surface(state: GraphState, gate_name: str) -> object:
    """Print/return the state field this gate is about (the thing to review)."""
    field = GATE_FIELDS.get(gate_name)
    if field is None:
        raise KeyError(f"Unknown gate '{gate_name}'. Known: {sorted(GATE_FIELDS)}")
    value = getattr(state, field, None)
    print(f"\n===== HUMAN GATE: {gate_name} =====")
    print(f"Review field '{field}':\n{value}\n")
    return value


def human_gate(state: GraphState, gate_name: str) -> dict:
    """Run one gate. Returns the dict update LangGraph merges into state."""
    surface(state, gate_name)
    snapshot_path = log_state_snapshot(state, label=gate_name)
    print(f"(state snapshot saved -> {snapshot_path})")

    # ▼▼▼ YOUR CODE — collect + apply structured feedback ▼▼▼
    # 1. Get the user's decision: approve / edit / reject (+ optional notes,
    #    edited_payload). For now read from input(); later from the UI / the
    #    value passed back into interrupt().
    # 2. Build a GateFeedback(gate=gate_name, decision=..., feedback=...,
    #    edited_payload=...).
    # 3. Return {"gate_feedback": [feedback]}  (the list reducer appends it),
    #    plus any edited field the user changed.
    raise NotImplementedError(
        "human_gate feedback collection is yours to implement (Instructions #26)."
    )
    # ▲▲▲ END YOUR CODE ▲▲▲
