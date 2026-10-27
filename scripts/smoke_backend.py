#!/usr/bin/env python3
"""
End-to-end smoke test of the bridge API, against a RUNNING server.

test_backend_api.py stubs the graph. This drives the real one, so it also covers
the offline/live switch, the four gates, and SSE over a real socket.

    .venv/bin/python -m uvicorn scripts.frontend_api:app --port 8000 &
    .venv/bin/python scripts/smoke_backend.py

Reads ADMIN_TOKEN from .env. Exits non-zero on the first failure.
"""

from __future__ import annotations

import json
import sys
import os
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

import config

BASE = os.getenv("SMOKE_BASE", "http://127.0.0.1:8000/api")
PASS, FAIL = "\033[32m✓\033[0m", "\033[31m✗\033[0m"
_failures = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global _failures
    if not ok:
        _failures += 1
    print(f"  {PASS if ok else FAIL} {label}{'' if ok else f'  -> {detail}'}")


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def gate_waits(c: httpx.Client, run_id: str, token: str, n: int, limit: float = 120.0) -> list[dict]:
    """Read the run's SSE until n gate_wait events have arrived (or the run ends).

    For a run parked on a gate: its stream never closes on its own. A read
    timeout (no event for the client's timeout) ends the read instead of the
    script, and the caller's check reports what did arrive.
    """
    seen: list[dict] = []
    deadline = time.time() + limit
    try:
        with c.stream("GET", f"/runs/{run_id}/events", params={"token": token}) as r:
            for line in r.iter_lines():
                if not line.startswith("data: "):
                    continue
                ev = json.loads(line[6:])
                if ev["type"] == "gate_wait":
                    seen.append(ev)
                if len(seen) >= n or ev["type"] in ("run_done", "run_stopped", "run_error") \
                        or time.time() > deadline:
                    break
    except httpx.HTTPError as exc:
        print(f"    (SSE read for {run_id} ended early: {type(exc).__name__})")
    return seen


def main() -> int:
    admin = config.ADMIN_TOKEN
    if not admin:
        print("ADMIN_TOKEN is not set in .env — cannot run.")
        return 2

    c = httpx.Client(base_url=BASE, timeout=httpx.Timeout(30.0, read=180.0))

    print("\n1. open + guarded routes")
    check("GET /health is open", c.get("/health").status_code == 200)
    for path in ("/config", "/auth/me", "/runs", "/kb", "/profile/entries"):
        code = c.get(path).status_code
        check(f"GET {path} without a token -> 401", code == 401, f"got {code}")

    print("\n2. admin identity")
    me = c.get("/auth/me", headers=auth(admin))
    check("admin /auth/me -> 200", me.status_code == 200, me.text[:80])
    check("admin runs_remaining is null", me.json().get("runs_remaining") is None)

    print("\n3. request -> approve -> login")
    name = f"smoke-{int(time.time())}"
    req = c.post("/auth/request-access", json={"identifier": name, "note": "smoke test"})
    check("POST /auth/request-access (open) -> 200", req.status_code == 200, req.text[:80])
    rid = req.json()["id"]

    listed = c.get("/auth/requests", headers=auth(admin))
    check("admin sees the request", any(r["id"] == rid for r in listed.json()["requests"]))

    approved = c.post(f"/auth/requests/{rid}/approve", headers=auth(admin))
    check("approve returns a raw token", "token" in approved.json(), approved.text[:80])
    token = approved.json()["token"]

    check("double approve -> 409", c.post(f"/auth/requests/{rid}/approve", headers=auth(admin)).status_code == 409)

    login = c.post("/auth/login", json={"token": token})
    check("login with the issued token -> 200", login.status_code == 200, login.text[:80])
    check("user starts with the configured allowance",
          login.json()["runs_remaining"] == config.DEFAULT_RUN_ALLOWANCE)
    check("bad token login -> 401", c.post("/auth/login", json={"token": "nope"}).status_code == 401)
    check("user hitting an admin route -> 403 (never 401)",
          c.get("/auth/requests", headers=auth(token)).status_code == 403)

    print("\n3b. the user adds a CV (a non-admin cannot start a run without a confirmed one)")
    cv_file = Path(config.CV_DEFAULT_PATH)
    if not cv_file.is_file():
        check("sample CV exists to upload", False, f"no file at {cv_file}")
        print(f"\n{_failures} CHECK(S) FAILED\n")
        return 1
    up = c.post("/profile/cv", files={"file": (cv_file.name, cv_file.read_bytes(), "application/pdf")},
                headers=auth(token))
    check("POST /profile/cv -> 201", up.status_code == 201, up.text[:200])
    cv_id = (up.json().get("cv") or {}).get("id") if up.status_code == 201 else None
    check("the upload returns a cv id", bool(cv_id), up.text[:200])
    if cv_id:
        conf = c.post(f"/profile/cv/{cv_id}/confirm", headers=auth(token))
        check("POST /profile/cv/{id}/confirm -> 200", conf.status_code == 200, conf.text[:200])

    print("\n4. offline pipeline through all four gates (real graph)")
    started = c.post("/runs", json={"job_description": "Python data engineer, SQL, ETL.",
                                    "mode": "offline", "pace_seconds": 0.05},
                     headers=auth(token))
    check("POST /runs -> 200", started.status_code == 200, started.text[:200])
    if started.status_code != 200:
        # Nothing below can run without a started run; say so instead of raising KeyError.
        print(f"\n{_failures} CHECK(S) FAILED (stopped: the run did not start)\n")
        return 1
    run_id = started.json()["run_id"]

    # ONE stream, open for the whole run. SSE replays the full history on every
    # connect, on purpose, so the frontend can rebuild the trail after a refresh.
    # Reconnecting per gate would re-count gates already answered. Answers go out
    # on a second client while this one stays open.
    poster = httpx.Client(base_url=BASE, timeout=httpx.Timeout(30.0, read=180.0))
    gates: list[tuple[str, str | None]] = []
    errored = None
    with c.stream("GET", f"/runs/{run_id}/events", params={"token": token}) as r:
        check("SSE stream opened", r.status_code == 200, f"status {r.status_code}")
        if r.status_code == 200:
            for line in r.iter_lines():
                if not line.startswith("data: "):
                    continue
                ev = json.loads(line[6:])
                if ev["type"] == "gate_wait":
                    gates.append((ev["node"], ev.get("artifact_node")))
                    poster.post(f"/runs/{run_id}/gate",
                                json={"decision": "approve", "feedback": "smoke"},
                                headers=auth(token))
                elif ev["type"] == "run_error":
                    errored = ev.get("error")
                    break
                elif ev["type"] in ("run_done", "run_stopped"):
                    break

    check("run did not error", errored is None, str(errored)[:200])
    check("four gates fired", len(gates) == 4, str(gates))
    check("gate 3 opens after cv_link and reviews the fit",
          len(gates) > 2 and gates[2] == ("cv_link", "matching"), str(gates[2:3]))
    check("final gate reviews the DOCUMENT, not the verifier",
          bool(gates) and gates[-1] == ("verifier", "document"), str(gates[-1:]))

    log = poster.get(f"/runs/{run_id}/log", headers=auth(token))
    check("run log readable by its owner", log.status_code == 200, log.text[:120])
    events = log.json().get("events", []) if log.status_code == 200 else []
    check("run completed", any(e["type"] == "run_done" for e in events))
    doc = [e for e in events if e["type"] == "node_done" and e["node"] == "document"]
    check("document artifact present in the trail", bool(doc))
    check("document is real: stub:false", bool(doc) and doc[0].get("stub") is False)
    ver = [e for e in events if e["type"] == "node_done" and e["node"] == "verifier"]
    check("placeholder agents flagged stub:true for the UI",
          bool(ver) and ver[0].get("stub") is True)
    check("snapshots land in logs/<run_id>/, not logs/no_run_id/",
          (config.BASE_DIR / "logs" / run_id).is_dir(), f"no logs/{run_id}/")

    print("\n4b. request validation (422 before any allowance is spent)")
    for label, body in (("pace_seconds: -1", {"job_description": "jd", "pace_seconds": -1}),
                        ('mode: "Live"', {"job_description": "jd", "mode": "Live"}),
                        ("empty JD", {"job_description": ""})):
        code = c.post("/runs", json=body, headers=auth(token)).status_code
        check(f"POST /runs with {label} -> 422", code == 422, f"got {code}")

    print("\n5. allowance + ownership")
    # Run 1 was section 4. Spend the rest of the allowance, then one more must
    # be refused. Each new run supersedes this user's previous one, so the last
    # one started is the one left parked on a gate.
    extra = [c.post("/runs", json={"job_description": f"extra run {i + 2}", "mode": "offline",
                                   "pace_seconds": 0.05}, headers=auth(token))
             for i in range(max(0, config.DEFAULT_RUN_ALLOWANCE - 1))]
    check(f"the rest of the allowance ({len(extra)} more run(s)) is usable",
          all(r.status_code == 200 for r in extra), str([r.status_code for r in extra]))
    over = c.post("/runs", json={"job_description": "over the allowance", "mode": "offline",
                                 "pace_seconds": 0.05}, headers=auth(token))
    check("one run past the allowance -> 403", over.status_code == 403, f"got {over.status_code}")
    second = extra[-1] if extra else None

    other_req = c.post("/auth/request-access", json={"identifier": f"{name}-b"}).json()
    other = c.post(f"/auth/requests/{other_req['id']}/approve", headers=auth(admin)).json()["token"]
    check("another user cannot read this run's log",
          c.get(f"/runs/{run_id}/log", headers=auth(other)).status_code == 403)
    check("another user cannot see it in /runs",
          run_id not in [r["id"] for r in c.get("/runs", headers=auth(other)).json()["runs"]])
    check("owner still sees it in /runs",
          run_id in [r["id"] for r in c.get("/runs", headers=auth(token)).json()["runs"]])
    check("admin sees it too",
          run_id in [r["id"] for r in c.get("/runs", headers=auth(admin)).json()["runs"]])
    check("another user cannot open its SSE stream",
          c.get(f"/runs/{run_id}/events", params={"token": other}).status_code == 403)

    print("\n5b. a rejected gate sends the work back (second gate_wait, not run_stopped)")
    second_id = second.json().get("run_id") if second is not None and second.status_code == 200 else None
    if not second_id:
        print("    (skipped: no second run; the allowance is 1 or the run was refused)")
    else:
        first = gate_waits(c, second_id, token, n=1)
        check("second run reached its first gate", len(first) == 1, "no gate_wait arrived")
        if first:
            rejected = c.post(f"/runs/{second_id}/gate",
                              json={"decision": "reject", "feedback": "smoke"}, headers=auth(token))
            check("reject accepted", rejected.status_code == 200, f"got {rejected.status_code}")
            again = gate_waits(c, second_id, token, n=2)
            check("reject reopens the same gate",
                  len(again) == 2 and again[1]["node"] == first[0]["node"],
                  str([(e["node"], e["artifact_node"]) for e in again]))
        # Left parked on that gate: the allowance is spent, so no new run can
        # supersede it. It ends when the server stops; its checkpoint stays resumable.

    listed_runs = c.get("/runs", headers=auth(admin)).json()["runs"]
    started_at = [r["started"] or "" for r in listed_runs]
    check("GET /runs is newest-first", started_at == sorted(started_at, reverse=True))

    print("\n6. knowledge base + search")
    kb = c.get("/kb", headers=auth(admin))
    check("GET /kb -> 200", kb.status_code == 200, kb.text[:80])
    check("stores present", "profile" in kb.json().get("stores", {}))
    check("path traversal blocked",
          c.get("/kb/profile/..%2f..%2fconfig", headers=auth(admin)).status_code == 404)

    print(f"\n{'ALL CHECKS PASSED' if not _failures else f'{_failures} CHECK(S) FAILED'}\n")
    return 1 if _failures else 0


if __name__ == "__main__":
    sys.exit(main())
