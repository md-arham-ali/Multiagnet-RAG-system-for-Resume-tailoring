"""
The log plane, read-only (backend/bugs.md "2026-10-09 (design)" §5).

`/logs/mine` is every authenticated caller's own, server-projected view —
`backend/logplane.for_user()` strips every field with no allowlisted entry
for that event type before this route ever sees it, so there is nothing left
here to accidentally leak by passing the wrong thing through. `/admin/logs`
is unprojected and admin-only (403, never 401, for anyone else — the same
discipline as every other admin route in this package).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend import logplane
from backend.deps import AdminIdentity, Caller

router = APIRouter()


def _checked_kind(kind: str | None) -> str | None:
    """`kind` validated at the boundary, or 400 (bugs_audit_fixed.md #68 item 3).

    `logplane._path()` raises `ValueError` on an unknown kind, which escaped
    both routes uncaught as a **500** for what is plainly a bad query param.
    400 rather than an empty result: "no such kind" and "you have no entries
    of that kind" are different answers, and silently returning the second
    for the first hides a client's typo. 400 rather than 404 because the
    route exists and it is the argument that doesn't, and never 401/403 —
    `deps.py`'s discipline reserves those, and a 401 would sign the caller
    out over a typo.

    Validated here, not as a FastAPI `Literal` on the signature: these two
    functions are also called directly (by tests, and anything in-process),
    where annotations do no validating at all, so the guard has to be in the
    body to actually hold.
    """
    if kind is not None and kind not in logplane.KINDS:
        raise HTTPException(400, f"Unknown log kind {kind!r}. "
                                 f"Expected one of: {', '.join(logplane.KINDS)}.")
    return kind


@router.get("/logs/mine")
def logs_mine(scope: Caller, kind: str | None = None, run_id: str | None = None,
              since: str | None = None, cursor: str | None = None, limit: int = 100):
    return logplane.for_user(scope.profile_id, kind=_checked_kind(kind), run_id=run_id,
                              since=since, cursor=cursor, limit=limit)


@router.get("/admin/logs")
def admin_logs(identity: AdminIdentity, kind: str | None = None, profile_id: str | None = None,
                run_id: str | None = None, event: str | None = None, since: str | None = None,
                cursor: str | None = None, limit: int = 100):
    return logplane.query(_checked_kind(kind), profile_id=profile_id, run_id=run_id,
                           event=event, since=since, cursor=cursor, limit=limit)
