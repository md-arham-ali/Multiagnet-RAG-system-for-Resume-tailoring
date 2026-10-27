"""
What happens once the graph has finished: read gate 4's outcome, save the
approved CV, write the review into the learning store. Called after the run
ends by both drivers (backend/runs/worker.py and scripts/run_gated_graph.py),
so the rule lives in one place.

  - approved = the LATEST gate-4 answer is "approve" or "edit". A "reject" only
    reaches the end of a run at the revision cap (decide() stops honouring it),
    and that draft is not saved: the human said no to it.
  - learning: every gate-4 answer goes to knowledge_base/learning/document/
    feedback.jsonl, and a human edit becomes line-level corrections in
    corrections.json. Live runs only: an offline run's draft is fixture text, and
    the store is what future prompts will be built from.
  - Exemplars are NOT written: what is worth keeping is the Evaluation team's call
    (EvalRecord.exemplar_worthy), not something an approval implies.
"""

from __future__ import annotations

import difflib
import re

import config
from state.state import Document, GateFeedback, Requirements
from utils.export import export_document

FINAL_GATE = "gate4_document"   # same name as utils/human_gate.FINAL_GATE
LEARNING_AGENT = "document"      # knowledge_base/learning/document/
MAX_CORRECTIONS = 40             # a full rewrite is one opinion, not 40 lessons
_BULLET = re.compile(r"^\s*(?:[-*•]|#{1,6})\s+")


def _as(model, value):
    """Checkpointed values usually come back as models; accept a dict as well."""
    if value is None or isinstance(value, model):
        return value
    return model.model_validate(value)


def final_answers(values: dict) -> list[GateFeedback]:
    """Every gate-4 answer of the run, oldest first (one per review round)."""
    entries = [_as(GateFeedback, fb) for fb in values.get("gate_feedback") or []]
    return [fb for fb in entries if fb.gate == FINAL_GATE]


def review_outcome(values: dict) -> dict | None:
    """The final review's verdict, or None when gate 4 never answered."""
    answers = final_answers(values)
    if not answers:
        return None
    latest = answers[-1]
    edited = bool((latest.edited_payload or {}).get("draft"))
    return {
        "decision": latest.decision,
        "approved": latest.decision in ("approve", "edit"),
        "edited": edited,
        "revision": latest.revision,
        "rounds": len(answers),
    }


def line_corrections(draft: str, edited: str) -> list[tuple[str, str]]:
    """(before, after) pairs for the lines the human changed.

    Same-size replaced blocks pair line by line; anything else (lines added,
    removed, or a block rewritten into a different number of lines) becomes one
    pair, with "" on the empty side. Markdown markers are stripped, so a record
    reads like the bullets already in the store.
    """
    def clean(lines):
        return [_BULLET.sub("", l).strip() for l in lines]

    a, b = draft.splitlines(), edited.splitlines()
    pairs: list[tuple[str, str]] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        old, new = clean(a[i1:i2]), clean(b[j1:j2])
        if tag == "replace" and len(old) == len(new):
            pairs += [(o, n) for o, n in zip(old, new) if o != n]
        else:
            pairs.append(("\n".join(l for l in old if l), "\n".join(l for l in new if l)))
    return [(o, n) for o, n in pairs if o or n][:MAX_CORRECTIONS]


def record_learning(values: dict, *, run_id: str) -> dict:
    """Write gate 4's answers into the learning store. Returns what was written."""
    from learning.store import append_feedback, save_correction

    reqs = _as(Requirements, values.get("requirements"))
    role = reqs.role_title if reqs else None
    feedback_rows = corrections = 0
    for fb in final_answers(values):
        payload = fb.edited_payload or {}
        append_feedback(LEARNING_AGENT, {
            "run_id": run_id, "gate": fb.gate, "revision": fb.revision,
            "decision": fb.decision, "feedback": fb.feedback or "",
            "edited": bool(payload.get("draft")), "role": role,
        })
        feedback_rows += 1
        if payload.get("draft") and payload.get("content"):
            reason = fb.feedback or "edited by the candidate at the final review"
            for before, after in line_corrections(payload["draft"], payload["content"]):
                save_correction(LEARNING_AGENT, before, after, reason, extra={
                    "run_id": run_id, "gate": fb.gate, "revision": fb.revision, "role": role,
                })
                corrections += 1
    return {"feedback_rows": feedback_rows, "corrections": corrections}


def close_run(values: dict, *, owner: str, run_id: str, live: bool) -> dict:
    """Gate 4's outcome -> export + learning record. Returns a JSON-safe summary:

        {"review": {...} | None,
         "export": {"md": "<owner>/<file>.md", "txt": ...} | None,   # relative to OUTPUTS_DIR
         "learning": {"feedback_rows": n, "corrections": n} | "skipped: ..."}
    """
    review = review_outcome(values)
    summary = {"review": review, "export": None, "learning": None}
    if review is None:
        summary["learning"] = "skipped: the final review never answered"
        return summary

    document = _as(Document, values.get("document"))
    if review["approved"] and document is not None:
        reqs = _as(Requirements, values.get("requirements"))
        paths = export_document(document, owner=owner, run_id=run_id,
                                role_title=reqs.role_title if reqs else None)
        summary["export"] = {k: p.relative_to(config.OUTPUTS_DIR).as_posix() for k, p in paths.items()}

    summary["learning"] = (record_learning(values, run_id=run_id) if live
                           else "skipped: offline run (fixture text must not enter the learning store)")
    return summary
