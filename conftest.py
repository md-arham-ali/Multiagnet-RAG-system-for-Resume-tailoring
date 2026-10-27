"""Pytest hooks: save every run's result to logs/testruns/.

Each session writes pytest-<timestamp>.json (summary, every test's outcome and
duration, the full failure text) and refreshes pytest-latest.json. logs/ is
git-ignored; copy the summary line into context/ if it should be kept.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

import pytest

RESULTS_DIR = Path(__file__).resolve().parent / "logs" / "testruns"
_results: dict[str, dict] = {}
_started = time.time()


# Fixtures that put several parts together (a graph, the HTTP app, a scripted provider, a fake world).
_MEDIUM_FIXTURES = {"client", "together", "pipeline", "ledger", "world", "offline_world", "fake_llm", "gate_io",
                    "lane", "stub", "linker", "search_store", "kb_tree", "loader_env", "snapshots"}
_MEDIUM_SOURCE = ("build_graph", ".stream(", "StateGraph", "TestClient", "subprocess", "_python(", "threading",
                  "ThreadPool", "read_text(", ".glob(", "inspect.getsource")


def _tier(item) -> str:
    """The cost level of a test, for choosing what to run. Decided from the test itself:
    heavy  (marker real_models): loads the real embedder / reranker. This machine only.
    medium: puts parts together (graph, HTTP app, scripted provider, threads, a fresh process, reads the repo).
    easy:   one function or one store, nothing else."""
    if item.name.startswith("test_real_"):
        return "real_models"
    if _MEDIUM_FIXTURES & set(item.fixturenames):
        return "medium"
    try:
        import inspect
        src = inspect.getsource(item.function)
    except (OSError, TypeError):
        return "medium"
    return "medium" if any(token in src for token in _MEDIUM_SOURCE) else "easy"


def pytest_collection_modifyitems(items):
    #   pytest -m easy                 seconds: the logic checks
    #   pytest -m "easy or medium"     = what CI runs (same as -m "not real_models")
    #   RUN_REAL_EMBED=1 RUN_REAL_RERANK=1 pytest -m real_models     heavy, this machine only
    for item in items:
        item.add_marker(getattr(pytest.mark, _tier(item)))


def pytest_runtest_logreport(report):
    # setup/teardown errors count too; the call phase is the test's own verdict
    if report.when == "call" or (report.when != "call" and report.outcome != "passed"):
        entry = _results.setdefault(report.nodeid, {"nodeid": report.nodeid})
        entry["outcome"] = "error" if report.when != "call" and report.outcome == "failed" else report.outcome
        if hasattr(report, "wasxfail"):   # pytest reports xfail/xpass as skipped/passed
            entry["outcome"] = "xfailed" if report.outcome == "skipped" else "xpassed"
            entry["xfail_reason"] = report.wasxfail
        entry["phase"] = report.when
        entry["duration_s"] = round(getattr(report, "duration", 0.0), 3)
        if report.outcome == "failed":
            entry["failure"] = str(report.longrepr)


def pytest_sessionfinish(session, exitstatus):
    if os.getenv("CI"):             # a CI runner keeps no logs/ folder; its own log is the record
        return
    try:
        counts: dict[str, int] = {}
        for r in _results.values():
            counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        doc = {
            "kind": "pytest",
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "duration_s": round(time.time() - _started, 1),
            "args": list(session.config.invocation_params.args),
            "exit_status": int(exitstatus),
            "summary": counts,
            "failed": [r["nodeid"] for r in _results.values() if r["outcome"] in ("failed", "error")],
            "tests": list(_results.values()),
        }
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        text = json.dumps(doc, indent=2)
        (RESULTS_DIR / f"pytest-{stamp}.json").write_text(text)
        (RESULTS_DIR / "pytest-latest.json").write_text(text)
    except Exception as exc:  # never let result-saving break a test run
        print(f"\n[conftest] could not save test results: {exc}")
