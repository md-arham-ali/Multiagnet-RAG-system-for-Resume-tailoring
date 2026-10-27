#!/usr/bin/env python3
"""
Live probe of the bridge API, against a RUNNING server. Offline runs only.

smoke_backend.py walks the happy path. test_backend_api.py stubs the graph. This
covers what neither can: refusals against the real graph, upload limits through
real uvicorn, two accounts running at once, restart survival, and that no raw
token reaches a log file.

    .venv/bin/python scripts/dev.py up --no-frontend --offline &
    .venv/bin/python scripts/probe_backend.py            # sections 1-11; parks a run for 12
    (restart the server)
    .venv/bin/python scripts/probe_backend.py --resume   # section 12: interrupted -> resume -> done

Creates two accounts (probe-<stamp>-a / -b) with the sample CV. Never writes
Build-Profile entries (there is no delete route, bugs_audit_fixed.md #119).
Reads ADMIN_TOKEN from .env and never prints a token. Exits non-zero if a check fails.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

import config

BASE = os.getenv("SMOKE_BASE", "http://127.0.0.1:8000/api")
STATE_FILE = Path(tempfile.gettempdir()) / "probe_backend_state.json"   # outside every scanned folder
PASS, FAIL, KNOWN = "\033[32m✓\033[0m", "\033[31m✗\033[0m", "\033[33m⚠\033[0m"
REFUSED = (403, 404)
_failures = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global _failures
    if not ok:
        _failures += 1
    print(f"  {PASS if ok else FAIL} {label}{'' if ok else f'  -> {detail}'}")


def known(label: str, ok: bool, ref: str, detail: str = "") -> None:
    """A check pinned to an open bug: reported, never counted as a failure."""
    print(f"  {PASS if ok else KNOWN} {label}{'' if ok else f'  -> still open ({ref}) {detail}'}")


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def client() -> httpx.Client:
    return httpx.Client(base_url=BASE, timeout=httpx.Timeout(30.0, read=180.0))


def new_account(c: httpx.Client, admin: str, name: str) -> dict:
    rid = c.post("/auth/request-access", json={"identifier": name, "note": "probe"}).json()["id"]
    token = c.post(f"/auth/requests/{rid}/approve", headers=auth(admin)).json()["token"]
    me = c.post("/auth/login", json={"token": token}).json()
    return {"name": name, "token": token, "profile_id": me["profile_id"]}


def give_cv(c: httpx.Client, token: str) -> int:
    cv_file = Path(config.CV_DEFAULT_PATH)
    up = c.post("/profile/cv", files={"file": (cv_file.name, cv_file.read_bytes(), "application/pdf")},
                headers=auth(token))
    if up.status_code != 201:
        return up.status_code
    return c.post(f"/profile/cv/{up.json()['cv']['id']}/confirm", headers=auth(token)).status_code


def start(c: httpx.Client, token: str, jd: str, request_id: str | None = None) -> httpx.Response:
    body = {"job_description": jd, "mode": "offline", "pace_seconds": 0.05}
    if request_id:
        body["client_request_id"] = request_id
    return c.post("/runs", json=body, headers=auth(token))


def first_gate(c: httpx.Client, run_id: str, token: str, limit: float = 120.0) -> dict | None:
    """Read the stream until the first gate_wait; None if the run ends first."""
    deadline = time.time() + limit
    with c.stream("GET", f"/runs/{run_id}/events", params={"token": token}) as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                ev = json.loads(line[6:])
                if ev["type"] == "gate_wait":
                    return ev
                if ev["type"] in ("run_done", "run_stopped", "run_error"):
                    return None
            if time.time() > deadline:
                return None
    return None


def drive(run_id: str, token: str, stop_at: str | None = None, limit: float = 300.0) -> dict:
    """Follow one run on ONE stream, approving every gate (gate 2 with one gap answer).

    The stream replays history on connect, so every answer names its gate: a
    replayed, already-answered gate_wait then gets a harmless 409 instead of
    landing on whichever gate is open now. stop_at parks the run at that gate.
    """
    c, poster = client(), client()
    out = {"events": [], "keepalive": False, "max_gap": 0.0, "parked": None, "answers": []}
    last = time.time()
    deadline = time.time() + limit
    try:
        with c.stream("GET", f"/runs/{run_id}/events", params={"token": token}) as r:
            out["status"] = r.status_code
            for line in r.iter_lines():
                now = time.time()
                if line.startswith(": keepalive"):
                    out["keepalive"] = True
                if not line.startswith("data: "):
                    continue
                out["max_gap"] = max(out["max_gap"], now - last)
                last = now
                ev = json.loads(line[6:])
                out["events"].append(ev)
                if ev["type"] == "gate_wait":
                    if ev["gate"] == stop_at:
                        out["parked"] = ev
                        break
                    body = {"decision": "approve", "feedback": "", "gate": ev["gate"]}
                    questions = ev.get("gap_questions") or []
                    if ev["gate"] == "gate2_evidence" and questions:
                        body["gap_answers"] = {questions[0]["requirement"]: "Probe answer."}
                    out["answers"].append(poster.post(f"/runs/{run_id}/gate", json=body,
                                                      headers=auth(token)).status_code)
                if ev["type"] in ("run_done", "run_stopped", "run_error") or now > deadline:
                    break
    except httpx.HTTPError as exc:
        out["error"] = type(exc).__name__
    return out


def ended(result: dict) -> str | None:
    return next((e["type"] for e in result["events"] if e["type"] in ("run_done", "run_stopped", "run_error")), None)


def blank_pdf() -> bytes:
    """A valid one-page PDF with no text layer (a hand-written one without an
    xref table is refused earlier, as unreadable)."""
    from pypdf import PdfWriter
    writer, buf = PdfWriter(), io.BytesIO()
    writer.add_blank_page(width=612, height=792)
    writer.write(buf)
    return buf.getvalue()


def zip_text(data: bytes) -> str:
    """Every file in an export as text, minus the caller's own `forbidden` audit
    lines: those name the path the caller typed, which may hold someone else's
    run id the caller already knew (that is the attempt being recorded)."""
    parts = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            text = zf.read(name).decode("utf-8", "replace")
            if name == "logs.json":
                entries = json.loads(text)
                entries = entries.get("entries", entries) if isinstance(entries, dict) else entries
                text = json.dumps([e for e in entries if e.get("event") != "forbidden"])
            parts.append(f"{name}\n{text}")
    return "\n".join(parts)


def main_phase(admin: str) -> int:
    c = client()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    print(f"\n0. two accounts (probe-{stamp}-a / -b)")
    a = new_account(c, admin, f"probe-{stamp}-a")
    b = new_account(c, admin, f"probe-{stamp}-b")
    check("both accounts exist and differ", a["profile_id"] != b["profile_id"])
    check("A gets the sample CV (confirm -> 200)", give_cv(c, a["token"]) == 200)

    print("\n1. start rules")
    no_cv = start(c, b["token"], "Data engineer.")
    check("a start with no confirmed CV -> 409", no_cv.status_code == 409, f"{no_cv.status_code} {no_cv.text[:120]}")
    request_id = f"probe-{stamp}-req1"
    first = start(c, a["token"], "Python data engineer, SQL, ETL. Probe run A1.", request_id)
    check("A's first start -> 200", first.status_code == 200, first.text[:200])
    if first.status_code != 200:
        print(f"\n{_failures} CHECK(S) FAILED (stopped: no run to probe)\n")
        return 1
    run_a1 = first.json()["run_id"]
    again = start(c, a["token"], "Python data engineer, SQL, ETL. Probe run A1.", request_id)
    check("the same client_request_id returns the same run",
          again.status_code == 200 and again.json().get("run_id") == run_a1, again.text[:200])
    left = c.get("/auth/me", headers=auth(a["token"])).json().get("runs_remaining")
    check("the retried start spent nothing", left == config.DEFAULT_RUN_ALLOWANCE - 1, f"runs_remaining={left}")

    print("\n2. gate input bounds, on the real graph (gate 1 open)")
    gate = first_gate(c, run_a1, a["token"])
    check("run A1 parks at gate 1", bool(gate) and gate["gate"] == "gate1_requirements", str(gate)[:200])
    post = lambda body, tok=a["token"]: c.post(f"/runs/{run_a1}/gate", json=body, headers=auth(tok))
    r = post({"decision": "approve", "feedback": "x" * 2001})
    check("feedback of 2,001 chars -> 422", r.status_code == 422, str(r.status_code))
    r = post({"decision": "approve", "gap_answers": {"SQL": "yes"}})
    check("gap_answers at gate 1 -> 422", r.status_code == 422, str(r.status_code))
    r = post({"decision": "aprove"})
    check("an unknown decision -> 422", r.status_code == 422, str(r.status_code))
    r = post({"decision": "approve", "gate": "gate3_fit"})
    check("an answer naming another gate -> 409", r.status_code == 409, str(r.status_code))
    r = post({"decision": "edit", "edited_content": "# hijack"})
    check("edited_content before the final review -> 422", r.status_code == 422, str(r.status_code))

    print("\n3. another account against A's run (writes, not just reads)")
    r = post({"decision": "approve", "gate": "gate1_requirements"}, tok=b["token"])
    check("B answering A's gate -> 403", r.status_code == 403, str(r.status_code))
    r = c.post(f"/runs/{run_a1}/resume", headers=auth(b["token"]))
    check("B resuming A's run -> 403", r.status_code == 403, str(r.status_code))
    r = c.get(f"/runs/{run_a1}/events", params={"token": b["token"]})
    check("B opening A's stream -> 403", r.status_code == 403, str(r.status_code))
    gate = first_gate(c, run_a1, a["token"])
    check("A's gate 1 is still open after B's attempts", bool(gate) and gate["gate"] == "gate1_requirements")

    print("\n4. run_id traversal through real routing")
    for method, path in (("GET", "/runs/..%2F..%2Fknowledge_base%2Fauth%2Ftokens/log"),
                         ("GET", "/runs/..%2F..%2Fetc%2Fpasswd/document"),
                         ("POST", "/runs/..%2Ffrontend_runs/resume"),
                         ("GET", "/runs/%2e%2e%2f%2e%2e%2fconfig/log")):
        r = c.request(method, path, headers=auth(a["token"]))
        check(f"{method} {path} refused", r.status_code in (400, 403, 404, 405, 422),
              f"{r.status_code} {r.text[:80]}")

    print("\n5. A1 to the end (keepalive, gate_done echo, snapshots)")
    a1 = drive(run_a1, a["token"])
    check("run A1 -> run_done", ended(a1) == "run_done", f"{ended(a1)} {a1.get('error')}")
    check("every first answer accepted (replays may 409)", 200 in a1["answers"], str(a1["answers"]))
    if a1["max_gap"] >= 11:
        check("a silent stretch carried ': keepalive' (DEC-156)", a1["keepalive"], f"gap {a1['max_gap']:.1f}s")
    else:
        print(f"    (keepalive not exercised: longest silence {a1['max_gap']:.1f}s < 10s on a warm server)")
    done = [e for e in a1["events"] if e["type"] == "gate_done"]
    bad = [e.get("gate") for e in done if e.get("feedback") == "None"]
    known("no gate_done echoes feedback as the string 'None'", not bad, "#110 item 4", str(bad))
    snaps = sorted(p.name for p in (config.BASE_DIR / "logs" / run_a1).glob("*.json"))
    per_gate = {g: sum(g in n for n in snaps) for g in
                ("gate1_requirements", "gate2_evidence", "gate3_fit", "gate4_document")}
    known("one state snapshot per gate", all(v == 1 for v in per_gate.values()), "#110 item 5", str(per_gate))

    print("\n6. the saved CV: cross-account, delete, delete again")
    r = c.get(f"/runs/{run_a1}/document", params={"fmt": "md"}, headers=auth(b["token"]))
    check("B downloading A's CV refused", r.status_code in REFUSED, str(r.status_code))
    r = c.delete(f"/runs/{run_a1}/document", headers=auth(b["token"]))
    check("B deleting A's CV refused", r.status_code in REFUSED, str(r.status_code))
    r = c.get(f"/runs/{run_a1}/document", params={"fmt": "md"}, headers=auth(a["token"]))
    check("A downloads own CV -> 200", r.status_code == 200, str(r.status_code))
    check("DELETE own CV -> 204", c.delete(f"/runs/{run_a1}/document", headers=auth(a["token"])).status_code == 204)
    r = c.delete(f"/runs/{run_a1}/document", headers=auth(a["token"]))
    check("DELETE again -> 404", r.status_code == 404, str(r.status_code))

    print("\n7. CV upload limits (B)")
    up = lambda name, data: c.post("/profile/cv", files={"file": (name, data, "application/pdf")},
                                   headers=auth(b["token"]))
    r = up("notes.pdf", b"hello, I am not a PDF")
    check("non-PDF bytes -> 415", r.status_code == 415, str(r.status_code))
    r = up("big.pdf", b"%PDF-1.4\n" + b"0" * (5 * 1024 * 1024 + 1))
    check("over 5 MB -> 413", r.status_code == 413, str(r.status_code))
    r = up("blank.pdf", blank_pdf())
    check("a PDF with no text -> 422", r.status_code == 422, f"{r.status_code} {r.text[:120]}")
    check("B gets the sample CV (confirm -> 200)", give_cv(c, b["token"]) == 200)

    print("\n8. two accounts at once")
    ra = start(c, a["token"], "Probe run A2: analytics engineer, dbt, SQL.")
    rb = start(c, b["token"], "Probe run B1: ML engineer, Python, MLOps.")
    check("both start -> 200", ra.status_code == rb.status_code == 200, f"{ra.status_code} {rb.status_code}")
    run_a2, run_b1 = ra.json()["run_id"], rb.json()["run_id"]
    results: dict[str, dict] = {}
    threads = [threading.Thread(target=lambda k, rid, tok: results.__setitem__(k, drive(rid, tok)),
                                args=(k, rid, tok), daemon=True)
               for k, rid, tok in (("a2", run_a2, a["token"]), ("b1", run_b1, b["token"]))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=400)
    for key, run_id, tok in (("a2", run_a2, a["token"]), ("b1", run_b1, b["token"])):
        res = results.get(key, {"events": []})
        check(f"run {key} -> run_done", ended(res) == "run_done", f"{ended(res)} {res.get('error')}")
        log = c.get(f"/runs/{run_id}/log", headers=auth(tok)).json()
        same = [e["type"] for e in res["events"]] == [e["type"] for e in log.get("events", [])]
        check(f"run {key}'s stream equals its own log (no cross-talk)", same,
              f"stream {len(res['events'])} vs log {len(log.get('events', []))}")

    print("\n9. the log plane")
    mine_b = c.get("/logs/mine", headers=auth(b["token"])).json()["entries"]
    forbidden_b = [e for e in mine_b if e["event"] == "forbidden"]
    check("B's /logs/mine lists B's own refusals", len(forbidden_b) >= 3, f"{len(forbidden_b)} forbidden entries")
    a_runs = {run_a1, run_a2}
    leaked = [e for e in mine_b if e.get("run_id") in a_runs and e["event"] != "forbidden"]
    check("B's /logs/mine carries none of A's run events", not leaked, str(leaked)[:200])
    adm = c.get("/admin/logs", params={"profile_id": b["profile_id"], "event": "forbidden"},
                headers=auth(admin)).json()["entries"]
    check("admin finds B's refusals by profile_id", len(adm) >= len(forbidden_b), f"{len(adm)} vs {len(forbidden_b)}")

    print("\n10. /me/export holds only the caller's own data")
    za = c.get("/me/export", headers=auth(a["token"]))
    zb = c.get("/me/export", headers=auth(b["token"]))
    check("both exports -> 200 zip", za.status_code == zb.status_code == 200, f"{za.status_code} {zb.status_code}")
    if za.status_code == zb.status_code == 200:
        ta, tb = zip_text(za.content), zip_text(zb.content)
        check("A's export holds A's runs", run_a1 in ta and run_a2 in ta)
        check("A's export names nothing of B's", run_b1 not in ta and b["profile_id"] not in ta)
        check("B's export names nothing of A's",
              all(x not in tb for x in (run_a1, run_a2, a["profile_id"])))
        check("no export carries a raw token", all(t not in ta + tb for t in (a["token"], b["token"])))

    print("\n11. no raw token in a log or data file")
    roots = [config.BASE_DIR / "logs" / "logplane", config.RUNS_DIR, config.OUTPUTS_DIR,
             config.CV_UPLOADS_DIR / a["profile_id"], config.CV_UPLOADS_DIR / b["profile_id"]]
    roots += [config.BASE_DIR / "logs" / rid for rid in (run_a1, run_a2, run_b1)]
    files = [p for root in roots if root.exists() for p in root.rglob("*") if p.is_file()]
    files += [config.KB_AUTH_DIR / n for n in ("requests.json", "profiles.json")]   # tokens.json IS the credential store
    hits = sorted({str(p.relative_to(config.BASE_DIR)) for p in files if p.exists()
                   for t in (a["token"], b["token"]) if t.encode() in p.read_bytes()})
    check(f"neither probe token in {len(files)} files", not hits, str(hits[:5]))

    print("\n12a. park B's second run at gate 2 for the restart check")
    rb2 = start(c, b["token"], "Probe run B2: data engineer, restart check.")
    check("B's second start -> 200", rb2.status_code == 200, rb2.text[:200])
    if rb2.status_code == 200:
        run_b2 = rb2.json()["run_id"]
        parked = drive(run_b2, b["token"], stop_at="gate2_evidence")
        check("run B2 parked at gate 2", bool(parked["parked"]), f"{ended(parked)} {parked.get('error')}")
        STATE_FILE.write_text(json.dumps({"token": b["token"], "run_id": run_b2}))
        print(f"\n  Restart the server now, then run:  .venv/bin/python scripts/probe_backend.py --resume")
    print(f"\n  accounts: {a['name']} ({a['profile_id']}), {b['name']} ({b['profile_id']})")
    print(f"  runs: A1 {run_a1}, A2 {run_a2}, B1 {run_b1}" + (f", B2 {run_b2}" if rb2.status_code == 200 else ""))
    print(f"\n{'ALL CHECKS PASSED' if not _failures else f'{_failures} CHECK(S) FAILED'}\n")
    return 1 if _failures else 0


def resume_phase() -> int:
    if not STATE_FILE.exists():
        print(f"No parked run ({STATE_FILE} missing): run the main phase first.")
        return 2
    state = json.loads(STATE_FILE.read_text())
    token, run_id = state["token"], state["run_id"]
    c = client()
    print(f"\n12b. after the restart: run {run_id}")
    started = c.get("/health").json().get("started")
    print(f"    (server started {started})")
    row = next((r for r in c.get("/runs", headers=auth(token)).json()["runs"] if r["id"] == run_id), None)
    check("GET /runs lists the run as interrupted", bool(row) and row.get("interrupted") is True, str(row)[:200])
    r = c.post(f"/runs/{run_id}/resume", headers=auth(token))
    check("POST /resume -> 200", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
    after = drive(run_id, token)
    reopened = [e["gate"] for e in after["events"] if e["type"] == "gate_wait"]
    check("the run reopens at gate 2 (no gate re-run before it)",
          "gate2_evidence" in reopened, str(reopened))
    check("the resumed run -> run_done", ended(after) == "run_done", f"{ended(after)} {after.get('error')}")
    r = c.post(f"/runs/{run_id}/resume", headers=auth(token))
    check("resuming a finished run is refused", r.status_code in (404, 409), str(r.status_code))
    STATE_FILE.unlink(missing_ok=True)
    print(f"\n{'ALL CHECKS PASSED' if not _failures else f'{_failures} CHECK(S) FAILED'}\n")
    return 1 if _failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--resume", action="store_true", help="section 12b: run after restarting the server")
    args = parser.parse_args()
    if args.resume:
        return resume_phase()
    if not config.ADMIN_TOKEN:
        print("ADMIN_TOKEN is not set in .env — cannot run.")
        return 2
    return main_phase(config.ADMIN_TOKEN)


if __name__ == "__main__":
    sys.exit(main())
