"""
Profile identity: the account, not the credential.

`profiles.json`  [{profile_id, identifier_norm, display, created}]

An account is keyed on `profile_id`, a fresh `"p-<8hex>"` minted at creation -
never derived from the identifier text itself. Two reasons: Chroma's naming
rules forbid raw text in a collection name (Stage 0 plan §13.1), and a path or
log line built from someone's typed name puts PII where neither belongs.

`normalise_identifier()` is the single point that decides whether two typed
names are "the same account" - NFKC + casefold + collapsed whitespace, so
"Jane Doe", "jane  doe" and "JANE DOE" can't quietly become three accounts, or
let a confusable spelling take over an existing one (October scoping §5 item
1: approving a typed name identical to an existing user's hands the approver
that user's whole account the moment a route resolves by identifier instead of
by profile_id).

Deliberately a flat JSON file via `backend/jsonstore`, matching
`backend/auth/store.py`'s existing `requests.json`/`tokens.json` pattern,
*not* the `profiles.db` SQLite store Stage 0 §13.1 eventually wants. This
module's contract (`profile_for` / `get_or_create_profile` returning a stable
`profile_id` string) is what the rest of the backend calls; swapping the
storage underneath later is this module's own business.
"""

from __future__ import annotations

import threading
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path

import config
from backend.jsonstore import read_records, write_json

_LOCK = threading.RLock()

# Rejected at normalisation so none of these can ever be queued as a request,
# let alone approved: they would be confusable with the synthesised admin
# identity (backend/auth/store.ADMIN_TOKEN_ID) or with "no identifier at all".
RESERVED = {"admin", "system", "root"}

MAX_IDENTIFIER = 64


class ProfileError(Exception):
    """A rejected profile operation. Routes translate this into an HTTP status."""


def _profiles_path() -> Path:
    return config.KB_AUTH_DIR / "profiles.json"


def normalise_identifier(identifier: str) -> str:
    """The canonical uniqueness key for an identifier.

    Raises ProfileError on empty, oversized, ':'-containing or reserved input
    - the route layer turns that into a 400 (request-access) or carries it
    into create_profile's 409 (approval).
    """
    text = unicodedata.normalize("NFKC", (identifier or "")).strip().casefold()
    text = " ".join(text.split())  # collapse internal whitespace runs
    if not text:
        raise ProfileError("A name is required.")
    if len(text) > MAX_IDENTIFIER:
        raise ProfileError(f"Name must be {MAX_IDENTIFIER} characters or fewer.")
    if ":" in text:
        raise ProfileError("Name may not contain ':'.")
    if text in RESERVED:
        raise ProfileError("That name is reserved.")
    return text


def _find(profiles: list[dict], identifier_norm: str) -> dict | None:
    return next((p for p in profiles if p["identifier_norm"] == identifier_norm), None)


def profile_for(identifier: str) -> str | None:
    """The existing profile_id for this identifier, or None. Never creates.

    Only ever finds an account keyed on a *typed* name: a system-keyed one
    (get_or_create_system_profile) is unreachable from here by construction,
    which is the point of it.
    """
    identifier_norm = normalise_identifier(identifier)
    match = _find(read_records(_profiles_path()), identifier_norm)
    return match["profile_id"] if match else None


def display_for(profile_id: str) -> str | None:
    """The account's own display name, or None if `profile_id` names no
    account. The reverse of `profile_for` — looked up by the account's own
    key, never by typed text, so this is also the admin cross-vault route's
    input-validation boundary: `profile_id` only ever reaches a filesystem
    path (`cv_store`'s `CV_UPLOADS_DIR/<profile_id>/`) after this confirms it
    is one of the handful of server-generated `p-<8hex>` strings this module
    itself minted — never a raw path fragment an admin typed into the URL.
    """
    match = next((p for p in read_records(_profiles_path())
                  if p["profile_id"] == profile_id), None)
    return match["display"] if match else None


def _new_record(identifier: str, identifier_norm: str) -> dict:
    return {
        "profile_id": f"p-{uuid.uuid4().hex[:8]}",
        "identifier_norm": identifier_norm,
        "display": (identifier or "").strip(),
        "created": datetime.now(timezone.utc).isoformat(),
    }


def create_profile(identifier: str) -> str:
    """A brand-new profile for this identifier.

    Raises ProfileError when one already exists for the normalised form -
    callers that must never silently attach to an existing account under a
    typed name (approval) use this, not get_or_create_profile.
    """
    identifier_norm = normalise_identifier(identifier)
    with _LOCK:
        profiles = read_records(_profiles_path())
        if _find(profiles, identifier_norm) is not None:
            raise ProfileError("An account already exists for that name.")
        record = _new_record(identifier, identifier_norm)
        profiles.append(record)
        write_json(_profiles_path(), profiles)
        return record["profile_id"]


def get_or_create_profile(identifier: str) -> str:
    """Idempotent lookup-or-create.

    Only for entry points where seeing the same identifier twice is expected
    and safe to reuse - a backfill for a token issued before this module
    existed, or (once it lands) an authenticated top-up that takes its
    identifier from the caller's own existing record, never from typed text.
    A fresh public approval must use create_profile instead, so a typed name
    that collides with an existing account is refused rather than merged.
    """
    identifier_norm = normalise_identifier(identifier)
    with _LOCK:
        profiles = read_records(_profiles_path())
        match = _find(profiles, identifier_norm)
        if match is not None:
            return match["profile_id"]
        record = _new_record(identifier, identifier_norm)
        profiles.append(record)
        write_json(_profiles_path(), profiles)
        return record["profile_id"]


def get_or_create_system_profile(key: str, display: str = "") -> str:
    """Idempotent lookup-or-create under a key no typed name can ever reach.

    `key` is the uniqueness key verbatim - deliberately NOT run through
    normalise_identifier, so it must contain ':', which that function rejects
    outright. That one character is the whole guarantee: a system-keyed
    account cannot be collided with, or taken over by, anything a human types
    into request-access. Same shape reserved for `"{provider}:{subject}"` if
    OAuth lands (backend/context.md -> October scoping pass §5).

    For an account that demonstrably exists but whose own identifier can no
    longer be normalised - a token approved before the rule existed. Refusing
    it there locks out an already-approved holder; see
    `backend/auth/store._with_profile_id`.
    """
    if ":" not in key:
        raise ProfileError("A system profile key must contain ':'.")
    with _LOCK:
        profiles = read_records(_profiles_path())
        match = _find(profiles, key)
        if match is not None:
            return match["profile_id"]
        # _new_record, not a second record shape of its own: one place builds
        # a profile row, so the two can't drift apart.
        record = _new_record(display or key, key)
        profiles.append(record)
        write_json(_profiles_path(), profiles)
        return record["profile_id"]
