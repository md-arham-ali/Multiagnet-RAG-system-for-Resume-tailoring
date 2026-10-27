"""
Build Profile — conversational KB feeding.

Writes to manual_entries.json ONLY; the curated KB files are never touched.

Every write is also embedded into the `profile` collection. Retrieval reads the
collection and nothing else, so a JSON-only write is an entry the system can
never find, and a JSON-only edit leaves the superseded text answering queries
forever (bugs.md #30). `VectorStore.add` is an upsert on a stable id, so
re-indexing the same entry overwrites rather than accumulating.

Every entry is owner-scoped (backend/bugs.md "2026-10-09 (design)" §4's
interim fix, built 2026-10-10): `GET` returned, and `PUT` could silently
overwrite, every user's entries until now. `visible_entries()` is the one
place that decides who may see which record — `backend/routes/kb.py` reuses
it for `/kb/profile/manual_entries`, which exposes the same file through a
second route, rather than re-deriving the rule there.

**Known gap, outside this folder's jurisdiction:** `learning/profile_store.
save_gap_answers` (the gate-2 answer path, called from the graph, not from
here) writes into this SAME file with no `owner` field — confirmed against
the real `knowledge_base/profile/manual_entries.json`, which already holds 3
such records from offline CLI runs (`run_id`s, no `owner`). `visible_entries`
treats an ownerless entry as admin-only (the same convention
`backend/runs/registry.owns()` already uses for run logs written before
ownership existed), so until that module stamps `owner` the same way
`backend/auth/store.py` now does for tokens (§1), a user's OWN gate-2 answers
won't appear in their own Build-Profile list. Flagged, not fixed here — it is
Agents/Data-Storage lane code, not backend/.
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

import config
from backend.deps import Caller, Scope
from backend.jsonstore import read_json, update_json
from backend.vectorstore import get_vector_store

log = logging.getLogger("backend")

router = APIRouter(prefix="/profile")

MANUAL_ENTRIES = config.KB_DIR / "profile" / "manual_entries.json"

# Build-Profile section -> the record `type` the profile collection already uses
# (vectordb/ingest.py SOURCES). agents/profile.py's QUOTAS filters retrieval on
# exactly these values, so a new type invented here would be a record that is
# indexed and never retrieved.
SECTION_TYPES = {
    "projects":    "project",
    "skills":      "skill",
    "achievements": "achievement",
    "education":   "education",
    "internships": "work_experience",
    "extras":      "extracurricular",
}


class ProfileEntry(BaseModel):
    section: str  # projects | skills | achievements | education | internships | extras
    record: dict

    @field_validator("section")
    @classmethod
    def _section_is_indexable(cls, value: str) -> str:
        """A section outside SECTION_TYPES is a 422, not a silent save
        (bugs_audit_fixed.md #69 item 2).

        `_index_entry` below warns and returns for an unknown section, so the
        save answered 200, the record sat in manual_entries.json, and
        retrieval could never find it - the user is told their entry is in
        when nothing will ever read it. The docstring on SECTION_TYPES calls
        an invented type "a record that is indexed and never retrieved";
        this was worse, not even indexed.

        Validated against SECTION_TYPES itself rather than a `Literal[...]`
        spelled out on the field: one source of truth for the allowed
        sections, so adding a section to the table can't leave this check
        behind (the drift that produced `AGENTS`/`GATES`/`STUB_NODES`).
        """
        if value not in SECTION_TYPES:
            raise ValueError(f"Unknown section {value!r}. Expected one of: "
                             f"{', '.join(SECTION_TYPES)}.")
        return value


def _entry_text(entry: dict) -> str:
    """The one string that gets embedded. Chroma metadata is scalars only, so
    list answers ("tools", "skills") belong in the text, same as ingest.py."""
    parts = []
    for key, value in (entry.get("record") or {}).items():
        if isinstance(value, (list, tuple)):
            value = ", ".join(str(v) for v in value)
        value = str(value).strip()
        if value:
            parts.append(f"{key.replace('_', ' ')}: {value}")
    return f"{entry.get('section', '')}. " + " ".join(parts)


def _index_entry(entry: dict) -> None:
    record_type = SECTION_TYPES.get(entry.get("section"))
    if record_type is None:
        # Kept as defence in depth, not as the gate: ProfileEntry refuses an
        # unknown section at the door now, so this can only be reached by an
        # entry already on disk (one written before that validator, or by
        # learning/profile_store.save_gap_answers, which doesn't come through
        # these routes).
        log.warning("profile entry %s has unknown section %r, not indexed",
                    entry.get("id"), entry.get("section"))
        return
    text = _entry_text(entry)
    if not text.strip():
        return
    try:
        get_vector_store().add(
            "profile",
            [f"{record_type}:{entry['id']}"],
            [text],
            [{
                "type": record_type,          # what QUOTAS filters on
                "source_id": entry["id"],
                "section": entry["section"],
                "source": "build_profile",
            }],
        )
    except Exception:
        # The JSON record is already written; a failed embed must not 500 the
        # save, but it must not be silent either — it is why retrieval would
        # then not find the entry.
        log.exception("failed to index profile entry %s", entry.get("id"))


def _index_in_background(entry: dict) -> None:
    """First call loads the ~440MB embedder, which cannot sit in the request
    path. The save returns immediately; indexing follows."""
    threading.Thread(target=_index_entry, args=(entry,), daemon=True).start()


def visible_entries(scope: Scope) -> list[dict]:
    """Every entry `scope` may see. Admin sees all; otherwise only entries
    this account owns. An entry with no "owner" (written before this field
    existed, or by learning/profile_store.save_gap_answers - see the module
    docstring) is admin-visible only - never shown to everyone, and never a
    KeyError on a missing field."""
    entries = read_json(MANUAL_ENTRIES)
    if scope.role == "admin":
        return entries
    return [e for e in entries if e.get("owner") == scope.profile_id]


@router.get("/entries")
def profile_entries(scope: Caller):
    return {"entries": visible_entries(scope)}


@router.post("/entries")
def add_profile_entry(entry: ProfileEntry, scope: Caller):
    new = {
        "id": uuid.uuid4().hex[:8],
        "owner": scope.profile_id,
        "section": entry.section,
        "record": entry.record,
        "created": datetime.now(timezone.utc).isoformat(),
    }
    # update_json, not read + write: FastAPI serves these handlers from a thread
    # pool and a graph run writes the same file from a worker thread, so a bare
    # read-modify-write drops one of two overlapping saves (bugs.md #35).
    update_json(MANUAL_ENTRIES, lambda entries: (entries + [new], new))
    _index_in_background(new)
    return new


_FORBIDDEN = object()


@router.put("/entries/{entry_id}")
def edit_profile_entry(entry_id: str, entry: ProfileEntry, scope: Caller):
    def replace(entries):
        for item in entries:
            if item["id"] != entry_id:
                continue
            # Checked inside the same read-modify-write as the edit itself,
            # under MANUAL_ENTRIES' own lock (update_json) - not as a separate
            # read beforehand, which would leave a window between the check
            # and the write for a concurrent edit to land in between.
            if scope.role != "admin" and item.get("owner") != scope.profile_id:
                return None, _FORBIDDEN
            item["record"] = entry.record
            item["updated"] = datetime.now(timezone.utc).isoformat()
            return entries, item
        return None, None  # no such entry: nothing to write

    item = update_json(MANUAL_ENTRIES, replace)
    if item is _FORBIDDEN:
        raise HTTPException(403, "Not your entry")
    if item is None:
        raise HTTPException(404, "Unknown entry")
    # Re-embed under the same id: the upsert replaces the old text, so the
    # correction actually reaches the thing that retrieves it.
    _index_in_background(item)
    return item
