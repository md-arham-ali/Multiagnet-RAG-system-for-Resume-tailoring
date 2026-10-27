"""
The log plane: records *about* what happened, kept apart from every user's
vault (backend/bugs.md "2026-10-09 (design)" §5).

Five kinds are designed for; only `audit` is wired up this round, from
`backend/routes/auth.py` (login, access requests, approve/reject) and
`backend/app.py` (a global handler that logs every 403 automatically, so a
new ownership check doesn't need its own explicit log line to be covered).
`run` needs instrumenting `backend/runs/worker.py` — a separate, larger pass,
deliberately not done here. `llm`/`retrieval`/`system` are written by other
lanes into this same module; also not built here.

Storage: one append-only JSONL file per kind under
`config.BASE_DIR/logs/logplane/<kind>.jsonl`. Append, never rewrite — a log
write is O(1) and a crash mid-write can corrupt at most the last line, never
the history before it. (`backend/jsonstore.py`'s read-modify-write +
atomic-replace pattern is right for a file with a handful of records that
all get rewritten together, like `tokens.json`; it would make every single
log line cost O(n) here, which is the wrong trade for an append-only trail.)

**The rule that makes "admin sees everything" safe: never log secrets or
content.** No token, no API key — log `token_id`/`profile_id` only. No raw
CV, profile, or free-text answer — log the id, never the text. This is what
lets the admin read every line here without the log plane becoming a second,
unprotected copy of every vault. Enforced by convention at each call site
(review before adding a field to any `write()` call above), not scanned for
here — see `_USER_VISIBLE_FIELDS` below for the complementary rule about what
a NON-admin gets to see of their own entries.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config

log = logging.getLogger("backend")

LOG_DIR = config.BASE_DIR / "logs" / "logplane"

KINDS = ("audit", "run", "llm", "retrieval", "system")

MAX_LIMIT = 500

_locks_guard = threading.Lock()
_locks: dict[str, threading.Lock] = {}


def _lock_for(kind: str) -> threading.Lock:
    with _locks_guard:
        lock = _locks.get(kind)
        if lock is None:
            lock = _locks[kind] = threading.Lock()
        return lock


def _path(kind: str) -> Path:
    if kind not in KINDS:
        raise ValueError(f"unknown log kind {kind!r}")
    return LOG_DIR / f"{kind}.jsonl"


def write(kind: str, *, event: str, actor: str, profile_id: str | None = None,
          run_id: str | None = None, fields: dict[str, Any] | None = None,
          critical: bool = False) -> None:
    """Append one entry.

    By default, never raises into the caller's own request — a failed log
    write must not fail the operation it was recording (the same stance
    `backend/routes/profile.py` already takes for a failed vector embed:
    write what matters first, log the side-channel, don't 500 the user over
    the side-channel failing).

    `critical=True` inverts that for the one call site where it must:
    `§2`'s admin cross-vault access ("writes an audit entry first — if that
    audit write fails, access is refused"). There, the log write IS the
    thing being guarded on, so a failure has to re-raise rather than be
    swallowed, or "audited" would be a lie the one time it matters most.
    """
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "event": event,
        "profile_id": profile_id,
        "run_id": run_id,
        "actor": actor,
        "fields": fields or {},
    }
    try:
        # Serialise BEFORE opening anything: an unserialisable field (a
        # caller's mistake, not a disk problem) must leave nothing behind —
        # no directory, no empty file — same as any other failed write.
        # json.dumps as an argument to an already-open file's .write() would
        # create the file first and raise second, which is the wrong order.
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        path = _path(kind)
        with _lock_for(kind):
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line)
    except Exception:
        log.exception("log-plane write failed: kind=%s event=%s", kind, event)
        if critical:
            raise


def _read_all(kind: str) -> list[dict]:
    path = _path(kind)
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # one corrupt line must not take out the whole log
    return out


CURSOR_SEP = "|"


def _positioned(kinds: list[str]) -> list[tuple[str, str, int, dict]]:
    """Every entry across `kinds`, each with a total, stable sort position.

    `(ts, kind, line number)` is unique per entry and identical on every
    request: these files are append-only, so an entry's line never moves, and
    `kinds` is iterated in a fixed order. That totality is what makes the
    cursor below safe — `ts` alone has no way to express "I have already had
    2 of the 3 entries stamped this exact microsecond".
    """
    rows = []
    for kind in kinds:
        for line_no, entry in enumerate(_read_all(kind)):
            rows.append((entry.get("ts", ""), kind, line_no, entry))
    return rows


def _parse_cursor(cursor: str) -> tuple[str, int]:
    """A cursor as `(ts, how many entries at that exact ts were already sent)`.

    Deliberately tolerant: a cursor is an opaque token this module minted, so
    a malformed one is a client error, and degrading to "the start of that
    ts" (possibly re-sending a page) beats raising — this round's whole point
    is that a hand-typed query param can't 500 these routes.
    """
    ts, _, count = (cursor or "").partition(CURSOR_SEP)
    try:
        taken = max(0, int(count))
    except ValueError:
        taken = 0
    return ts, taken


def query(kind: str | None, *, profile_id: str | None = None, run_id: str | None = None,
          event: str | None = None, since: str | None = None, cursor: str | None = None,
          limit: int = 100) -> dict:
    """Entries matching the filters, newest first, paginated.

    `profile_id` is the only filter that enforces isolation — callers decide
    whether to pass it (`for_user()` below always does; the admin route only
    when the admin asks for one account). Every other filter is a
    convenience narrower, not a security boundary, so it is never a
    substitute for `profile_id` when isolation is the point of the call.

    **Paging is on `(ts, count-at-that-ts)`, not `ts` alone**
    (bugs_audit_fixed.md #68 item 3). The old cursor was the last entry's
    `ts` and the next page took `ts < cursor`, which dropped *every*
    remaining entry sharing that timestamp — so a tie group straddling a
    page boundary lost its tail silently, with no short page or error to
    show it. Several entries landing in one microsecond is ordinary here: a
    run writes `node_done` in a tight loop, and `kind=None` merges five
    files whose timestamps are unrelated.

    A cursor is only meaningful against the same filters it was minted
    under; changing `kind`/`profile_id`/`since` mid-walk and reusing it is a
    caller error (the position it names is a position in *that* result set).
    """
    limit = max(1, min(limit, MAX_LIMIT))
    kinds = [kind] if kind else list(KINDS)
    rows = _positioned(kinds)
    if profile_id is not None:
        rows = [r for r in rows if r[3].get("profile_id") == profile_id]
    if run_id is not None:
        rows = [r for r in rows if r[3].get("run_id") == run_id]
    if event is not None:
        rows = [r for r in rows if r[3].get("event") == event]
    if since is not None:
        rows = [r for r in rows if r[0] >= since]
    # Newest first. Reversing the whole key also puts the latest-appended
    # entry first *within* one timestamp, which is the right reading of
    # "newest" for a tie, and makes the order the cursor counts against
    # deterministic rather than a product of read order.
    rows.sort(key=lambda r: (r[0], r[1], r[2]), reverse=True)

    cursor_ts, taken = _parse_cursor(cursor) if cursor is not None else (None, 0)
    if cursor is not None:
        kept, at_cursor_ts = [], 0
        for row in rows:
            if row[0] > cursor_ts:
                continue            # delivered on an earlier page
            if row[0] == cursor_ts:
                at_cursor_ts += 1
                if at_cursor_ts <= taken:
                    continue        # ...and so were these, inside the tie group
            kept.append(row)
        rows = kept

    page = rows[:limit]
    next_cursor = None
    if len(page) == limit:
        last_ts = page[-1][0]
        # Carry the count forward when the page ended inside the same tie
        # group the incoming cursor was already pointing into.
        carried = taken if last_ts == cursor_ts else 0
        next_cursor = f"{last_ts}{CURSOR_SEP}{carried + sum(1 for r in page if r[0] == last_ts)}"
    # A short page does not necessarily mean "no more" if some were hidden by
    # for_user()'s projection after this slice - see its own docstring.
    return {"entries": [r[3] for r in page], "next_cursor": next_cursor}


# event -> the field names inside `fields` a non-admin may see of their OWN
# entry. An event with no entry here is hidden from a non-admin entirely —
# fail closed (§5: "An event type with no allowlist is hidden from users"),
# so a future event type can't leak a field just by being written.
_USER_VISIBLE_FIELDS: dict[str, frozenset[str]] = {
    "login_ok": frozenset(),
    "login_failed": frozenset(),
    "request_access": frozenset(),
    "request_more": frozenset(),
    "request_approved": frozenset(),
    "request_rejected": frozenset(),
    "forbidden": frozenset({"path"}),
    "document_downloaded": frozenset({"fmt"}),
    "document_deleted": frozenset(),
    "run_resumed": frozenset(),
    # The account exported itself. Size only - the zip's contents are this
    # account's own data, and naming them here would duplicate it into the log.
    "account_exported": frozenset({"bytes"}),
    # Deliberately visible, not hidden: a user should be able to see that an
    # admin opened their vault, even though they can't see which admin did
    # it (that's `actor`, which `_project()` never includes) or any content
    # from the access itself.
    "admin_data_access": frozenset({"resource"}),
    # The `run` kind (backend/bugs.md "2026-10-09 (design)" §5): "own run
    # timeline, node durations, gate decisions, error message" are
    # explicitly user-visible; "stack traces, server paths, internal state"
    # are not — none of these fields ever carry that, by construction
    # (worker._log_run only ever passes a node/gate name, a decision, a
    # duration or the short exception-message string already shown on the
    # SSE run_error event, never a traceback or prompt/response text).
    "run_started": frozenset({"mode"}),
    "node_done": frozenset({"node", "duration_s"}),
    "gate_opened": frozenset({"gate"}),
    "gate_decided": frozenset({"gate", "decision"}),
    "run_done": frozenset({"approved"}),
    "run_stopped": frozenset({"reason"}),
    "run_error": frozenset({"error", "node"}),
    "allowance_spent": frozenset(),
    "allowance_refunded": frozenset(),
}


def _project(entry: dict) -> dict | None:
    """The user-safe view of one entry belonging to them, or None if its
    event type has no allowlist. Never includes `actor` — a user's own
    audit view doesn't need to say "admin" did something to their account
    differently from "the system" did; the admin's own unprojected view
    (`query()` directly) already carries it for anyone who needs that."""
    event = entry.get("event")
    allowed = _USER_VISIBLE_FIELDS.get(event)
    if allowed is None:
        return None
    fields = {k: v for k, v in (entry.get("fields") or {}).items() if k in allowed}
    return {"ts": entry["ts"], "kind": entry["kind"], "event": event,
            "run_id": entry.get("run_id"), "fields": fields}


def for_user(profile_id: str, *, kind: str | None = None, run_id: str | None = None,
             since: str | None = None, cursor: str | None = None, limit: int = 100) -> dict:
    """`GET /api/logs/mine`'s data: this account's own entries, projected.

    Filters, then projects — so a page can come back shorter than `limit`
    even when more of this account's entries exist, if some of them are of
    an event type with no user-visible fields. Acceptable for Stage 0 at
    this scale (the admin route, which never projects, is the exhaustive
    view); a client that wants every page filled exactly would need a
    continuation loop, not assumed here.
    """
    result = query(kind, profile_id=profile_id, run_id=run_id, since=since,
                    cursor=cursor, limit=limit)
    projected = [p for e in result["entries"] if (p := _project(e)) is not None]
    return {"entries": projected, "next_cursor": result["next_cursor"]}
