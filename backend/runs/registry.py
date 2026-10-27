"""
Run records, per-owner run slots, and ownership.

The bridge used to hold ONE `_active_run` for the whole process, so any new run
superseded whichever run happened to be in flight — regardless of who started
it. With real identities that is wrong: one user's run must never abort
another's. Runs are now slotted per owner (`profile_id`).

`profile_id`, not `token_id` (backend/bugs.md "2026-10-09 (design)" §1,
built 2026-10-10): a re-issued token is a new `token_id` for the same
account, and keying ownership off it would silently orphan that account's
own in-flight runs and run history the moment its token is replaced.
`token_id` still rides on every run record, but only for audit — never for
an `owns()`/`_active` lookup.

Ownership failures are 403, never 404 or 401 — see backend/deps.py for why.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timezone

import config
from backend.auth.store import ADMIN_TOKEN_ID
from backend.deps import ScopeError, contained_path
from backend.jsonstore import read_json, update_json, write_json
from backend.runs.worker import gate_info, pending_interrupt, run_worker, run_worker_resume

log = logging.getLogger("backend")

_LOCK = threading.RLock()
_runs: dict[str, dict] = {}          # run_id -> run record (in-memory, this process)
_active: dict[str, dict] = {}        # owner profile_id -> that owner's in-flight run

# In-memory runs are pruned past this; every run is on disk regardless, so the
# only thing lost is live SSE replay of a long-finished run.
MAX_RETAINED = 50

# Fallback for a resumed run whose log predates save_log() persisting `pace`
# (below). Same default RunRequest.pace_seconds uses.
_DEFAULT_PACE = 0.8

# A log's event trail is parked, not finished, when its last event is this -
# see save_log()'s new call inside worker._park (bugs.md "gate 4" §7). Any
# other type as the last line means the process died mid-stream somewhere
# that was never a gate; resume() will find no pending interrupt for those
# and refuse, same as it would for an unknown thread_id.
_PARKED_LAST_EVENT = "gate_wait"

# Terminal event type -> this run's outcome, for list_for's summary. Before
# this, "completed: any(type == run_done)" collapsed a crash and a
# supersede into the same "false" - the Runs list and Account page showed
# both identically, in red, as "stopped" (bugs.md "2026-10-08" §5 /
# "Round 8-10" §7: "an errored run is indistinguishable from a cancelled
# one"). None for a run still in progress, including one merely parked at
# an open gate - that's `interrupted` above, not an outcome.
_OUTCOME = {"run_done": "done", "run_error": "error", "run_stopped": "stopped"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log_path(run_id: str):
    # run_id is server-generated (uuid4().hex[:8]) at every call site that
    # writes - save_log() below only ever receives its own run["id"]. It is
    # NOT trusted here: load_log() is also reached with run_id straight off
    # the URL (GET /runs/{id}/log, /document), so the containment check has
    # to live where the untrusted value actually enters, not rely on every
    # future caller remembering to pre-validate it.
    return config.RUNS_DIR / f"{run_id}.json"


def save_log(run: dict) -> None:
    """Persist the run's event trail. Atomic — a crash mid-write kept the old
    file intact rather than truncating the audit trail (it used to be a bare
    write_text).

    Called from inside a gate now, not only at the end (worker._persist, for
    "gate 4" §7's restart survival) - `pace` is included so a run resumed
    from one of those mid-run writes keeps its original presentation pacing
    instead of silently falling back to _DEFAULT_PACE. Read with .get(), not
    the hard `run[k]` every other field here uses: unlike those, "pace" is
    allowed to be absent on a run dict a caller built by hand (tests do),
    since resume() already tolerates a log that predates this field.
    """
    data = {k: run[k] for k in
            ("id", "job_description", "mode", "started", "owner", "token_id", "cv", "sample_cv", "events")}
    data["pace"] = run.get("pace", _DEFAULT_PACE)
    write_json(_log_path(run["id"]), data)


def load_log(run_id: str) -> dict | None:
    """None for an unknown run_id - including a crafted one, and a damaged one.

    Before this, a run_id like "../../../etc/passwd" resolved straight
    through to config.RUNS_DIR/"../../../etc/passwd.json", outside RUNS_DIR
    entirely (backend/bugs.md "2026-10-09 (design)" §2: "a crafted run_id or
    cv_id cannot climb out" - confirmed exploitable before this fix, not
    hypothetical). An admin caller's `owns()` check passes regardless of a
    record's content, so this was a real arbitrary-*.json-read for that
    role, not just for the run's own owner. contained_path() raising is
    treated the same as "file not found" - the two are indistinguishable to
    a caller either way.

    A file that is not a readable JSON **object** reads as unknown too
    (bugs_audit_fixed.md #68 item 6). `read_json` turns an empty or
    whitespace-only file into its `default` - which is `[]`, not None, since
    `default is None` means "a new list" there - and a truncated one raises
    `JSONDecodeError`. Both used to reach `owns()`, where an admin passes the
    role check and `[].get(...)` is an `AttributeError`, and the raise was
    never caught either: a **500** on `/runs/{id}/log` and `/document` for a
    damaged file, not for a bad request. `list_for()` already skipped both,
    so two readers of the same file disagreed about whether it existed.

    "Unknown" rather than a 5xx: the caller can do nothing about a
    half-written file, and a 404 says exactly what the admin's own Runs list
    already says about it. Logged rather than silent, so the file stays
    findable by whoever can repair or delete it.
    """
    try:
        path = contained_path(config.RUNS_DIR, f"{run_id}.json")
    except ScopeError:
        return None
    if not path.exists():
        return None
    try:
        data = read_json(path, default=None)
    except (ValueError, OSError) as exc:   # JSONDecodeError/UnicodeDecodeError are ValueErrors
        log.warning("run log %s is unreadable (%s); treating it as unknown",
                    path.name, type(exc).__name__)
        return None
    if not isinstance(data, dict):
        log.warning("run log %s holds %s, not a JSON object; treating it as unknown",
                    path.name, type(data).__name__)
        return None
    return data


def owns(record: dict | None, identity: dict) -> bool:
    """Admin sees everything. Otherwise the owner must match.

    Run logs written before ownership existed have no `owner` key: those are
    admin-visible only, rather than crashing or leaking to whoever asks.
    Compares against `profile_id`, not `token_id` — a run started before a
    re-issued token is still this account's run after the reissue.
    """
    if record is None:
        return False
    if identity["role"] == "admin":
        return True
    return record.get("owner") == identity["profile_id"]


def get(run_id: str) -> dict | None:
    return _runs.get(run_id)


# A run's `final` block ({review, export, learning}) lands on run_done when
# the graph ends cleanly, but on run_error too the moment anything after
# gate 4 fails (worker._drive's except calls the same _close()) - a step
# failing after an approved CV must not lose it (bugs.md "gate 4" §2). A
# reader that only ever checked run_done saw such a run as unreviewed and
# unsaved (backend/bugs.md "2026-10-14 (frontend, Rounds 27-42)" A1) even
# though the file was sitting on disk the whole time.
_TERMINAL_WITH_FINAL = ("run_done", "run_error")


def _find_final_event(events: list[dict]) -> dict | None:
    """The run_done or run_error event carrying this run's `final` block,
    whichever one actually fired."""
    return next((e for e in reversed(events) if e.get("type") in _TERMINAL_WITH_FINAL), None)


def current_export(record: dict) -> dict:
    """This run's saved-CV export paths (`{"md": ..., "txt": ...}`, relative
    to `OUTPUTS_DIR`), or `{}` if nothing was ever saved. The one place this
    is read from, shared by list_for, delete_document and
    routes/runs.py's download_document - a second, independently
    maintained copy of this lookup is exactly how A1 (above) happened in
    the first place: one reader fixed, two others still only checking
    run_done."""
    done = _find_final_event(record.get("events", []))
    return ((done or {}).get("final") or {}).get("export") or {}


def _strip_export(events: list[dict]) -> bool:
    """Null out the export on whichever terminal event carries it, in
    place. True if there was one to strip (the caller only wants to write
    when something actually changed)."""
    done = _find_final_event(events)
    if done is None or not (done.get("final") or {}).get("export"):
        return False
    final = {**done.get("final", {}), "export": None, "export_deleted_at": _now()}
    done["final"] = final
    return True


def delete_document(run_id: str, identity: dict) -> str | None:
    """Delete a run's saved CV (both .md and .txt) and null out the export on
    its run_done event - in memory (if a record is still live) and on disk.

    Design: backend/bugs.md "gate 4" §5c. Raises KeyError (unknown run),
    PermissionError (not the caller's), or RuntimeError (nothing saved to
    delete) - routes/runs.py maps these to 404/403/404.

    Returns the run's `owner` (None for a log predating ownership) so the
    caller can audit the deletion against the account whose document it was
    rather than whoever asked - an admin may delete anyone's (bugs_audit_fixed.md
    #68 item 4). Returned rather than re-looked-up in the route: the record is
    already in hand here, and a second read could disagree with the one the
    ownership check actually passed.
    """
    record = get(run_id) or load_log(run_id)
    if record is None:
        raise KeyError("Unknown run")
    if not owns(record, identity):
        raise PermissionError("Not your run")

    export = current_export(record)
    if not export:
        raise RuntimeError("No saved document for this run")

    for rel in export.values():
        try:
            path = contained_path(config.OUTPUTS_DIR, rel)
        except ScopeError:
            continue  # already not a real file under OUTPUTS_DIR - nothing to unlink
        path.unlink(missing_ok=True)

    live = get(run_id)
    if live is not None:
        _strip_export(live.get("events", []))

    def _clear(data):
        if not data or not _strip_export(data.get("events", [])):
            return None, None  # no write: nothing on disk to change
        return data, None

    update_json(_log_path(run_id), _clear, default=None)
    return record.get("owner")


def abort(run: dict) -> None:
    """Unblock a run parked on a gate so its worker thread can exit.

    Its own flag, not a fake "reject" answer: since the graph owns gating a
    reject no longer ends a run, it sends the work back to the agent that
    produced the artifact (bugs.md #10), so answering one would keep the
    superseded run alive instead of retiring it.
    """
    run["aborted"] = True
    run["gate_event"].set()


def _prune() -> None:
    finished = [r for r in _runs.values() if r.get("done")]
    for stale in sorted(finished, key=lambda r: r["started"])[: max(0, len(finished) - MAX_RETAINED)]:
        _runs.pop(stale["id"], None)


# start() itself reads _active[owner], releases _LOCK, aborts + joins the old
# run, then re-takes _LOCK to install the new one. Two concurrent starts from
# ONE owner can both read the same "previous" run and both proceed: the
# second overwrites _active[owner], so the first is never aborted - it keeps
# running, parked at its first gate forever, still holding a worker thread and
# a sqlite connection, and in live mode still spending quota (bugs.md
# 2026-10-09 "Round 8-10" #4b - "a real bug, not a UX nicety"). owner_lock
# serialises start() per owner, which closes that window; other owners are
# never blocked by it.
_OWNER_LOCKS_GUARD = threading.Lock()
_owner_locks: dict[str, threading.Lock] = {}


def owner_lock(owner: str) -> threading.Lock:
    """The lock that serialises start() for this one owner, created once."""
    with _OWNER_LOCKS_GUARD:
        lock = _owner_locks.get(owner)
        if lock is None:
            lock = _owner_locks[owner] = threading.Lock()
        return lock


# (owner, client_request_id) -> (run_id, seen_at). Lets a retried POST /runs
# (a network blip, a double-submit before the frontend's in-flight guard
# mounts) get its own run back instead of spending a second allowance -
# bugs.md #4a. Kept only long enough to catch a genuine retry, not as a
# permanent index.
_SEEN_LOCK = threading.Lock()
_SEEN_TTL_SECONDS = 600
_seen: dict[tuple[str, str], tuple[str, float]] = {}


def seen(owner: str, client_request_id: str) -> str | None:
    """The run_id already started for this (owner, client_request_id), if any
    and not yet expired."""
    key = (owner, client_request_id)
    with _SEEN_LOCK:
        entry = _seen.get(key)
        if entry is None:
            return None
        run_id, ts = entry
        if time.monotonic() - ts > _SEEN_TTL_SECONDS:
            _seen.pop(key, None)
            return None
        return run_id


def remember(owner: str, client_request_id: str | None, run_id: str) -> None:
    """Record that this request id started run_id, for seen() to find."""
    if not client_request_id:
        return
    now = time.monotonic()
    with _SEEN_LOCK:
        _seen[(owner, client_request_id)] = (run_id, now)
        # Opportunistic prune, so a long-lived process doesn't accumulate one
        # entry per request forever from clients that never retry.
        stale = [k for k, (_, seen_ts) in _seen.items() if now - seen_ts > _SEEN_TTL_SECONDS]
        for k in stale:
            _seen.pop(k, None)


def start(job_description: str, mode: str, pace: float, identity: dict,
          cv_path: str, cv_info: dict | None, sample_cv: bool) -> dict:
    """Create + start a run for this owner, superseding only their own.

    cv_path/cv_info/sample_cv come from the caller (backend/routes/runs.py),
    which resolves the owner's current uploaded CV - or, for an admin with
    none, the shared sample (design.md D-CV2) - before any allowance is spent.
    """
    owner = identity["profile_id"]

    with _LOCK:
        previous = _active.get(owner)
    if previous and not previous["done"]:
        abort(previous)
        # Wait for the old worker to actually exit before starting the new one,
        # so one owner never has two live runs writing to the same slot.
        thread = previous.get("thread")
        if thread is not None:
            thread.join(timeout=15)

    run = {
        "id": uuid.uuid4().hex[:8],
        "job_description": job_description,
        "mode": mode,
        "pace": pace,
        "started": _now(),
        "owner": owner,
        # Audit only - never compare against this for ownership (owns()
        # above compares "owner", which is profile_id).
        "token_id": identity["token_id"],
        "cv_path": cv_path,
        "cv": cv_info,
        "sample_cv": sample_cv,
        "events": [],
        "gate": None,
        # Serialises answer_gate against itself for this run, so two racing
        # POSTs to one open gate can't both be accepted (bugs.md 2026-10-09
        # "gate 4" #1) - at the final gate that let a reject in one tab
        # silently override an approve in another.
        "lock": threading.Lock(),
        "gate_event": threading.Event(),
        "gate_answer": None,
        "aborted": False,
        "done": False,
    }
    with _LOCK:
        _runs[run["id"]] = run
        _active[owner] = run
        _prune()

    run["thread"] = threading.Thread(
        target=run_worker, args=(run,), kwargs={"on_finish": save_log}, daemon=True
    )
    run["thread"].start()
    return run


def resume(run_id: str, identity: dict) -> dict:
    """Rebuild a run parked at a gate whose process died, and restart its
    worker from exactly that gate.

    Design: backend/bugs.md "gate 4" §7. Never charges a run - the allowance
    was already spent when this run first started; this only picks the same
    run back up. Raises KeyError (unknown run), PermissionError (not the
    caller's), or RuntimeError (nothing to resume: a worker already owns this
    id, another of this owner's runs is active, or the run isn't actually
    parked at a gate) - routes/runs.py maps these to 404/403/409.

    load_log()/owns() run unlocked first (pure reads, same as every other
    route here) so an unknown or not-mine run_id fails fast without ever
    touching a lock. Everything that can actually change in-memory state -
    the "is something already driving this" checks, the graph read, and the
    new run's registration - happens under owner_lock(owner), the same lock
    start() is always called under (routes/runs.py). Without that, a
    resume() racing a concurrent start() for the same owner could read
    _active[owner] as empty, spend the ~20s pending_interrupt() graph read,
    and only then install itself into _active - silently clobbering a run
    that start() had installed there in the meantime, orphaning it exactly
    the way "Round 8-10" #4b already described for two concurrent starts.
    """
    data = load_log(run_id)
    if data is None:
        raise KeyError("Unknown run")
    if not owns(data, identity):
        raise PermissionError("Not your run")

    owner = data.get("owner")
    if owner is None:
        # A log from before per-owner slots existed. Resuming it would have
        # no _active slot to hold it in, and no caller could pass owns()
        # against it going forward either - nothing to attach the resumed
        # run to.
        raise RuntimeError("This run predates ownership and cannot be resumed")

    with owner_lock(owner):
        with _LOCK:
            live = _runs.get(run_id)
            current = _active.get(owner)
        if live is not None and not live.get("done"):
            raise RuntimeError("A worker is already driving this run")
        if current is not None and not current.get("done") and current["id"] != run_id:
            raise RuntimeError("Another run is already active for this owner")

        payload = pending_interrupt(run_id)
        if payload is None:
            raise RuntimeError("This run is not parked at a gate")
        # Computed and installed before the worker thread exists, let alone
        # runs - so POST .../gate is answerable the instant this call
        # returns, rather than only once that thread gets scheduled and
        # reaches this same computation itself (which, on the first run
        # since a restart, is the ~20s embedding-model cold start). See
        # gate_info's own docstring and _run_loop's `resuming` branch, which
        # is what makes re-deriving it a second time here safe to skip.
        gate = gate_info(payload)

        run = {
            **{k: data.get(k) for k in
               ("id", "job_description", "mode", "started", "owner", "token_id", "cv", "sample_cv")},
            "pace": data.get("pace", _DEFAULT_PACE),
            "events": list(data.get("events", [])),
            "gate": gate,
            "lock": threading.Lock(),
            "gate_event": threading.Event(),
            "gate_answer": None,
            "aborted": False,
            "done": False,
        }
        with _LOCK:
            _runs[run["id"]] = run
            _active[owner] = run
            _prune()

        run["thread"] = threading.Thread(
            target=run_worker_resume, args=(run,), kwargs={"on_finish": save_log}, daemon=True
        )
        run["thread"].start()
        return run


def records_for_owner(profile_id: str) -> list[dict]:
    """Every saved run record owned by exactly this account, newest first.

    Not `list_for`: that one answers "what may this caller see", which widens
    for an admin and returns summaries. This answers "what belongs to this
    account", which is what an account's own export needs - an admin exporting
    itself must get its own runs, not everyone's - and it returns the whole
    record, trail included. Reads through `load_log`, so a damaged file is
    skipped here exactly as it is everywhere else (#68 item 6).

    An ownerless (pre-2026-10-10) log belongs to nobody resolvable and is
    never exported: it would otherwise land in the first account that asked.
    """
    if not profile_id:
        return []
    records = []
    config.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    for path in config.RUNS_DIR.glob("*.json"):
        data = load_log(path.stem)
        if data is not None and data.get("owner") == profile_id:
            records.append(data)
    records.sort(key=lambda r: r.get("started") or "", reverse=True)
    return records


def list_for(identity: dict) -> list[dict]:
    """Summaries of saved runs this identity may see, newest first.

    One endpoint serves both the admin Runs view (everything) and the Account
    page (your own) — the filtering has to be right here, there is no separate
    'my runs' route.
    """
    runs = []
    config.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    for path in config.RUNS_DIR.glob("*.json"):
        # Through load_log(), not a reader of its own: this list already
        # tolerated a corrupt file while `/log` 500'd on the same one (#68
        # item 6), and its own `if not data` still let a non-empty non-dict
        # log reach owns(), where an admin passes the role check and
        # `data.get` then raises. One tolerant reader, one verdict.
        data = load_log(path.stem)
        if data is None or not owns(data, identity):
            continue
        events = data.get("events", [])
        live = _runs.get(data.get("id"))
        last_type = events[-1].get("type") if events else None
        done = _find_final_event(events)
        final = (done or {}).get("final") or {}
        runs.append(
            {
                "id": data.get("id", path.stem),
                "started": data.get("started"),
                "mode": data.get("mode"),
                "job_description": (data.get("job_description") or "")[:120],
                "events": len(events),
                "completed": any(e.get("type") == "run_done" for e in events),
                "cv": data.get("cv"),
                "sample_cv": data.get("sample_cv", False),
                # null for a run that never reached gate 4 - RunsView/Account
                # use this (and "saved" below) to show a review verdict and a
                # download/delete per row (bugs.md "gate 4" §5b) instead of
                # making a client open every run's full log just to find out.
                "review": final.get("review"),
                "saved": bool((final.get("export") or {}).get("md")),
                # "done" | "stopped" | "error" | null (still in progress).
                # Additive alongside `completed`, which stays exactly what
                # it already was - a second, more honest field, not a
                # replacement for the first.
                "outcome": _OUTCOME.get(last_type),
                # True only for a gate parked by a worker that is no longer
                # running it - a worker still holding this run in memory is
                # not "interrupted", it's just slow to be answered (bugs.md
                # "gate 4" §7). RunsView/Account show a Resume action on this.
                "interrupted": last_type == _PARKED_LAST_EVENT and (live is None or live["done"]),
            }
        )
    # Sort the content, not the container. A run's filename IS its id
    # (uuid4().hex[:8]), so reverse-lexicographic order over random hex is
    # random order — and this list is the one screen whose job is chronology
    # (bugs.md #31). `started` is ISO-8601 and sorts correctly as a string.
    runs.sort(key=lambda r: r.get("started") or "", reverse=True)
    return runs
