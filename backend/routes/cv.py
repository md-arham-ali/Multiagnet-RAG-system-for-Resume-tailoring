"""
CV upload - the PDF a run tailors.

Every route takes a `Scope` (backend/deps.py), not a raw `Identity` - the
account to touch comes only from the verified token, never from anything in
the request (backend/bugs.md "2026-10-09 (design)" §2). `backend/cv_store.py`
keys everything off `scope.profile_id` - the account, not a credential a
re-issue would replace (§1). No route ever takes a path from the client. A
`cv_id` that is not in the caller's own index - whether it belongs to someone
else or never existed - is reported as 403, never 404: this store has no
cross-owner listing to tell the two apart, and 403 keeps the "not yours"
discipline consistent with every other ownership check in this package. Never
401 - a 401 anywhere logs the caller out (backend/deps.py).

Upload is a two-step commit: POST stores the file and returns a preview but
does not make it current; confirm does. `GET` answers `{"cv": null}` for "no
CV yet", never 404 - the frontend reads a 404 there as "this backend has no CV
routes at all" (frontend/bugs.md, Round 12).

See backend/bugs.md, "2026-10-09 (later) - what the backend must build for a
user-supplied CV" and frontend/design.md for the full contract this implements.
Deliberately not yet covered here (left for a follow-up pass): stripping CV
text out of the existing cv_link SSE/run-log artifact (bugs.md item 4), and
exposing the unmatched-line count for gate 4 (item 5).
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, File, HTTPException, UploadFile

from backend import cv_store
from backend.deps import Caller

router = APIRouter(prefix="/profile/cv")

# design.md "Caps": 5 MB and 4 pages.
MAX_BYTES = 5 * 1024 * 1024
MAX_PAGES = 4
_CHUNK = 1024 * 1024


@router.get("")
def get_current_cv(scope: Caller):
    return {"cv": cv_store.current_summary(scope.profile_id)}


@router.post("", status_code=201)
async def upload_cv(scope: Caller, file: UploadFile = File(...)):
    # Read in chunks and stop at the cap - never load the whole body first and
    # check after (design.md "Caps").
    content = bytearray()
    while True:
        chunk = await file.read(_CHUNK)
        if not chunk:
            break
        content.extend(chunk)
        if len(content) > MAX_BYTES:
            raise HTTPException(413, "This PDF is larger than 5 MB.")
    content = bytes(content)
    # By magic bytes, not extension: a renamed .docx is still not a PDF.
    if not content.startswith(b"%PDF-"):
        raise HTTPException(415, "This file isn't a PDF.")

    try:
        # Parsing is CPU work with no model load (~1s), but it is still CPU
        # work: off the event loop, so one slow PDF can't stall every request.
        summary, preview = await asyncio.to_thread(
            cv_store.ingest_pending, scope.profile_id, content, file.filename or "cv.pdf", MAX_PAGES
        )
    except cv_store.CvTooManyPages:
        raise HTTPException(422, "too_many_pages")
    except cv_store.CvNoText:
        raise HTTPException(422, "no_text")
    except cv_store.CvNoSections:
        raise HTTPException(422, "no_sections")
    except cv_store.CvUnreadable:
        raise HTTPException(415, "This file isn't a PDF.")

    return {"cv": summary, "preview": preview}


@router.post("/{cv_id}/confirm")
def confirm_cv(cv_id: str, scope: Caller):
    summary = cv_store.confirm(scope.profile_id, cv_id)
    if summary is None:
        raise HTTPException(403, "Not your CV")
    return {"cv": summary}


@router.delete("/{cv_id}", status_code=204)
def delete_cv(cv_id: str, scope: Caller):
    if not cv_store.delete(scope.profile_id, cv_id):
        raise HTTPException(403, "Not your CV")
