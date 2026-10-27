"""
Auth dependencies.

Status codes are load-bearing here. The frontend installs a global 401 handler
(`api.js` -> `AuthContext`) that logs the user out of the whole app on ANY 401
from any route except /auth/login and the boot /auth/me. So:

    401  this token is missing, malformed, or unknown   -> ends the session
    403  the token is fine, but not for THIS            -> fails one request

Never use 401 for "wrong role", "not your run", or "out of runs": that would
sign a legitimate user out over a single refused action.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Header, HTTPException

from backend.auth import store


class ScopeError(Exception):
    """A path that fell outside its scope root. Routes turn this into 403 —
    same discipline as every other ownership failure (backend/bugs.md
    "2026-10-09 (design)" §2: "not yours" is 403, never 401)."""


def contained_path(root: Path, *parts: str) -> Path:
    """Join `parts` onto `root`, resolved, and refuse anything that climbs
    outside it.

    The same containment `backend/routes/kb.py`'s `kb_file()` already does
    inline (`path.is_relative_to(store_dir)`) — pulled out here so every
    other profile_id/run_id/cv_id-keyed lookup can share one checked
    implementation instead of re-deriving its own resolve()+check (§2: "the
    same containment as the kb_file hardening... a crafted run_id or cv_id
    cannot climb out"). `root` itself is never created or validated here —
    callers pass an existing config.*_DIR constant.
    """
    base = root.resolve()
    candidate = (base / Path(*parts)).resolve()
    if not candidate.is_relative_to(base):
        raise ScopeError(f"path escapes its root: {parts!r}")
    return candidate


@dataclass(frozen=True)
class Scope:
    """The account a route is allowed to touch, resolved once from the
    verified token alone — never from a path, query or body value
    (backend/bugs.md "2026-10-09 (design)" §2).

    Deliberately thin: `profile_id` is the only thing storage calls need to
    find the right subtree, and `role` lets a route special-case admin
    without a second `Depends(require_admin)` lookup. `role` grants nothing
    by itself here — an admin route that needs to reach ANOTHER account's
    data goes through its own dependency once one exists (§2's
    `/api/admin/users/{profile_id}/...`, not built yet: it also needs an
    audit-write-first guarantee this type alone can't make, since the log
    plane is §5, a later item).
    """

    profile_id: str
    role: str

    def own(self, root: Path, *parts: str) -> Path:
        """This scope's own subtree under `root` — `root/<profile_id>/parts`,
        contained. The shape every profile_id-keyed store function already
        uses (`config.CV_UPLOADS_DIR/{owner}/cv/`, etc.); this just adds the
        containment check most of them don't have yet."""
        return contained_path(root, self.profile_id, *parts)


def require_scope(identity: Annotated[dict, Depends(require_auth)]) -> Scope:
    """Every route that reaches profile_id-keyed storage should depend on
    this instead of pulling `identity["profile_id"]` by hand.

    Fails closed: `require_auth` already guarantees `profile_id` on every
    identity (backend/auth/store.identity_of, since §1) — this is only the
    one place that would notice if that contract were ever broken, rather
    than handing out a scope keyed on `None`.
    """
    profile_id = identity.get("profile_id")
    if not profile_id:
        raise RuntimeError("require_auth returned an identity with no profile_id")
    return Scope(profile_id=profile_id, role=identity["role"])


def _identity_or_401(raw: str | None) -> dict:
    record = store.resolve_token(raw)
    if record is None:
        raise HTTPException(401, "Invalid or missing access token")
    return store.identity_of(record)


def require_auth(authorization: Annotated[str | None, Header()] = None) -> dict:
    """Resolve `Authorization: Bearer <token>` to an identity, else 401."""
    if not authorization:
        raise HTTPException(401, "Invalid or missing access token")
    scheme, _, raw = authorization.partition(" ")
    if scheme.lower() != "bearer" or not raw.strip():
        raise HTTPException(401, "Invalid or missing access token")
    return _identity_or_401(raw.strip())


def require_admin(identity: Annotated[dict, Depends(require_auth)]) -> dict:
    """403, not 401 — the token is valid, it just isn't an admin's."""
    if identity["role"] != "admin":
        raise HTTPException(403, "Admin access required")
    return identity


def identity_from_query_token(token: str | None) -> dict:
    """SSE only. EventSource cannot set headers, so the token rides as ?token=.

    Deliberately confined to the events route — every other route uses the
    Authorization header, keeping tokens out of logs and browser history.
    """
    return _identity_or_401(token)


Identity = Annotated[dict, Depends(require_auth)]
AdminIdentity = Annotated[dict, Depends(require_admin)]
Caller = Annotated[Scope, Depends(require_scope)]
