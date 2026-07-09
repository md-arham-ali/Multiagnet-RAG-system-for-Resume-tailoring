"""
ONE TIME RUN ONLY< FOR BUILD!!!
Load the knowledge_base/*.json fixtures into the vector store.

Three collections:
  - "profile"   : projects, work_experience, education, skills, coursework,
                  achievements, extracurriculars   (the candidate's evidence)
  - "documents" : cv_examples, cover_letter_examples   (examples / templates)
  - "learning"  : agent_learnings   (exemplars, retrieved by role type)

The do-not-claim list is intentionally NOT here: it is a hard constraint loaded
whole and checked exhaustively, never embedded.

Each record becomes (id, text, metadata):
  - text     : a short human-readable summary -> this is what we embed
  - metadata : a few scalar fields for filtering (Chroma metadata = scalars only,
               so list fields go into the text, not the metadata)
"""

from __future__ import annotations

import json
from pathlib import Path

import config
from vectordb.store import VectorStore


def _load(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _join(values, n: int = 8) -> str:
    return ", ".join(str(v) for v in (values or [])[:n])


# --- text builders: turn a record into the string we embed -------------------
def _project_text(r: dict) -> str:
    bi = r.get("basic_info", {})
    return (f"Project: {bi.get('title', '')}. Domain: {_join(bi.get('domain'))}. "
            f"{r.get('problem', {}).get('business_problem', '')} "
            f"Skills: {_join(r.get('skills_demonstrated'))}. "
            f"{r.get('resume_material', {}).get('one_line', '')}")


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
    return r.get("embedding_text") or r.get("lesson", {}).get("summary", "")


# --- (file, id_field, type, collection, text_builder, extra-metadata) --------
SOURCES = [
    ("profile/projects.json", "project_id", "project", "profile",
     _project_text, lambda r: {"title": r.get("basic_info", {}).get("title", "")}),
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


def build(store: VectorStore, kb_dir: Path | None = None, reset: bool = True) -> dict[str, int]:
    """Embed and index every fixture. Returns {record_type: count}."""
    kb_dir = kb_dir or config.KB_DIR
    if reset:
        for name in COLLECTIONS:
            store.reset(name)

    counts: dict[str, int] = {}
    for rel, id_field, rtype, collection, text_fn, meta_fn in SOURCES:
        records = _load(kb_dir / rel)
        if not records:
            continue
        ids, texts, metas = [], [], []
        for r in records:
            ids.append(f"{rtype}:{r[id_field]}")
            texts.append(text_fn(r))
            meta = {"type": rtype, "source_id": r[id_field]}
            meta.update({k: v for k, v in meta_fn(r).items() if v})
            metas.append(meta)
        store.add(collection, ids, texts, metas)
        counts[rtype] = len(ids)
    return counts
