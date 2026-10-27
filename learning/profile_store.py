"""
Profile-store enrichment — persist gap-interview answers so future runs find them.

The gap-interview closes a gap for the *current* run by appending a ProfileBlock
to `state.evidence`. This module is the other half: it writes the same polished
text to disk and embeds it, so the next run retrieves it instead of asking the
same question again.

Two destinations, one text:
  - `knowledge_base/profile/manual_entries.json` — the durable record. Same file
    the frontend's Build-Profile flow writes (`backend/routes/profile.py`), so
    CLI and UI enrichment land in one place rather than two.
  - the `profile` Chroma collection, tagged `type="gap_answer"` — what makes it
    retrievable. `agents/profile.py`'s QUOTAS has a slot for that type.

The curated KB fixtures (`profile/projects.json` etc.) are never touched.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import config
from backend.jsonstore import update_json

MANUAL_ENTRIES = config.KB_DIR / "profile" / "manual_entries.json"

# Chroma metadata must be scalars, and ingest.py's id convention is "<type>:<id>".
RECORD_TYPE = "gap_answer"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_gap_answers(entries: list[dict], store=None, run_id: str | None = None) -> list[dict]:
    """
    Persist enriched gap answers and index them for retrieval.

    `entries` is what the profile_enrich LLM produced, one dict per answered gap:
        {"requirement": str, "question": str, "raw_answer": str,
         "content": str, "category": str, "skills": list[str]}

    Entries with empty `content` are skipped — that is how profile_enrich reports
    "the candidate said they haven't done this", and storing an empty block would
    pollute retrieval.

    `store` is injected so tests can pass a fake/in-memory VectorStore; when None
    a real one is constructed lazily (it loads a ~440MB embedding model, so it is
    deliberately NOT imported at module scope — see the boot-time regression noted
    in context.md 2026-08-19).

    Returns the records actually written (empty list if nothing qualified).
    """
    usable = [e for e in entries if (e.get("content") or "").strip()]
    if not usable:
        return []

    records: list[dict] = []
    for entry in usable:
        record_id = uuid.uuid4().hex[:8]
        records.append({
            "id": record_id,
            "section": "gap_answers",
            "source": "gap_interview",
            "run_id": run_id,
            "created": _now(),
            "record": {
                "gap_answer_id": record_id,
                "requirement": entry.get("requirement", ""),
                "question": entry.get("question", ""),
                "raw_answer": entry.get("raw_answer", ""),   # kept for audit//traceability
                "content": entry["content"],                  # the polished, embedded text
                "category": entry.get("category", ""),
                "skills": entry.get("skills", []),
            },
        })

    # Through update_json, like the Build-Profile routes: a raw read + write here
    # dropped a concurrent UI save, and with the shared temp name it once tore
    # the file (bugs_audit_fixed.md #35; scripts/check_storage.py --stress).
    update_json(MANUAL_ENTRIES, lambda existing: (existing + records, None))
    index_gap_answers(records, store=store)
    return records


def index_gap_answers(records: list[dict], store=None) -> int:
    """Embed `records` into the profile collection. Returns how many were indexed."""
    if not records:
        return 0

    if store is None:
        # Lazy, and no longer a fresh ~440MB embedder per save: VectorStore's
        # default embedder is the process's shared one (vectordb/models.py, #43).
        from vectordb.store import VectorStore
        store = VectorStore()

    ids, texts, metas = [], [], []
    for rec in records:
        inner = rec["record"]
        ids.append(f"{RECORD_TYPE}:{inner['gap_answer_id']}")
        texts.append(inner["content"])
        metas.append({
            "type": RECORD_TYPE,                       # what QUOTAS filters on
            "source_id": inner["gap_answer_id"],
            "requirement": inner.get("requirement", ""),
            "category": inner.get("category", ""),
            # Chroma rejects list values, so skills are flattened to a string.
            "skills": ", ".join(inner.get("skills") or []),
        })

    store.add("profile", ids, texts, metas)
    return len(ids)
