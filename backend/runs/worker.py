"""
The pipeline worker: relays the graph's OWN human gates to the UI.

One of these per run, on its own daemon thread.

The bridge used to implement gates itself - four positions in a GATE_AFTER table
plus a threading.Event. The graph grew a real `gate` node on 2026-08-20
(interrupt() + a SQLite checkpointer) and the two collided: interrupt() yields
{"__interrupt__": (Interrupt(...),)} and ENDS the stream, which the old loop read
as a dict of state fields and died on with "'tuple' object has no attribute
'items'" right after gate 1 (bugs.md #9). The graph owns pausing now; this file
relays it - stream, park on __interrupt__, wait for the UI, resume with
Command(resume=answer).

Two things follow from that. A paused run is durable, because the checkpointer
outlives the process while this thread does not. And `reject` finally means what
the graph says it means - send the work back to the agent that produced the
artifact (bugs.md #10) - instead of killing the run here at the bridge.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from langgraph.types import Command
from pydantic import BaseModel

import config
from backend import logplane
from state.state import GraphState
from state.state_utils import scrub_cv_tree

# Imported lazily, not at module scope: agents/profile.py instantiates
# Retriever(reranker=Reranker()) at import time, which pulls in PyTorch and
# loads two ~440MB models (~25s). At module scope that cost lands on every
# `import backend.app` — server boot, every test, every `--help`. Deferring it
# here means the API boots in well under a second and the models load on the
# first run that actually needs them. Tests override BUILD_GRAPH with a stub.
BUILD_GRAPH = None
MAKE_CHECKPOINTER = None

# The 9 pipeline nodes in dispatch order. profile_enrich became a real node on
# 2026-08-26 and was missing here, so the UI was told nothing at all while it ran
# (bugs.md #28); cv_link (2026-10-06) went missing the same way. Everything not
# in this list — "gate", "END" — is not an agent and gets no routing/node_start
# event.
AGENTS = [
    "jd_analysis",
    "profile",
    "profile_enrich",
    "matching",
    "cv_link",
    "document",
    "critic",
    "verifier",
    "evaluation",
]

# The graph's four gates, keyed by the name human_gate() puts in the interrupt
# payload (agents/supervisor.py STAGE_GATE). Two things per gate that are NOT the
# same thing: `after` is the node the pause follows, `artifact_node` is whose
# output the human is being asked to approve. They differ for the last gate — it
# fires after `verifier` but reviews the `document` — and keying only by position
# is what used to show the fact-check on the screen titled "Final document
# review" (bugs_fixed.md #2). Gate 3 is the same case since cv_link: STAGE_GATE
# pauses before Stage.DOCUMENT, which is after cv_link, but it reviews the fit.
GATES = {
    "gate1_requirements": {"after": "jd_analysis", "title": "Requirements review",   "artifact_node": "jd_analysis"},
    "gate2_evidence":     {"after": "profile",     "title": "Evidence review",       "artifact_node": "profile"},
    "gate3_fit":          {"after": "cv_link",     "title": "Fit review",            "artifact_node": "matching"},
    "gate4_document":     {"after": "verifier",    "title": "Final document review", "artifact_node": "document"},
}

# Agents whose node() is still a placeholder returning fabricated-but-plausible
# output. Emitted as `stub: true` on node_done so the frontend can stop guessing
# from response shape (frontend/src/stubs.js). DELETE an entry the moment its
# agent becomes real — a stale entry mislabels genuine output as fabricated,
# which is what happened to `matching` between 2026-08-30 and 2026-08-31
# (bugs.md #28). Real as of this list: jd_analysis, profile, profile_enrich,
# matching, cv_link, document, critic. Each stub module's docstring points back
# here, so whoever makes the agent real sees this list.
STUB_NODES = {"verifier", "evaluation"}


def _build_graph():
    """Compile the graph on a per-run checkpointer. Returns (graph, checkpointer).

    Per run, not per process: SqliteSaver wraps one sqlite3 connection, and runs
    execute concurrently on their own threads. A fresh connection per run is
    cheaper than reasoning about sharing one across them.
    """
    global BUILD_GRAPH, MAKE_CHECKPOINTER
    if BUILD_GRAPH is None:
        from agents.supervisor import build_graph

        BUILD_GRAPH = build_graph
    if MAKE_CHECKPOINTER is None:
        from utils.checkpointer import make_checkpointer

        MAKE_CHECKPOINTER = make_checkpointer
    checkpointer = MAKE_CHECKPOINTER()
    return BUILD_GRAPH(checkpointer=checkpointer), checkpointer


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jsonable(value):
    """Pydantic artifacts / enums / lists -> plain JSON-safe values."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if hasattr(value, "value"):  # Enum
        return value.value
    return value


def emit(run: dict, type_: str, **fields) -> None:
    run["events"].append({"type": type_, "ts": _now(), **fields})


def _scrub_cv_tree(tree: dict) -> dict:
    """Drop what frontend/design.md's CV-privacy rule forbids from a cv_link
    artifact before it is emitted/persisted: the header section outright
    (name, email, phone - section_type "header", state/state.py SectionType)
    and raw_text everywhere else in the tree.

    This was "harmless only while every run uses the shared sample CV"
    (bugs.md 2026-10-09 "later" #4) - real CV uploads landed 2026-10-10, so
    it is now a live PII leak into the persisted, replayed run log. It is a
    pure subtraction, not a wire-shape change: bugs.md's own inventory of
    what the CV Reader card/drawer actually read off this artifact
    ("Round 8-10" #5) is node_id/title from cv_tree.root.children and text
    from the separate line_links list - never cv_tree's own text/raw_text at
    any depth, so nothing the frontend renders is touched.

    2026-10-22, Agents + Orchestration, FLAGGED FOR THIS LANE'S REVIEW: the
    body moved to state/state_utils.py:scrub_cv_tree, unchanged, and this is
    now a one-line delegation. The gate snapshot needed the same rule and
    could not import backend/ (bugs_audit_fixed.md #72 item 4); two copies of
    one privacy rule is exactly how this one came to be applied on one path
    and not the other. The name stays - tests/test_backend_api.py calls it.
    """
    return scrub_cv_tree(tree)


# state/state.py's MatchStatus values. A new user with an empty profile gets
# every CV line back unmatched, so Document has no evidence to edit with and
# the CV returns mostly unchanged - the frontend wants to say so rather than
# look broken (bugs.md "later" #5). If `contradicted` ever becomes a fourth
# MatchStatus (state/state.py's own comment anticipates it), this total will
# silently stop covering every line_link - add it here too when that lands.
_MATCH_STATUSES = ("matched", "partial", "unmatched")


def _match_counts(line_links: list[dict]) -> dict[str, int]:
    """How many of this cv_link run's line_links landed in each MatchStatus -
    a derived summary, not new data (line_links already carries every line's
    own status), so the frontend doesn't need to walk the whole list itself
    just to decide whether to show the empty-profile warning."""
    counts = {status: 0 for status in _MATCH_STATUSES}
    for link in line_links:
        status = link.get("status")
        if status in counts:
            counts[status] += 1
    return counts


# A node update carrying nothing but the next stage is a "no change", not a
# result. `stage` is the one field every node returns, so this is the whole
# payload of a skipped re-run; an empty update never reaches here at all
# (`not fields` continues above).
_NOTHING_BUT_STAGE = {"stage"}


def _log_run(run: dict, event: str, **fields) -> None:
    """One entry in the log plane's `run` kind (backend/bugs.md "2026-10-09
    (design)" §5) - the account's own run timeline, separate from the SSE
    event trail in run["events"]: `actor="account"` throughout, since every
    event here is either a direct answer from the run's owner or a
    consequence of a run they started. Never raises (logplane.write's own
    contract) and never carries anything beyond what §5's "who sees what"
    table lists as run-kind-visible (node/gate names, durations, decisions,
    error messages) - never prompt/response text, stack traces or paths."""
    # .get, not run["owner"]: this helper's contract above is "never raises",
    # and logplane.write honours it - but a missing key raised *before* the call,
    # from the argument list. That turned _drive's own error path into a second
    # exception that escaped the worker, losing the run_error it was in the
    # middle of reporting. A log line that cannot name its account is still
    # worth writing; a run that cannot report why it failed is not acceptable.
    logplane.write("run", event=event, actor="account", profile_id=run.get("owner"),
                    run_id=run.get("id"), fields=fields)


def _emit_routing(run: dict, fields: dict) -> str | None:
    """Announce the Supervisor's recorded decision. Returns the node that was
    just started, or None, so _drain can time it.

    Read off supervisor_decision rather than guessed from the previous node's
    `stage`: the old bridge emitted node_start optimistically and so claimed
    `profile` had started on a run that died before it ever ran (bugs.md #9).
    """
    decision = fields.get("supervisor_decision")
    next_node = getattr(decision, "next_node", None)
    if next_node not in AGENTS:
        return None  # "gate" has its own events; "END" is not a node
    emit(run, "routing", decision=f"supervisor -> {next_node}")
    emit(run, "node_start", node=next_node)
    return next_node


def _drain(run: dict, graph, stream_input, cfg: dict):
    """Traced wrapper: one Langfuse segment per stretch between gates."""
    from utils import observability

    with observability.segment(run, "resume-gate" if isinstance(stream_input, Command) else "start-run"):
        return _drain_stream(run, graph, stream_input, cfg)


def _drain_stream(run: dict, graph, stream_input, cfg: dict):
    """Stream until the graph pauses at a gate (payload returned) or ends (None)."""
    started_at: dict[str, float] = {}
    for update in graph.stream(stream_input, config=cfg, stream_mode="updates"):
        for node, fields in update.items():
            if node == "__interrupt__":
                # A tuple of Interrupt objects, not a dict of state fields. The
                # stream is over at this point; the run resumes via Command.
                return fields[0].value
            time.sleep(run["pace"])
            if node == "supervisor":
                started = _emit_routing(run, fields)
                if started is not None:
                    started_at[started] = time.monotonic()
                    run["in_flight"] = started
                continue
            if node == run.get("in_flight"):
                # Any update from it means it finished - an empty one included,
                # which gets no node_done below.
                run["in_flight"] = None
            if node == "gate" and fields and fields.get("document") is not None:
                # Gate 4 "edit": the candidate's own text replaced the draft. Its own
                # event, not a node_done for document - the Writer did not produce it.
                emit(run, "document_edited", artifact=_jsonable({"document": fields["document"]}))
                continue
            if node == "gate" or not fields:
                continue  # the gate's own events are emitted around the pause
            artifact = _jsonable({k: v for k, v in fields.items() if k != "messages"})
            extra = {}
            if _NOTHING_BUT_STAGE >= set(artifact):
                # The node ran and produced no new artifact: cv_link skipping a
                # re-read of the same CV on a gate-3 loop-back, profile_enrich
                # with no answers to add. Returning `{stage}` as the artifact
                # made that look like an empty *result* - a CV Reader card with
                # nothing in it - so the frontend grew a cv_link-shaped special
                # case for it (bugs.md "Round 8-10" §6). Say it outright
                # instead: still a node_done (node_start was emitted, and
                # without the done the step pulses "working" forever), with no
                # artifact key at all rather than a misleading one.
                extra["unchanged"] = True
                artifact = None
            elif node == "cv_link":
                if "cv_tree" in artifact:
                    artifact = {**artifact, "cv_tree": _scrub_cv_tree(artifact["cv_tree"])}
                if "line_links" in artifact:
                    extra["match_counts"] = _match_counts(artifact["line_links"])
            if artifact is None:
                emit(run, "node_done", node=node, stub=node in STUB_NODES, **extra)
            else:
                emit(run, "node_done", node=node, artifact=artifact, stub=node in STUB_NODES, **extra)
            # The elapsed wall clock since node_start includes this same
            # update's own pacing sleep just above (every update gets one) -
            # subtracted so a "node duration" doesn't read as "at least
            # pace_seconds" for every node regardless of real work done.
            since_start = time.monotonic() - started_at.pop(node, time.monotonic())
            _log_run(run, "node_done", node=node, duration_s=round(max(0.0, since_start - run["pace"]), 3))
    return None


def _persist(run: dict) -> None:
    """Write the run's trail to disk now, not only at the end.

    Before this, save_log only ran from run_worker's on_finish, so a run
    parked at a gate had NO log on disk at all - a restart while a human was
    slow to answer lost it completely, with nothing to resume from (bugs.md
    "gate 4" §7). Lazy import: registry imports this module at its own module
    scope, so importing it back here at module scope would be circular; by
    the time this function actually runs both modules have already finished
    loading.
    """
    from backend.runs.registry import save_log

    save_log(run)


def gate_info(payload: dict) -> dict:
    """The run["gate"] shape built from a just-opened interrupt payload -
    `{gate, after, title, artifact_node, gap_questions}` - with no side
    effect on `run` and no event emitted.

    Factored out of _park so registry.resume() can compute it too: a resumed
    run needs this dict installed on `run["gate"]` *before* its worker thread
    is even started, not only once that thread gets scheduled and reaches
    _park itself - which on a cold process can be the ~20s embedding-model
    load (agents/profile.py's module-scope Retriever). Without that, POST
    .../gate would wrongly 409 ("no gate is waiting") for several seconds
    right after a resume, even though the UI already shows the gate (replayed
    off the saved log) and the human is ready to answer it.

    Kept on the parked gate (not just in the emitted event) so answer_gate
    can check a gap_answers key against the questions THIS gate actually
    asked, rather than trusting whatever a client sends (bugs.md
    2026-10-09 "Round 8-10" #1b) - a mismatched key would otherwise reach
    enrich() as a near-duplicate "QUESTION: No question found" block.
    """
    gate_name = payload.get("gate")
    gate = GATES.get(gate_name)
    if gate is None:
        raise KeyError(
            f"The graph opened a gate the bridge does not know: {gate_name!r}. "
            f"Known: {sorted(GATES)}."
        )
    return {**gate, "gate": gate_name, "gap_questions": payload.get("gap_questions") or []}


def _park(run: dict, payload: dict) -> None:
    """Install run["gate"] for a payload the graph just produced, and
    announce + persist it. Not called for the first gate of a resumed run -
    registry.resume() already installed run["gate"] (via gate_info, above)
    before the worker thread started, and the gate_wait this would emit is
    already the last line of the log it was resumed from (that's how
    registry.resume() found it); emitting it again would duplicate the event
    and show the same review screen twice in a row to whoever is watching.
    """
    gate = gate_info(payload)
    run["gate"] = gate
    extras = {k: v for k, v in payload.items() if k not in _PAYLOAD_NOT_PASSED}
    emit(
        run,
        "gate_wait",
        gate=gate["gate"],
        node=gate["after"],
        title=gate["title"],
        artifact_node=gate["artifact_node"],
        **{"gap_questions": [], **extras},
    )
    _persist(run)
    _log_run(run, "gate_opened", gate=gate["gate"])


def _await_answer(run: dict) -> dict | None:
    """Block for the UI's answer to the currently open run["gate"]. None if
    the run was superseded (aborted) while waiting."""
    gate = run["gate"]
    run["gate_event"].wait()
    run["gate_event"].clear()
    run["gate"] = None
    if run["aborted"]:
        return None

    answer = run["gate_answer"]
    emit(
        run,
        "gate_done",
        gate=gate["gate"],
        node=gate["after"],
        decision=answer["decision"],
        feedback=answer.get("feedback", ""),
        gap_answers=answer.get("gap_answers") or {},
        # A flag, not the text: the edited CV arrives once, as document_edited.
        edited=bool((answer.get("edited_payload") or {}).get("content")),
    )
    # The decision only, never the typed feedback/gap_answers/edited text -
    # backend/bugs.md "2026-10-09 (design)" §5's content rule for this kind.
    _log_run(run, "gate_decided", gate=gate["gate"], decision=answer["decision"])
    return answer


def _wait_for_gate(run: dict, payload: dict) -> dict | None:
    """Park on the gate the graph just opened and block for its answer.
    Returns the answer, or None if this run was superseded while waiting."""
    _park(run, payload)
    return _await_answer(run)


# The payload keys the gate_wait event already carries in its own form, plus the
# event's own fields, which a payload key must never overwrite.
_PAYLOAD_NOT_PASSED = {"gate", "field", "value", "type", "ts", "node", "title", "artifact_node"}


def _close(run: dict, graph, cfg: dict) -> dict:
    """After the graph ends: gate 4's outcome, the saved CV, the learning record
    (utils/final_review.close_run). A failure here is reported on run_done, never
    turned into run_error: the CV is already in the event trail either way."""
    try:
        from utils.final_review import close_run

        values = graph.get_state(cfg).values
        return {"final": close_run(values, owner=run["owner"], run_id=run["id"],
                                   live=run["mode"] == "live")}
    except Exception as exc:
        return {"final": None, "final_error": f"{type(exc).__name__}: {exc}"}


def _run_loop(run: dict, graph, cfg: dict, stream_input=None, resuming: bool = False) -> None:
    """Drive the graph from either a fresh GraphState or a gate it is already
    parked on, until it ends.

    `resuming=True` is set only by a resumed run (run_worker_resume): the
    gate it's parked on is already open - registry.resume() installed
    run["gate"] from the checkpoint's own pending interrupt before this
    thread was even started (gate_info), and that gate's gate_wait is
    already the last line of the log it was resumed from. So the first
    iteration here must not _drain (nothing new to stream - resuming IS the
    payload) and must not _park (run["gate"] is already right; re-parking
    would overwrite it with a fresh dict and silently drop an "answered"
    flag if an answer had already raced in via POST .../gate, reopening the
    double-answer window bugs.md "gate 4" §1 closed). It only needs to
    _await_answer. Every gate after that first one - whether this run was
    resumed or not - is a brand new pause the graph just produced, and goes
    through the normal _wait_for_gate (_park + _await_answer, in full).
    """
    while True:
        if resuming:
            answer = _await_answer(run)
            resuming = False
        else:
            payload = _drain(run, graph, stream_input, cfg)
            if payload is None:
                result = _close(run, graph, cfg)
                emit(run, "run_done", **result)
                review = ((result.get("final") or {}).get("review")) or {}
                _log_run(run, "run_done", approved=review.get("approved"))
                return
            answer = _wait_for_gate(run, payload)
        if answer is None:
            emit(run, "run_stopped", reason="superseded by a new run")
            _log_run(run, "run_stopped", reason="superseded")
            return
        stream_input = Command(resume=answer)


def _drive(run: dict, on_finish, body) -> None:
    """Shared setup/teardown for both a fresh run and a resumed one: per-run
    fake-LLM scoping, graph/checkpointer lifecycle, error surfacing that
    still saves whatever CV gate 4 already approved, and on_finish."""
    config.set_fake_llm(run["mode"] == "offline")
    checkpointer = graph = cfg = None
    # The agent that has a node_start but hasn't sent its update yet. Set and
    # cleared in _drain_stream; a resumed run starts at a gate, so None.
    run["in_flight"] = None
    try:
        # The run's account, bound on this worker thread before the graph is
        # built (backend/bugs.md "2026-10-09 (design)" §3). Same carrier and the
        # same reason as set_fake_llm above: every node, inline or on a
        # copy_context() pool thread, reads the profile its own run set, never
        # another in-flight run's. Bound here rather than in
        # run_worker/run_worker_resume so a resumed run is scoped identically to
        # a fresh one - the gate it reopens writes to the same vault the first
        # process was writing to. Inside the try, and off run["owner"] with no
        # fallback: a run that somehow has no owner must fail visibly as a
        # run_error, not run on silently with the shared, everyone's-data scope
        # this exists to end, and not die as a thread the UI waits on forever.
        config.set_profile_id(run["owner"])
        graph, checkpointer = _build_graph()
        # The run id is the thread_id, so a paused run is resumable by id — the
        # same contract scripts/run_gated_graph.py drives from the CLI.
        cfg = {"configurable": {"thread_id": run["id"]}, "recursion_limit": config.RECURSION_LIMIT}
        body(graph, cfg)
    except Exception as exc:  # surface the real error, not a generic one
        # `node`: the step that failed, or None when the error came from outside
        # one (Supervisor, a gate, graph build) - frontend used to infer it from
        # whichever step was left "working" (backend/bugs.md "2026-10-14
        # (frontend, Rounds 27-42)" A2).
        fields = {"error": f"{type(exc).__name__}: {exc}", "node": run.get("in_flight")}
        if graph is not None and cfg is not None:
            # A step after gate 4 (evaluation) raising must not lose the CV
            # the human already approved or edited - it's already sitting in
            # the checkpoint, _close just has to read it out (bugs.md
            # 2026-10-09 "gate 4" #2). Before gate 4 there's no review yet:
            # close_run then reads an empty gate_feedback, returns
            # review=None, and saves nothing - same as today. _close already
            # swallows its own failures (final=None, final_error=...), so
            # this can't mask the original error.
            fields.update(_close(run, graph, cfg))
        emit(run, "run_error", **fields)
        _log_run(run, "run_error", error=fields.get("error", ""), node=fields["node"])
    finally:
        run["done"] = True
        if checkpointer is not None:
            try:
                checkpointer.conn.close()
            except Exception:
                pass  # closing a spent connection must not mask a run error
        if on_finish is not None:
            on_finish(run)


def run_worker(run: dict, on_finish=None) -> None:
    """Drive the graph, relaying every gate to the UI. Runs on its own thread."""

    def body(graph, cfg):
        # run_id is what log_state_snapshot names its directory with. Omitted, it
        # falls back to "no_run_id" and every gate of every UI run writes into
        # one shared folder, timestamped to the second, overwriting each other
        # (bugs.md #32).
        # cv_path: the cv_link node raises without one. Resolved by the caller
        # (backend/routes/runs.py) before the run was started - the owner's own
        # uploaded CV, or the shared sample for an admin with none.
        stream_input = GraphState(
            run_id=run["id"],
            # Checkpointed beside the ContextVar set in _drive: the ContextVar is
            # what nodes read, this is what survives the process, so a resume in a
            # new process can restore the scope from the run's own state.
            profile_id=run["owner"],
            job_description=run["job_description"],
            cv_path=run["cv_path"],
        )
        _run_loop(run, graph, cfg, stream_input=stream_input)

    # cv/sample_cv come from the caller's resolved CV (backend/routes/runs.py,
    # backend/cv_store.py) - never the text, only {id, filename} or the sample
    # flag, so this event is safe to persist and replay (design.md "Privacy").
    emit(run, "run_started", cv=run.get("cv"), sample=bool(run.get("sample_cv")))
    _log_run(run, "run_started", mode=run["mode"])
    _drive(run, on_finish, body)


def run_worker_resume(run: dict, on_finish=None) -> None:
    """Pick a run back up at the gate it was parked on when its process died.

    No run_started here - that event is already in the replayed log. `run`
    arrives already rebuilt from the saved log, with run["gate"] already set
    from the checkpoint's own pending interrupt (backend/runs/registry.resume,
    via gate_info) - so this thread's only job for that first gate is to
    _await_answer, not to re-derive or re-announce it.
    """

    def body(graph, cfg):
        _run_loop(run, graph, cfg, resuming=True)

    _drive(run, on_finish, body)


def pending_interrupt(run_id: str) -> dict | None:
    """Read this thread_id's parked interrupt payload straight off the
    checkpointer, without driving anything - the same read
    scripts/run_gated_graph.py's `_pending_interrupt` does for `--thread
    --resume` from the CLI. None if the thread has no pending gate (already
    finished, or never existed).

    Used by registry.resume() when nothing in memory remembers this run: the
    process that was running it is gone, so this is the only place left to
    ask what gate it was on.
    """
    graph, checkpointer = _build_graph()
    try:
        cfg = {"configurable": {"thread_id": run_id}, "recursion_limit": config.RECURSION_LIMIT}
        for task in graph.get_state(cfg).tasks:
            if task.interrupts:
                return task.interrupts[0].value
        return None
    finally:
        try:
            checkpointer.conn.close()
        except Exception:
            pass
