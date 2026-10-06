"""
Reusable human gate (Instructions.md #26-28).

ONE node for all four gates. gate_name says which field to surface. Shows the
work, saves a snapshot, then interrupt() pauses the graph until someone answers.

No input() here on purpose - it lives in the driver. That is what lets this node
unwind so the process can exit while a human takes their time.
"""

from __future__ import annotations

from pydantic import BaseModel

from state.state import GraphState, GateFeedback
from state.state_utils import log_state_snapshot
from langgraph.types import interrupt

# gate -> the state field it surfaces
GATE_FIELDS: dict[str, str] = {
    "gate1_requirements": "requirements",   # after JD Analysis
    "gate2_evidence": "evidence",           # after Profile (also profile gaps)
    "gate3_fit": "fit_report",              # after Matching
    "gate4_document": "document",           # final verified draft
}


def surface(state: GraphState, gate_name: str) -> object:
    """Print + return the field this gate is about."""
    field = GATE_FIELDS.get(gate_name)
    if field is None:
        raise KeyError(f"Unknown gate '{gate_name}'. Known: {sorted(GATE_FIELDS)}")
    value = getattr(state, field, None)
    print(f"\n===== HUMAN GATE: {gate_name} =====")
    print(f"Review field '{field}':\n{value}\n")
    return value


def _jsonable(value):
    """Models / lists -> JSON-safe, so the interrupt() payload can always be sent."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def human_gate(state: GraphState, gate_name: str) -> dict:
    """Surface the field, pause on interrupt(), turn the answer into GateFeedback."""
    value = surface(state, gate_name)
    snapshot_path = log_state_snapshot(state, label=gate_name)
    print(f"(state snapshot saved -> {snapshot_path})")

    answer = interrupt({
        "gate": gate_name,
        "field": GATE_FIELDS[gate_name],
        "value": _jsonable(value),
        "gap_questions": _jsonable(state.gap_questions) if gate_name == "gate2_evidence" else [],
    })

    decision = answer["decision"]
    feedback_text = answer.get("feedback")
    edited_payload = answer.get("edited_payload")
    gap_answers = answer.get("gap_answers", {})

    valid_decisions = {"approve", "edit", "reject"}
    if decision not in valid_decisions:
        # Can't re-prompt here. A resumed node replays from a checkpoint with the
        # answer already in hand and no terminal attached, so validating is the
        # job of whoever sends Command(resume=...).
        raise ValueError(
            f"Gate '{gate_name}' resumed with invalid decision {decision!r}; "
            f"expected one of {sorted(valid_decisions)}."
        )

    feedback = GateFeedback(
        gate=gate_name,
        decision=decision,
        feedback=feedback_text or None,
        edited_payload=edited_payload,
        # Stamp the round this answer was given in. route() compares it against
        # the CURRENT revision_count, so a loop-back that produces a new draft
        # reopens the gate instead of inheriting the old approval.
        revision=state.revision_count,
    )

    # Open: an "edit" is recorded but never written back onto the artifact.
    # Payload is a dict, the field is a typed model, so that mapping needs a
    # design call. For now the edit only lands in the audit trail.
    result = {"gate_feedback": [feedback]}
    if gap_answers:
        result["gap_answers"] = gap_answers
    return result
   
