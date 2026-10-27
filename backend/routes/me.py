"""
The caller's own data, as one zip (design "2026-10-09 (design)" §6, D-T6).

Everything here is the account's own: built from `scope.profile_id` and
nothing else in the request. The one deliberate subtlety is that an **admin
exporting itself gets only its own data** - `visible_entries` and
`registry.owns()` both widen for role "admin", which is right for an admin
tool and wrong for "export my account", so this route builds a `Scope` with
role "user" over its own `profile_id`, the same move `routes/admin.py` makes
for the opposite reason (there it narrows an admin to one user's vault; here
it narrows the admin to its own).

Read-only. The destructive half of §6 - deleting an account - is NOT here:
step 3 of that plan is "drop its collection", and there are no per-profile
collections yet, nor a `VectorStore.delete` to remove an account's rows from
the shared `profile` one. Deleting everything else while the user's embedded
evidence stayed searchable would be a deletion that lies, so it waits for the
KB lane (`bugs_audit_fixed.md` #30's open half).

No secret ever enters the zip: not the bearer token, not an API key. The
account file carries the account's own ids and counts, which the caller
already sees on `/auth/me`.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

import config
from backend import cv_store, logplane
from backend.deps import Caller, Identity, Scope, ScopeError, contained_path
from backend.routes.profile import visible_entries
from backend.runs import registry

router = APIRouter(prefix="/me")

# A zip is built in memory, so it has to have a ceiling: CV PDFs are capped at
# 5 MB each (routes/cv.py) and nothing else here is large, but a long-lived
# account with many saved CVs should fail loudly rather than take the process
# down. 413 is the same answer an oversized upload gets.
MAX_EXPORT_BYTES = 64 * 1024 * 1024


def _own_scope(scope: Scope) -> Scope:
    """This account, as a plain user - see the module docstring."""
    return Scope(profile_id=scope.profile_id, role="user")


def _add(zf: zipfile.ZipFile, name: str, data: bytes, budget: list[int]) -> None:
    budget[0] += len(data)
    if budget[0] > MAX_EXPORT_BYTES:
        raise HTTPException(413, "This account's data is too large to export in one file.")
    zf.writestr(name, data)


def _json_bytes(value) -> bytes:
    return json.dumps(value, indent=2, ensure_ascii=False, default=str).encode("utf-8")


@router.get("/export")
def export_account(scope: Caller, identity: Identity):
    """Everything this account owns, as `application/zip`."""
    own = _own_scope(scope)
    budget = [0]
    buf = io.BytesIO()
    when = datetime.now(timezone.utc)

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        _add(zf, "account.json", _json_bytes({
            "profile_id": scope.profile_id,
            "identifier": identity["identifier"],
            "role": identity["role"],
            "runs_remaining": identity.get("runs_remaining"),
            "exported_at": when.isoformat(),
        }), budget)

        # Build Profile entries, this account's own only.
        _add(zf, "profile_entries.json", _json_bytes(visible_entries(own)), budget)

        # The CV index and every PDF still on disk under it.
        index = cv_store.export_index(scope.profile_id)
        if index:
            _add(zf, "cv/index.json", _json_bytes(index), budget)
            for name, data in cv_store.export_files(scope.profile_id):
                _add(zf, f"cv/{name}", data, budget)

        # Run trails this account owns, and the CVs saved out of them. The
        # export paths come from each run's own record (registry.current_export),
        # not from guessing the outputs folder's name for this owner.
        for record in registry.records_for_owner(scope.profile_id):
            run_id = record.get("id") or "unknown"
            _add(zf, f"runs/{run_id}.json", _json_bytes(record), budget)
            for fmt, relative in (registry.current_export(record) or {}).items():
                try:
                    path = contained_path(config.OUTPUTS_DIR, str(relative))
                except ScopeError:
                    continue  # a record naming a path outside OUTPUTS_DIR is not exported
                if path.is_file():
                    _add(zf, f"documents/{path.name}", path.read_bytes(), budget)

        # The account's own audit trail, exactly as /logs/mine projects it:
        # no `actor`, no content, nothing another account can be read out of.
        _add(zf, "logs.json", _json_bytes(logplane.for_user(scope.profile_id, limit=10_000)), budget)

    logplane.write("audit", event="account_exported", actor="account",
                    profile_id=scope.profile_id, fields={"bytes": budget[0]})
    filename = f"export_{scope.profile_id}_{when:%Y-%m-%d}.zip"
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
