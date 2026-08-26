"""
TEMPORARY tracing, so a slow step never looks frozen.

flush=True matters: the message has to print BEFORE the wait, otherwise it is
useless for the exact case it exists for. On by default, TRACE=0 silences it.

    with step("loading model"):   # "⏳ loading model ..." then "✓ ... (2.3s)"
        heavy()
    log("quick note")

Delete this module and its call sites when the visibility isn't needed.
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager

_ON = os.getenv("TRACE", "1").strip().lower() not in {"0", "false", "no", ""}


def log(msg: str) -> None:
    if _ON:
        print(f"   … {msg}", flush=True)


@contextmanager
def step(msg: str):
    """Announce a slow step, then report how long it took."""
    if _ON:
        print(f"⏳ {msg} ...", flush=True)
    start = time.perf_counter()
    try:
        yield
    finally:
        if _ON:
            print(f"✓ {msg}  ({time.perf_counter() - start:.1f}s)", flush=True)
