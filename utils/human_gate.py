"""
Reusable human gate (Instructions.md #26-28).

ONE node for all four gates. gate_name says which field to surface. Shows the
work, saves a snapshot, then interrupt() pauses the graph until someone answers.

No input() here on purpose - it lives in the driver. That is what lets this node
unwind so the process can exit while a human takes their time.
"""

from __future__ import annotations

from pydantic import BaseModel

from state.state import (
    GraphState, GateFeedback, Verdict, VerifyStatus, ClaimLabel,
)
from state.state_utils import log_state_snapshot
from utils.trace import log
from langgraph.types import interrupt

# gate -> the state field it surfaces
GATE_FIELDS: dict[str, str] = {
    "gate1_requirements": "requirements",   # after JD Analysis
    "gate2_evidence": "evidence",           # after Profile (also profile gaps)
    "gate3_fit": "fit_report",              # after Matching
    "gate4_document": "document",           # final verified draft
}


def _size(value) -> str:
    """How much there is to review, without any of it: "3 items", "1,840 chars"."""
    if value is None:
        return "empty"
    if isinstance(value, (list, tuple, dict, set)):
        return f"{len(value)} item{'' if len(value) == 1 else 's'}"
    if isinstance(value, BaseModel):
        text = getattr(value, "content", None)
        if isinstance(text, str):
            return f"{len(text):,} chars"
        return type(value).__name__
    if isinstance(value, str):
        return f"{len(value):,} chars"
    return type(value).__name__


def surface(state: GraphState, gate_name: str) -> object:
    """Return the field this gate is about; announce it WITHOUT printing it.

    The value is in the interrupt() payload, and each driver prints it for the human
    at the terminal. This function's print also reaches the API server's stdout, where
    at gate 4 the field IS the CV - design.md: CV text never goes into logs. The worker
    scrubs the separate cv_link artifact, not this (bugs_audit_fixed.md #74 item 3).
    """
    field = GATE_FIELDS.get(gate_name)
    if field is None:
        raise KeyError(f"Unknown gate '{gate_name}'. Known: {sorted(GATE_FIELDS)}")
    value = getattr(state, field, None)
    print(f"\n===== HUMAN GATE: {gate_name} =====")
    print(f"Review field '{field}' ({_size(value)}) - see the gate payload for the content.")
    return value


FINAL_GATE = "gate4_document"


def _jsonable(value):
    """Models / lists -> JSON-safe, so the interrupt() payload can always be sent."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def final_changes(state: GraphState) -> list[dict]:
    """Gate 4's diff: every CV line the Document changed, before -> after, with its reason.

    Rebuilt from the pristine cv_tree plus document_patches, the same way Document
    built the draft. Read-only, so it is safe before interrupt() (the node replays
    on resume). The diff is a convenience: if it cannot be built, the gate still opens.
    """
    patches = state.document_patches
    if state.cv_tree is None or patches is None or not patches.edits:
        return []
    from utils.cv_handling.cv_edit import apply_edits, changed_lines, index_nodes

    try:
        new_tree = apply_edits(state.cv_tree, patches.edits)
    except Exception as exc:
        print(f"(gate 4: could not rebuild the diff: {type(exc).__name__}: {exc})")
        return []
    nodes = index_nodes(state.cv_tree)
    edit_of = {e.target_id: e for e in patches.edits}

    def where(node_id: str) -> str:
        # "Projects › <entry>" for a bullet under an entry, "Skills" for a loose item
        path, node = [], nodes.get(node_id)
        while node is not None and node.depth > 1:
            node = nodes.get(node.parent_id)
            if node is not None and node.depth >= 1:
                path.append(node.title or node.text)
        return " › ".join(reversed([p for p in path if p]))

    changes = []
    for change in changed_lines(state.cv_tree, new_tree):
        edit = edit_of.get(change.node_id)
        changes.append({
            "node_id": change.node_id,
            "where": where(change.node_id),
            "before": change.before,
            "after": change.after,
            "reason": edit.reason if edit else None,
            "evidence_ids": list(edit.evidence_ids) if edit else [],
        })
    return changes


def standing_verdict(state: GraphState) -> dict:
    """What the Critic and the Verifier still say about the draft gate 4 shows.

    At the revision cap decide() stops honouring a REVISE and moves the run on,
    the same way it stops honouring a reject. That is deliberate: the loop has to
    end. But gate 4 then showed the draft with no sign of the verdict still
    standing against it, so the one review that ships the CV was the least
    informed in the run (bugs_audit_fixed.md #60 item 2).

    Only a verdict still AGAINST the draft is carried. A pass is the normal case
    and would be noise - and noise in a form is how a real warning gets skipped.
    The key is always present so the form can read it without asking which gate
    it is, the same reason gap_questions is.
    """
    standing: dict = {}

    critique = state.critique
    if critique is not None and critique.verdict == Verdict.REVISE:
        # Items, not just the verdict: "the Critic still asks for X" is the only
        # form of this a reviewer can act on. _sift already dropped off-rubric
        # findings, so every item here is about a dimension someone asked for.
        standing["critique"] = {
            "verdict": critique.verdict.value,
            "items": [
                {
                    "rubric_item": item.rubric_item,
                    "severity": item.severity,
                    "location": item.location,
                    "instruction": item.instruction,
                }
                for item in critique.items
            ],
        }

    report = state.verifier_report
    if report is not None and report.status == VerifyStatus.FAIL:
        # Supported claims are why it passed the ones it passed - they are not
        # what still stands against the draft, so they are left out.
        standing["verifier_report"] = {
            "status": report.status.value,
            "claims": [
                {
                    "claim": c.claim,
                    "label": c.label.value,
                    "evidence_id": c.evidence_id,
                }
                for c in report.claims
                if c.label != ClaimLabel.SUPPORTED
            ],
            "do_not_claim_hits": [
                {"text": h.text, "matched_entry": h.matched_entry}
                for h in report.do_not_claim_hits
            ],
        }

    return standing


# gate -> extra state the review form needs, sent next to the reviewed field.
GATE_EXTRAS = {
    "gate2_evidence": lambda s: {"gap_questions": _jsonable(s.gap_questions)},
    FINAL_GATE: lambda s: {
        "changes": final_changes(s),
        "standing_verdict": standing_verdict(s),
    },
}


def _final_edit(state: GraphState, edited_payload: dict | None):
    """Gate 4 "edit": the candidate's own text becomes the final document.

    Returns (new Document or None, payload to record). The payload keeps the draft
    the human saw next to what they wrote, so the learning step can turn the
    difference into corrections. No usable text (missing, blank, unchanged, or a
    CLI note) means no write-back: the draft stands, and the note is still recorded.
    """
    content = (edited_payload or {}).get("content")
    draft = state.document
    if draft is None or not isinstance(content, str) or not content.strip():
        return None, edited_payload
    content = content.strip() + "\n"
    if content == draft.content:
        return None, edited_payload
    recorded = {**edited_payload, "content": content, "draft": draft.content}
    return draft.model_copy(update={"content": content}), recorded


# The only answers a gate accepts. Also hardcoded in the drivers' own input()
# loops (scripts/run_graph.py, run_gated_graph.py) and as a Literal in
# backend/routes/runs.py - worth collapsing onto one import later.
VALID_DECISIONS = frozenset({"approve", "edit", "reject"})

GAP_GATE = "gate2_evidence"


def _key(text: str) -> str:
    """Normalise a requirement so an answer's key matches the question we asked.

    Same rule as agents/matching.py::_key and agents/profile.py::_key.
    """
    return " ".join((text or "").split()).lower()


def _unreadable(gate_name: str, answer) -> str | None:
    """Why this answer cannot be used, or None if it can (bugs_audit_fixed.md #74 item 4).

    Checked BEFORE anything is read out of the answer, and reported back through
    the gate's re-ask loop rather than raised. A raise here is what #82 was: the
    runner commits the resume write on the error path, so the thread wedges. It
    is also not only `decision` that can wedge it - an `edited_payload` that is
    not a dict reaches `_final_edit` as an AttributeError at gate 4, and reaches
    `GateFeedback` as a ValidationError at gates 1-3, both from inside the node,
    both after the answer has been consumed.

    The backend's `GateAnswer` already types all three, so no UI answer can fail
    here. The CLI drivers build the dict by hand, and a resumed node has no
    terminal to re-prompt from - which is exactly why the message has to name
    what was wrong rather than surface a bare KeyError or AttributeError.
    """
    if not isinstance(answer, dict):
        return (f"Gate '{gate_name}' needs a dict answer with a 'decision' key; "
                f"got {type(answer).__name__}.")

    decision = answer.get("decision")
    if decision not in VALID_DECISIONS:
        if "decision" not in answer:
            return (f"Gate '{gate_name}' got an answer with no 'decision' key "
                    f"(keys: {sorted(answer)}); expected one of {sorted(VALID_DECISIONS)}.")
        return (f"Gate '{gate_name}' got invalid decision {decision!r}; "
                f"expected one of {sorted(VALID_DECISIONS)}.")

    edited = answer.get("edited_payload")
    if edited is not None and not isinstance(edited, dict):
        return (f"Gate '{gate_name}' got an 'edited_payload' of type "
                f"{type(edited).__name__}; expected a dict "
                f"(gate 4 reads its 'content' key).")

    gaps = answer.get("gap_answers")
    if gaps is not None and not isinstance(gaps, dict):
        return (f"Gate '{gate_name}' got 'gap_answers' of type "
                f"{type(gaps).__name__}; expected a dict of requirement -> answer.")
    if isinstance(gaps, dict):
        bad = sorted(k for k, v in gaps.items() if not isinstance(k, str) or not isinstance(v, str))
        if bad:
            return (f"Gate '{gate_name}' got gap_answers entries that are not "
                    f"text: {bad}. Every key and value must be a string.")
    return None


def _scoped_gap_answers(state: GraphState, gate_name: str, gaps: dict) -> dict:
    """Only answers to questions THIS gate actually asked (bugs_audit_fixed.md #74 item 5).

    `backend/routes/runs.py` refuses gap_answers outside gate 2 and refuses keys
    nobody was asked about (422). `human_gate` did neither, and the CLI drivers
    go straight to it - so an answer for a requirement never raised reached
    `state.gap_answers`, then `enrich()`, which polishes it, writes it to
    `knowledge_base/profile/manual_entries.json` and embeds it. Every later run
    then retrieves it as real profile evidence. That is #14's lesson one layer
    earlier: the gate, not the agent, is where unasked content gets in.

    Dropped, not refused. The decision is valid and the review is done; re-asking
    (the #82 loop) would punish a reviewer who answered correctly, and raising
    wedges the thread. Each dropped key is logged by name, so a real answer lost
    to a key mismatch is recoverable from the trace.

    A kept key is rewritten to the requirement text we asked under. `enrich()`
    looks its question up with `q.requirement == requirement`, an exact match, so
    an answer that round-tripped through a form with different spacing would
    otherwise be polished with "No question found" as its question.
    """
    if not gaps:
        return {}
    if gate_name != GAP_GATE:
        log(f"human_gate: {len(gaps)} gap answer(s) sent at '{gate_name}', not the gap "
            f"gate ('{GAP_GATE}'); dropped: {sorted(gaps)}")
        return {}

    asked = {_key(q.requirement): q.requirement for q in state.gap_questions}
    kept, dropped = {}, []
    for requirement, answer_text in gaps.items():
        canonical = asked.get(_key(requirement))
        if canonical is None:
            dropped.append(requirement)
            continue
        kept[canonical] = answer_text
    if dropped:
        log(f"human_gate: {len(dropped)} gap answer(s) for question(s) never asked; "
            f"dropped: {sorted(dropped)}")
    return kept


def human_gate(state: GraphState, gate_name: str) -> dict:
    """Surface the field, pause on interrupt(), turn the answer into GateFeedback."""
    value = surface(state, gate_name)
    snapshot_path = log_state_snapshot(state, label=gate_name)
    print(f"(state snapshot saved -> {snapshot_path})")

    extras = GATE_EXTRAS.get(gate_name, lambda s: {})(state)
    payload = {
        "gate": gate_name,
        "field": GATE_FIELDS[gate_name],
        "value": _jsonable(value),
        "gap_questions": [],   # always present: drivers read it without checking the gate
        # Which round this is, and how many the run allows. decide() stops
        # honouring a reject once revision_count hits the cap, so a reviewer has
        # to be able to see that coming (bugs_audit_fixed.md #78 item 2).
        "revision": state.revision_count,
        "max_revisions": state.max_revisions,
        **extras,
    }

    # Re-ask rather than raise (#82). Raising does NOT undo the bad resume: the
    # runner commits this task's RESUME write on the error path too
    # (langgraph/pregel/_runner.py), and interrupt() hands that stored value back
    # on every later resume - resume[idx] is returned before any new value is
    # considered (langgraph/types.py) - so one typo wedges the thread for good.
    # Each interrupt() call in a node run takes its OWN resume slot, so asking
    # again consumes the NEXT answer instead of replaying the bad one.
    error = None
    while True:
        answer = interrupt(payload if error is None else {**payload, "error": error})
        error = _unreadable(gate_name, answer)
        if error is None:
            break
        print(f"({error} Re-opening the gate.)")

    decision = answer["decision"]
    feedback_text = answer.get("feedback")
    edited_payload = answer.get("edited_payload")
    gap_answers = _scoped_gap_answers(state, gate_name, answer.get("gap_answers") or {})

    edited_document = None
    if gate_name == FINAL_GATE and decision == "edit":
        edited_document, edited_payload = _final_edit(state, edited_payload)

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

    # Gates 1-3: an "edit" is recorded but never written back onto the artifact
    # (payload is a dict, the field a typed model; that mapping is still open).
    # Gate 4 writes back: Document.content is plain text, so the human's edit
    # maps onto it directly. decide() treats "edit" like approve, so the edited
    # CV goes straight on to evaluation and is what the run delivers.
    result = {"gate_feedback": [feedback]}
    if gap_answers:
        result["gap_answers"] = gap_answers
    if edited_document is not None:
        result["document"] = edited_document
    return result
   
