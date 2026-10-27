"""
ONE TIME RUN ONLY< FOR BUILD!!!
Load the knowledge_base/*.json fixtures into the vector store.

Three collections:
  - "profile"   : projects, work_experience, education, skills, coursework,
                  achievements, extracurriculars   (the candidate's evidence)
  - "documents" : cv_examples, cover_letter_examples   (examples / templates)
  - "learning"  : agent_learnings   (exemplars, retrieved by role type)

User-entered records (`profile/manual_entries.json`: gap-interview answers and
Build-Profile entries) are indexed into "profile" too, after the fixtures, so a
rebuild re-embeds them instead of dropping them (#65.1).

The do-not-claim list is intentionally NOT here: it is a hard constraint loaded
whole and checked exhaustively, never embedded.

Each record becomes (id, text, metadata):
  - text     : a short human-readable summary -> this is what we embed
  - metadata : a few scalar fields for filtering (Chroma metadata = scalars only,
               so list fields go into the text, not the metadata)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import config
from vectordb.store import VectorStore

log = logging.getLogger("vectordb")


def _load(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _sub(r: dict, key: str) -> dict:
    """A nested object, as a dict. `r.get(key, {})` handles a *missing* key, not
    one explicitly `null` — a hand-edited or imported record writing JSON null
    gave `AttributeError: 'NoneType' has no attribute 'get'` (#80.3)."""
    return r.get(key) or {}


def _join(values, n: int = 8) -> str:
    if isinstance(values, str):  # a bare string where a list belongs: one item, not characters
        values = [values]
    return ", ".join(str(v) for v in (values or [])[:n])


# --- text builders: turn a record into the string we embed -------------------
def _project_text(r: dict) -> str:
    bi = _sub(r, "basic_info")
    return (f"Project: {bi.get('title', '')}. Domain: {_join(bi.get('domain'))}. "
            f"{_sub(r, 'problem').get('business_problem', '')} "
            f"Skills: {_join(r.get('skills_demonstrated'))}. "
            f"{_sub(r, 'resume_material').get('one_line', '')}")


def _work_text(r: dict) -> str:
    return (f"{r.get('role', '')} at {r.get('company', '')}. {r.get('summary', '')} "
            f"Technologies: {_join(r.get('technologies'))}. "
            f"Skills: {_join(r.get('skills_demonstrated'))}.")


def _education_text(r: dict) -> str:
    return (f"{r.get('degree', '')} in {r.get('major', '')}, {r.get('institution', '')}. "
            f"Coursework: {_join(r.get('coursework'))}. "
            f"Skills: {_join(r.get('skills_gained'))}.")


def _skill_text(r: dict) -> str:
    return (f"Skill: {r.get('name', '')} ({r.get('category', '')}, "
            f"{r.get('proficiency', '')}). {r.get('description', '')} "
            f"Keywords: {_join(r.get('keywords'))}.")


def _course_text(r: dict) -> str:
    return (f"Course: {r.get('course_name', '')} at {r.get('institution', '')}. "
            f"{r.get('description', '')} Topics: {_join(r.get('topics'))}.")


def _achievement_text(r: dict) -> str:
    return (f"Achievement: {r.get('title', '')} ({r.get('category', '')}). "
            f"{r.get('description', '')} {r.get('impact', '')} "
            f"Skills: {_join(r.get('skills_demonstrated'))}.")


def _activity_text(r: dict) -> str:
    return (f"{r.get('role', '')} — {r.get('activity_name', '')} at "
            f"{r.get('organization', '')}. {r.get('description', '')} "
            f"Skills: {_join(r.get('skills_demonstrated'))}.")


def _cv_text(r: dict) -> str:
    return (f"CV example for {r.get('target_role', '')} in {r.get('industry', '')}. "
            f"{r.get('summary', '')} {r.get('cv_text', '')}")


def _cl_text(r: dict) -> str:
    return (f"Cover letter for {r.get('target_role', '')} in "
            f"{r.get('industry', '')}. {r.get('cover_letter', '')}")


def _learning_text(r: dict) -> str:
    # These records already carry an embedding_text; fall back to the lesson.
    return r.get("embedding_text") or _sub(r, "lesson").get("summary", "")


# --- (file, id_field, type, collection, text_builder, extra-metadata) --------
SOURCES = [
    ("profile/projects.json", "project_id", "project", "profile",
     _project_text, lambda r: {"title": _sub(r, "basic_info").get("title", "")}),
    ("profile/work_experience.json", "experience_id", "work_experience", "profile",
     _work_text, lambda r: {"company": r.get("company", ""), "role": r.get("role", "")}),
    ("profile/education.json", "education_id", "education", "profile",
     _education_text, lambda r: {"degree": r.get("degree", ""), "major": r.get("major", "")}),
    ("profile/skills.json", "skill_id", "skill", "profile",
     _skill_text, lambda r: {"name": r.get("name", ""), "category": r.get("category", "")}),
    ("profile/coursework.json", "course_id", "coursework", "profile",
     _course_text, lambda r: {"course": r.get("course_name", "")}),
    ("profile/achievements.json", "achievement_id", "achievement", "profile",
     _achievement_text, lambda r: {"category": r.get("category", "")}),
    ("profile/extracurriculars.json", "activity_id", "extracurricular", "profile",
     _activity_text, lambda r: {"activity": r.get("activity_name", "")}),
    ("documents/cv_examples.json", "example_id", "cv_example", "documents",
     _cv_text, lambda r: {"target_role": r.get("target_role", ""), "industry": r.get("industry", "")}),
    ("documents/cover_letter_examples.json", "example_id", "cover_letter_example", "documents",
     _cl_text, lambda r: {"target_role": r.get("target_role", ""), "industry": r.get("industry", "")}),
    ("learning/agent_learnings.json", "learning_id", "agent_learning", "learning",
     _learning_text, lambda r: {"agent": r.get("agent_name", ""), "task_type": r.get("task_type", "")}),
]

COLLECTIONS = ("profile", "documents", "learning")
STAGING_SUFFIX = "__staging"     # a rebuild embeds into <name>__staging, then swaps it in

# --- user-entered records: profile/manual_entries.json ------------------------
# Two live writers append to this file and embed what they wrote the moment they
# write it. A rebuild resets "profile", so it has to re-embed them too, and what
# it embeds must equal what the live writer embedded. Each pair below is a
# contract with that writer: change one, change both (L1 in logic.md).
MANUAL_FILE = "profile/manual_entries.json"
GAP_SECTION = "gap_answers"        # learning/profile_store.py:save_gap_answers
GAP_TYPE = "gap_answer"            # == learning/profile_store.py:RECORD_TYPE
# == backend/routes/profile.py:SECTION_TYPES
BUILD_PROFILE_TYPES = {
    "projects": "project",
    "skills": "skill",
    "achievements": "achievement",
    "education": "education",
    "internships": "work_experience",
    "extras": "extracurricular",
}


def _gap_answer_text(entry: dict) -> str:
    # The polished answer, verbatim: what profile_store.index_gap_answers embeds.
    return ((entry.get("record") or {}).get("content") or "").strip()


def _build_profile_text(entry: dict) -> str:
    # Same string as backend/routes/profile.py:_entry_text. Lists fold into the
    # text because Chroma metadata is scalars only.
    parts = []
    for key, value in (entry.get("record") or {}).items():
        if isinstance(value, (list, tuple)):
            value = ", ".join(str(v) for v in value)
        value = str(value).strip()
        if value:
            parts.append(f"{key.replace('_', ' ')}: {value}")
    return f"{entry.get('section', '')}. " + " ".join(parts)


def _manual_row(entry: dict):
    """One manual entry -> (count_key, record type, text, metadata), or None to skip it."""
    section = entry.get("section")
    if section == GAP_SECTION:
        inner = entry.get("record") or {}
        meta = {
            "type": GAP_TYPE,
            "source_id": entry["id"],
            "requirement": inner.get("requirement", ""),
            "category": inner.get("category", ""),
            "skills": ", ".join(inner.get("skills") or []),
        }
        return "gap_answer", GAP_TYPE, _gap_answer_text(entry), meta
    if section in BUILD_PROFILE_TYPES:
        rtype = BUILD_PROFILE_TYPES[section]
        meta = {"type": rtype, "source_id": entry["id"], "section": section, "source": "build_profile"}
        return "build_profile", rtype, _build_profile_text(entry), meta
    log.warning("%s: entry %s has unknown section %r, not indexed", MANUAL_FILE, entry["id"], section)
    return None


def _manual_rows(entries: list) -> dict[str, tuple[list, list, list]]:
    """manual_entries.json -> {count_key: (ids, texts, metadatas)}.

    count_key is "gap_answer" or "build_profile", not the record type: a
    Build-Profile "skill" and a fixture "skill" share a type, and `build`'s
    counts would otherwise merge them. Entries that cannot be indexed are
    skipped with a warning, as the live writers skip them. A malformed entry
    (no id, a duplicate id, a field of the wrong shape) raises, naming the file
    and the entry, before anything is reset.
    """
    if not entries:                     # missing file, [], {} or null: nothing to index
        return {}
    if not isinstance(entries, list):
        raise ValueError(f"{MANUAL_FILE}: expected a list of entries, found {type(entries).__name__}")
    rows: dict[str, tuple[list, list, list]] = {}
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or "id" not in entry:
            raise ValueError(f"{MANUAL_FILE}: entry without an 'id': {str(entry)[:80]}")
        # A hand-edited field of the wrong shape ("record": "text", "skills": 3)
        # raised AttributeError/TypeError with no file or id, as a fixture's
        # null once did (#80.3). Name both, the way the fixture path does.
        try:
            row = _manual_row(entry)
        except Exception as exc:
            raise ValueError(
                f"{MANUAL_FILE}: entry {entry['id']!r} could not be indexed "
                f"({type(exc).__name__}: {exc})"
            ) from exc
        if row is None:
            continue
        key, rtype, text, meta = row
        if not text.strip():
            log.warning("%s: entry %s has no text, not indexed", MANUAL_FILE, entry["id"])
            continue
        id_ = f"{rtype}:{entry['id']}"
        if id_ in seen:
            raise ValueError(f"{MANUAL_FILE}: two entries share the id {entry['id']!r}")
        seen.add(id_)
        ids, texts, metas = rows.setdefault(key, ([], [], []))
        ids.append(id_)
        texts.append(text)
        metas.append(meta)
    return rows


def build(store: VectorStore, kb_dir: Path | None = None, reset: bool = True) -> dict[str, int]:
    """Embed and index every fixture, then the user's manual entries.

    Returns {record_type: count}, plus "gap_answer" and "build_profile" counts
    for the manual entries (their types overlap the fixtures', so they are
    counted by origin).
    """
    kb_dir = kb_dir or config.KB_DIR

    # Phase 1: build every record first. A bad record raises here, before reset
    # touches the old index (#65.2).
    batches = []
    for rel, id_field, rtype, collection, text_fn, meta_fn in SOURCES:
        records = _load(kb_dir / rel)
        if not records:
            continue
        ids, texts, metas = [], [], []
        for r in records:
            if id_field not in r:
                raise KeyError(
                    f"{rel}: record missing its id field '{id_field}': {str(r)[:80]}"
                )
            # Any failure building one record names the file and the id, the way
            # the missing-id KeyError above already does (#80.3).
            try:
                ids.append(f"{rtype}:{r[id_field]}")
                texts.append(text_fn(r))
                meta = {"type": rtype, "source_id": r[id_field]}
                meta.update({k: v for k, v in meta_fn(r).items() if v})
                metas.append(meta)
            except Exception as exc:
                raise ValueError(
                    f"{rel}: record {r[id_field]!r} could not be indexed "
                    f"({type(exc).__name__}: {exc})"
                ) from exc
        batches.append((rtype, collection, ids, texts, metas))

    # User-entered records go in after the fixtures, validated in the same phase.
    manual = _manual_rows(_load(kb_dir / MANUAL_FILE))
    for key, (ids, texts, metas) in manual.items():
        batches.append((key, "profile", ids, texts, metas))

    # Phase 2: write. Without a reset it is an upsert straight into the live
    # collections. With one, everything is embedded into staging collections and
    # only swapped in once all of it worked, so a failure in `store.add` (embedder
    # crash, disk) leaves the old index untouched instead of half-built (#65.2).
    counts: dict[str, int] = {}
    if not reset:
        for rtype, collection, ids, texts, metas in batches:
            store.add(collection, ids, texts, metas)
            counts[rtype] = len(ids)
        return counts

    staged = {name: name + STAGING_SUFFIX for name in COLLECTIONS}
    try:
        for target in staged.values():
            store.drop_collection(target)               # a crashed earlier build's leftovers
        used = set()
        for rtype, collection, ids, texts, metas in batches:
            store.add(staged[collection], ids, texts, metas)
            used.add(collection)
            counts[rtype] = len(ids)
        # A collection with no records is removed, as the old reset did.
        store.swap({name: staged[name] if name in used else None for name in COLLECTIONS})
    except Exception:
        for target in staged.values():
            try:
                store.drop_collection(target)
            except Exception:
                log.exception("could not drop staging collection %r", target)
        raise
    return counts
