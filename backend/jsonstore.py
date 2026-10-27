"""
Atomic JSON file helpers.

Same tmp-file + `os.replace` pattern as `learning/store.py:38-51`: a crash
mid-write can never truncate the file, because readers only ever see the old
inode or the new one, never a half-written one. `os.replace` is atomic on POSIX.

Lifted into its own module here because three separate callers now need it (the
auth store, profile entries, and run logs) and `learning/store.py`'s copy is
private to that package.

`write_json` alone is not enough for a file with more than one writer:
read-modify-write is three steps and only the last is atomic, so two overlapping
writers lose one another's changes entirely. `update_json` holds a per-path lock
across all three.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable

# One lock per file, created on demand. Per path rather than one global lock so
# an edit to manual_entries.json does not serialise against an unrelated file.
_locks: dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()


def _lock_for(path: Path) -> threading.RLock:
    key = str(Path(path).resolve())  # so two spellings of one file share a lock
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = _locks[key] = threading.RLock()
        return lock


def lock_for(path: Path) -> threading.RLock:
    """The lock `update_json` holds for `path`. For a read-modify-write whose
    step also touches something outside the file (cv_store moves a PDF into
    place beside its index), so both land together. Re-entrant."""
    return _lock_for(path)


def read_json(path: Path, default: Any = None) -> Any:
    """Parse `path`, or return `default` (a new list by default) if absent/empty."""
    if default is None:
        default = []
    if not path.exists():
        return default
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return default
    return json.loads(text)


def read_records(path: Path) -> list:
    """Rows from a store where "no data" and "damaged" must not look alike.

    `read_json` answers `[]` for a file that is absent, empty or whitespace —
    right for a cache, wrong for the auth stores, where "no records" is a
    *decision*: no account has that name, no token is valid, no request is
    waiting. A present-but-empty file is damage, and reading it as "none"
    silently (a) answers those questions wrongly and (b) becomes the base for
    the next read-modify-write, so one transient empty file permanently
    destroys every row the store had. Reproduced before this was written: an
    empty `profiles.json` let `create_profile` mint a second profile for a
    name that already had one — the collision guard bug#68 item 1 exists for —
    and the next write left only that new row on disk.

    So: `[]` only when the file does not exist (a first run), and otherwise a
    raise. A decode error is deliberately left to propagate from `json.loads`
    unchanged — `tokens.json` corrupt raising `JSONDecodeError` is a pinned
    decision (`test_the_admin_still_gets_in_when_tokens_json_is_corrupt`), and
    `ADMIN_TOKEN` is compared before any of these reads, so the admin can
    still sign in and repair the file.
    """
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"{path.name} is present but empty; refusing to read it as 'no records'")
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError(f"{path.name} holds {type(data).__name__}, not a list of records")
    return data


def write_json(path: Path, data: Any) -> None:
    """Write `data` as JSON atomically, creating parent directories as needed.

    Each call gets its own temp file in the target's folder. A shared
    `<file>.tmp` let two writers on one path rename each other's half-written
    file into place - a torn JSON file under 16 threads - or find it already
    gone (`FileNotFoundError`) (bugs_audit_fixed.md #62 item 1).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, ensure_ascii=False)   # serialise first: a TypeError leaves no temp file
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        # mkstemp makes the file 0600; keep the mode the file already had (0644 if new).
        os.chmod(tmp, (path.stat().st_mode & 0o777) if path.exists() else 0o644)
        os.replace(tmp, path)  # atomic on POSIX
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def update_json(path: Path, fn: Callable[[Any], tuple[Any, Any]], default: Any = None) -> Any:
    """Read-modify-write `path` under its lock. Use this for any file with more
    than one writer.

    `fn` receives the parsed contents and returns `(data_to_write, result)`.
    Return `None` as the data to skip the write entirely (nothing changed, e.g. a
    lookup that found no match); `result` is handed back to the caller either way.

    NOTE this only serialises callers that come through here (or hold
    `lock_for(path)`), and only within one process. A writer that calls
    read_json/write_json itself still races.
    """
    with _lock_for(path):
        data, result = fn(read_json(path, default=default))
        if data is not None:
            write_json(path, data)
        return result
