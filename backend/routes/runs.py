"""
Pipeline runs: start, stream, answer a gate, browse the audit trail.

Every route here is ownership-checked. `POST /runs` also spends one run off the
caller's allowance — and must return exactly 403 when exhausted, which is the
status the frontend special-cases into "No runs remaining on your token".

`start_run` depends on `Caller` (`backend/deps.py`) for `profile_id`/`role`,
alongside `Identity` for `token_id` alone — the allowance counter is the
credential's property, not the account's, so it has nowhere to live on
`Scope` (backend/bugs.md "2026-10-09 (design)" §2). The other routes here
still take bare `Identity` and pass it to `registry.owns()`, which already
resolves ownership by `profile_id` internally — they never pull a field off
`identity` themselves, so there's nothing for `Scope` to replace there.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, StringConstraints
from typing import Annotated, Literal

import config
from backend import cv_store, logplane
from backend.auth import store
from backend.deps import Caller, Identity, ScopeError, contained_path, identity_from_query_token
from backend.runs import registry

router = APIRouter(prefix="/runs")


class RunRequest(BaseModel):
    # Bounded on purpose (bugs.md #37). The 2026-08-19 hardening put floors on
    # request-access because it takes no auth; an authenticated route is still a
    # route whose values reach a prompt, a state snapshot and time.sleep.
    # It reaches every agent's prompt, the run log, and every gate's state
    # snapshot at whatever size it arrives.
    job_description: str = Field(min_length=1, max_length=20_000)
    # Literal, same reasoning as GateAnswer.decision (audit #10). mode is only
    # ever compared against "live" and "offline", so a typo'd "Live" skipped the
    # GROQ key check AND left the fake-LLM switch off — an unkeyed billed run off
    # a one-character mistake. Found in passing 2026-08-31, not part of #37.
    mode: Literal["offline", "live"] = "offline"
    # Presentation pacing between events. The worker sleeps this once per node
    # update: negative raises inside the worker after an allowance is already
    # spent, and a large value parks the caller's one run slot (and its sqlite
    # connection) for as long as it likes. 422 at the boundary costs nothing.
    pace_seconds: float = Field(0.8, ge=0, le=5)
    # Optional. A retried POST (network blip, double-submit) with the same id
    # gets its existing run back instead of spending a second allowance and
    # leaving the first run orphaned at its first gate (bugs.md 2026-10-09
    # "Round 8-10" #4). A client that omits it just doesn't get the dedup.
    client_request_id: str | None = Field(None, min_length=8, max_length=64)


# Bounds on one gap answer (bugs.md 2026-10-09 "Round 8-10" #1a) - the same
# reasoning as #37: these values reach the profile_enrich prompt, a state
# snapshot, manual_entries.json and the profile Chroma collection, at
# whatever size they arrive. The frontend's maxLength={2000} is a courtesy,
# not enforcement.
GapKey = Annotated[str, StringConstraints(min_length=1, max_length=200)]
GapText = Annotated[str, StringConstraints(max_length=2000)]


class GateAnswer(BaseModel):
    # Literal: an unknown decision string ("aprove", "cancel") must 422, not
    # silently count as approval — only "reject" was ever checked downstream.
    decision: Literal["approve", "edit", "reject"]
    # Bounded, same reasoning as #37 and gap_answers above (bugs.md
    # 2026-10-09 "gate 4" #4): this reaches the checkpoint, every state
    # snapshot, the gate_done echo (persisted and replayed on every SSE
    # connect), knowledge_base/learning/document/feedback.jsonl and every
    # correction's `reason` on live runs, and will soon reach the Document
    # prompt directly (bugs_audit_fixed.md #55.1) - at whatever size it
    # arrives, since nothing capped it before now.
    feedback: str = Field("", max_length=2000)
    # Gate 2 is the gap interview: human_gate() reads answer["gap_answers"],
    # keyed by requirement, and enrich() looks each answer up by that key.
    # Without this field the dict is always empty, enrich() early-returns and
    # profile_enrich no-ops on every UI run while reporting success — the exact
    # failure the CLI drivers were fixed for on 2026-08-26 (bugs.md #29, #12).
    gap_answers: dict[GapKey, GapText] = Field(default_factory=dict, max_length=20)
    # Gate 4 only, with decision "edit": the candidate's own text of the CV. The
    # gate writes it back as the final document (utils/human_gate._final_edit).
    edited_content: str | None = Field(None, max_length=50_000)
    # The gate this form was answering. A stale or retried POST from an earlier
    # gate's form must not land on whichever gate is open now - a stale gate-3
    # "approve" applied at gate 4 would finalise a CV nobody looked at. Optional,
    # so a client that does not send it keeps working.
    gate: str | None = None


FINAL_GATE = "gate4_document"
GAP_GATE = "gate2_evidence"


def _live_key_problem() -> str | None:
    """Why a live run could not be served, or None (#51).

    This used to be `not config.GROQ_API_KEY`, which asked the wrong question
    in both directions. Every lane happens to end in Groq today, so the check
    was *sufficient* — but it refused a live run that `USE_OPENAI`, or any
    other keyed provider, could have served perfectly well, and it would stop
    being sufficient the moment a lane's last entry changed.

    So ask what `agents/base._live_answer` actually asks: an agent runs if ANY
    entry in its own lane has a key (a keyless provider is skipped, the primary
    included), and raises only when none does. Read off `config` attributes,
    not `os.getenv`, for the same reason `base._has_key` does — that is where a
    provider key can be overridden in-process.
    """
    def key_of(entry: str) -> str | None:
        # A lane entry whose provider has no PROVIDER_KEY row counts as
        # keyless: agents/base._has_key raises ValueError on it, so the run
        # would fail at the first call anyway - better refused here, before an
        # allowance is spent, than mid-run.
        return config.PROVIDER_KEY.get(entry.partition("/")[0])

    stuck = [agent for agent in config.PIPELINE_AGENTS
             if not any(getattr(config, key_of(entry) or "", "")
                        for entry in config.fallback_chain_for(agent))]
    if not stuck:
        return None
    keys = sorted({key for agent in stuck for entry in config.fallback_chain_for(agent)
                   if (key := key_of(entry))})
    fix = f" Set one of {', '.join(keys)} in .env." if keys else ""
    return f"Live mode needs an API key: {', '.join(stuck)} can reach no provider.{fix}"


@router.post("")
def start_run(req: RunRequest, identity: Identity, scope: Caller):
    if req.mode == "live":
        problem = _live_key_problem()
        if problem is not None:
            raise HTTPException(400, problem)

    # Resolve the CV before anything is spent (design.md D-CV2): block a
    # non-admin with none; an admin with none falls back to the shared sample,
    # clearly labelled on the wire (sample=True) rather than silently.
    # scope.profile_id, not identity["token_id"] (backend/bugs.md "2026-10-09
    # (design)" §1 and §2): run/CV ownership belongs to the account, which
    # survives a re-issued token. The allowance counter is still a property
    # of the credential itself (store.consume_run/refund_run key on the
    # token's own id, and a top-up adds to that same token —
    # backend/auth/store.approve_request), so `identity` is kept only for
    # that one purpose rather than folded into `scope`.
    owner = scope.profile_id
    token_id = identity["token_id"]
    resolved = cv_store.resolve_path(owner)
    if resolved is not None:
        cv_path, cv_info, sample_cv = str(resolved[0]), resolved[1], False
    elif scope.role == "admin":
        cv_path, cv_info, sample_cv = str(config.CV_DEFAULT_PATH), None, True
    else:
        raise HTTPException(409, "Add your CV to start a run.")

    # The file has to be there before an allowance is spent (bugs_audit_fixed.md
    # #42): cv_link is the sixth node, so a missing CV surfaced only after
    # jd_analysis, gate 1, profile, gate 2, profile_enrich and matching had run
    # - four LLM calls and two answered gates - as a run_error, and refund_run
    # covers failure to *start* only. 503, never 401/403: nothing is wrong with
    # the caller or their token, the server is missing a file it needs.
    # resolve_path already checks the owner's own upload, so in practice this
    # catches the admin's shared sample CV, which is git-ignored and absent on a
    # fresh clone.
    if not Path(cv_path).is_file():
        raise HTTPException(503, "No CV is configured on the server.")

    # Serialises this owner's starts only (bugs.md 2026-10-09 "Round 8-10"
    # #4): two concurrent POSTs could otherwise both find no in-flight run,
    # both consume an allowance, and both start a worker - the second
    # overwrites the owner's active-run slot, orphaning the first at its
    # first gate. Other owners are never blocked by this lock.
    with registry.owner_lock(owner):
        if req.client_request_id:
            existing = registry.seen(owner, req.client_request_id)
            if existing is not None:
                # A retry of a request already started: hand back the same
                # run rather than spending a second allowance.
                return {"run_id": existing, "cv": cv_info, "sample": sample_cv}

        # Every run costs one, offline or live. 403 exactly — a 401 here
        # would log the user out of the app instead of just refusing the run.
        spent = scope.role != "admin"
        if spent and not store.consume_run(token_id):
            raise HTTPException(403, "No runs remaining")

        try:
            run = registry.start(req.job_description, req.mode, req.pace_seconds, identity,
                                  cv_path=cv_path, cv_info=cv_info, sample_cv=sample_cv)
        except Exception:
            # Nothing ran, so nothing should have been charged.
            if spent:
                store.refund_run(token_id)
                logplane.write("run", event="allowance_refunded", actor="account", profile_id=owner)
            raise
        registry.remember(owner, req.client_request_id, run["id"])
        if spent:
            logplane.write("run", event="allowance_spent", actor="account",
                            profile_id=owner, run_id=run["id"])
    return {"run_id": run["id"], "cv": cv_info, "sample": sample_cv}


@router.get("")
def list_runs(identity: Identity):
    return {"runs": registry.list_for(identity)}


@router.post("/{run_id}/resume")
def resume_run(run_id: str, identity: Identity):
    """Pick a run back up after a server restart lost its in-memory worker
    while it sat parked at a gate (backend/bugs.md "gate 4" §7). Never spends
    a run - the allowance was already charged when this run first started.

    A 403 here is already covered by app.py's global "every 403 is audited"
    handler, so only the success path gets its own logplane write, same as
    download_document just below.
    """
    try:
        run = registry.resume(run_id, identity)
    except KeyError:
        raise HTTPException(404, "Unknown run")
    except PermissionError:
        raise HTTPException(403, "Not your run")
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))
    logplane.write("audit", event="run_resumed", actor="account",
                    profile_id=identity["profile_id"], run_id=run_id)
    return {"run_id": run["id"]}


SSE_KEEPALIVE_SECONDS = 10.0


@router.get("/{run_id}/events")
async def run_events(run_id: str, token: str | None = None):
    """SSE. EventSource cannot set headers, so this one route takes ?token=."""
    identity = identity_from_query_token(token)
    run = registry.get(run_id)
    if not run:
        raise HTTPException(404, "Unknown run")
    if not registry.owns(run, identity):
        raise HTTPException(403, "Not your run")

    async def stream():
        i = 0
        loop = asyncio.get_running_loop()
        last_sent = loop.time()
        while True:
            while i < len(run["events"]):
                yield f"data: {json.dumps(run['events'][i])}\n\n"
                i += 1
                last_sent = loop.time()
            if run["done"]:
                break
            # A node (cv_link on a cold server) can run for a minute and emit nothing.
            # An SSE comment line keeps proxies and clients from timing the stream out
            # (bugs_audit_fixed.md #87); EventSource and the smoke test both skip it.
            if loop.time() - last_sent >= SSE_KEEPALIVE_SECONDS:
                yield ": keepalive\n\n"
                last_sent = loop.time()
            await asyncio.sleep(0.15)

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/{run_id}/gate")
def answer_gate(run_id: str, answer: GateAnswer, identity: Identity):
    run = registry.get(run_id)
    if not run:
        raise HTTPException(404, "Unknown run")
    if not registry.owns(run, identity):
        raise HTTPException(403, "Not your run")
    # Two POSTs can otherwise both pass "a gate is open": one arriving between
    # the other's write and the worker's resume would silently overwrite the
    # first answer, and at the final gate a reject in one tab could override
    # an approve in another while both callers were told 200 (bugs.md
    # 2026-10-09 "gate 4" #1). The lock plus the "answered" flag below close
    # that window; _wait_for_gate builds a fresh `run["gate"]` per pause, so
    # the flag resets by itself at the next gate.
    with run["lock"]:
        open_gate = run["gate"]   # read once: the worker clears it the moment it resumes
        if not open_gate:
            raise HTTPException(409, "No gate is waiting on this run")
        if open_gate.get("answered"):
            raise HTTPException(409, "This review was already answered")
        if answer.gate is not None and answer.gate != open_gate["gate"]:
            raise HTTPException(409, "This review is no longer open - the run has moved on")
        if answer.edited_content is not None and (open_gate["gate"] != FINAL_GATE or answer.decision != "edit"):
            raise HTTPException(422, "edited_content is only accepted with an 'edit' at the final review")
        if answer.gap_answers:
            # Nothing server-side held this line until now: the frontend only
            # ever sends gap_answers at gate 2, but a client that doesn't
            # follow that (curl, the smoke script, a retried stale form) was
            # never refused, and a mismatched key would reach enrich() as a
            # near-duplicate "QUESTION: No question found" block (bugs.md
            # 2026-10-09 "Round 8-10" #1b).
            if open_gate["gate"] != GAP_GATE:
                raise HTTPException(422, "gap_answers are only accepted at the evidence-gap gate")
            known = {q.get("requirement") for q in open_gate.get("gap_questions", [])}
            unknown = sorted(set(answer.gap_answers) - known)
            if unknown:
                raise HTTPException(422, f"Unknown gap_answers key(s): {unknown}")
        run["gate_answer"] = {
            "decision": answer.decision,
            "feedback": answer.feedback,
            # A rejected round loops back and reopens the same gate; stale
            # answers must not ride along into the next round just because
            # the graph stores whatever it's handed regardless of decision
            # (bugs.md #1c). The frontend already sends {} on reject for this
            # reason, but that rule shouldn't live in only one client.
            "gap_answers": {} if answer.decision == "reject" else answer.gap_answers,
        }
        if answer.edited_content is not None:
            run["gate_answer"]["edited_payload"] = {"content": answer.edited_content}
        open_gate["answered"] = True
    run["gate_event"].set()
    return {"ok": True}


_EXPORT_TYPES = {"md": "text/markdown; charset=utf-8", "txt": "text/plain; charset=utf-8"}


def _audit_document(event: str, owner: str | None, identity: dict, run_id: str,
                    **fields) -> None:
    """Audit a saved-document action against the document's OWNER, never the
    caller (bugs_audit_fixed.md #68 item 4).

    `registry.owns()` lets any admin through, so both routes below can act on
    a document belonging to someone else. Logging `identity["profile_id"]`
    put the entry in the admin's own trail and nowhere else: the owner's
    `GET /api/logs/mine` never showed that their CV had been downloaded - or
    deleted - and `GET /api/admin/logs?profile_id=<owner>` could not find it
    either, which is the one lookup an audit trail keyed on accounts exists
    to answer.

    `actor` follows the split `routes/admin.py` already uses for
    `admin_data_access`: "admin" when the caller is not the owner, so the
    entry doesn't claim the account did it to itself. One helper for both
    call sites on purpose - two independently-written `logplane.write` calls
    with the same attribution rule is how the three `AGENTS`/`GATES`/
    `STUB_NODES` tables drifted from the graph.

    `owner` is None only for a run log written before ownership existed.
    Those are admin-visible only (`registry.owns`), so there is no account to
    attribute to and `profile_id: None` is the honest record. A pre-10-10 log
    carries a `token_id` there rather than a `profile_id`; that is the same
    string `owns()` itself decides ownership by, so this stays consistent
    with it either way.
    """
    logplane.write("audit", event=event,
                   actor="account" if owner == identity.get("profile_id") else "admin",
                   profile_id=owner, run_id=run_id, fields=fields or None)


@router.get("/{run_id}/document")
def download_document(run_id: str, identity: Identity, fmt: Literal["md", "txt"] = "md"):
    """The CV this run saved at its final review (Stage 0 plan §16), owner-checked.

    The file path comes from the run's own run_done (or run_error, if a step
    after gate 4 failed - "gate 4" §2 - registry.current_export reads
    either) event, never from the request, and must resolve inside
    OUTPUTS_DIR. 404 when nothing was saved: the run is unfinished, or its
    last draft was rejected at the revision cap.
    """
    record = registry.get(run_id) or registry.load_log(run_id)
    if record is None:
        raise HTTPException(404, "Unknown run")
    if not registry.owns(record, identity):
        raise HTTPException(403, "Not your run")
    export = registry.current_export(record)
    if fmt not in export:
        raise HTTPException(404, "No saved document for this run: it is unfinished, or the final review did not approve one")
    try:
        # Same contained_path() the path-traversal fix in registry.load_log
        # uses, not a second independently-maintained resolve()+check — this
        # one was already safe (export[fmt] is server-generated, never from
        # the request), but two copies of the same containment logic is
        # exactly how it drifts (backend/bugs.md "2026-10-09 (design)" §2).
        path = contained_path(config.OUTPUTS_DIR, export[fmt])
    except ScopeError:
        raise HTTPException(404, "The saved document is missing on the server")
    if not path.is_file():
        raise HTTPException(404, "The saved document is missing on the server")
    _audit_document("document_downloaded", record.get("owner"), identity, run_id, fmt=fmt)
    return FileResponse(path, media_type=_EXPORT_TYPES[fmt], filename=path.name)


@router.delete("/{run_id}/document", status_code=204)
def delete_document(run_id: str, identity: Identity):
    """Delete a run's saved CV, both formats (backend/bugs.md "gate 4" §5c).
    After this, GET .../document 404s the same way it would for a run that
    never saved one - "deleted" and "never existed" are indistinguishable on
    the wire, on purpose, same as every other not-found here."""
    try:
        # Returns the owner so the audit entry lands on the right account
        # without this route re-reading the run log to find out who that was.
        owner = registry.delete_document(run_id, identity)
    except KeyError:
        raise HTTPException(404, "Unknown run")
    except PermissionError:
        raise HTTPException(403, "Not your run")
    except RuntimeError as exc:
        raise HTTPException(404, str(exc))
    _audit_document("document_deleted", owner, identity, run_id)


@router.get("/{run_id}/log")
def run_log(run_id: str, identity: Identity):
    data = registry.load_log(run_id)
    if data is None:
        raise HTTPException(404, "Unknown run")
    if not registry.owns(data, identity):
        raise HTTPException(403, "Not your run")
    return data
