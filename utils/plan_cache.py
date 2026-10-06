"""
On-disk cache for the Document planner's answer (LLM call 1), keyed by the
fingerprint of the exact call (agents/document.py, `_plan`).

The plan saved in graph state only lives as long as one run, and only if the node
gets to return. This cache outlives both: a fresh process, a new run on the same
inputs, or a node that failed after call 1 (for instance on a rate limit in call 2)
finds the answer here instead of paying for the call again.

It stores the model's RAW answer, not the resolved plan. Resolving is deterministic
code, so a change to it applies to cached answers too.

The cache never fails a run: an unreadable or unwritable file is a miss, not an error.

    from utils.plan_cache import load_plan, save_plan
    raw = load_plan(key) or call_the_model()
    save_plan(key, raw)
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Optional

import config
from state.state import VerdictSet
from utils.trace import log

_KEY = re.compile(r"[0-9a-f]{8,64}")


def _path(key: str) -> Path:
    if not _KEY.fullmatch(key):
        raise ValueError(f"plan cache key must be a hex digest, got {key!r}")
    return config.PLAN_CACHE_DIR / f"{key}.json"


def load_plan(key: str) -> Optional[VerdictSet]:
    # in : key = the call fingerprint (a hex digest)
    # out: the cached model answer, or None when the cache is off, the key is unknown, or the file
    #      is unreadable or no longer fits VerdictSet (a schema change makes old answers misses)
    if not config.PLAN_CACHE:
        return None
    try:
        return VerdictSet.model_validate_json(_path(key).read_text(encoding="utf-8"))
    except (OSError, ValueError):          # missing file, unreadable file, bad JSON, wrong shape
        return None


def save_plan(key: str, plan: VerdictSet) -> None:
    # Writes the answer atomically (temp file, then rename), so a reader never sees half a file.
    # in : key = the call fingerprint, plan = the model's raw answer
    # A write that fails is logged and swallowed: the cache is an optimisation.
    if not config.PLAN_CACHE:
        return
    target = _path(key)
    tmp = None
    try:
        config.PLAN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=config.PLAN_CACHE_DIR, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(plan.model_dump_json(indent=2))
        os.replace(tmp, target)
    except OSError as exc:
        log(f"plan cache: could not write {target.name}: {exc}")
        if tmp is not None:
            Path(tmp).unlink(missing_ok=True)
