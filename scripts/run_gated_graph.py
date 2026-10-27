#!/usr/bin/env python3
"""
Full graph with the 4 gates live. Pause -> print payload -> ask -> resume, until
END. Real SqliteSaver, so a Ctrl-C mid-gate is resumable with the SAME --thread.

Overlaps scripts/run_graph.py almost completely now (that one was rewritten as a
driver too). Worth folding these two into one.

Usage:
    USE_FAKE_LLM=1 python scripts/run_gated_graph.py                    # new run, random id
    USE_FAKE_LLM=1 python scripts/run_gated_graph.py --thread my-run-1  # name it, or resume it
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph.types import Command

import config
from agents.supervisor import build_graph
from state.state import GraphState
from utils.checkpointer import make_checkpointer
from utils.final_review import FINAL_GATE, close_run

SAMPLE_JD = "We need a Python data engineer with strong MLOps experience."
SAMPLE_CV = str(config.CV_DEFAULT_PATH)   # cv_link needs a CV on every run; same default as the backend


def _ask_decision(payload: dict) -> dict:
    """Print the payload, get one gate answer from the terminal."""
    print(f"\n===== GATE: {payload.get('gate')} (field: {payload.get('field')}) =====")
    print(payload.get("value"))
    final_gate = payload.get("gate") == FINAL_GATE
    if final_gate:
        changes = payload.get("changes") or []
        print(f"\n{len(changes)} line(s) changed from your CV:")
        for c in changes:
            print(f"  [{c['where'] or c['node_id']}]\n    - {c['before']}\n    + {c['after']}"
                  + (f"\n    why: {c['reason']}" if c.get("reason") else ""))

    valid = {"approve", "edit", "reject"}
    decision = input("\nDecision (approve/edit/reject): ").strip().lower()
    while decision not in valid:
        print("Invalid. Enter 'approve', 'edit', or 'reject'.")
        decision = input("Decision (approve/edit/reject): ").strip().lower()

    feedback = input("Feedback (optional): ").strip() or None

    edited_payload = None
    if decision == "edit" and final_gate:
        # Gate 4 writes the edit back as the final CV. A whole CV does not fit an
        # input() line, so it comes from a file: save the draft above, edit it, give the path.
        path = input("Path to your edited CV (.md; enter to keep the draft): ").strip()
        while path and not Path(path).expanduser().is_file():
            path = input("No such file. Path (enter to keep the draft): ").strip()
        if path:
            edited_payload = {"content": Path(path).expanduser().read_text(encoding="utf-8")}
    elif decision == "edit":
        note = input("What should change? (press enter to skip): ").strip()
        if note:
            edited_payload = {"note": note}

    answer = {"decision": decision, "feedback": feedback, "edited_payload": edited_payload}

    # Gate 2 carries the gap interview. human_gate() reads answer["gap_answers"],
    # keyed by requirement, which is what enrich() looks up. Without this the
    # dict stays empty and profile_enrich early-returns every run.
    if (gaps := payload.get("gap_questions")) and decision != "reject":
        gap_answers = {}
        print(f"\n{len(gaps)} gap question(s) — press enter to skip any.")
        for gap in gaps:
            reply = input(f"  [{gap['requirement']}] {gap['question']}\n  > ").strip()
            if reply:
                gap_answers[gap["requirement"]] = reply
        if gap_answers:
            answer["gap_answers"] = gap_answers
    return answer


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--thread", default=None,
        help="Resume an existing run by its thread_id instead of starting a new one.",
    )
    parser.add_argument("--jd", default=SAMPLE_JD, help="Job description text (new runs only).")
    args = parser.parse_args()

    checkpointer = make_checkpointer()
    graph = build_graph(checkpointer=checkpointer)

    thread_id = args.thread or f"run-{uuid.uuid4().hex[:8]}"
    cfg = {"configurable": {"thread_id": thread_id}, "recursion_limit": config.RECURSION_LIMIT}

    # Resume is decided by whether this thread HAS a checkpoint, not by whether
    # --thread was passed. Keying it on the flag made naming a FRESH run
    # impossible - the documented "--thread my-run-1" took the resume branch,
    # found no pending gate and exited 1. Same created_at check run_graph.py uses.
    resuming = graph.get_state(cfg).created_at is not None
    print(f"thread_id = {thread_id}" + ("  (resuming)" if resuming else "  (new run)"))

    # A step AFTER gate 4 (evaluation) raising must not lose the CV the human
    # already approved: it is in the checkpoint either way, close_run just has
    # to read it out. The backend worker has done this since 10-09
    # (backend/runs/worker.py _drive); this driver had no equivalent, so a raise
    # in the last node skipped the export entirely.
    try:
        if resuming:
            payload = _pending_interrupt(graph, cfg)
            if payload is None:
                print("Thread exists but is not parked at a gate — nothing to resume.")
                return 1
            result = graph.invoke(Command(resume=_ask_decision(payload)), config=cfg)
        else:
            result = graph.invoke(GraphState(run_id=thread_id, job_description=args.jd, cv_path=SAMPLE_CV), config=cfg)

        # keep resuming through whatever gates are left
        while "__interrupt__" in result:
            payload = result["__interrupt__"][0].value
            result = graph.invoke(Command(resume=_ask_decision(payload)), config=cfg)
    except Exception as exc:
        print(f"\n!! the run raised: {type(exc).__name__}: {exc}")
        print("   closing out whatever gate 4 already approved before re-raising...")
        try:
            saved = close_run(graph.get_state(cfg).values, owner="cli", run_id=thread_id,
                              live=not config.fake_llm_active())
            print("   saved:", saved.get("export") or "nothing (no approved review yet)")
        except Exception as close_exc:            # never mask the original error
            print(f"   close_run also failed: {type(close_exc).__name__}: {close_exc}")
        raise

    print("\n=== Run complete ===")
    print("final stage:", result.get("stage"))
    tree = result.get("cv_tree")
    print("cv_tree:", tree.source_file if tree else None, "| line_links:", len(result.get("line_links", [])))
    print("gate_feedback:")
    for fb in result.get("gate_feedback", []):
        print(f"  - {fb.gate}: {fb.decision}" + (f" ({fb.feedback})" if fb.feedback else ""))

    # Same closing step as the backend worker: gate 4's outcome -> saved CV + learning record.
    final = close_run(result, owner="cli", run_id=thread_id, live=not config.fake_llm_active())
    review = final["review"]
    print("final review:", review and f"{review['decision']} (approved={review['approved']}, "
                                      f"edited={review['edited']}, rounds={review['rounds']})")
    if final["export"]:
        print("saved:", ", ".join(str(config.OUTPUTS_DIR / p) for p in final["export"].values()))
    print("learning:", final["learning"])
    return 0


def _pending_interrupt(graph, cfg) -> dict | None:
    """Is this thread parked at a gate right now? Used by --thread resume."""
    snapshot = graph.get_state(cfg)
    for task in snapshot.tasks:
        if task.interrupts:
            return task.interrupts[0].value
    return None


if __name__ == "__main__":
    raise SystemExit(main())
