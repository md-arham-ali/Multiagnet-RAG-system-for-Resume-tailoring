#!/usr/bin/env python3
"""
Drives the graph end to end. Invokes, and each time it comes back paused at a
gate, prompts here and resumes with Command(resume=...).

input() lives in the driver, not the gate node. That is what lets the node unwind
so the process can exit while you think. Every pause is checkpointed, so --resume
works from a brand new process.

Usage:
    USE_FAKE_LLM=1 TRACE=0 python scripts/run_graph.py      # offline, no API keys
    python scripts/run_graph.py                             # live providers
    python scripts/run_graph.py --thread my-run             # name the run
    python scripts/run_graph.py --thread my-run --resume    # continue a paused run
    python scripts/run_graph.py --auto-approve              # approve every gate
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph.types import Command

from agents.supervisor import build_graph
from state.state import GraphState
from utils.checkpointer import make_checkpointer

# SAMPLE_JD = "We need a JAVA data engineer with strong OOps experience."
SAMPLE_JD = " WE need a python data engineer with must have strong MLops experience"

VALID_DECISIONS = ("approve", "edit", "reject")


def _line(label: str, value: object) -> None:
    """One summary line, long values truncated."""
    text = "—" if value is None else str(value)
    if len(text) > 100:
        text = text[:100] + "…"
    print(f"  {label:<16}: {text}")


def ask_gate(payload: dict, auto_approve: bool = False) -> dict:
    """
    One gate decision from the terminal.

    The returned dict goes back as Command(resume=...), so its keys have to match
    what human_gate() unpacks: decision / feedback / edited_payload.
    """
    gate = payload.get("gate", "?")
    if auto_approve:
        print(f"\n[gate: {gate}] auto-approved")
        return {"decision": "approve"}

    print(f"\n{'=' * 60}")
    print(f"HUMAN GATE: {gate}   (reviewing '{payload.get('field')}')")
    print(f"{'=' * 60}")
    print(json.dumps(payload.get("value"), indent=2, default=str)[:2000])

    decision = input(f"\nDecision {VALID_DECISIONS}: ").strip().lower()
    while decision not in VALID_DECISIONS:
        print(f"Invalid. Choose one of {VALID_DECISIONS}.")
        decision = input(f"Decision {VALID_DECISIONS}: ").strip().lower()

    answer: dict = {"decision": decision}
    if (feedback := input("Feedback (optional): ").strip()):
        answer["feedback"] = feedback
    if decision == "edit" and (note := input("What should change? ").strip()):
        answer["edited_payload"] = {"note": note}
    return answer


def run(thread_id: str, resume: bool, auto_approve: bool) -> dict:
    """Invoke, answer gates until the run finishes."""
    app = build_graph(checkpointer=make_checkpointer())
    cfg = {"configurable": {"thread_id": thread_id}}

    # Fresh run starts from state, a resumed one picks up the checkpoint and must
    # NOT pass state again or it overwrites what was saved.
    if resume and app.get_state(cfg).created_at is None:
        # No checkpoint -> invoke(None) dies deep inside Pregel with
        # "EmptyInputError: Received no input for __start__". Catch it here where
        # we still know which run was asked for and can name the real threads.
        known = sorted(c.config["configurable"]["thread_id"] for c in app.checkpointer.list(None))
        raise SystemExit(
            f"No checkpointed run named {thread_id!r} — nothing to resume.\n"
            f"  Start it with:  --thread {thread_id}   (drop --resume)\n"
            f"  Known threads:  {', '.join(dict.fromkeys(known)) or '(none yet)'}"
        )

    payload = None if resume else GraphState(run_id=thread_id, job_description=SAMPLE_JD)
    result = app.invoke(payload, config=cfg)

    while interrupts := result.get("__interrupt__"):
        answer = ask_gate(interrupts[0].value, auto_approve=auto_approve)
        result = app.invoke(Command(resume=answer), config=cfg)

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--thread", default=None, help="run id (default: random)")
    parser.add_argument("--resume", action="store_true", help="continue a paused run")
    parser.add_argument("--auto-approve", action="store_true", help="approve every gate")
    args = parser.parse_args()

    thread_id = args.thread or f"run-{uuid.uuid4().hex[:8]}"
    if args.resume and not args.thread:
        parser.error("--resume needs --thread <id> (which run to continue)")

    print(f"thread_id: {thread_id}   (resume later with --thread {thread_id} --resume)")
    result = run(thread_id, resume=args.resume, auto_approve=args.auto_approve)

    print("\n=== Graph run complete ===")
    print("final stage:", result.get("stage"))

    # 1. jd_analysis
    reqs = result.get("requirements")
    print("\n[jd_analysis] requirements")
    if reqs:
        _line("role_title", reqs.role_title)
        for r in reqs.requirements:
            _line(r.kind, r.text)

    # 2. profile
    evidence = result.get("evidence") or []
    print(f"\n[profile] evidence ({len(evidence)} block(s))")
    for block in evidence:
        _line(block.source_id, block.content)

    # 3. matching
    fit = result.get("fit_report")
    print("\n[matching] fit_report")
    if fit:
        _line("overall_fit", fit.overall_fit)
        _line("must_have_cov", fit.must_have_coverage)

    # 4. document
    doc = result.get("document")
    print("\n[document] draft")
    if doc:
        _line("kind", doc.kind)
        _line("content", doc.content)

    # 5. critic
    crit = result.get("critique")
    print("\n[critic] critique")
    if crit:
        _line("verdict", crit.verdict)

    # 6. verifier
    vr = result.get("verifier_report")
    print("\n[verifier] report")
    if vr:
        _line("status", vr.status)

    # 7. evaluation
    ev = result.get("eval_record")
    print("\n[evaluation] record")
    if ev:
        _line("ats_score", ev.ats_score)

    # 8. gates - the audit trail the append reducer built up
    gates = result.get("gate_feedback") or []
    print(f"\n[gates] {len(gates)} decision(s)")
    for fb in gates:
        _line(fb.gate, f"{fb.decision}" + (f" — {fb.feedback}" if fb.feedback else ""))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
