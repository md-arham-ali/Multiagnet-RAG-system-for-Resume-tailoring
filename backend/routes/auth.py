"""
Access-token lifecycle: request -> admin approves -> token -> login.

Response shapes are fixed by the frontend that already consumes them; see
backend/bugs.md "Routes" for the table. In particular `runs_remaining` must be
null for admin, and /auth/requests must return ALL requests (the admin UI does
its own pending/resolved split).

Every route here writes an `audit` log-plane entry (backend/logplane.py,
backend/bugs.md "2026-10-09 (design)" §5) — `actor` is one of "account" (the
caller acting on their own behalf), "admin" (approve/reject), or "anonymous"
(request-access, and a login that never resolved to anyone). `profile_id` is
the account the entry is ABOUT, which for `approve` is the newly
approved/topped-up account, not the admin doing the approving.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend import logplane
from backend.auth import store
from backend.deps import AdminIdentity, Identity, require_auth

router = APIRouter(prefix="/auth")


class AccessRequest(BaseModel):
    identifier: str
    note: str = ""


class TopupRequest(BaseModel):
    note: str = ""


class LoginRequest(BaseModel):
    token: str


@router.post("/request-access")
def request_access(body: AccessRequest):
    """Open to the world — store.create_request carries the input floor."""
    try:
        record = store.create_request(body.identifier, body.note)
    except store.AuthError as exc:
        raise HTTPException(400, str(exc)) from exc
    logplane.write("audit", event="request_access", actor="anonymous",
                    fields={"request_id": record["id"]})
    return record


@router.post("/request-more")
def request_more(body: TopupRequest, identity: Identity):
    """Authenticated top-up: more runs on the caller's OWN existing account.

    The identifier-takeover/re-issue fix (backend/bugs.md "2026-10-09
    (design)" §1, October scoping §5 items 1+4): this never mints a token,
    and the account it tops up comes from the caller's own bearer token, not
    from a typed name the way `/request-access` works. Use this instead of
    `/request-access` for "I already have an account and want more runs" —
    the frontend's Account.jsx "request more runs" button currently calls
    the wrong one; flagged to the frontend side, not changed here.
    """
    try:
        record = store.create_topup_request(identity, body.note)
    except store.AuthError as exc:
        raise HTTPException(400, str(exc)) from exc
    logplane.write("audit", event="request_more", actor="account",
                    profile_id=identity["profile_id"], fields={"request_id": record["id"]})
    return record


@router.post("/login")
def login(body: LoginRequest):
    """401 here is expected and is suppressed from the global logout handler."""
    record = store.resolve_token(body.token)
    if record is None:
        logplane.write("audit", event="login_failed", actor="anonymous")
        raise HTTPException(401, "That token is not valid")
    identity = store.identity_of(record)
    logplane.write("audit", event="login_ok", actor="account", profile_id=identity["profile_id"])
    return identity


@router.get("/me")
def me(identity: Identity):
    return identity


@router.get("/requests")
def list_requests(identity: AdminIdentity):
    return {"requests": store.list_requests()}


@router.post("/requests/{request_id}/approve")
def approve(request_id: str, identity: AdminIdentity):
    """Returns the raw token exactly once — it is never retrievable again."""
    try:
        result = store.approve_request(request_id)
    except store.AuthError as exc:
        raise HTTPException(409, str(exc)) from exc
    # profile_id is the newly approved/topped-up account's own — the entry is
    # about THEM, not about the admin who clicked approve (that's `actor`).
    logplane.write("audit", event="request_approved", actor="admin",
                    profile_id=result.get("profile_id"), fields={"request_id": request_id})
    return result


@router.post("/requests/{request_id}/reject")
def reject(request_id: str, identity: AdminIdentity):
    try:
        record = store.reject_request(request_id)
    except store.AuthError as exc:
        raise HTTPException(409, str(exc)) from exc
    # profile_id is the account the decision was about, not the admin who made
    # it (that's `actor`) - the same rule `approve` just above follows. A
    # top-up keeps its `token_id` through the rejection now
    # (bugs_audit_fixed.md #70 item 2), so there is an account to name; a
    # rejected signup has none, and None is the honest record.
    logplane.write("audit", event="request_rejected", actor="admin",
                    profile_id=store.profile_id_for_token(record.get("token_id")),
                    fields={"request_id": request_id})
    return record
