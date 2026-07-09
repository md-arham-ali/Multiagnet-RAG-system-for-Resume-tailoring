"""
TEMPORARY workflow tracing — so nothing looks 'frozen'.

Prints what each slow step is doing and how long it took, with flush=True so the
message appears BEFORE the wait (not after). On by default; silence with TRACE=0.

    from utils.trace import step, log
    with step("loading model"):   # prints "⏳ loading model ..." then "✓ ... (2.3s)"
        heavy()
    log("quick note")             # prints "   … quick note"

Remove this module (and its call sites) once you no longer need the visibility.
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
    """Announce a slow step before it runs, then report its duration."""
    if _ON:
        print(f"⏳ {msg} ...", flush=True)
    start = time.perf_counter()
    try:
        yield
    finally:
        if _ON:
            print(f"✓ {msg}  ({time.perf_counter() - start:.1f}s)", flush=True)
