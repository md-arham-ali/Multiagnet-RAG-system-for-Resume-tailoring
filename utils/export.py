"""
Final-document export (Stage 0 plan §16). Pure file I/O, no model.

    outputs/{owner}/{date}_{run_id}_{role-slug}.md   the CV as the run delivered it
    outputs/{owner}/{date}_{run_id}_{role-slug}.txt  the same, Markdown stripped

`owner` stands in for `profile_id` until the profile layer exists (§B): the
backend passes the run owner's token id, the CLI passes "cli". Every path part
is slugged, so no caller-supplied text can climb out of OUTPUTS_DIR.
Writes are atomic (tmp + os.replace), like every other store in the project.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path

import config
from state.state import Document

_UNSAFE = re.compile(r"[^a-z0-9_-]+")


def _slug(text: str | None, fallback: str, limit: int = 40) -> str:
    slug = _UNSAFE.sub("-", (text or "").lower()).strip("-")[:limit].strip("-")
    return slug or fallback


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def plain_text(markdown: str) -> str:
    """The CV without Markdown markup: headings lose their #, bold loses its **,
    bullets become "•". Only the markup render_markdown emits is handled."""
    lines = []
    for line in markdown.splitlines():
        line = re.sub(r"^#{1,6}\s+", "", line)
        line = re.sub(r"^[-*]\s+", "• ", line)
        line = line.replace("**", "").rstrip()   # also drops the "  " Markdown line break
        lines.append(line)
    return "\n".join(lines).strip() + "\n"


def export_document(document: Document, *, owner: str, run_id: str,
                    role_title: str | None = None, when: datetime | None = None) -> dict[str, Path]:
    """Write the final document as .md and .txt. Returns {"md": path, "txt": path}."""
    when = when or datetime.now(timezone.utc)
    folder = config.OUTPUTS_DIR / _slug(owner, "unknown")
    stem = f"{when:%Y-%m-%d}_{_slug(run_id, 'run')}_{_slug(role_title, document.kind or 'document')}"
    paths = {"md": folder / f"{stem}.md", "txt": folder / f"{stem}.txt"}
    _atomic_write(paths["md"], document.content)
    _atomic_write(paths["txt"], plain_text(document.content))
    return paths
