"""
Knowledge-base browsing + evidence search.

Ported from scripts/frontend_api.py unchanged except for the auth dependency:
read-only over the KB files and the Chroma index.

The "profile" store's `manual_entries` file is the one exception to "read-only
over curated files": it's Build Profile's own owner-scoped data
(backend/routes/profile.py), reached here through a second route onto the same
file. `visible_entries()` is reused rather than re-derived, so this route can't
silently drift back to showing everyone's entries while profile.py's own stays
fixed (backend/bugs.md "2026-10-09 (design)" §4's interim fix, built
2026-10-10). Every OTHER file under every store here is genuinely shared and
curated, and stays unscoped.
"""

from __future__ import annotations

import os
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import config
from backend.deps import Caller, Identity
from backend.jsonstore import read_json
from backend.routes.profile import MANUAL_ENTRIES, visible_entries
from backend.vectorstore import get_vector_store

router = APIRouter()

KB_DIR = config.KB_DIR
_MANUAL_ENTRIES_RESOLVED = MANUAL_ENTRIES.resolve()

# UI store name -> KB subfolder (jargon-free names live in the UI, real paths here).
STORES = {
    "profile": "profile",
    "documents": "documents",
    "claim_boundaries": "do_not_claim",
    "agent_memory": "learning",
}


def _is_manual_entries(path) -> bool:
    """Same file, not same spelling (#69 item 1): path-equality let a case
    variant open manual_entries unscoped on a case-insensitive filesystem."""
    try:
        return os.path.samefile(path, _MANUAL_ENTRIES_RESOLVED)
    except OSError:  # either side missing
        return False


def _records(path, scope) -> list:
    """The records of one KB file, whatever shape it is stored in (#51).

    `do_not_claim.json` is a wrapper object — `{_comment, version,
    forbidden_claims}` — so `len()` on the parsed file counted its three *keys*
    and the browser said "3 records", while `kb_file` sent the whole wrapper as
    a single record. Both now read through here: a wrapper's first list value
    IS its records.

    One function for both routes on purpose. The count and the listing
    disagreeing about one file is the same two-readers drift that produced the
    `AGENTS`/`GATES`/`STUB_NODES` tables and `load_log`'s three `final`
    lookups.
    """
    if _is_manual_entries(path):
        return visible_entries(scope)
    data = read_json(path)
    if isinstance(data, dict):
        # The wrapper's own scalar keys (_comment, version) are metadata about
        # the list, not records beside it. A dict with no list at all stays one
        # record, which is what it is.
        lists = [v for v in data.values() if isinstance(v, list)]
        return lists[0] if lists else [data]
    return data


def _record_count(path, scope) -> int:
    return len(_records(path, scope))


@router.get("/kb")
def kb_overview(scope: Caller):
    stores = {}
    for name, folder in STORES.items():
        files = sorted((KB_DIR / folder).glob("*.json"))
        stores[name] = [{"file": f.stem, "records": _record_count(f, scope)} for f in files]

    import chromadb  # local import: keeps module import light

    client = chromadb.PersistentClient(path=str(config.VECTORDB_DIR))
    vectors = {c.name: c.count() for c in client.list_collections()}
    return {"stores": stores, "vectors": vectors}


@router.get("/kb/{store}/{file}")
def kb_file(store: str, file: str, scope: Caller, limit: int = 100):
    if store not in STORES:
        raise HTTPException(404, f"Unknown store '{store}'")
    store_dir = (KB_DIR / STORES[store]).resolve()
    # Exact on-disk names only: a case variant opens the same file on macOS but
    # 404s on Linux - refuse it everywhere. Also no traversal: only listed names match.
    path = next((f for f in store_dir.glob("*.json") if f.stem == file), None)
    if path is None or not path.resolve().is_relative_to(store_dir):
        raise HTTPException(404, f"No file '{file}' in store '{store}'")
    # manual_entries is Build Profile's own owner-scoped data, reached through
    # this second route onto the same file as backend/routes/profile.py - see
    # the module docstring. Every other file here is genuinely shared.
    records = _records(path, scope)
    return {"file": file, "total": len(records), "records": records[:limit]}


# The shared collections search may read (#45). An allowlist, not any string:
# Stage 0's per-profile collections will live in this same index, and a free
# name would let any caller search someone else's.
Searchable = Literal["profile", "documents", "learning"]


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    collection: Searchable = "profile"
    k: int = Field(5, ge=1, le=50)  # Chroma 500s on k<=0


@router.post("/search")
def search(req: SearchRequest, identity: Identity):
    from vectordb.store import CollectionNotFound  # local: keeps module import light

    try:
        hits = get_vector_store().query(req.collection, req.query, k=req.k)
    except CollectionNotFound as exc:
        raise HTTPException(404, f"The '{req.collection}' index hasn't been built yet.") from exc
    return {
        "query": req.query,
        "collection": req.collection,
        "hits": [
            {"id": h.id, "text": h.document, "metadata": h.metadata, "score": h.score}
            for h in hits
        ],
    }
