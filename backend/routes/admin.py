"""
Admin cross-vault access: one specific account's own data, for the admin
only (backend/bugs.md "2026-10-09 (design)" §2's last open piece).

Every route here resolves a `Scope` for ANOTHER account — never the caller's
own — and writes an `admin_data_access` audit entry FIRST, refusing access
if that write fails (§2: "Building a scope for another user's vault writes
an admin_data_access audit entry first. If that audit write fails, access
is refused."). `logplane.write(..., critical=True)` is what makes the
refusal real: an ordinary audit write swallows its own failure so a logging
outage can't break the operation it's recording, but here the write IS the
guard, so a failure has to propagate.

An unknown `profile_id` is **404, not 403**: only the admin can reach this
route at all, so refusing a real "not yours" the same way a nonexistent
account is refused leaks nothing (backend/deps.py's status-code note, and
§2: "an unknown profile_id on an admin-only route is 404, since only the
admin can reach it and nothing leaks"). `profiles.display_for()` is both
that existence check AND the input-validation boundary: `profile_id` never
reaches a filesystem path (`cv_store`'s `CV_UPLOADS_DIR/<profile_id>/`)
unless it already matched one of the handful of server-generated
`p-<8hex>` strings this account layer itself minted.

**Deliberately not built here: `GET .../runs`.** `GET /api/runs` already
shows the admin every run with full content, unaudited
(`registry.list_for`) — the design's own open decision D-T2 is whether to
keep that or replace it with an audited, per-account route, and that is a
product decision for the user, not an assumption to make while building
this. Scoping it out keeps this route's two additions (profile, CV) from
quietly deciding D-T2 by default.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend import cv_store, logplane
from backend.auth import profiles
from backend.deps import AdminIdentity, Scope
from backend.routes.profile import visible_entries

router = APIRouter(prefix="/admin/users/{profile_id}")


def _opened_vault(profile_id: str, resource: str) -> Scope:
    """A `Scope` for another account's own vault — `role="user"` always,
    regardless of the caller's own role, since this describes WHOSE data to
    fetch, not who is fetching it (the `AdminIdentity` dependency already
    gates who can reach this route at all). Letting `visible_entries()` see
    `role="admin"` here would make it return *everyone's* entries instead of
    this one account's — the opposite of what a targeted lookup means.
    """
    display = profiles.display_for(profile_id)
    if display is None:
        raise HTTPException(404, "No such account")
    try:
        logplane.write("audit", event="admin_data_access", actor="admin",
                        profile_id=profile_id, fields={"resource": resource}, critical=True)
    except Exception:
        raise HTTPException(503, "Could not record the access audit entry; refusing access")
    return Scope(profile_id=profile_id, role="user")


@router.get("/profile")
def admin_user_profile(profile_id: str, identity: AdminIdentity):
    scope = _opened_vault(profile_id, "profile")
    return {"entries": visible_entries(scope)}


@router.get("/cv")
def admin_user_cv(profile_id: str, identity: AdminIdentity):
    scope = _opened_vault(profile_id, "cv")
    return {"cv": cv_store.current_summary(scope.profile_id)}
