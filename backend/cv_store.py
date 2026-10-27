"""
CV storage: one owner, one small index, PDFs on disk under a server-chosen name.

Pure functions, no FastAPI import (mirrors backend/auth/store.py's split between
HTTP concerns and the data they touch). Every function takes `owner` first and
only ever reads or writes that owner's own subtree
(config.CV_UPLOADS_DIR/{owner}/cv/) - there is no cross-owner listing, so a
confirm/delete on an id this owner never uploaded is indistinguishable from an
id that does not exist anywhere, and both are reported the same way by the
caller (403 - see backend/routes/cv.py).

Two-step commit: `ingest_pending` writes the file and indexes it as "pending";
`confirm` is what makes it the owner's current CV. A pending upload nobody
confirms just sits there until the next upload (which evicts it) or an
explicit delete - no background sweep yet (bugs.md's "Unconfirmed uploads"
note).

File name is `{sha256(content)[:12]}.pdf`, never the uploaded name: this is
what keeps `agents/CV_Link.py`'s skip-if-already-linked check
(`cv_tree.source_file == pdf.name`) correct across re-runs, and keeps PII out
of the path. Re-uploading byte-identical content is a no-op on an already
confirmed CV, so it can't accidentally demote the current CV back to pending.

See backend/bugs.md, "2026-10-09 (later)" and frontend/design.md for the full
contract this backs.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import config
from backend.jsonstore import lock_for, read_json, update_json, write_json
from state.state import NodeKind, SectionType


class CvUnreadable(Exception):
    """Not a readable PDF, despite passing the %PDF- magic-byte check."""


class CvTooManyPages(Exception):
    pass


class CvNoText(Exception):
    """No text layer at all - a scanned or image-only PDF."""


class CvNoSections(Exception):
    """Text was read, but no known section heading was found."""


_SUMMARY_KEYS = ("id", "filename", "size_bytes", "pages", "uploaded_at")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cv_dir(owner: str) -> Path:
    # Fail closed (backend/bugs.md "2026-10-09 (design)" §2): a falsy owner
    # must never resolve to CV_UPLOADS_DIR/cv - a shared, unnamespaced path
    # every caller passing "" or None by mistake would land on together.
    if not owner:
        raise ValueError("cv_store requires a non-empty owner")
    return config.CV_UPLOADS_DIR / owner / "cv"


def _index_path(owner: str) -> Path:
    return _cv_dir(owner) / "index.json"


def _empty_index() -> dict:
    return {"current_id": None, "cvs": {}}


def _public_summary(entry: dict) -> dict:
    return {k: entry[k] for k in _SUMMARY_KEYS}


def _delete_file(owner: str, entry: dict) -> None:
    stored = entry.get("stored_name")
    if stored:
        (_cv_dir(owner) / stored).unlink(missing_ok=True)


def _build_preview(tree, lines) -> dict:
    """CvPreview = {sections: [{type, title, entries: [{header, lines}]}], warnings}.

    Walked generically off NodeKind, not per SectionType, so a new section type
    in the parser needs no change here.
    """
    from utils.cv_handling.cv_extract import line_problems

    sections = []
    for sec in tree.root.children:
        if sec.section_type == SectionType.HEADER:
            continue  # identity info (name/email/phone) - not shown in the preview
        entries = []
        for child in sec.children:
            if child.kind == NodeKind.BULLET:
                # a bullet with no entry wrapper directly under the section
                if child.text:
                    entries.append({"header": None, "lines": [child.text]})
                continue
            header = child.title or None if child.kind == NodeKind.ENTRY else None
            body = [grand.text for grand in child.children if grand.text]
            if not body and child.text and child.text != header:
                body = [child.text]
            entries.append({"header": header, "lines": body})
        sections.append({
            "type": sec.section_type.value,
            "title": sec.title or sec.section_type.value.replace("_", " ").title(),
            "entries": entries,
        })

    warnings = []
    found = {s.section_type for s in tree.root.children}
    for stype, label in (
        (SectionType.EXPERIENCE, "Experience"),
        (SectionType.PROJECTS, "Projects"),
        (SectionType.SKILLS, "Skills"),
        (SectionType.EDUCATION, "Education"),
    ):
        if stype not in found:
            warnings.append(f"No {label} section found")
    problems = line_problems(tree, lines)
    if problems:
        warnings.append(f"{len(problems)} line(s) could not be placed in a section")
    return {"sections": sections, "warnings": warnings}


def current_summary(owner: str) -> dict | None:
    """The owner's current (confirmed) CV, or None. Never raises - GET /profile/cv
    answers {"cv": null} for "no CV yet", never 404 (frontend/bugs.md, Round 12)."""
    index = read_json(_index_path(owner), default=None)
    if not index:
        return None
    entry = index["cvs"].get(index.get("current_id") or "")
    return _public_summary(entry) if entry and entry["status"] == "confirmed" else None


def resolve_path(owner: str) -> tuple[Path, dict] | None:
    """(file path, CvSummary) for the owner's current CV, for a run to tailor.
    None if there is none, or its file has gone missing from under the index."""
    index = read_json(_index_path(owner), default=None)
    if not index:
        return None
    entry = index["cvs"].get(index.get("current_id") or "")
    if not entry or entry["status"] != "confirmed":
        return None
    path = _cv_dir(owner) / entry["stored_name"]
    if not path.is_file():
        return None
    return path, _public_summary(entry)


def export_index(owner: str) -> dict | None:
    """This owner's whole CV index, or None if they have never uploaded one.

    For the account's own export (backend/routes/me.py) - unlike
    `current_summary`, it keeps `status` and `stored_name`, because the export
    ships the files beside it and they have to be identifiable. Still this
    owner's subtree only; there is no cross-owner read here.
    """
    index = read_json(_index_path(owner), default=None)
    return index or None


def export_files(owner: str):
    """(stored_name, bytes) for every CV file this owner still has on disk.

    Reads only names the index itself holds - never a directory listing - so a
    stray file dropped into the folder cannot be exported, and `index.json`
    itself is not re-shipped as a CV.
    """
    index = read_json(_index_path(owner), default=None) or {}
    for entry in (index.get("cvs") or {}).values():
        stored = entry.get("stored_name")
        if not stored:
            continue
        path = _cv_dir(owner) / stored
        if path.is_file():
            yield stored, path.read_bytes()


def ingest_pending(owner: str, content: bytes, filename: str, max_pages: int) -> tuple[dict, dict]:
    """Validate + store `content` as a pending CV. Runs CPU work (PDF parsing),
    so the caller (backend/routes/cv.py) must run this off the event loop.

    Raises CvUnreadable / CvTooManyPages / CvNoText / CvNoSections; the file is
    cleaned up on every failure path, nothing partial is left on disk.
    """
    from pypdf import PdfReader

    from utils.cv_handling.cv_extract import has_sections, has_text, parse_cv

    cv_dir = _cv_dir(owner)
    cv_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = cv_dir / f".tmp-{uuid.uuid4().hex}.pdf"
    tmp_path.write_bytes(content)
    try:
        try:
            n_pages = len(PdfReader(str(tmp_path)).pages)
        except Exception as exc:
            raise CvUnreadable(str(exc)) from exc
        if n_pages > max_pages:
            raise CvTooManyPages(n_pages)

        try:
            tree, lines = parse_cv(tmp_path)
        except Exception as exc:
            raise CvUnreadable(str(exc)) from exc
        # Same two predicates agents/CV_Link.py uses, so the upload path and the
        # pipeline path cannot drift apart again (#79 item 4). The exception
        # types - and so the messages the UI shows - are unchanged.
        if not has_text(lines):
            raise CvNoText()
        if not has_sections(tree):
            raise CvNoSections()

        # Before the file moves (#68 item 5): a preview failure after it used
        # to leave the PDF in place with no index entry - unlisted, and out of
        # reach of the owner's own delete.
        preview = _build_preview(tree, lines)
        sha = hashlib.sha256(content).hexdigest()[:12]
        summary = {
            "id": sha,
            "filename": filename,
            "size_bytes": len(content),
            "pages": n_pages,
            "uploaded_at": _now(),
        }
        _commit_pending(owner, tmp_path, summary)
    finally:
        tmp_path.unlink(missing_ok=True)  # moved on success; gone either way
    return summary, preview


def _commit_pending(owner: str, tmp_path: Path, summary: dict) -> None:
    """Move a validated upload into place and index it as pending, under the
    index's lock so the file and its entry land together (#68 item 5).

    On a failed index write the moved file is removed only if this upload
    created it: `{sha}.pdf` may already be an indexed CV with identical bytes.
    Evicted pending files go only after the write, so a failure never leaves
    the index naming a file that's already gone.
    """
    index_path = _index_path(owner)
    sha = summary["id"]
    stored_name = f"{sha}.pdf"
    target = _cv_dir(owner) / stored_name
    with lock_for(index_path):
        index = read_json(index_path, default=_empty_index()) or _empty_index()
        existing = index["cvs"].get(sha)
        if existing and existing["status"] == "confirmed":
            return  # byte-identical re-upload of the current CV: no-op
        evicted = [cid for cid, entry in index["cvs"].items() if entry["status"] == "pending" and cid != sha]
        evicted = [index["cvs"].pop(cid) for cid in evicted]
        index["cvs"][sha] = {**summary, "stored_name": stored_name, "status": "pending"}

        created = not target.exists()
        os.replace(tmp_path, target)
        try:
            write_json(index_path, index)
        except Exception:
            if created:
                target.unlink(missing_ok=True)
            raise
        for entry in evicted:
            _delete_file(owner, entry)


def confirm(owner: str, cv_id: str) -> dict | None:
    """Make `cv_id` the owner's current CV. None if it is not in their index -
    not theirs, or never existed; the caller reports both as 403."""

    def update(index):
        index = index or _empty_index()
        entry = index["cvs"].get(cv_id)
        if entry is None:
            return None, None
        entry["status"] = "confirmed"
        index["current_id"] = cv_id
        return index, entry

    entry = update_json(_index_path(owner), update, default=_empty_index())
    return _public_summary(entry) if entry else None


def delete(owner: str, cv_id: str) -> bool:
    """Remove a pending upload or a CV no run references (the latter check is
    not built yet - see backend/bugs.md item 2's note on this)."""

    def update(index):
        index = index or _empty_index()
        entry = index["cvs"].pop(cv_id, None)
        if entry is None:
            return None, False
        _delete_file(owner, entry)
        if index.get("current_id") == cv_id:
            index["current_id"] = None
        return index, True

    return update_json(_index_path(owner), update, default=_empty_index())
