"""
Access requests and issued tokens — pure file I/O, no FastAPI import.

Two JSON arrays under `config.KB_AUTH_DIR` (git-ignored, see .gitignore):

    requests.json  {id, kind, identifier, note, status, created, resolved, token_id}
    tokens.json    {id, token, identifier, profile_id, role, runs_remaining, created, request_id}

`kind` on a request is "signup" (default — mints a token + a profile) or
"topup" (an authenticated top-up on an existing token; see
create_topup_request). `profile_id` on a token is the account key — see
`backend/auth/profiles.py` for the third store this module now calls into
(`profiles.json`), which is what lets a re-issued token still resolve to the
same account instead of splitting it in two.

Tokens are stored in plaintext. That is a deliberate, documented choice for this
internal tool (same as `manual_entries.json` storing raw profile data): the
threat model is a single-user machine, and hashing would mean the admin could
never re-read a token to hand it over. `knowledge_base/auth/` is git-ignored so
they never reach a commit.

Every read-modify-write goes through `_LOCK`. `learning/store.py` needs no such
lock because it is CLI-driven and single-threaded; this module is hit
concurrently by FastAPI request threads, where a bare read-modify-write would
lose an approval or double-spend a run allowance.
"""

from __future__ import annotations

import logging
import secrets
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import config
from backend.auth import profiles
from backend.jsonstore import read_records, write_json

log = logging.getLogger("backend")

# Serialises every read-modify-write below. Re-entrant so a public function can
# call another one while already holding it.
_LOCK = threading.RLock()

# The admin identity is synthesised from config.ADMIN_TOKEN and never persisted,
# so it has no record in tokens.json to key off. This sentinel stands in for one.
ADMIN_TOKEN_ID = "__admin__"
# Same treatment, same reason: the admin account has no profiles.json row
# either. A fixed sentinel, not profiles.get_or_create_profile("admin") -
# "admin" is reserved there precisely so no typed identifier can collide with
# this one (backend/auth/profiles.RESERVED).
ADMIN_PROFILE_ID = "p-__admin__"

# Floor on the open request-access route (it takes no auth, so anyone who can
# reach the port can append to disk).
MAX_IDENTIFIER = 64
MAX_NOTE = 500
MAX_PENDING = 100


class AuthError(Exception):
    """A rejected auth operation. Routes translate this into an HTTP status."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Paths are resolved lazily, per call, rather than captured at import time —
# that is what lets the tests point config.KB_AUTH_DIR at a tmp_path.
def _requests_path() -> Path:
    return config.KB_AUTH_DIR / "requests.json"


def _tokens_path() -> Path:
    return config.KB_AUTH_DIR / "tokens.json"


# --- access requests ---------------------------------------------------------
def _queue_key(identifier: str) -> str:
    """The pending-duplicate key for one queued name.

    `normalise_identifier` where it applies, and a case-folded fallback for a
    row it refuses. Only pending rows written *before* create_request started
    normalising can be in that state; without the fallback they would stop
    de-duplicating against anything at all, which is the opposite of the fix.
    """
    try:
        return profiles.normalise_identifier(identifier)
    except profiles.ProfileError:
        return " ".join((identifier or "").split()).casefold()


def create_request(identifier: str, note: str = "") -> dict:
    """Queue one access request. Raises AuthError on invalid or duplicate input.

    The account's own identity rule is applied **here**, at the queue
    (bugs_audit_fixed.md #68 item 2), not only at approval. `profiles.py`
    says a reserved or ':'-containing name is "rejected at normalisation so
    none of these can ever be queued"; it wasn't true - this function never
    called `normalise_identifier`, so `admin`, `ＡＤＭＩＮ`, `a:b` and a name
    that only passes the length check before casefolding (40x"ß" measures 40
    raw and 80 folded) all queued happily and were refused with a 409 at
    approval, after a person had been told their request was in.

    The raw length check stays in front of it: this route takes no auth, so
    the cheap bound on the typed string runs before any NFKC work, and the
    normalised check below then catches what folding expands.

    Deliberately NOT checked here: whether the name already *has* an account
    or an issued token. That stays at approval (`_name_held_by_a_token`,
    #68 item 1), because answering it on an open, unauthenticated route would
    tell the world which names are registered.
    """
    identifier = (identifier or "").strip()
    note = (note or "").strip()
    if not identifier:
        raise AuthError("A name is required.")
    if len(identifier) > MAX_IDENTIFIER:
        raise AuthError(f"Name must be {MAX_IDENTIFIER} characters or fewer.")
    if len(note) > MAX_NOTE:
        raise AuthError(f"Note must be {MAX_NOTE} characters or fewer.")
    try:
        identifier_norm = profiles.normalise_identifier(identifier)
    except profiles.ProfileError as exc:
        # Same text the approval path already surfaces for these names - the
        # caller just gets it now instead of after a wait for review.
        raise AuthError(str(exc)) from exc

    with _LOCK:
        requests = read_records(_requests_path())
        pending = [r for r in requests if r.get("status") == "pending"]
        if len(pending) >= MAX_PENDING:
            raise AuthError("Too many requests are already waiting for review.")
        # On the normalised key, not .lower(): "Jane Doe" and "jane  doe" are
        # one account, so they must be one pending request.
        if any(_queue_key(r.get("identifier", "")) == identifier_norm for r in pending):
            raise AuthError("A request from that name is already awaiting review.")

        record = {
            "id": uuid.uuid4().hex[:8],
            "kind": "signup",
            "identifier": identifier,
            "note": note,
            "status": "pending",
            "created": _now(),
            "resolved": None,
            "token_id": None,
        }
        requests.append(record)
        write_json(_requests_path(), requests)
        return record


def create_topup_request(identity: dict, note: str = "") -> dict:
    """Queue a request for more runs on an EXISTING, already-authenticated
    account - never a fresh signup under a typed name.

    This is the fix for the re-issue/takeover path (October scoping §5 items
    1 and 4): `identity["token_id"]` is resolved from the caller's own bearer
    token, not from free text, so the request can only ever top up the
    account that is already theirs. approve_request() below recognises
    `kind == "topup"` and adds to that token's own `runs_remaining` instead of
    minting a second token for the same person.
    """
    note = (note or "").strip()
    # The admin has no tokens.json row and no allowance to add to, so its
    # top-up could only ever be approved into a 409 ("That account no longer
    # exists") while holding a MAX_PENDING slot (#70 item 3). Refused at the
    # door, in the store rather than the route, so every caller of this
    # function gets the same answer - approve_request's own "no such account"
    # check stays as the backstop for a token deleted after queueing.
    if identity.get("token_id") == ADMIN_TOKEN_ID:
        raise AuthError("The admin account has no run limit.")
    if len(note) > MAX_NOTE:
        raise AuthError(f"Note must be {MAX_NOTE} characters or fewer.")
    with _LOCK:
        requests = read_records(_requests_path())
        pending = [r for r in requests if r.get("status") == "pending"]
        if len(pending) >= MAX_PENDING:
            raise AuthError("Too many requests are already waiting for review.")
        if any(r.get("kind") == "topup" and r.get("token_id") == identity["token_id"]
               for r in pending):
            raise AuthError("A top-up request for your account is already awaiting review.")

        record = {
            "id": uuid.uuid4().hex[:8],
            "kind": "topup",
            "identifier": identity["identifier"],
            "note": note,
            "status": "pending",
            "created": _now(),
            "resolved": None,
            # Set at creation, not at approval - this is what makes it a
            # top-up for a known account rather than a signup that mints one.
            "token_id": identity["token_id"],
        }
        requests.append(record)
        write_json(_requests_path(), requests)
        return record


def list_requests() -> list[dict]:
    """Every request, newest first — pending AND resolved.

    The admin UI splits on `status` itself and renders a resolved table, so
    filtering here would silently empty half that screen.
    """
    return sorted(read_records(_requests_path()), key=lambda r: r.get("created", ""), reverse=True)


def _resolve(request_id: str, status: str, token_id: str | None = None) -> dict:
    """Flip one pending request to a terminal status. Caller must hold _LOCK.

    `token_id` is only ever *set* here, never cleared (bugs_audit_fixed.md
    #70 item 2). A top-up carries its account's `token_id` from the moment it
    is created - that is the whole difference between a top-up and a signup -
    and rejecting one used to pass `token_id=None` straight into the record,
    erasing the request's only link to the account it was for. The `reject`
    route then had nothing left to attribute its audit entry to, so that
    account's own `/logs/mine` never showed the rejection although approvals
    showed. A rejected *signup* still ends with `token_id: None`, because it
    never had one - no account exists to point at.
    """
    requests = read_records(_requests_path())
    for record in requests:
        if record["id"] != request_id:
            continue
        if record.get("status") != "pending":
            # Guards a double-clicked Approve: without it, the second click
            # would mint a second token for the same request.
            raise AuthError(f"That request was already {record['status']}.")
        record["status"] = status
        record["resolved"] = _now()
        record["token_id"] = token_id or record.get("token_id")
        write_json(_requests_path(), requests)
        return record
    raise AuthError("No such request.")


def _name_held_by_a_token(identifier: str) -> bool:
    """True if any issued token's identifier normalises to the same account key.

    The gap this closes (backend/bugs.md #68 item 1): a token issued before
    profiles existed is backfilled by name on its next use. Approving a
    same-normalised name in between ("Jane" -> "JANE") would pass
    create_profile, and the legacy holder's backfill would then attach to the
    newcomer's profile - two people, one account. Checking tokens.json makes
    approval refuse whether or not that backfill has happened yet. Caller
    holds _LOCK.
    """
    try:
        wanted = profiles.normalise_identifier(identifier)
    except profiles.ProfileError:
        return False  # create_profile refuses it with the real reason
    for tok in read_records(_tokens_path()):
        try:
            if profiles.normalise_identifier(tok.get("identifier", "")) == wanted:
                return True
        except profiles.ProfileError:
            continue  # a pre-rule name can't equal a name that passes the rule
    return False


def approve_request(request_id: str) -> dict:
    """Approve a request.

    Two shapes, by `kind`:
    - **signup** (default, incl. every request queued before this field
      existed): mints a brand-new token AND a brand-new profile. Raises
      AuthError (-> 409 at the route) when the identifier already has a
      profile or is held by any issued token — the identifier-takeover fix (October scoping §5 item 1): a
      typed name that collides with an existing account must be refused, not
      silently attached to it. Returns the token record INCLUDING the raw
      `token` — the only time it is ever returned; the admin UI shows it once
      for copy/paste hand-off.
    - **topup** (from create_topup_request): mints nothing. Adds one
      allowance to the SAME token the caller was already authenticated with,
      so "request more runs" can never split one account across two tokens
      (October scoping §5 item 4). Returns that token's record, token
      withheld — the caller already has it.
    """
    with _LOCK:
        requests = read_records(_requests_path())
        match = next((r for r in requests if r["id"] == request_id), None)
        if match is None:
            raise AuthError("No such request.")
        if match.get("status") != "pending":
            raise AuthError(f"That request was already {match['status']}.")

        if match.get("kind") == "topup":
            tokens = read_records(_tokens_path())
            tok = next((t for t in tokens if t["id"] == match["token_id"]), None)
            if tok is None:
                raise AuthError("That account no longer exists.")
            tok["runs_remaining"] = (tok.get("runs_remaining") or 0) + config.DEFAULT_RUN_ALLOWANCE
            write_json(_tokens_path(), tokens)
            _resolve(request_id, "approved", token_id=tok["id"])
            return {k: v for k, v in tok.items() if k != "token"}

        # A legacy token has no profiles.json row until it's next used, so
        # create_profile alone can't see it - check tokens.json too (#68 item 1).
        if _name_held_by_a_token(match["identifier"]):
            raise AuthError("An account already exists for that name.")
        try:
            profile_id = profiles.create_profile(match["identifier"])
        except profiles.ProfileError as exc:
            raise AuthError(str(exc)) from exc

        record = {
            "id": f"t-{uuid.uuid4().hex[:8]}",
            "token": secrets.token_urlsafe(32),
            "identifier": match["identifier"],
            "profile_id": profile_id,
            "role": "user",
            "runs_remaining": config.DEFAULT_RUN_ALLOWANCE,
            "created": _now(),
            "request_id": request_id,
        }
        tokens = read_records(_tokens_path())
        tokens.append(record)
        write_json(_tokens_path(), tokens)
        _resolve(request_id, "approved", token_id=record["id"])
        return record


def reject_request(request_id: str) -> dict:
    with _LOCK:
        return _resolve(request_id, "rejected")


def profile_id_for_token(token_id: str | None) -> str | None:
    """The account a `token_id` belongs to, or None if it names no token.

    For audit attribution only (`routes/auth.py`'s `reject`): an entry about
    a decision on someone's request has to name that account, the same way
    `request_approved` already does, or it never reaches their own
    `/logs/mine` (bugs_audit_fixed.md #70 item 2). Never a permission check -
    `Scope` is still the only way a route reaches profile-keyed storage.

    `ADMIN_TOKEN_ID` maps to the admin's own sentinel profile, which has no
    `tokens.json` row to find (#70 item 3 is the separate matter of such a
    top-up being queueable at all).
    """
    if not token_id:
        return None
    if token_id == ADMIN_TOKEN_ID:
        return ADMIN_PROFILE_ID
    for record in read_records(_tokens_path()):
        if record.get("id") == token_id:
            return record.get("profile_id")
    return None


# --- tokens ------------------------------------------------------------------
def _admin_identity() -> dict:
    return {
        "id": ADMIN_TOKEN_ID,
        "identifier": "admin",
        "role": "admin",
        "runs_remaining": None,  # the frontend hides the runs-left pill on None
        "profile_id": ADMIN_PROFILE_ID,
    }


def _with_profile_id(record: dict) -> dict:
    """Backfill `profile_id` onto a token issued before this field existed.

    Looked up via get_or_create_profile, not minted via create_profile: the
    identifier here is the one already attached to an approved token, never
    typed input fresh off a request, so the 409-on-collision guard that
    create_profile enforces at approval time doesn't apply - there is nothing
    for this identifier to collide with except the profile it already owns.

    The typed-name rule is NEWER than some issued tokens, so normalising one
    can fail. That is not a reason to refuse a credential this file itself
    says is valid - see the fallback below (#70 item 1).
    """
    if record.get("profile_id"):
        return record
    identifier = record.get("identifier", "")
    try:
        profile_id = profiles.get_or_create_profile(identifier)
    except profiles.ProfileError as exc:
        # This token is KNOWN and already approved, so the only two options
        # are "give it an account" or "lock its holder out". Before this, the
        # ProfileError escaped resolve_token uncaught and every request
        # carrying the token - login, any Authorization route, the ?token=
        # SSE stream - was a 500, while deps.py promises 401 for an UNKNOWN
        # token and this one is not unknown: runs, CV and entries all
        # unreachable, with nothing on screen explaining why.
        #
        # Reachable for any token approved before normalise_identifier
        # existed whose name is reserved, holds ':', or casefolds past
        # MAX_IDENTIFIER (create_request measures the raw string, so 40x"ss"
        # queues and then doubles in length). Keyed on the token's own id,
        # which never changes, so the account is stable and this runs once.
        profile_id = profiles.get_or_create_system_profile(f"legacy:{record['id']}",
                                                           identifier)
        log.warning("token %s has an identifier the current rule rejects (%s); "
                    "kept its own account as %s under a system key",
                    record["id"], exc, profile_id)
    with _LOCK:
        tokens = read_records(_tokens_path())
        for tok in tokens:
            if tok["id"] == record["id"]:
                tok["profile_id"] = profile_id
                write_json(_tokens_path(), tokens)
                break
    return {**record, "profile_id": profile_id}


def resolve_token(raw: str | None) -> dict | None:
    """Map a raw bearer token to its record, or None if unknown.

    ADMIN_TOKEN is checked first and only when non-empty, so an unset
    ADMIN_TOKEN can never be matched by an empty/missing header.
    """
    if not raw:
        return None
    # Bytes, not str: compare_digest raises TypeError on a non-ASCII str, which
    # made a pasted "é" a 500 at every door instead of a 401 (bugs_audit_fixed.md #63 item 1).
    given = raw.encode("utf-8")
    if config.ADMIN_TOKEN and secrets.compare_digest(given, config.ADMIN_TOKEN.encode("utf-8")):
        return _admin_identity()
    for record in read_records(_tokens_path()):
        if secrets.compare_digest(given, record.get("token", "").encode("utf-8")):
            return _with_profile_id(record)
    return None


def identity_of(record: dict) -> dict:
    """The exact shape the frontend reads from /auth/me, /auth/login.

    `profile_id` is new (2026-10-10, backend/bugs.md "2026-10-09 (design)"
    §1): the account key, stable across a re-issued token. `token_id` stays
    for audit only - do not key ownership off it (backend/runs/registry.py).
    """
    return {
        "identifier": record["identifier"],
        "role": record.get("role", "user"),
        "runs_remaining": record.get("runs_remaining"),
        "token_id": record["id"],
        "profile_id": record.get("profile_id"),
    }


def consume_run(token_id: str) -> bool:
    """Spend one run off a token. False (and no write) when nothing is left."""
    if token_id == ADMIN_TOKEN_ID:
        return True  # admin is unlimited and never decremented
    with _LOCK:
        tokens = read_records(_tokens_path())
        for record in tokens:
            if record["id"] != token_id:
                continue
            if (record.get("runs_remaining") or 0) <= 0:
                return False
            record["runs_remaining"] -= 1
            write_json(_tokens_path(), tokens)
            return True
        return False


def refund_run(token_id: str) -> None:
    """Give back a consumed run — used only when the run fails to start at all."""
    if token_id == ADMIN_TOKEN_ID:
        return
    with _LOCK:
        tokens = read_records(_tokens_path())
        for record in tokens:
            if record["id"] == token_id:
                record["runs_remaining"] = (record.get("runs_remaining") or 0) + 1
                write_json(_tokens_path(), tokens)
                return
