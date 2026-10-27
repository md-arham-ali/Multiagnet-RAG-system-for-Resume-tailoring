#!/usr/bin/env python3
"""
Whole-system check with the FAKE LLM. No provider key, no API spend.

Drives the real graph (real Supervisor, gates, checkpointer, retrieval, cv_link,
Document patcher) and asserts that every agent ran, every GraphState field is
filled, and every path through the graph behaves. Only the LLM answers are fixtures.

Scenarios (each on its own run id and checkpoint file):
    happy    all 4 gates approve, gate 2 answers the gap questions
    revise   Critic says revise every time -> the loop stops at max_revisions
    reject   gate 3 is rejected once -> goes back to matching, then passes
    edit     gate 4 "edit" writes the human's text back as the final CV
    durable  pause at gate 1, rebuild graph + checkpointer, resume to the end

Usage:
    python scripts/check_system.py                 # everything
    python scripts/check_system.py --only happy,revise
    python scripts/check_system.py -v              # show what the graph prints
    python scripts/check_system.py --keep          # keep the temp folder + logs/syscheck-*

Needs the local models (embedder + reranker), the profile index, and the CV at
config.CV_DEFAULT_PATH. It makes no network call to any LLM provider: the live
call path is replaced with one that raises if it is ever reached.

Isolated: outputs, the plan cache, gap-answer storage and checkpoints go to a temp
folder. The real knowledge base and Chroma index are only read. Gate snapshots land
in logs/syscheck-<scenario>-<id>/ (removed at the end unless --keep).
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import sys
import tempfile
import traceback
import uuid
import warnings
from contextlib import nullcontext, redirect_stdout
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

# Before config is imported: the fake LLM must be on for the whole process.
os.environ["USE_FAKE_LLM"] = "1"
os.environ.setdefault("TRACE", "0")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph.types import Command

import config
from state.state import (
    GraphState, MatchStatus, Stage, Verdict, VerifyStatus,
)
from utils.checkpointer import make_checkpointer

PASS, FAIL, INFO = "\033[32m✓\033[0m", "\033[31m✗\033[0m", "\033[2m·\033[0m"
M = SimpleNamespace()          # modules that are slow to import, loaded in main()
CALLS: list[dict] = []         # every LLM call the graph made: agent, prompt, schema
RUN_IDS: list[str] = []        # for cleanup of logs/<run_id>/
LAST_OUTPUT = io.StringIO()    # what the graph printed during the current drive()
_failures = 0
_checks = 0
RECORD: list[dict] = []        # every check() verdict, saved to logs/testruns/ at the end
_scenario = ""                 # name of the scenario currently running

JD = "We need a Python data engineer with SQL and ETL pipeline experience."
GATES = ["gate1_requirements", "gate2_evidence", "gate3_fit", "gate4_document"]
AGENTS = ["jd_analysis", "profile", "profile_enrich", "matching", "cv_link",
          "document", "critic", "verifier", "evaluation"]
STUBS = {"verifier", "evaluation"}     # same set as backend/runs/worker.py STUB_NODES

# what each node must return, and the stage it hands the run to
NODE_KEYS = {
    "jd_analysis": {"requirements", "stage"},
    "profile": {"evidence", "gap_questions", "stage"},
    "profile_enrich": {"evidence", "stage"},
    "matching": {"fit_report", "stage"},
    "cv_link": {"cv_tree", "line_links", "stage"},
    "document": {"document", "document_patches", "document_plan", "document_plan_key",
                 "evidence", "critique", "verifier_report", "stage"},
    "critic": {"critique", "stage"},
    "verifier": {"verifier_report", "stage"},
    "evaluation": {"eval_record", "stage"},
}
NODE_STAGE = {
    "jd_analysis": Stage.PROFILE, "profile": Stage.PROFILE_ENRICH,
    "profile_enrich": Stage.MATCHING, "matching": Stage.CV_LINK,
    "cv_link": Stage.DOCUMENT, "document": Stage.CRITIC, "critic": Stage.VERIFIER,
    "verifier": Stage.EVALUATION, "evaluation": Stage.DONE,
}
GAP_TEXT = "Syscheck answer about {req}: used it at a previous job."
EDIT_TEXT = "# Edited by syscheck\n- one line the human wrote\n"


# =============================================================================
# Reporting
# =============================================================================
def check(label: str, ok: bool, detail: str = "") -> bool:
    global _failures, _checks
    _checks += 1
    if not ok:
        _failures += 1
    RECORD.append({"scenario": _scenario, "label": label, "ok": bool(ok), "detail": detail})
    print(f"  {PASS if ok else FAIL} {label}{'' if ok else f'   -> {detail}'}")
    return ok


def info(text: str) -> None:
    print(f"  {INFO} {text}")


def section(title: str) -> None:
    print(f"\n\033[1m{title}\033[0m")


def guarded(label: str, fn) -> bool:
    """check() for a predicate that may raise (a None field, a missing key)."""
    try:
        ok = bool(fn())
        return check(label, ok, "" if ok else "predicate was false")
    except Exception as exc:
        return check(label, False, f"{type(exc).__name__}: {exc}")


# =============================================================================
# Fakes and isolation
# =============================================================================
class HashEmbedder:
    """Tiny bag-of-words embedder: the gap-answer store needs no model."""
    dim = 32

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dim
            for word in text.lower().split():
                vec[sum(map(ord, word)) % self.dim] += 1.0
            norm = sum(x * x for x in vec) ** 0.5 or 1.0
            out.append([x / norm for x in vec])
        return out


def install_fakes(tmp: Path) -> SimpleNamespace:
    """Record every LLM call, refuse live ones, and point all writes at tmp."""
    base, profile = M.base, M.profile

    real_offline = base._offline_answer

    def recording(agent, prompt, schema, fake_json):
        result = real_offline(agent, prompt, schema, fake_json)
        CALLS.append({"agent": agent, "prompt": prompt, "schema": schema.__name__})
        return result

    def refuse_live(*_a, **_k):
        raise AssertionError("a LIVE provider call was attempted during the offline check")

    base._offline_answer = recording
    base._live_answer = refuse_live

    config.OUTPUTS_DIR = tmp / "outputs"
    config.PLAN_CACHE_DIR = tmp / "plan_cache"
    config.PLAN_CACHE = True

    gap_store = M.VectorStore(embedder=HashEmbedder(), persist_dir=tmp / "gap_chroma")
    M.profile_store.MANUAL_ENTRIES = tmp / "manual_entries.json"
    real_save = M.profile_store.save_gap_answers

    def save_isolated(entries, store=None, run_id=None):
        return real_save(entries, store=gap_store, run_id=run_id)

    profile.save_gap_answers = save_isolated   # agents.profile imported the name directly
    profile.SAVE_OFFLINE = True                # the store above is disposable, so let the
                                               # offline write through (#73 item 6 skips it)
    return SimpleNamespace(gap_store=gap_store, manual=tmp / "manual_entries.json")


# =============================================================================
# Driving the graph
# =============================================================================
@dataclass
class Run:
    trail: list[str] = field(default_factory=list)            # every node, in order
    updates: dict[str, list[dict]] = field(default_factory=dict)
    gates: list[dict] = field(default_factory=list)           # interrupt payloads, in order

    @property
    def agents(self) -> list[str]:
        return [n for n in self.trail if n in AGENTS]

    def opened(self, gate: str) -> int:
        return sum(1 for g in self.gates if g["gate"] == gate)


def approve_all(payload: dict, nth: int) -> dict:
    """Answer a gate: approve, and answer every gap question at gate 2."""
    answer = {"decision": "approve", "feedback": f"syscheck {payload['gate']}"}
    gaps = payload.get("gap_questions") or []
    if gaps:
        answer["gap_answers"] = {g["requirement"]: GAP_TEXT.format(req=g["requirement"]) for g in gaps}
    return answer


def drive(graph, first, cfg, answer, verbose: bool, max_gates: int | None = None) -> Run:
    """stream -> park on __interrupt__ -> answer -> resume, until the run ends.

    `answer(payload, nth)`: nth counts how often THIS gate has opened (1-based).
    """
    global LAST_OUTPUT
    LAST_OUTPUT = io.StringIO()
    run, inp = Run(), first
    with (nullcontext() if verbose else redirect_stdout(LAST_OUTPUT)):
        while True:
            payload = None
            for update in graph.stream(inp, config=cfg, stream_mode="updates"):
                for node, fields in update.items():
                    if node == "__interrupt__":
                        payload = fields[0].value
                        continue
                    run.trail.append(node)
                    run.updates.setdefault(node, []).append(fields or {})
            if payload is None:
                break
            run.gates.append(payload)
            if max_gates is not None and len(run.gates) >= max_gates:
                break                                     # leave it parked
            inp = Command(resume=answer(payload, run.opened(payload["gate"])))
    return run


def final_values(graph, cfg) -> dict:
    values = graph.get_state(cfg).values
    if isinstance(values, dict):
        return values
    return {name: getattr(values, name) for name in GraphState.model_fields}


def start(tag: str, tmp: Path, *, critic: str = "pass", max_revisions: int = 2):
    os.environ["FAKE_CRITIC_VERDICT"] = critic
    CALLS.clear()
    run_id = f"syscheck-{tag}-{uuid.uuid4().hex[:6]}"
    RUN_IDS.append(run_id)
    cp = make_checkpointer(tmp / f"{tag}.sqlite")
    graph = M.build_graph(checkpointer=cp)
    config.PLAN_CACHE_DIR = tmp / f"plan_cache-{tag}"
    cfg = {"configurable": {"thread_id": run_id}}
    state = GraphState(run_id=run_id, job_description=JD,
                       cv_path=str(config.CV_DEFAULT_PATH), max_revisions=max_revisions)
    return run_id, cp, graph, cfg, state


def calls(agent: str) -> list[dict]:
    return [c for c in CALLS if c["agent"] == agent]


# =============================================================================
# Shared checks
# =============================================================================
def check_node_contracts(run: Run) -> None:
    """Every agent returned its keys, and handed the run to the right next stage."""
    for node in AGENTS:
        first = (run.updates.get(node) or [None])[0]
        if first is None:
            check(f"{node} returned an update", False, "node never ran")
            continue
        missing = NODE_KEYS[node] - set(first)
        stage_ok = first.get("stage") == NODE_STAGE[node]
        check(f"{node}: returns {sorted(NODE_KEYS[node])} -> {NODE_STAGE[node].value}",
              not missing and stage_ok,
              f"missing {sorted(missing)}" if missing else f"stage was {first.get('stage')}")


def check_gate_audit(v: dict, decisions: dict[str, list[str]] | None = None) -> None:
    fbs = v["gate_feedback"]
    check("gate_feedback holds one entry per gate answer, oldest first",
          [f.gate for f in fbs][:1] == [GATES[0]] and {f.gate for f in fbs} == set(GATES),
          str([f.gate for f in fbs]))
    for gate, want in (decisions or {}).items():
        got = [f.decision for f in fbs if f.gate == gate]
        check(f"{gate} decisions {want}", got == want, str(got))


def field_audit(v: dict, run_id: str, run: Run, gap_texts: dict) -> None:
    """Every GraphState field gets an expectation. A new field with none fails here."""
    req, fit, tree, doc = v["requirements"], v["fit_report"], v["cv_tree"], v["document"]
    node_ids = {n.node_id for n in M.walk(tree.root)} if tree else set()
    evidence_ids = [b.source_id for b in v["evidence"]]
    expect = {
        "messages": (lambda: True, "unused by design"),
        "run_id": (lambda: v["run_id"] == run_id, "the run id"),
        "stage": (lambda: v["stage"] == Stage.DONE, "DONE"),
        "job_description": (lambda: v["job_description"] == JD, "the JD"),
        "cv_path": (lambda: v["cv_path"] == str(config.CV_DEFAULT_PATH), "the default CV"),
        "requirements": (lambda: req.role_title and len(req.requirements) == 3 and req.keywords,
                         "role, 3 requirements, keywords"),
        "evidence": (lambda: len(evidence_ids) >= 3 and len(evidence_ids) == len(set(evidence_ids))
                     and "gap_answer:SQL" in evidence_ids and all(b.content for b in v["evidence"]),
                     "retrieved blocks, unique ids, plus the polished gap answer"),
        "gap_questions": (lambda: sorted(q.requirement for q in v["gap_questions"]) == ["ETL pipelines", "SQL"],
                          "SQL + ETL pipelines asked"),
        "gap_answers": (lambda: v["gap_answers"] == gap_texts, "what gate 2 sent"),
        "fit_report": (lambda: len(fit.matches) == 3 and fit.overall_fit == 0.5
                       and fit.must_have_coverage == 0.5 and fit.unmet_must_haves == ["ETL pipelines"]
                       and fit.ranked_evidence_ids and set(fit.ranked_evidence_ids) <= set(evidence_ids),
                       "strong/partial/none -> fit 0.5, ETL unmet, ranked ids are real"),
        "cv_tree": (lambda: tree.source_file == Path(config.CV_DEFAULT_PATH).name and len(node_ids) > 10,
                    "parsed CV"),
        "line_links": (lambda: v["line_links"] and all(l.node_id in node_ids for l in v["line_links"]),
                       "every link points at a tree node"),
        "document": (lambda: doc.kind == "cv" and doc.content.strip()
                     and doc.unsupported_flags == fit.unmet_must_haves,
                     "CV text; flags come from the fit report"),
        "document_patches": (lambda: v["document_patches"] is not None
                             and all(e.target_id in node_ids and e.new_text in doc.content
                                     for e in v["document_patches"].edits),
                             "edits target real nodes and are in the text"),
        "document_plan": (lambda: v["document_plan"] and all(p.node_id in node_ids for p in v["document_plan"].verdicts),
                          "verdicts for real nodes"),
        "document_plan_key": (lambda: re.fullmatch(r"[0-9a-f]{16}", v["document_plan_key"] or ""),
                              "16-hex call fingerprint"),
        "critique": (lambda: v["critique"].verdict == Verdict.PASS, "pass"),
        "verifier_report": (lambda: v["verifier_report"].status == VerifyStatus.PASS and not v["verifier_report"].claims,
                            "stub: PASS, no claims"),
        "eval_record": (lambda: 0.0 <= v["eval_record"].ats_score <= 1.0
                        and v["eval_record"].prompt_versions == v["prompt_versions"]   # copied from the run, #77 item 3
                        and v["eval_record"].fit_score == v["fit_report"].overall_fit,   # recorded since #77 item 2
                        "ats score, prompt versions, no invented scores"),
        "active_rubric": (lambda: v["active_rubric"] is None, "not left stale after the Critic stage"),
        "profile_id": (lambda: v.get("profile_id") is None, "this script runs without an account"),
        "prompt_versions": (lambda: {"jd_analysis", "profile", "matching", "document", "critic"} <= set(v["prompt_versions"])
                            and all(isinstance(n, int) for n in v["prompt_versions"].values()),
                            "every agent that called the model recorded the version it used"),
        "supervisor_decision": (lambda: v["supervisor_decision"].next_node == "END", "last decision: END"),
        "revision_count": (lambda: v["revision_count"] == 0, "no redo on the happy path"),
        "max_revisions": (lambda: v["max_revisions"] == 2, "default cap"),
        "gate_feedback": (lambda: [f.gate for f in v["gate_feedback"]] == GATES
                          and all(f.decision == "approve" and f.revision == 0 for f in v["gate_feedback"]),
                          "4 approvals in gate order, round 0"),
    }
    uncovered = sorted(set(GraphState.model_fields) - set(expect))
    check("every GraphState field has an expectation in this script", not uncovered,
          f"add one for: {uncovered}")
    for name in GraphState.model_fields:
        if name in expect:
            predicate, why = expect[name]
            guarded(f"field {name}: {why}", predicate)


# =============================================================================
# Scenarios
# =============================================================================
def scenario_happy(tmp: Path, fakes: SimpleNamespace, verbose: bool) -> None:
    run_id, cp, graph, cfg, state = start("happy", tmp)
    run = drive(graph, state, cfg, approve_all, verbose)
    v = final_values(graph, cfg)
    cp.conn.close()

    section("happy: route")
    check("agents ran in order", run.agents == AGENTS, str(run.agents))
    check("gates opened in order, once each", [g["gate"] for g in run.gates] == GATES,
          str([g["gate"] for g in run.gates]))
    check("graph finished (nothing left parked)", not run.gates or run.opened(GATES[-1]) == 1)

    section("happy: each agent's output")
    check_node_contracts(run)
    check("verifier and evaluation are the stubs the UI labels as placeholder",
          STUBS == set(M.worker.STUB_NODES), f"worker.STUB_NODES = {sorted(M.worker.STUB_NODES)}")

    section("happy: LLM calls (fake)")
    want = {"jd_analysis": 1, "profile": 1, "profile_enrich": 1, "matching": 1,
            "document_plan": 1, "critic": 1}
    for agent, n in want.items():
        check(f"{agent}: {n} call", len(calls(agent)) == n, f"{len(calls(agent))} calls")
    check("document (the writer): at least 1 call, one per section with lines to write",
          len(calls("document")) >= 1, "0 calls: Document never reached its writer")
    check("stubs and cv_link make no LLM call",
          not any(c["agent"] in {"verifier", "evaluation", "cv_link", "supervisor"} for c in CALLS))
    info("calls: " + ", ".join(f"{a} x{sum(1 for c in CALLS if c['agent'] == a)}"
                               for a in dict.fromkeys(c["agent"] for c in CALLS)))

    section("happy: state reached each prompt")
    first_ev = v["evidence"][0].source_id if v["evidence"] else "<no evidence>"
    doc_head = v["document"].content[:30] if v["document"] else "<no document>"
    needs = {
        "jd_analysis": [JD],
        "profile": ["REQUIREMENT: Python", "EVIDENCE:"],
        "profile_enrich": [GAP_TEXT.format(req="SQL")],
        "matching": ["REQUIREMENTS TO SCORE", first_ev],
        "document_plan": ["CV SECTIONS", "UNMET MUST-HAVES"],
        "document": ["LINES TO WRITE", "EVIDENCE (cite by id"],
        "critic": ["RUBRIC:", "Relevance", "DOCUMENT:", doc_head],
    }
    for agent, parts in needs.items():
        sent = calls(agent)[0]["prompt"] if calls(agent) else ""
        for part in parts:
            check(f"{agent} prompt contains {part[:40]!r}", part in sent)

    section("happy: every GraphState field")
    gap_texts = {q.requirement: GAP_TEXT.format(req=q.requirement) for q in v["gap_questions"]}
    field_audit(v, run_id, run, gap_texts)
    check_gate_audit(v)
    info(f"CV links: " + ", ".join(
        f"{s.value} {sum(1 for l in v['line_links'] if l.status == s)}" for s in MatchStatus))
    edits = v["document_patches"].edits if v["document_patches"] else []
    info(f"Document accepted {len(edits)} edit(s)" + ("" if edits else
         "  (0 is possible offline: the writer fixture cites fixed ids; the guards reject the rest)"))

    section("happy: side effects")
    entries = M.read_json(fakes.manual)
    polished = json.loads(M.profile._ENRICH_FAKE_JSON)["polished"][0]["polished_answer"]
    check("gap answer saved to manual_entries (temp copy)",
          len(entries) == 1 and entries[0]["section"] == "gap_answers"
          and entries[0]["run_id"] == run_id and entries[0]["record"]["content"] == polished,
          str(entries)[:200])
    check("gap answer embedded in the (temp) profile index", fakes.gap_store.count("profile") == 1)
    key = v["document_plan_key"]
    check("planner answer cached on disk", (config.PLAN_CACHE_DIR / f"{key}.json").exists())
    snaps = list((config.BASE_DIR / "logs" / run_id).glob("*.json"))
    check("a state snapshot was written at every gate",
          {p.stem.split("_", 1)[1] for p in snaps} == set(GATES), str(sorted(p.name for p in snaps)))
    final = M.final_review.close_run(v, owner="syscheck", run_id=run_id, live=False)
    exported = final["export"] or {}
    md = config.OUTPUTS_DIR / exported["md"] if "md" in exported else None
    check("final review read: approved, not edited, 1 round",
          final["review"] and final["review"]["approved"] and not final["review"]["edited"]
          and final["review"]["rounds"] == 1, str(final["review"]))
    check("approved CV exported (temp outputs/)", md is not None and md.read_text() == v["document"].content)
    check("offline run is kept out of the learning store",
          str(final["learning"]).startswith("skipped: offline"), str(final["learning"]))


def scenario_revise(tmp: Path, fakes: SimpleNamespace, verbose: bool) -> None:
    run_id, cp, graph, cfg, state = start("revise", tmp, critic="revise", max_revisions=2)
    run = drive(graph, state, cfg, approve_all, verbose)
    v = final_values(graph, cfg)
    cp.conn.close()

    section("revise: the loop stops at the cap")
    check("run still reaches DONE (no recursion error)", v["stage"] == Stage.DONE, str(v["stage"]))
    check("revision_count == max_revisions", v["revision_count"] == 2, str(v["revision_count"]))
    check("document and critic each ran 3 times (1 draft + 2 redos)",
          run.agents.count("document") == 3 and run.agents.count("critic") == 3,
          f"document x{run.agents.count('document')}, critic x{run.agents.count('critic')}")
    check("redos skip cv_link, matching and profile",
          run.agents.count("cv_link") == 1 and run.agents.count("matching") == 1
          and run.agents.count("profile") == 1)
    check("the verifier ran once, only after the cap",
          run.agents.count("verifier") == 1 and run.agents.index("verifier") > len(run.agents) - 4)
    check("final critique is the REVISE with its 3 items",
          v["critique"].verdict == Verdict.REVISE
          and [i.rubric_item for i in v["critique"].items] == ["Relevance", "Evidence traceability", "Readability"])
    docs = run.updates["document"]
    check("every Document pass clears critique + verifier_report (D3)",
          all(u["critique"] is None and u["verifier_report"] is None for u in docs))
    check("redo rounds keep the saved plan (same key)", len({u["document_plan_key"] for u in docs}) == 1)
    check("the planner was called once; the writer again on every round",
          len(calls("document_plan")) == 1 and len(calls("document")) >= 3
          and len(calls("document")) % 3 == 0,
          f"planner x{len(calls('document_plan'))}, writer x{len(calls('document'))}")
    check("critic read the same rubric on every lap",
          len(calls("critic")) == 3 and all("Relevance" in c["prompt"] for c in calls("critic")))
    gate4 = [f for f in v["gate_feedback"] if f.gate == GATES[3]]
    check("gate 4 opened once, in the last round", len(gate4) == 1 and gate4[0].revision == 2,
          str([(f.gate, f.revision) for f in v["gate_feedback"]]))


def scenario_reject(tmp: Path, fakes: SimpleNamespace, verbose: bool) -> None:
    def answer(payload, nth):
        a = approve_all(payload, nth)
        if payload["gate"] == "gate3_fit" and nth == 1:
            a.update(decision="reject", feedback="syscheck: send it back")
        return a

    run_id, cp, graph, cfg, state = start("reject", tmp)
    run = drive(graph, state, cfg, answer, verbose)
    v = final_values(graph, cfg)
    cp.conn.close()

    section("reject: gate 3 sends the work back to Matching")
    check("run reaches DONE", v["stage"] == Stage.DONE, str(v["stage"]))
    check("gate 3 opened twice", run.opened("gate3_fit") == 2, str(run.opened("gate3_fit")))
    check("matching ran twice (LLM called twice)",
          run.agents.count("matching") == 2 and len(calls("matching")) == 2)
    check("cv_link ran twice; the second run returned only the stage (already linked)",
          run.agents.count("cv_link") == 2 and set(run.updates["cv_link"][1]) == {"stage"},
          str(set(run.updates["cv_link"][1])))
    check("a reject costs one revision", v["revision_count"] == 1, str(v["revision_count"]))
    check_gate_audit(v, {"gate3_fit": ["reject", "approve"]})
    stamps = [f.revision for f in v["gate_feedback"] if f.gate == "gate3_fit"]
    check("the second answer is stamped with the new round", stamps == [0, 1], str(stamps))
    check("Document ran once, after the gate passed", run.agents.count("document") == 1)


def scenario_edit(tmp: Path, fakes: SimpleNamespace, verbose: bool) -> None:
    def answer(payload, nth):
        a = approve_all(payload, nth)
        if payload["gate"] == "gate1_requirements":
            a.update(decision="edit", edited_payload={"note": "tighten the requirements"})
        if payload["gate"] == "gate4_document":
            a.update(decision="edit", edited_payload={"content": EDIT_TEXT})
        return a

    run_id, cp, graph, cfg, state = start("edit", tmp)
    run = drive(graph, state, cfg, answer, verbose)
    v = final_values(graph, cfg)
    cp.conn.close()

    section("edit: gate 4 writes the human's CV back")
    check("run reaches DONE (edit advances like approve)", v["stage"] == Stage.DONE, str(v["stage"]))
    check("final document is the human's text", v["document"].content == EDIT_TEXT.strip() + "\n",
          repr(v["document"].content[:60]))
    last = [f for f in v["gate_feedback"] if f.gate == "gate4_document"][-1]
    draft_seen = run.gates[-1]["value"]["content"]
    check("the draft the human saw is kept next to their edit",
          (last.edited_payload or {}).get("draft") == draft_seen)
    check("gate 4 showed the line-by-line changes", "changes" in run.gates[-1])
    first = [f for f in v["gate_feedback"] if f.gate == "gate1_requirements"][0]
    check("gate 1 edit is recorded (not written back; known open item)",
          first.decision == "edit" and first.edited_payload == {"note": "tighten the requirements"})
    check("evaluation scored the edited text (no JD keyword in it -> 0.0)",
          v["eval_record"].ats_score == 0.0, str(v["eval_record"].ats_score))
    final = M.final_review.close_run(v, owner="syscheck", run_id=run_id, live=False)
    md = config.OUTPUTS_DIR / final["export"]["md"] if final["export"] else None
    check("final review sees an edit", final["review"]["edited"] and final["review"]["approved"],
          str(final["review"]))
    check("the exported file is the edited CV", md is not None and md.read_text() == v["document"].content)


def scenario_durable(tmp: Path, fakes: SimpleNamespace, verbose: bool) -> None:
    run_id, cp, graph, cfg, state = start("durable", tmp)
    path = tmp / "durable.sqlite"
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        first = drive(graph, state, cfg, approve_all, verbose, max_gates=1)
        cp.conn.close()                                   # the "process" ends here
        before = [c["agent"] for c in CALLS]
        CALLS.clear()

        cp2 = make_checkpointer(path)                     # a new connection, a new graph
        graph2 = M.build_graph(checkpointer=cp2)
        pending = [t.interrupts[0].value for t in graph2.get_state(cfg).tasks if t.interrupts]
        rest = None
        if pending:
            rest = drive(graph2, Command(resume=approve_all(pending[0], 1)), cfg, approve_all, verbose)
        v = final_values(graph2, cfg)
        cp2.conn.close()

    section("durable: pause, rebuild everything, resume")
    check("first pass parked at gate 1", [g["gate"] for g in first.gates] == [GATES[0]]
          and first.agents == ["jd_analysis"], str(first.agents))
    check("the pause survives: new graph sees gate 1 pending",
          len(pending) == 1 and pending[0]["gate"] == GATES[0])
    check("resume finishes the run", rest is not None and v["stage"] == Stage.DONE, str(v.get("stage")))
    check("jd_analysis was NOT run again after the resume",
          "jd_analysis" not in [c["agent"] for c in CALLS] and before.count("jd_analysis") == 1)
    check("all 4 gate answers are in the audit trail",
          [f.gate for f in v["gate_feedback"]] == GATES, str([f.gate for f in v["gate_feedback"]]))
    bad = [str(w.message) for w in caught
           if re.search(r"unregistered|deserializ|msgpack|blocked", str(w.message), re.I)]
    check("no checkpoint-serialization warning (every state type is allow-listed)", not bad, "; ".join(bad)[:200])


SCENARIOS = {
    "happy": scenario_happy,
    "revise": scenario_revise,
    "reject": scenario_reject,
    "edit": scenario_edit,
    "durable": scenario_durable,
}


# =============================================================================
# Main
# =============================================================================
def preflight() -> list[str]:
    problems = []
    if not Path(config.CV_DEFAULT_PATH).is_file():
        problems.append(f"no CV at {config.CV_DEFAULT_PATH}  (set CV_DEFAULT_PATH, or put CV_test.pdf in knowledge_base/input/)")
    try:
        import chromadb

        count = chromadb.PersistentClient(path=str(config.VECTORDB_DIR)).get_collection("profile").count()
        if count == 0:
            problems.append("the 'profile' index is empty:  python scripts/build_vectordb.py")
    except Exception as exc:
        problems.append(f"cannot read the profile index ({type(exc).__name__}):  python scripts/build_vectordb.py")
    return problems


def load_modules() -> None:
    """The graph import is slow: agents/profile.py loads the embedder + reranker."""
    from agents import base, matching, profile
    from agents.supervisor import build_graph
    from backend.jsonstore import read_json
    from backend.runs import worker
    from learning import profile_store
    from utils import final_review
    from utils.cv_handling.cv_extract import walk
    from vectordb.store import VectorStore

    M.base, M.matching, M.profile, M.build_graph = base, matching, profile, build_graph
    M.read_json, M.worker, M.profile_store = read_json, worker, profile_store
    M.final_review, M.walk, M.VectorStore = final_review, walk, VectorStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", default="", help=f"comma list of: {', '.join(SCENARIOS)}")
    parser.add_argument("-v", "--verbose", action="store_true", help="show what the graph prints")
    parser.add_argument("--keep", action="store_true", help="keep the temp folder and logs/syscheck-*")
    args = parser.parse_args()

    chosen = [s.strip() for s in args.only.split(",") if s.strip()] or list(SCENARIOS)
    unknown = [s for s in chosen if s not in SCENARIOS]
    if unknown:
        parser.error(f"unknown scenario(s): {unknown}. Known: {list(SCENARIOS)}")

    problems = preflight()
    if problems:
        print("Cannot run the check:")
        for p in problems:
            print(f"  ! {p}")
        return 2

    print("importing the graph (loads the local embedding + rerank models; slow the first time) ...", flush=True)
    load_modules()
    tmp = Path(tempfile.mkdtemp(prefix="syscheck-"))
    fakes = install_fakes(tmp)
    print(f"fake LLM on, live calls blocked, writes go to {tmp}")

    global _scenario
    started = datetime.now()
    for name in chosen:
        _scenario = name
        section(f"== scenario: {name} " + "=" * 50)
        try:
            SCENARIOS[name](tmp, fakes, args.verbose)
        except Exception as exc:
            check(f"scenario {name} ran to the end", False, f"{type(exc).__name__}: {exc}")
            traceback.print_exc(limit=6)
            tail = LAST_OUTPUT.getvalue().splitlines()[-15:]
            if tail:
                print("  last graph output:\n    " + "\n    ".join(tail))

    if not args.keep:
        shutil.rmtree(tmp, ignore_errors=True)
        for run_id in RUN_IDS:
            shutil.rmtree(config.BASE_DIR / "logs" / run_id, ignore_errors=True)
    else:
        print(f"\nkept: {tmp} and logs/syscheck-*")

    print(f"\n{_checks - _failures}/{_checks} checks passed" + ("" if not _failures else f", {_failures} FAILED"))
    save_results(chosen, started)
    return 1 if _failures else 0


def save_results(chosen: list[str], started: datetime) -> None:
    """Write logs/testruns/syscheck-<stamp>.json (+ syscheck-latest.json)."""
    try:
        per = {n: {"passed": 0, "failed": 0} for n in chosen}
        for r in RECORD:
            if r["scenario"] in per:
                per[r["scenario"]]["passed" if r["ok"] else "failed"] += 1
        doc = {
            "kind": "syscheck",
            "started_at": started.isoformat(timespec="seconds"),
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "scenarios": per,
            "summary": {"checks": _checks, "passed": _checks - _failures, "failed": _failures},
            "failed": [r for r in RECORD if not r["ok"]],
            "checks": RECORD,
        }
        out = config.BASE_DIR / "logs" / "testruns"
        out.mkdir(parents=True, exist_ok=True)
        text = json.dumps(doc, indent=2)
        (out / f"syscheck-{started:%Y%m%d-%H%M%S}.json").write_text(text)
        (out / "syscheck-latest.json").write_text(text)
        print(f"results saved: logs/testruns/syscheck-{started:%Y%m%d-%H%M%S}.json")
    except Exception as exc:
        print(f"could not save results: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
