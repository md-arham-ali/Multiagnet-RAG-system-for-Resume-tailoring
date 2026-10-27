"""
Bridge API end to end, through TestClient.

The graph is replaced with a stub that yields canned node updates and pauses at
the four gates the way interrupt() does, so these tests never load a model,
never call a provider, and run in milliseconds while still exercising the real
worker thread, the real gate relay (park on __interrupt__, resume with
Command), and the real event stream.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from langgraph.types import Command, Interrupt

import config
from backend import cv_store, logplane
from backend import vectorstore as backend_vectorstore
from backend.auth import store
from backend.jsonstore import write_json
from backend.routes import kb as kb_routes
from backend.routes import profile as profile_routes
from backend.runs import registry, worker
from vectordb.store import VectorStore

ADMIN = "admin-secret"


GAP_QUESTIONS = [{"requirement": "Kubernetes", "question": "Have you used Kubernetes?"}]

# Every StubGraph the worker built in this test, in order (one per run).
BUILT: list["StubGraph"] = []


def _hop(next_node):
    """The Supervisor's update: the worker reads only supervisor_decision.next_node."""
    return {"supervisor": {"supervisor_decision": SimpleNamespace(next_node=next_node)}}


def _pause(gate, field, gap_questions=()):
    """The payload utils/human_gate.py hands to interrupt()."""
    return {"gate": gate, "field": field, "value": {}, "gap_questions": list(gap_questions),
            "revision": 0, "max_revisions": 2}                      # the round counter of #78 item 2


class StubGraph:
    """Mimics the compiled graph as backend/runs/worker.py drives it.

    stream(input, config=, stream_mode=) runs one segment of nodes, then yields
    {"__interrupt__": (Interrupt(value={"gate": ...}),)} and ends, as
    interrupt() does. stream(Command(resume=answer), ...) continues from the
    paused gate: approve/edit move on, reject replays the segment and reopens the
    SAME gate (since 08-31 a reject sends the work back, it never ends the run).
    Gate positions follow agents/supervisor.STAGE_GATE: gate 3 opens after
    cv_link, gate 4 after verifier.
    """

    SEGMENTS = [
        ([("jd_analysis", {"requirements": [{"text": "Python"}], "stage": "profile"})],
         _pause("gate1_requirements", "requirements")),
        ([("profile", {"evidence": [{"id": "e1"}], "stage": "profile_enrich"})],
         _pause("gate2_evidence", "evidence", GAP_QUESTIONS)),
        ([("profile_enrich", {"stage": "matching"}),
          ("matching", {"fit_report": {"overall_fit": 0.45}, "stage": "cv_link"}),
          ("cv_link", {"line_links": [], "stage": "document"})],
         _pause("gate3_fit", "fit_report")),
        ([("document", {"document": {"kind": "cv", "content": "THE CV BODY"}, "stage": "critic"}),
          ("critic", {"critique": {"verdict": "pass"}, "stage": "verifier"}),
          ("verifier", {"verifier_report": {"status": "pass"}, "stage": "evaluation"})],
         {**_pause("gate4_document", "document"), "changes": [],
          "standing_verdict": None}),                            # human_gate's FINAL_GATE extras
        ([("evaluation", {"eval_record": {}, "stage": "done"})], None),
    ]

    # The stub's "SQLite file": thread_id -> where that run is, what it is parked on, and
    # the few values utils/final_review.close_run reads. Shared by every StubGraph, as a
    # checkpoint DB is shared by every graph built on it, so a run resumed on a NEW graph
    # (registry.resume after a restart) picks up exactly where the old one stopped.
    CHECKPOINTS: dict[str, dict] = {}

    def __init__(self, checkpointer=None):
        self.checkpointer = checkpointer
        self.at = 0
        self.first_input = None   # the GraphState the worker started the run with
        self.answers = []         # every Command(resume=...) payload, in order

    # `config` has to be the parameter's name: the worker passes it by keyword.
    # Inside this method it shadows the config module, which is not used here.
    def stream(self, stream_input, config=None, stream_mode=None):
        # A failed assert here surfaces as the run's run_error event, which
        # wait_for_gate() prints.
        assert config["configurable"]["thread_id"]  # resumable by run id
        assert stream_mode == "updates"
        ck = self._thread(config)
        self.at = ck["at"]
        if isinstance(stream_input, Command):
            answer = stream_input.resume
            self.answers.append(answer)
            paused = self.SEGMENTS[self.at][1]["gate"]
            feedback = {"gate": paused, "decision": answer["decision"]}
            ck["values"]["gate_feedback"].append(feedback)
            # The gate node finishing, as human_gate() returns. The worker must
            # skip it: "gate" is not an agent and gets no node_done.
            yield {"gate": {"gate_feedback": [feedback]}}
            if answer["decision"] != "reject":
                self.at += 1
        else:
            self.first_input = stream_input
        ck["at"], ck["paused"] = self.at, None
        nodes, payload = self.SEGMENTS[self.at]
        for node, fields in nodes:
            yield _hop(node)
            if "document" in fields:
                ck["values"]["document"] = fields["document"]
            yield {node: fields}
        if payload is None:
            yield _hop("END")
            return
        ck["paused"] = payload
        yield _hop("gate")
        yield {"__interrupt__": (Interrupt(value=payload),)}

    def get_state(self, config):
        """What the worker reads at a run's close (values) and on a resume (tasks)."""
        ck = StubGraph.CHECKPOINTS.get(config["configurable"]["thread_id"])
        if ck is None:
            return SimpleNamespace(values={}, tasks=[], created_at=None)
        tasks = [SimpleNamespace(interrupts=[SimpleNamespace(value=ck["paused"])])] if ck["paused"] else []
        return SimpleNamespace(values={**ck["values"], "gate_feedback": list(ck["values"]["gate_feedback"])},
                               tasks=tasks, created_at="stub")

    @staticmethod
    def _thread(config) -> dict:
        return StubGraph.CHECKPOINTS.setdefault(config["configurable"]["thread_id"],
                                                {"at": 0, "paused": None, "values": {"gate_feedback": []}})


class StubCheckpointer:
    """The worker closes checkpointer.conn when a run ends."""

    def __init__(self):
        self.conn = SimpleNamespace(close=lambda: None)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "KB_AUTH_DIR", tmp_path / "auth")
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path / "runs")
    # The audit log and CV uploads are storage too: without these, every test
    # appends to the real logs/logplane/ and seeds CVs into the real uploads/.
    monkeypatch.setattr(logplane, "LOG_DIR", tmp_path / "logplane")
    monkeypatch.setattr(config, "CV_UPLOADS_DIR", tmp_path / "uploads")
    # A run that reaches the end is closed (utils/final_review.close_run): an approved
    # one exports its CV, which must never land in the real outputs/.
    monkeypatch.setattr(config, "OUTPUTS_DIR", tmp_path / "outputs")
    StubGraph.CHECKPOINTS.clear()
    SEEDED_CV.clear()
    # Build-Profile entries and their vectors: a saved entry is indexed into the
    # process's one vector store. Without these, a save loads the real embedder
    # and writes into the real knowledge_base/chroma "profile" collection.
    manual = tmp_path / "profile" / "manual_entries.json"
    monkeypatch.setattr(profile_routes, "MANUAL_ENTRIES", manual)
    monkeypatch.setattr(kb_routes, "_MANUAL_ENTRIES_RESOLVED", manual.resolve())
    monkeypatch.setattr(config, "VECTORDB_DIR", tmp_path / "chroma")
    fake_store = VectorStore(embedder=_HashEmbedder(), in_memory=True)
    fake_store.reset("profile")
    monkeypatch.setattr(backend_vectorstore, "_store", fake_store)
    # Indexed in the request, not on a daemon thread that could outlive the
    # test and reach a real store after monkeypatch has undone the fake.
    monkeypatch.setattr(profile_routes, "_index_in_background", profile_routes._index_entry)
    monkeypatch.setattr(config, "ADMIN_TOKEN", ADMIN)
    monkeypatch.setattr(config, "DEFAULT_RUN_ALLOWANCE", 2)
    BUILT.clear()

    def build_graph(checkpointer=None):
        BUILT.append(StubGraph(checkpointer))
        return BUILT[-1]

    monkeypatch.setattr(worker, "BUILD_GRAPH", build_graph)
    # Patched too, or every test run opens the real logs/checkpoints.sqlite.
    monkeypatch.setattr(worker, "MAKE_CHECKPOINTER", StubCheckpointer)
    registry._runs.clear()
    registry._active.clear()
    yield
    # Retire every run this test started, while config is still patched. A
    # worker that outlives the test writes its log through save_log() into
    # whatever config.RUNS_DIR is by then (the real one, once monkeypatch
    # undoes it), and a parked one sits on its gate for the rest of the session.
    for run in list(registry._runs.values()):
        if not run["done"]:
            registry.abort(run)
    for run in list(registry._runs.values()):
        if run.get("thread") is not None:
            run["thread"].join(timeout=5)


@pytest.fixture
def client():
    from backend.app import app

    with TestClient(app) as c:
        yield c


def auth(token):
    return {"Authorization": f"Bearer {token}"}


SEEDED_CV: dict[str, str] = {}   # token -> the confirmed CV seeded for its account


class _HashEmbedder:
    """No-download embedder: hashed bag of words, normalised."""

    def embed(self, texts):
        out = []
        for text in texts:
            v = [0.0] * 64
            for tok in re.findall(r"[a-z0-9]+", text.lower()):
                v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % 64] += 1.0
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / norm for x in v])
        return out


def seed_cv(token: str) -> str:
    """Give the token's account a confirmed CV, in backend/cv_store.py's own on-disk
    shape. A plain user can't start a run without one (design.md D-CV2), so
    every issued identity gets one; the stub graph never parses it."""
    profile_id = store.resolve_token(token)["profile_id"]
    cv_dir = config.CV_UPLOADS_DIR / profile_id / "cv"
    cv_dir.mkdir(parents=True, exist_ok=True)
    (cv_dir / "seededcv0001.pdf").write_bytes(b"%PDF-1.4 seeded for tests")
    write_json(cv_dir / "index.json", {"current_id": "seededcv0001", "cvs": {"seededcv0001": {
        "id": "seededcv0001", "filename": "cv.pdf", "size_bytes": 25, "pages": 1,
        "uploaded_at": "2026-10-12T00:00:00+00:00", "stored_name": "seededcv0001.pdf", "status": "confirmed"}}})
    SEEDED_CV[token] = str(cv_dir / "seededcv0001.pdf")
    return SEEDED_CV[token]


def issue_token(client, name="alice"):
    req = client.post("/api/auth/request-access", json={"identifier": name}).json()
    approved = client.post(f"/api/auth/requests/{req['id']}/approve", headers=auth(ADMIN))
    assert approved.status_code == 200
    token = approved.json()["token"]
    seed_cv(token)
    return token


def _tail(run, k=6):
    """The run's last few events, short: what to look at when a wait fails."""
    return [(e["type"], e.get("node") or e.get("error") or e.get("reason") or "")
            for e in run["events"][-k:]]


def wait_for_gate(client, run_id, token, n=1, timeout=5.0):
    """Poll the run until its n-th gate_wait is open, and return that gate.

    Counted, not just "a gate is set": right after an answer the previous gate
    is still in run["gate"] until the worker wakes, so a bare check could hand
    back the gate that was just answered. Fails with the run's last events
    (including any run_error) rather than returning None.
    """
    run = registry.get(run_id)
    assert run is not None, f"unknown run {run_id}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        waits = [e for e in run["events"] if e["type"] == "gate_wait"]
        if len(waits) >= n and run["gate"]:
            return run["gate"]
        if run["done"]:
            raise AssertionError(f"run ended before gate {n} opened: {_tail(run)}")
        time.sleep(0.02)
    raise AssertionError(f"gate {n} never opened within {timeout}s: {_tail(run)}")


def answer(client, run_id, token, decision="approve", **extra):
    """Answer the open gate; a refused answer fails here, not as a later timeout."""
    resp = client.post(f"/api/runs/{run_id}/gate", json={"decision": decision, **extra},
                       headers=auth(token))
    assert resp.status_code == 200, (resp.status_code, resp.text)


def finish(run_id):
    """Join the run's worker; fail if it is still alive."""
    run = registry.get(run_id)
    run["thread"].join(timeout=5)
    assert not run["thread"].is_alive(), f"worker still running: {_tail(run)}"
    return run


# --- auth surface ------------------------------------------------------------
def test_health_is_the_only_open_read(client):
    assert client.get("/api/health").status_code == 200
    for path in ("/api/config", "/api/auth/me", "/api/runs", "/api/profile/entries", "/api/kb"):
        assert client.get(path).status_code == 401, path


def test_malformed_authorization_headers_401(client):
    for header in ({"Authorization": "Basic xyz"}, {"Authorization": "Bearer"},
                   {"Authorization": "Bearer   "}, {"Authorization": ADMIN}):
        assert client.get("/api/auth/me", headers=header).status_code == 401


def test_bearer_scheme_is_case_insensitive(client):
    assert client.get("/api/auth/me", headers={"Authorization": f"bEaReR {ADMIN}"}).status_code == 200


def test_admin_identity_shape(client):
    body = client.get("/api/auth/me", headers=auth(ADMIN)).json()
    assert body == {"identifier": "admin", "role": "admin",
                    "runs_remaining": None, "token_id": "__admin__", "profile_id": "p-__admin__"}


def test_login_returns_identity_and_401s_on_bad_token(client):
    token = issue_token(client)
    body = client.post("/api/auth/login", json={"token": token}).json()
    assert body["identifier"] == "alice"
    assert body["role"] == "user"
    assert body["runs_remaining"] == 2
    assert client.post("/api/auth/login", json={"token": "nope"}).status_code == 401


def test_request_access_is_open_but_floored(client):
    assert client.post("/api/auth/request-access", json={"identifier": "zoe"}).status_code == 200
    # duplicate pending
    assert client.post("/api/auth/request-access", json={"identifier": "zoe"}).status_code == 400
    assert client.post("/api/auth/request-access", json={"identifier": ""}).status_code == 400


def test_non_admin_gets_403_not_401_on_admin_routes(client):
    """403 is load-bearing: a 401 would trip the frontend's global logout."""
    token = issue_token(client)
    assert client.get("/api/auth/requests", headers=auth(token)).status_code == 403
    assert client.post("/api/auth/requests/x/approve", headers=auth(token)).status_code == 403


def test_requests_list_includes_resolved(client):
    issue_token(client, "bob")
    body = client.get("/api/auth/requests", headers=auth(ADMIN)).json()
    assert body["requests"][0]["status"] == "approved"
    for key in ("id", "identifier", "note", "status", "created", "resolved"):
        assert key in body["requests"][0]


def test_double_approve_409s(client):
    req = client.post("/api/auth/request-access", json={"identifier": "dup"}).json()
    assert client.post(f"/api/auth/requests/{req['id']}/approve", headers=auth(ADMIN)).status_code == 200
    assert client.post(f"/api/auth/requests/{req['id']}/approve", headers=auth(ADMIN)).status_code == 409


# --- runs --------------------------------------------------------------------
def test_run_allowance_exhausts_with_403(client):
    token = issue_token(client)
    for _ in range(2):
        assert client.post("/api/runs", json={"job_description": "jd", "pace_seconds": 0}, headers=auth(token)).status_code == 200
    third = client.post("/api/runs", json={"job_description": "jd", "pace_seconds": 0}, headers=auth(token))
    assert third.status_code == 403
    assert "remaining" in third.json()["detail"].lower()


def test_admin_runs_are_never_decremented(client, tmp_path, monkeypatch):
    sample = tmp_path / "sample_cv.pdf"          # the admin's shared sample CV is git-ignored and absent in CI (503 without it)
    sample.write_bytes(b"%PDF-1.4 stand-in")
    monkeypatch.setattr(config, "CV_DEFAULT_PATH", sample)
    for _ in range(4):
        assert client.post("/api/runs", json={"job_description": "jd", "pace_seconds": 0}, headers=auth(ADMIN)).status_code == 200
    assert client.get("/api/auth/me", headers=auth(ADMIN)).json()["runs_remaining"] is None


def test_final_gate_carries_document_as_artifact_node(client):
    """The whole point of the gate fix: the last gate reviews `document`."""
    token = issue_token(client)
    run_id = client.post("/api/runs", json={"job_description": "jd", "pace_seconds": 0},
                         headers=auth(token)).json()["run_id"]
    seen = []
    for n in range(1, 5):
        gate = wait_for_gate(client, run_id, token, n=n)
        seen.append((gate["after"], gate["artifact_node"]))
        answer(client, run_id, token)
    events = finish(run_id)["events"]
    assert seen == [
        ("jd_analysis", "jd_analysis"),
        ("profile", "profile"),
        ("cv_link", "matching"),  # gate 3 opens after cv_link but reviews the fit (#52)
        ("verifier", "document"),
    ]
    # The stub's order, not the GATES table, decides where gate 3 sits: cv_link
    # must really have finished before the third gate_wait.
    kinds = [(e["type"], e.get("node")) for e in events]
    third_wait = [i for i, k in enumerate(kinds) if k[0] == "gate_wait"][2]
    assert kinds.index(("node_done", "cv_link")) < third_wait


def test_gate2_relays_gap_questions_and_answers(client):
    token = issue_token(client)
    run_id = client.post("/api/runs", json={"job_description": "jd", "pace_seconds": 0},
                         headers=auth(token)).json()["run_id"]
    wait_for_gate(client, run_id, token, n=1)
    answer(client, run_id, token)
    wait_for_gate(client, run_id, token, n=2)
    run = registry.get(run_id)
    waits = [e for e in run["events"] if e["type"] == "gate_wait"]
    assert waits[0]["gap_questions"] == []          # only gate 2 is an interview
    assert waits[1]["gap_questions"] == GAP_QUESTIONS
    answer(client, run_id, token, gap_answers={"Kubernetes": "2 years"})
    wait_for_gate(client, run_id, token, n=3)
    done = [e for e in run["events"] if e["type"] == "gate_done"][1]
    assert done["gap_answers"] == {"Kubernetes": "2 years"}
    # The answer has to reach the graph, not just the event log: human_gate()
    # reads answer["gap_answers"] off the Command (bugs.md #29).
    assert len(BUILT) == 1
    assert BUILT[0].answers[1]["gap_answers"] == {"Kubernetes": "2 years"}


def test_completed_run_log_has_document_artifact_and_owner(client):
    token = issue_token(client)
    run_id = client.post("/api/runs", json={"job_description": "jd", "pace_seconds": 0},
                         headers=auth(token)).json()["run_id"]
    for n in range(1, 5):
        wait_for_gate(client, run_id, token, n=n)
        answer(client, run_id, token)
    finish(run_id)

    resp = client.get(f"/api/runs/{run_id}/log", headers=auth(token))
    assert resp.status_code == 200, resp.text
    log = resp.json()
    assert log["owner"]
    doc = [e for e in log["events"] if e["type"] == "node_done" and e["node"] == "document"]
    assert doc and doc[0]["artifact"]["document"]["content"] == "THE CV BODY"
    # Placeholder agents are flagged for the UI from worker.STUB_NODES, and
    # document is real since 10-06.
    stub = {e["node"]: e["stub"] for e in log["events"] if e["type"] == "node_done"}
    assert stub == {node: node in worker.STUB_NODES for node in stub}
    assert stub["document"] is False
    # Every agent reached the UI (bugs.md #28/#41), each announced by a
    # node_start read off the Supervisor's decision; the gate node never is.
    done = [e["node"] for e in log["events"] if e["type"] == "node_done"]
    started = [e["node"] for e in log["events"] if e["type"] == "node_start"]
    assert set(done) == set(worker.AGENTS)
    assert started == done
    assert any(e["type"] == "run_done" for e in log["events"])
    # The worker starts the graph with the run id (snapshot dir, bugs.md #32)
    # and the server-side CV (cv_link raises without one).
    first = BUILT[0].first_input
    assert first.run_id == run_id
    assert first.job_description == "jd"
    assert first.cv_path == SEEDED_CV[token]                     # the account's own confirmed CV, not the sample


def test_gate_rejection_reopens_the_same_gate(client):
    """Since 08-31 a reject sends the work back to its producer (bugs.md #9/#10),
    so the run gets a second gate_wait for the same gate, not run_stopped."""
    token = issue_token(client)
    run_id = client.post("/api/runs", json={"job_description": "jd", "pace_seconds": 0},
                         headers=auth(token)).json()["run_id"]
    wait_for_gate(client, run_id, token, n=1)
    answer(client, run_id, token, "reject")
    gate = wait_for_gate(client, run_id, token, n=2)
    run = registry.get(run_id)
    assert gate["gate"] == "gate1_requirements"
    assert run["done"] is False
    redone = [e for e in run["events"] if e["type"] == "node_done" and e["node"] == "jd_analysis"]
    assert len(redone) == 2
    assert not any(e["type"] == "run_stopped" for e in run["events"])

    # Only superseding (abort) ends a parked run.
    registry.abort(run)
    finish(run_id)
    resp = client.get(f"/api/runs/{run_id}/log", headers=auth(token))
    assert resp.status_code == 200, resp.text
    assert any(e["type"] == "run_stopped" for e in resp.json()["events"])


def test_bad_gate_decision_422s(client):
    token = issue_token(client)
    run_id = client.post("/api/runs", json={"job_description": "jd", "pace_seconds": 0},
                         headers=auth(token)).json()["run_id"]
    wait_for_gate(client, run_id, token)
    assert client.post(f"/api/runs/{run_id}/gate", json={"decision": "aprove"},
                       headers=auth(token)).status_code == 422


# --- ownership ---------------------------------------------------------------
def test_one_user_cannot_see_or_touch_anothers_run(client):
    alice = issue_token(client, "alice")
    bob = issue_token(client, "bob")
    run_id = client.post("/api/runs", json={"job_description": "secret jd", "pace_seconds": 0},
                         headers=auth(alice)).json()["run_id"]
    wait_for_gate(client, run_id, alice)

    assert client.post(f"/api/runs/{run_id}/gate", json={"decision": "approve"},
                       headers=auth(bob)).status_code == 403
    assert client.get(f"/api/runs/{run_id}/events?token={bob}").status_code == 403
    # End it so the log is written (a reject would only reopen the gate).
    registry.abort(registry.get(run_id))
    finish(run_id)

    assert client.get(f"/api/runs/{run_id}/log", headers=auth(bob)).status_code == 403
    assert [r["id"] for r in client.get("/api/runs", headers=auth(bob)).json()["runs"]] == []
    assert run_id in [r["id"] for r in client.get("/api/runs", headers=auth(alice)).json()["runs"]]
    assert run_id in [r["id"] for r in client.get("/api/runs", headers=auth(ADMIN)).json()["runs"]]


def test_a_new_run_does_not_abort_another_owners_run(client):
    alice = issue_token(client, "alice")
    bob = issue_token(client, "bob")
    a_run = client.post("/api/runs", json={"job_description": "a", "pace_seconds": 0},
                        headers=auth(alice)).json()["run_id"]
    wait_for_gate(client, a_run, alice)
    client.post("/api/runs", json={"job_description": "b", "pace_seconds": 0}, headers=auth(bob))
    time.sleep(0.2)
    assert registry.get(a_run)["done"] is False  # alice's run still parked on its gate
    assert registry.get(a_run)["aborted"] is False


def test_legacy_logs_without_owner_are_admin_only(client):
    from backend.jsonstore import write_json

    config.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    write_json(config.RUNS_DIR / "old99.json",
               {"id": "old99", "started": "2026-01-01T00:00:00+00:00", "mode": "offline",
                "job_description": "legacy", "events": []})
    token = issue_token(client)
    assert client.get("/api/runs", headers=auth(token)).json()["runs"] == []
    assert "old99" in [r["id"] for r in client.get("/api/runs", headers=auth(ADMIN)).json()["runs"]]
    assert client.get("/api/runs/old99/log", headers=auth(token)).status_code == 403
    assert client.get("/api/runs/old99/log", headers=auth(ADMIN)).status_code == 200


# --- SSE ---------------------------------------------------------------------
def test_sse_requires_a_valid_query_token(client):
    token = issue_token(client)
    run_id = client.post("/api/runs", json={"job_description": "jd", "pace_seconds": 0},
                         headers=auth(token)).json()["run_id"]
    assert client.get(f"/api/runs/{run_id}/events").status_code == 401
    assert client.get(f"/api/runs/{run_id}/events?token=bogus").status_code == 401
    assert client.get(f"/api/runs/unknown/events?token={token}").status_code == 404


def test_sse_streams_events(client):
    token = issue_token(client)
    run_id = client.post("/api/runs", json={"job_description": "jd", "pace_seconds": 0},
                         headers=auth(token)).json()["run_id"]
    wait_for_gate(client, run_id, token)
    # End the run first: the SSE stream only closes once the run is done, and a
    # reject would just reopen the gate.
    registry.abort(registry.get(run_id))
    finish(run_id)
    body = client.get(f"/api/runs/{run_id}/events?token={token}").text
    assert "gate_wait" in body and '"artifact_node": "jd_analysis"' in body
    assert "run_stopped" in body


# --- profile -----------------------------------------------------------------
def test_profile_entry_roundtrip(client, tmp_path, monkeypatch):
    from backend.routes import profile as profile_routes

    monkeypatch.setattr(profile_routes, "MANUAL_ENTRIES", tmp_path / "manual.json")
    created = client.post("/api/profile/entries",
                          json={"section": "skills", "record": {"name": "Python"}},
                          headers=auth(ADMIN)).json()
    updated = client.put(f"/api/profile/entries/{created['id']}",
                         json={"section": "skills", "record": {"name": "Rust"}},
                         headers=auth(ADMIN))
    assert updated.status_code == 200
    assert updated.json()["record"]["name"] == "Rust"
    assert client.put("/api/profile/entries/nope",
                      json={"section": "skills", "record": {}},
                      headers=auth(ADMIN)).status_code == 404


# =============================================================================
# Backend routing (2026-10-12): the route table and each route's auth class,
# the status-code discipline (401 / 403 / 404 / 405 / 409 / 413 / 415 / 422),
# request validation at the boundary, the app-wide 403 audit, CORS, and each
# router's own contract over real HTTP. The graph is the StubGraph; storage,
# the log plane, uploads and the vector store are all in tmp_path.
# =============================================================================
def bare_token(client, name):
    """An approved account with NO CV (issue_token seeds one)."""
    req = client.post("/api/auth/request-access", json={"identifier": name}).json()
    return client.post(f"/api/auth/requests/{req['id']}/approve", headers=auth(ADMIN)).json()["token"]


def profile_of(token):
    return store.resolve_token(token)["profile_id"]


def audit_lines():
    path = logplane.LOG_DIR / "audit.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def runs_left(client, token):
    return client.get("/api/auth/me", headers=auth(token)).json()["runs_remaining"]


OPEN_ROUTES = {("GET", "/api/health"), ("POST", "/api/auth/request-access"), ("POST", "/api/auth/login")}
QUERY_TOKEN_ROUTES = {("GET", "/api/runs/{run_id}/events")}           # EventSource can't send headers
ADMIN_ROUTES = {
    ("GET", "/api/auth/requests"), ("POST", "/api/auth/requests/{request_id}/approve"),
    ("POST", "/api/auth/requests/{request_id}/reject"), ("GET", "/api/admin/logs"),
    ("GET", "/api/admin/users/{profile_id}/profile"), ("GET", "/api/admin/users/{profile_id}/cv"),
}
USER_ROUTES = {
    ("GET", "/api/config"), ("POST", "/api/auth/request-more"), ("GET", "/api/auth/me"),
    ("GET", "/api/kb"), ("GET", "/api/kb/{store}/{file}"), ("POST", "/api/search"),
    ("POST", "/api/runs"), ("GET", "/api/runs"), ("POST", "/api/runs/{run_id}/gate"),
    ("POST", "/api/runs/{run_id}/resume"),
    ("GET", "/api/runs/{run_id}/document"), ("GET", "/api/runs/{run_id}/log"),
    ("DELETE", "/api/runs/{run_id}/document"), ("GET", "/api/me/export"),    # added since the table was written; both user-auth
    ("GET", "/api/profile/entries"), ("POST", "/api/profile/entries"), ("PUT", "/api/profile/entries/{entry_id}"),
    ("GET", "/api/profile/cv"), ("POST", "/api/profile/cv"), ("POST", "/api/profile/cv/{cv_id}/confirm"),
    ("DELETE", "/api/profile/cv/{cv_id}"), ("GET", "/api/logs/mine"),
}


def _filled(path):
    return re.sub(r"\{(\w+)\}", lambda m: f"x-{m.group(1)}", path)


def _call(client, method, path, token=None, **kw):
    headers = auth(token) if token else {}
    if method in ("POST", "PUT") and "json" not in kw and "files" not in kw:
        kw["json"] = {}
    return client.request(method, _filled(path), headers=headers, **kw)


# --- the route table ----------------------------------------------------------
def test_the_route_table_is_exactly_the_classified_routes():
    # A new route must be added here with its auth class, deliberately.
    from backend.app import app

    table = {(m.upper(), p) for p, ops in app.openapi()["paths"].items() for m in ops}
    assert table == OPEN_ROUTES | QUERY_TOKEN_ROUTES | ADMIN_ROUTES | USER_ROUTES
    assert not (OPEN_ROUTES & ADMIN_ROUTES) and not (ADMIN_ROUTES & USER_ROUTES)
    assert all(path.startswith("/api/") for _, path in table)


@pytest.mark.parametrize("route", sorted(ADMIN_ROUTES | USER_ROUTES), ids=lambda r: f"{r[0]} {r[1]}")
@pytest.mark.parametrize("header", [None, "Bearer nope"], ids=["no-token", "bad-token"])
def test_every_authed_route_401s_without_a_valid_token(client, route, header):
    method, path = route
    resp = client.request(method, _filled(path), headers={"Authorization": header} if header else {},
                          **({"json": {}} if method in ("POST", "PUT") else {}))
    assert resp.status_code == 401, (route, resp.status_code, resp.text)


@pytest.mark.parametrize("route", sorted(OPEN_ROUTES), ids=lambda r: f"{r[0]} {r[1]}")
def test_the_open_routes_never_ask_for_a_token(client, route):
    assert _call(client, *route).status_code != 401


@pytest.mark.parametrize("route", sorted(ADMIN_ROUTES), ids=lambda r: f"{r[0]} {r[1]}")
def test_every_admin_route_403s_a_user_and_the_403_is_audited(client, route):
    token = issue_token(client, "ursula")
    resp = _call(client, *route, token=token)
    assert resp.status_code == 403 and resp.json() == {"detail": "Admin access required"}
    (entry,) = [e for e in audit_lines() if e["event"] == "forbidden"]
    assert (entry["actor"], entry["profile_id"], entry["fields"]) == ("account", profile_of(token), {"path": _filled(route[1])})
    assert token not in json.dumps(audit_lines())


def test_a_401_is_never_logged_as_forbidden(client):
    client.get("/api/auth/me")
    client.get("/api/auth/me", headers=auth("nope"))
    assert [e for e in audit_lines() if e["event"] == "forbidden"] == []


@pytest.mark.parametrize("method, path, status", [
    ("GET", "/api/nope", 404), ("DELETE", "/api/health", 405), ("GET", "/api/auth/login", 405),
    ("PUT", "/api/runs", 405), ("GET", "/api/profile/entries/x", 405),
])
def test_unknown_paths_404_and_wrong_methods_405(client, method, path, status):
    assert client.request(method, path, headers=auth(ADMIN)).status_code == status


def test_cors_answers_only_the_dashboards_own_origins(client):
    ok = client.get("/api/health", headers={"Origin": "http://localhost:3000"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "access-control-allow-origin" not in client.get("/api/health", headers={"Origin": "https://evil.example"}).headers
    pre = client.options("/api/runs", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
                                                "Access-Control-Request-Headers": "authorization"})
    assert pre.status_code == 200 and pre.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_config_is_behind_auth_and_shows_only_whether_keys_exist(client, monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "gsk_super_secret_value")
    body = client.get("/api/config", headers=auth(issue_token(client))).json()
    assert body["keys_present"]["groq"] is True and "gsk_super_secret_value" not in json.dumps(body)
    assert set(client.get("/api/health").json()) == {"ok", "test_mode", "offline_default", "started"}


# --- POST /api/runs: validation before anything is spent -----------------------
@pytest.mark.parametrize("body", [
    {}, {"job_description": ""}, {"job_description": "x" * 20_001}, {"job_description": "jd", "mode": "Live"},
    {"job_description": "jd", "pace_seconds": -1}, {"job_description": "jd", "pace_seconds": 6},
    {"job_description": "jd", "client_request_id": "short"}, {"job_description": "jd", "client_request_id": "x" * 65},
], ids=["no-jd", "empty-jd", "huge-jd", "mode-case", "pace-negative", "pace-huge", "id-short", "id-long"])
def test_a_bad_run_request_is_a_422_that_spends_nothing(client, body):
    token = issue_token(client)
    assert client.post("/api/runs", json=body, headers=auth(token)).status_code == 422
    assert runs_left(client, token) == 2 and registry._runs == {}


def test_live_mode_without_a_key_is_a_400_that_spends_nothing(client, monkeypatch):
    # Every lane needs at least one keyed provider (#70 item 2), so blank them all, not just Groq's.
    for key in ("GROQ_API_KEY", "GOOGLE_API_KEY", "CEREBRAS_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.setattr(config, key, "")
    token = issue_token(client)
    resp = client.post("/api/runs", json={"job_description": "jd", "mode": "live"}, headers=auth(token))
    assert resp.status_code == 400 and runs_left(client, token) == 2 and registry._runs == {}


def test_a_user_without_a_cv_gets_409_and_keeps_the_allowance(client):
    token = bare_token(client, "nocv")
    resp = client.post("/api/runs", json={"job_description": "jd", "pace_seconds": 0}, headers=auth(token))
    assert resp.status_code == 409 and "CV" in resp.json()["detail"]
    assert runs_left(client, token) == 2 and registry._runs == {}


def test_the_admin_without_a_cv_runs_on_the_labelled_sample(client, tmp_path, monkeypatch):
    sample = tmp_path / "sample_cv.pdf"          # the admin's shared sample CV is git-ignored and absent in CI (503 without it)
    sample.write_bytes(b"%PDF-1.4 stand-in")
    monkeypatch.setattr(config, "CV_DEFAULT_PATH", sample)
    resp = client.post("/api/runs", json={"job_description": "jd", "pace_seconds": 0}, headers=auth(ADMIN))
    assert resp.status_code == 200
    body = resp.json()
    assert (body["sample"], body["cv"]) == (True, None)
    run = registry.get(body["run_id"])
    assert run["cv_path"] == str(config.CV_DEFAULT_PATH) and run["sample_cv"] is True


def test_a_user_run_starts_on_their_own_cv(client):
    token = issue_token(client)
    body = client.post("/api/runs", json={"job_description": "jd", "pace_seconds": 0}, headers=auth(token)).json()
    assert body["sample"] is False and body["cv"]["id"] == "seededcv0001"
    assert registry.get(body["run_id"])["cv_path"] == SEEDED_CV[token]


def test_a_retried_start_returns_the_same_run_and_spends_once(client):
    token = issue_token(client)
    req = {"job_description": "jd", "pace_seconds": 0, "client_request_id": "retry-0001"}
    first = client.post("/api/runs", json=req, headers=auth(token)).json()["run_id"]
    assert client.post("/api/runs", json=req, headers=auth(token)).json()["run_id"] == first
    assert runs_left(client, token) == 1
    other = issue_token(client, "otto")
    assert client.post("/api/runs", json=req, headers=auth(other)).json()["run_id"] != first   # keyed per account


def test_a_start_that_fails_refunds_the_run(client, monkeypatch):
    token = issue_token(client)

    def broken_start(*a, **kw):
        raise RuntimeError("worker could not start")

    monkeypatch.setattr(registry, "start", broken_start)
    with pytest.raises(RuntimeError):
        client.post("/api/runs", json={"job_description": "jd", "pace_seconds": 0}, headers=auth(token))
    assert runs_left(client, token) == 2


def test_runs_list_shows_your_runs_and_the_admin_sees_all(client):
    alice, bob = issue_token(client, "alice"), issue_token(client, "bob")
    for run_id, token, hour in (("r-a", alice, "01"), ("r-b", bob, "02")):
        registry.save_log({"id": run_id, "job_description": "jd", "mode": "offline",
                           "started": f"2026-10-12T{hour}:00:00+00:00", "owner": profile_of(token),
                           "token_id": "t", "cv": None, "sample_cv": False, "events": []})
    assert [r["id"] for r in client.get("/api/runs", headers=auth(alice)).json()["runs"]] == ["r-a"]
    assert [r["id"] for r in client.get("/api/runs", headers=auth(ADMIN)).json()["runs"]] == ["r-b", "r-a"]


@pytest.mark.parametrize("path", ["/api/runs/unknown/log", "/api/runs/unknown/document"])
def test_an_unknown_run_is_a_404(client, path):
    assert client.get(path, headers=auth(issue_token(client))).status_code == 404


def test_a_document_in_an_unknown_format_is_a_422(client):
    assert client.get("/api/runs/x/document?fmt=pdf", headers=auth(ADMIN)).status_code == 422


# --- POST /api/runs/{id}/gate --------------------------------------------------
@pytest.mark.parametrize("body", [
    {"decision": "approve", "feedback": "x" * 2001},
    {"decision": "approve", "gap_answers": {f"k{i}": "a" for i in range(21)}},
    {"decision": "approve", "gap_answers": {"k" * 201: "a"}},
    {"decision": "approve", "gap_answers": {"": "a"}},
    {"decision": "approve", "gap_answers": {"k": "a" * 2001}},
    {"decision": "edit", "edited_content": "x" * 50_001},
    {"feedback": "no decision"},
], ids=["feedback", "too-many-answers", "long-key", "empty-key", "long-answer", "huge-edit", "no-decision"])
def test_a_malformed_gate_answer_is_a_422_before_any_run_lookup(client, body):
    assert client.post("/api/runs/unknown/gate", json=body, headers=auth(ADMIN)).status_code == 422


def test_answering_an_unknown_run_is_a_404(client):
    assert client.post("/api/runs/unknown/gate", json={"decision": "approve"}, headers=auth(ADMIN)).status_code == 404


def test_the_gate_route_refuses_answers_that_do_not_fit_the_open_gate(client):
    token = issue_token(client)
    run_id = client.post("/api/runs", json={"job_description": "jd", "pace_seconds": 0}, headers=auth(token)).json()["run_id"]
    gate = wait_for_gate(client, run_id, token, n=1)
    assert gate["gate"] == "gate1_requirements"
    post = lambda **body: client.post(f"/api/runs/{run_id}/gate", json=body, headers=auth(token))   # noqa: E731
    assert post(decision="approve", gate="gate3_fit").status_code == 409                    # a stale form
    assert post(decision="approve", gap_answers={"Kubernetes": "yes"}).status_code == 422    # not the gap gate
    assert post(decision="approve", edited_content="my cv").status_code == 422               # not the final gate
    answer(client, run_id, token)
    wait_for_gate(client, run_id, token, n=2)
    assert post(decision="approve", gap_answers={"Not asked": "x"}).status_code == 422       # unknown key at gate 2


def _parked(client, token, gate):
    """A run record parked in the registry with `gate` as its open gate: no
    worker, so nothing races the answer."""
    run = {"id": "parked01", "owner": profile_of(token), "gate": gate, "gate_answer": None,
           "lock": threading.Lock(), "gate_event": threading.Event(), "done": False, "events": []}
    registry._runs[run["id"]] = run
    return run


@pytest.mark.parametrize("gate, detail", [
    (None, "No gate is waiting on this run"),
    ({"gate": "gate1_requirements", "answered": True}, "This review was already answered"),
], ids=["between-gates", "already-answered"])
def test_an_answer_with_nothing_to_answer_is_a_409_that_changes_nothing(client, gate, detail):
    token = issue_token(client)
    run = _parked(client, token, gate)
    resp = client.post("/api/runs/parked01/gate", json={"decision": "reject"}, headers=auth(token))
    assert resp.status_code == 409 and resp.json()["detail"] == detail
    assert run["gate_answer"] is None and not run["gate_event"].is_set()


# --- /api/auth: top-ups over HTTP ----------------------------------------------
def test_a_topup_goes_through_request_more_and_lands_on_the_same_token(client):
    token = issue_token(client)
    client.post("/api/runs", json={"job_description": "jd", "pace_seconds": 0}, headers=auth(token))
    req = client.post("/api/auth/request-more", json={"note": "more please"}, headers=auth(token))
    assert req.status_code == 200 and req.json()["kind"] == "topup"
    assert client.post("/api/auth/request-more", json={}, headers=auth(token)).status_code == 400   # one at a time
    approved = client.post(f"/api/auth/requests/{req.json()['id']}/approve", headers=auth(ADMIN)).json()
    assert "token" not in approved                                       # nothing new is minted
    assert runs_left(client, token) == 1 + config.DEFAULT_RUN_ALLOWANCE


def test_auth_bodies_are_validated_at_the_boundary(client):
    assert client.post("/api/auth/request-access", json={}).status_code == 422
    assert client.post("/api/auth/login", json={}).status_code == 422
    assert client.post("/api/auth/request-access", json={"identifier": "x" * 65}).status_code == 400


# --- /api/profile/entries + /api/kb + /api/search --------------------------------
def test_a_profile_entry_is_scoped_over_http_and_a_refused_edit_is_audited(client):
    alice, bob = issue_token(client, "alice"), issue_token(client, "bob")
    created = client.post("/api/profile/entries", json={"section": "skills", "record": {"name": "Go"}},
                          headers=auth(alice)).json()
    assert created["owner"] == profile_of(alice)
    assert client.get("/api/profile/entries", headers=auth(bob)).json() == {"entries": []}
    resp = client.put(f"/api/profile/entries/{created['id']}", json={"section": "skills", "record": {"name": "x"}},
                      headers=auth(bob))
    assert resp.status_code == 403
    assert [e["profile_id"] for e in audit_lines() if e["event"] == "forbidden"] == [profile_of(bob)]
    assert client.post("/api/profile/entries", json={"section": "skills"}, headers=auth(alice)).status_code == 422
    # The save reached the (fake) index under a stable id, synchronously.
    assert f"skill:{created['id']}" in set(backend_vectorstore._store._collection("profile").get()["ids"])


def test_an_unknown_profile_section_is_refused(client):
    resp = client.post("/api/profile/entries", json={"section": "hobbies", "record": {"name": "chess"}},
                       headers=auth(issue_token(client)))
    assert resp.status_code == 422


def test_the_kb_mirror_of_manual_entries_is_scoped_too(client):
    alice, bob = issue_token(client, "alice"), issue_token(client, "bob")
    client.post("/api/profile/entries", json={"section": "skills", "record": {"name": "A"}}, headers=auth(alice))
    # kb_file reads KB_DIR/profile/; point it at the same tmp file the profile routes use.
    kb_routes_dir = profile_routes.MANUAL_ENTRIES.parent.parent
    with pytest.MonkeyPatch.context() as m:
        m.setattr(kb_routes, "KB_DIR", kb_routes_dir)
        body = client.get("/api/kb/profile/manual_entries", headers=auth(bob)).json()
        assert body["total"] == 0 and body["records"] == []
        assert client.get("/api/kb/profile/manual_entries", headers=auth(alice)).json()["total"] == 1


def _case_insensitive_fs() -> bool:
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "probe.txt").write_text("x", encoding="utf-8")
        return (Path(d) / "PROBE.TXT").exists()


def test_no_spelling_of_manual_entries_skips_the_owner_scope(client):
    alice, bob = issue_token(client, "alice"), issue_token(client, "bob")
    client.post("/api/profile/entries", json={"section": "skills", "record": {"name": "alice-only"}}, headers=auth(alice))
    with pytest.MonkeyPatch.context() as m:
        m.setattr(kb_routes, "KB_DIR", profile_routes.MANUAL_ENTRIES.parent.parent)
        resp = client.get("/api/kb/profile/MANUAL_ENTRIES", headers=auth(bob))
    assert resp.status_code == 404 or "alice-only" not in resp.text


@pytest.mark.parametrize("path", ["/api/kb/profile/..%2Fauth%2Ftokens", "/api/kb/auth/tokens", "/api/kb/profile/%2E%2E"])
def test_the_kb_browser_never_serves_outside_its_stores_over_http(client, path):
    assert client.get(path, headers=auth(issue_token(client))).status_code == 404


def test_search_validates_its_body(client):
    token = issue_token(client)
    assert client.post("/api/search", json={}, headers=auth(token)).status_code == 422
    assert client.post("/api/search", json={"query": "x", "k": "five"}, headers=auth(token)).status_code == 422


@pytest.mark.xfail(strict=True, reason="backend/bugs.md '2026-10-09 (design)' §4: /search is still unscoped "
                                       "(deferred: needs owner metadata on the profile vectors)")
def test_search_never_returns_another_accounts_entries(client):
    alice, bob = issue_token(client, "alice"), issue_token(client, "bob")
    client.post("/api/profile/entries", json={"section": "skills", "record": {"name": "zebra wrangling"}},
                headers=auth(alice))
    hits = client.post("/api/search", json={"query": "zebra wrangling", "collection": "profile", "k": 5},
                       headers=auth(bob)).json()["hits"]
    assert all("zebra" not in h["text"] for h in hits)


# --- /api/profile/cv -------------------------------------------------------------
def test_no_cv_yet_is_a_null_never_a_404(client):
    resp = client.get("/api/profile/cv", headers=auth(bare_token(client, "fresh")))
    assert resp.status_code == 200 and resp.json() == {"cv": None}


@pytest.mark.parametrize("content, status", [
    (b"PK\x03\x04 a docx really", 415),
    (b"%PDF-" + b"0" * (5 * 1024 * 1024), 413),
], ids=["not-a-pdf", "over-5mb"])
def test_an_upload_is_checked_by_magic_bytes_and_size_first(client, monkeypatch, content, status):
    called = []
    monkeypatch.setattr(cv_store, "ingest_pending", lambda *a: called.append(a))
    resp = client.post("/api/profile/cv", files={"file": ("cv.pdf", content, "application/pdf")},
                       headers=auth(bare_token(client, "up")))
    assert resp.status_code == status and called == []                   # never parsed


@pytest.mark.parametrize("error, status, detail", [
    (cv_store.CvTooManyPages(9), 422, "too_many_pages"), (cv_store.CvNoText(), 422, "no_text"),
    (cv_store.CvNoSections(), 422, "no_sections"), (cv_store.CvUnreadable("bad xref"), 415, None),
], ids=["pages", "no-text", "no-sections", "unreadable"])
def test_each_parse_failure_maps_to_its_status(client, monkeypatch, error, status, detail):
    def fail(*a):
        raise error

    monkeypatch.setattr(cv_store, "ingest_pending", fail)
    resp = client.post("/api/profile/cv", files={"file": ("cv.pdf", b"%PDF-1.4 x", "application/pdf")},
                       headers=auth(bare_token(client, "up")))
    assert resp.status_code == status and (detail is None or resp.json()["detail"] == detail)


def test_an_accepted_upload_is_201_with_its_preview(client, monkeypatch):
    token = bare_token(client, "up")
    seen = []

    def fake_ingest(owner, content, filename, max_pages):
        seen.append((owner, filename, max_pages))
        return {"id": "abc"}, {"sections": [], "warnings": []}

    monkeypatch.setattr(cv_store, "ingest_pending", fake_ingest)
    resp = client.post("/api/profile/cv", files={"file": ("My CV.pdf", b"%PDF-1.4 x", "application/pdf")},
                       headers=auth(token))
    assert resp.status_code == 201 and resp.json() == {"cv": {"id": "abc"}, "preview": {"sections": [], "warnings": []}}
    assert seen == [(profile_of(token), "My CV.pdf", 4)]                  # the caller's own account, the page cap


def test_another_accounts_cv_id_is_a_403_and_their_cv_survives(client):
    alice = issue_token(client, "alice")
    bob = bare_token(client, "bob")
    assert client.post("/api/profile/cv/seededcv0001/confirm", headers=auth(bob)).status_code == 403
    assert client.delete("/api/profile/cv/seededcv0001", headers=auth(bob)).status_code == 403
    assert client.get("/api/profile/cv", headers=auth(alice)).json()["cv"]["id"] == "seededcv0001"


def test_deleting_your_own_cv_is_a_204_with_no_body(client):
    token = issue_token(client)
    resp = client.delete("/api/profile/cv/seededcv0001", headers=auth(token))
    assert resp.status_code == 204 and resp.content == b""
    assert client.get("/api/profile/cv", headers=auth(token)).json() == {"cv": None}


# --- /api/logs + /api/admin/users ------------------------------------------------
def test_my_logs_show_only_my_entries_and_the_admin_sees_everyone(client):
    alice, bob = issue_token(client, "alice"), issue_token(client, "bob")
    for token in (alice, bob):
        client.post("/api/auth/login", json={"token": token})
    mine = client.get("/api/logs/mine", headers=auth(alice)).json()["entries"]
    assert mine and {e["event"] for e in mine} <= {"login_ok", "request_approved"}
    assert all("profile_id" not in e and "actor" not in e for e in mine)
    everyone = client.get("/api/admin/logs?event=login_ok", headers=auth(ADMIN)).json()["entries"]
    assert {e["profile_id"] for e in everyone} == {profile_of(alice), profile_of(bob)}
    assert client.get("/api/logs/mine?limit=abc", headers=auth(alice)).status_code == 422


def test_admin_vault_access_is_audited_first_and_scoped_to_that_account(client):
    alice, bob = issue_token(client, "alice"), issue_token(client, "bob")
    client.post("/api/profile/entries", json={"section": "skills", "record": {"name": "A"}}, headers=auth(alice))
    client.post("/api/profile/entries", json={"section": "skills", "record": {"name": "B"}}, headers=auth(bob))
    got = client.get(f"/api/admin/users/{profile_of(alice)}/profile", headers=auth(ADMIN)).json()["entries"]
    assert [e["record"]["name"] for e in got] == ["A"]                    # that one account, not everyone's
    assert client.get(f"/api/admin/users/{profile_of(alice)}/cv", headers=auth(ADMIN)).json()["cv"]["id"] == "seededcv0001"
    access = [e for e in audit_lines() if e["event"] == "admin_data_access"]
    assert [(e["profile_id"], e["fields"]["resource"]) for e in access] == [(profile_of(alice), "profile"),
                                                                           (profile_of(alice), "cv")]
    seen = client.get("/api/logs/mine", headers=auth(alice)).json()["entries"]
    assert {"resource": "cv"} in [e["fields"] for e in seen if e["event"] == "admin_data_access"]   # the user sees it


@pytest.mark.parametrize("profile_id", ["p-00000000", "..%2F..%2Fauth", "p-__admin__"])
def test_an_unknown_account_on_the_admin_route_is_a_404(client, profile_id):
    assert client.get(f"/api/admin/users/{profile_id}/cv", headers=auth(ADMIN)).status_code == 404
    assert [e for e in audit_lines() if e["event"] == "admin_data_access"] == []   # nothing opened, nothing logged


def test_admin_vault_access_is_refused_when_the_audit_cannot_be_written(client, monkeypatch, tmp_path):
    alice = issue_token(client, "alice")
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(logplane, "LOG_DIR", blocker / "logplane")     # every write now fails
    resp = client.get(f"/api/admin/users/{profile_of(alice)}/cv", headers=auth(ADMIN))
    assert resp.status_code == 503 and "seededcv0001" not in resp.text


def test_a_403_on_the_events_route_is_attributed_to_its_caller(client):
    alice, bob = issue_token(client, "alice"), issue_token(client, "bob")
    run_id = client.post("/api/runs", json={"job_description": "jd", "pace_seconds": 0}, headers=auth(alice)).json()["run_id"]
    assert client.get(f"/api/runs/{run_id}/events?token={bob}").status_code == 403
    (entry,) = [e for e in audit_lines() if e["event"] == "forbidden"]
    assert entry["profile_id"] == profile_of(bob)


# =============================================================================
# Backend authentication over HTTP (2026-10-13): what every 401 says, which
# door takes which credential, revocation and rotation, the one time a raw
# token is shown, body fields that try to aim a request at someone else, one
# account behind two tokens, scope from the token alone, and where a
# credential may and may not end up.
# =============================================================================
UNAUTHENTICATED = {"detail": "Invalid or missing access token"}


def _drop_token(token):
    """Revoke by hand, the only way there is: take the record out of tokens.json."""
    path = config.KB_AUTH_DIR / "tokens.json"
    write_json(path, [t for t in json.loads(path.read_text(encoding="utf-8")) if t["token"] != token])


def _start(client, token):
    return client.post("/api/runs", json={"job_description": "jd", "pace_seconds": 0}, headers=auth(token)).json()["run_id"]


def test_every_401_reads_the_same_so_a_caller_learns_nothing(client):
    live, gone = issue_token(client, "live"), issue_token(client, "gone")
    run_id = _start(client, live)
    _drop_token(gone)
    refused = [client.get("/api/auth/me", headers=h) for h in (
        {}, {"Authorization": "Basic eDp5"}, {"Authorization": "Bearer"}, {"Authorization": "Bearer never-issued"},
        {"Authorization": f"Bearer {gone}"}, {"Authorization": f"Bearer {live}x"})]
    refused += [client.get(f"/api/runs/{rid}/events{q}") for rid in (run_id, "no-such-run")
                for q in ("", "?token=never-issued", f"?token={gone}")]   # no run-existence oracle either
    refused.append(client.get(f"/api/runs/{run_id}/events", headers=auth(live)))   # the stream reads no header
    for resp in refused:
        assert (resp.status_code, resp.json()) == (401, UNAUTHENTICATED), resp.request.url
    login = [client.post("/api/auth/login", json={"token": t}) for t in ("never-issued", gone)]
    assert {r.status_code for r in login} == {401} and login[0].json() == login[1].json()


@pytest.mark.parametrize("route", sorted(ADMIN_ROUTES | USER_ROUTES), ids=lambda r: f"{r[0]} {r[1]}")
def test_a_query_token_opens_no_route_but_the_event_stream(client, route):
    # A URL token lands in access logs and browser history, so only the route
    # EventSource forces into it takes one (deps.identity_from_query_token).
    method, path = route
    resp = client.request(method, _filled(path), params={"token": ADMIN},
                          **({"json": {}} if method in ("POST", "PUT") else {}))
    assert resp.status_code == 401, (route, resp.status_code)


@pytest.mark.parametrize("header", ["Bearer stale-token", "Basic eDp5", "garbage"])
def test_the_open_routes_ignore_a_stale_authorization_header(client, header):
    # The login screen can still hold a dead token; it must never block a sign-in.
    token = issue_token(client)
    stale = {"Authorization": header}
    assert client.get("/api/health", headers=stale).status_code == 200
    assert client.post("/api/auth/request-access", json={"identifier": "newcomer"}, headers=stale).status_code == 200
    resp = client.post("/api/auth/login", json={"token": token}, headers=stale)
    assert resp.status_code == 200 and resp.json()["profile_id"] == profile_of(token)


def test_revoking_a_token_or_rotating_the_admin_token_bites_on_the_next_request(client, monkeypatch):
    token = issue_token(client, "rev")
    assert client.get("/api/auth/me", headers=auth(token)).status_code == 200
    _drop_token(token)                                                   # no session is cached anywhere
    assert client.get("/api/auth/me", headers=auth(token)).status_code == 401
    assert client.post("/api/auth/login", json={"token": token}).status_code == 401
    monkeypatch.setattr(config, "ADMIN_TOKEN", "rotated-admin-secret")
    assert client.get("/api/auth/requests", headers=auth(ADMIN)).status_code == 401
    assert client.get("/api/auth/me", headers=auth("rotated-admin-secret")).json()["role"] == "admin"


def test_login_is_me_and_writes_nothing_but_its_audit_line(client):
    token = issue_token(client)
    files = {p.name: p.read_bytes() for p in config.KB_AUTH_DIR.iterdir()}
    for raw in (token, ADMIN):
        login = client.post("/api/auth/login", json={"token": raw})
        assert login.status_code == 200 and login.json() == client.get("/api/auth/me", headers=auth(raw)).json()
    assert {p.name: p.read_bytes() for p in config.KB_AUTH_DIR.iterdir()} == files   # mints and spends nothing
    for body in ({"token": 123}, {"token": None}, {"token": ["x"]}, {"tok": token}):
        assert client.post("/api/auth/login", json=body).status_code == 422, body
    assert client.post("/api/auth/login", json={"token": ""}).status_code == 401
    logins = [(e["event"], e["profile_id"]) for e in audit_lines() if e["event"].startswith("login")]
    assert logins == [("login_ok", profile_of(token)), ("login_ok", store.ADMIN_PROFILE_ID), ("login_failed", None)]


def test_an_approval_shows_the_raw_token_once_and_nowhere_after(client):
    req = client.post("/api/auth/request-access", json={"identifier": "gil"}).json()
    raw = client.post(f"/api/auth/requests/{req['id']}/approve", headers=auth(ADMIN)).json()["token"]
    later = [
        client.post(f"/api/auth/requests/{req['id']}/approve", headers=auth(ADMIN)),   # the retried click
        client.get("/api/auth/requests", headers=auth(ADMIN)),
        client.get("/api/auth/me", headers=auth(raw)),
        client.post("/api/auth/login", json={"token": raw}),
        client.post("/api/auth/request-more", json={}, headers=auth(raw)),
        client.get("/api/admin/logs", headers=auth(ADMIN)),
        client.get("/api/logs/mine", headers=auth(raw)),
    ]
    assert later[0].status_code == 409
    for resp in later:
        assert raw not in resp.text, resp.request.url
    approved = client.post(f"/api/auth/requests/{later[4].json()['id']}/approve", headers=auth(ADMIN)).json()
    assert "token" not in approved and raw not in json.dumps(approved)  # a top-up mints nothing to show


def test_body_fields_cannot_aim_a_signup_at_another_account(client):
    victim = issue_token(client, "victim")
    smuggled = {"identifier": "mallory", "kind": "topup", "token_id": store.resolve_token(victim)["id"],
                "status": "approved", "role": "admin", "runs_remaining": 999, "id": "fixed001",
                "profile_id": profile_of(victim)}
    req = client.post("/api/auth/request-access", json=smuggled).json()
    assert (req["kind"], req["token_id"], req["status"]) == ("signup", None, "pending") and req["id"] != "fixed001"
    raw = client.post(f"/api/auth/requests/{req['id']}/approve", headers=auth(ADMIN)).json()["token"]
    me = client.get("/api/auth/me", headers=auth(raw)).json()
    assert (me["role"], me["runs_remaining"]) == ("user", config.DEFAULT_RUN_ALLOWANCE)
    assert me["profile_id"] not in (profile_of(victim), store.ADMIN_PROFILE_ID)
    assert runs_left(client, victim) == config.DEFAULT_RUN_ALLOWANCE      # the victim's account never moved


def test_body_fields_cannot_aim_a_topup_at_another_account(client):
    alice, bob = issue_token(client, "alice"), issue_token(client, "bob")
    smuggled = {"note": "", "token_id": store.resolve_token(bob)["id"], "identifier": "bob", "kind": "signup"}
    req = client.post("/api/auth/request-more", json=smuggled, headers=auth(alice)).json()
    assert (req["kind"], req["identifier"], req["token_id"]) == ("topup", "alice", store.resolve_token(alice)["id"])
    client.post(f"/api/auth/requests/{req['id']}/approve", headers=auth(ADMIN))
    assert (runs_left(client, alice), runs_left(client, bob)) == \
        (2 * config.DEFAULT_RUN_ALLOWANCE, config.DEFAULT_RUN_ALLOWANCE)


def test_one_account_is_one_vault_whichever_of_its_tokens_is_used(client):
    # The account is profile_id; a re-issued token is a new credential on the
    # same account (backend §1). The run allowance stays on the credential.
    first = issue_token(client, "ava")
    record = store.resolve_token(first)
    second = "SECOND-CREDENTIAL-FOR-AVA"
    path = config.KB_AUTH_DIR / "tokens.json"
    write_json(path, json.loads(path.read_text(encoding="utf-8")) + [
        {**record, "id": "t-5ec0d001", "token": second, "runs_remaining": 1, "request_id": "reissue"}])
    me = client.get("/api/auth/me", headers=auth(second)).json()
    assert (me["profile_id"], me["token_id"]) == (record["profile_id"], "t-5ec0d001")
    client.post("/api/profile/entries", json={"section": "skills", "record": {"name": "Go"}}, headers=auth(first))
    assert [e["record"]["name"] for e in client.get("/api/profile/entries", headers=auth(second)).json()["entries"]] == ["Go"]
    assert client.get("/api/profile/cv", headers=auth(second)).json()["cv"]["id"] == "seededcv0001"
    run_id = _start(client, second)
    wait_for_gate(client, run_id, second)
    registry.abort(registry.get(run_id))
    finish(run_id)
    assert run_id in [r["id"] for r in client.get("/api/runs", headers=auth(first)).json()["runs"]]
    assert client.get(f"/api/runs/{run_id}/log", headers=auth(first)).json()["token_id"] == "t-5ec0d001"   # the trail
    assert (runs_left(client, first), runs_left(client, second)) == (config.DEFAULT_RUN_ALLOWANCE, 0)


def test_scope_comes_from_the_token_never_from_the_query(client):
    alice, bob = issue_token(client, "alice"), bare_token(client, "bob")
    client.post("/api/profile/entries", json={"section": "skills", "record": {"name": "alice-only"}}, headers=auth(alice))
    registry.save_log({"id": "r-alice", "job_description": "alice-jd", "mode": "offline",
                       "started": "2026-10-13T01:00:00+00:00", "owner": profile_of(alice),
                       "token_id": "t", "cv": None, "sample_cv": False, "events": []})
    for token in (alice, bob):
        client.post("/api/auth/login", json={"token": token})
    widen = {"profile_id": profile_of(alice), "owner": profile_of(alice), "role": "admin"}
    for path in ("/api/logs/mine", "/api/profile/entries", "/api/profile/cv", "/api/runs"):
        plain = client.get(path, headers=auth(bob))
        assert client.get(path, params=widen, headers=auth(bob)).json() == plain.json(), path
        assert not {"alice-only", "alice-jd", "seededcv0001"} & set(re.findall(r"[\w-]+", plain.text)), path


def test_no_credential_appears_in_any_response_or_any_file_but_tokens_json(client, tmp_path):
    alice, bob = issue_token(client, "alice"), issue_token(client, "bob")
    credentials = (alice, bob, ADMIN)
    client.post("/api/auth/login", json={"token": alice})
    client.post("/api/auth/login", json={"token": "a-wrong-guess-" + bob})   # a failed sign-in that contains one
    client.post("/api/auth/request-more", json={"note": "more"}, headers=auth(alice))
    client.post("/api/profile/entries", json={"section": "skills", "record": {"name": "Go"}}, headers=auth(alice))
    run_id = _start(client, alice)
    wait_for_gate(client, run_id, alice)
    assert client.get(f"/api/runs/{run_id}/events?token={bob}").status_code == 403   # a URL token on a refused call
    registry.abort(registry.get(run_id))
    finish(run_id)
    pid = profile_of(alice)
    responses = [client.get(path, headers=auth(token)) for path, token in (
        ("/api/config", alice), ("/api/auth/me", alice), ("/api/runs", alice), (f"/api/runs/{run_id}/log", alice),
        ("/api/profile/entries", alice), ("/api/profile/cv", alice), ("/api/logs/mine", alice), ("/api/logs/mine", bob),
        ("/api/auth/me", ADMIN), ("/api/auth/requests", ADMIN), ("/api/runs", ADMIN), ("/api/admin/logs", ADMIN),
        (f"/api/admin/users/{pid}/profile", ADMIN), (f"/api/admin/users/{pid}/cv", ADMIN))]
    responses.append(client.get(f"/api/runs/{run_id}/events", params={"token": alice}))
    for resp in responses:
        assert resp.status_code == 200, resp.request.url
        assert not [c for c in credentials if c in resp.text], resp.request.url
    tokens_json = (config.KB_AUTH_DIR / "tokens.json").resolve()
    stored = [p for p in tmp_path.rglob("*") if p.is_file() and p.resolve() != tokens_json]
    assert {p.parent.name for p in stored} >= {"auth", "logplane", "runs", "cv"}   # the crawl reached every store
    for path in stored:
        data = path.read_bytes()
        assert not [c for c in credentials if c.encode() in data], path.relative_to(tmp_path)


def test_without_an_admin_token_the_app_warns_and_no_credential_is_admin(monkeypatch, caplog):
    from backend.app import app

    monkeypatch.setattr(config, "ADMIN_TOKEN", "")
    with caplog.at_level(logging.WARNING, logger="backend"), TestClient(app) as c:
        assert any("ADMIN_TOKEN is empty" in r.getMessage() for r in caplog.records)
        assert c.post("/api/auth/request-access", json={"identifier": "early"}).status_code == 200   # still open
        for header in ("Bearer", "Bearer   ", 'Bearer ""', "Bearer admin-secret", "Bearer None"):
            assert c.get("/api/auth/requests", headers={"Authorization": header}).status_code == 401, header
        for raw in ("", "admin-secret", "None"):
            assert c.post("/api/auth/login", json={"token": raw}).status_code == 401, raw


def test_the_admin_cannot_queue_a_topup_it_can_never_be_granted(client):
    resp = client.post("/api/auth/request-more", json={}, headers=auth(ADMIN))
    assert resp.status_code == 400
    assert client.get("/api/auth/requests", headers=auth(ADMIN)).json()["requests"] == []


def test_a_rejected_topup_shows_in_that_accounts_own_log(client):
    token = issue_token(client, "tess")
    req = client.post("/api/auth/request-more", json={}, headers=auth(token)).json()
    assert client.post(f"/api/auth/requests/{req['id']}/reject", headers=auth(ADMIN)).status_code == 200
    events = [e["event"] for e in client.get("/api/logs/mine", headers=auth(token)).json()["entries"]]
    assert "request_more" in events and "request_rejected" in events


def test_a_legacy_token_under_a_name_the_new_rule_refuses_can_still_sign_in():
    from backend.app import app

    write_json(config.KB_AUTH_DIR / "tokens.json", [
        {"id": "t-1e9ac701", "token": "LEGACY-ROOT-TOKEN", "identifier": "root", "role": "user",
         "runs_remaining": 2, "created": "2026-09-01T00:00:00+00:00", "request_id": "r-old"}])
    with TestClient(app, raise_server_exceptions=False) as c:
        login = c.post("/api/auth/login", json={"token": "LEGACY-ROOT-TOKEN"})
        me = c.get("/api/auth/me", headers=auth("LEGACY-ROOT-TOKEN"))
    assert (login.status_code, me.status_code) == (200, 200)
    assert re.fullmatch(r"p-[0-9a-f]{8}", me.json()["profile_id"])


# =============================================================================
# Third pass (2026-10-14, Instruction-test.md §5.13, §5.17)
# =============================================================================
# - POST /api/runs/{run_id}/resume had no test. StubGraph now keeps per-thread
#   checkpoints and answers get_state, as a real graph on SQLite does, so a run can be
#   picked up on a NEW graph after its worker is gone, and a finished run is closed
#   (close_run) instead of failing silently on a missing get_state.
# - The stub is held to the worker's real calls and to the real gate's payload.
# - The frontend's calls are read as text and held to the backend's route table (no npm).
import ast
import inspect

_REPO = Path(__file__).resolve().parent.parent


def _start_run(client, token, jd="jd"):
    resp = client.post("/api/runs", json={"job_description": jd, "pace_seconds": 0}, headers=auth(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["run_id"]


def _parked_then_lost(client, token):
    """A run parked at gate 2 whose worker is gone; its log and its checkpoint stay, as after a restart."""
    run_id = _start_run(client, token)
    wait_for_gate(client, run_id, token, n=1)
    answer(client, run_id, token)
    wait_for_gate(client, run_id, token, n=2)
    registry.abort(registry.get(run_id))
    finish(run_id)
    return run_id


def _resume(client, run_id, token):
    return client.post(f"/api/runs/{run_id}/resume", headers=auth(token))


def test_a_run_whose_worker_died_resumes_at_its_gate_and_finishes(client):
    """Catches a resume that restarts the run, spends a run again, or loses the gate it was parked on."""
    token = issue_token(client)
    run_id = _parked_then_lost(client, token)
    left = runs_left(client, token)
    resp = _resume(client, run_id, token)
    assert resp.status_code == 200 and resp.json() == {"run_id": run_id}
    assert runs_left(client, token) == left                                  # never charged twice
    assert wait_for_gate(client, run_id, token, n=2)["gate"] == "gate2_evidence"
    answer(client, run_id, token)
    for n in (3, 4):
        wait_for_gate(client, run_id, token, n=n)
        answer(client, run_id, token)
    events = finish(run_id)["events"]
    assert [e["type"] for e in events].count("run_started") == 1
    assert [e.get("node") for e in events if e["type"] == "node_done"].count("jd_analysis") == 1
    resumed = BUILT[-1]
    assert resumed.first_input is None and resumed.answers[0]["decision"] == "approve"   # picked up, not restarted
    done = [e for e in events if e["type"] == "run_done"][-1]
    assert done["final"]["review"]["approved"] is True
    assert (config.OUTPUTS_DIR / done["final"]["export"]["md"]).is_file()
    assert any(line.get("event") == "run_resumed" and line.get("run_id") == run_id for line in audit_lines())


def test_resume_refuses_an_unknown_run_and_someone_elses(client):
    """Catches a resume that drives another account's run, or reveals whether a run exists."""
    alice, bob = issue_token(client, "alice"), issue_token(client, "bob")
    run_id = _parked_then_lost(client, alice)
    assert _resume(client, "nope0001", alice).status_code == 404
    assert _resume(client, run_id, bob).status_code == 403
    assert registry.get(run_id)["done"] is True                              # nothing restarted


def test_resume_refuses_a_run_its_worker_is_still_driving(client):
    """Catches two workers on one run: both would answer the same gate."""
    token = issue_token(client)
    run_id = _start_run(client, token)
    wait_for_gate(client, run_id, token, n=1)
    resp = _resume(client, run_id, token)
    assert resp.status_code == 409 and resp.json()["detail"] == "A worker is already driving this run"


def test_resume_refuses_a_finished_run(client):
    """Catches a finished run being reopened (and its CV re-exported) by a stray resume."""
    token = issue_token(client)
    run_id = _start_run(client, token)
    for n in range(1, 5):
        wait_for_gate(client, run_id, token, n=n)
        answer(client, run_id, token)
    finish(run_id)
    resp = _resume(client, run_id, token)
    assert resp.status_code == 409 and resp.json()["detail"] == "This run is not parked at a gate"


def test_resume_refuses_while_another_run_of_the_owner_is_active(client):
    """Catches a resume clobbering the owner's one active slot (the start/resume race the lock prevents)."""
    token = issue_token(client)
    lost = _parked_then_lost(client, token)
    other = _start_run(client, token, jd="second")
    wait_for_gate(client, other, token, n=1)
    resp = _resume(client, lost, token)
    assert resp.status_code == 409 and resp.json()["detail"] == "Another run is already active for this owner"
    assert registry.get(other)["done"] is False


def test_resume_refuses_a_log_from_before_ownership(client):
    """Catches a legacy run resumed into a slot no account owns."""
    config.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    write_json(config.RUNS_DIR / "old98.json", {"id": "old98", "started": "2026-01-01T00:00:00+00:00",
                                                "mode": "offline", "job_description": "legacy", "events": []})
    resp = _resume(client, "old98", ADMIN)
    assert resp.status_code == 409 and "predates ownership" in resp.json()["detail"]


def test_a_finished_run_is_closed_and_its_cv_saved_under_its_owner(client):
    """Catches the run close failing silently (it did, while the stub had no get_state)."""
    token = issue_token(client)
    run_id = _start_run(client, token)
    for n in range(1, 5):
        wait_for_gate(client, run_id, token, n=n)
        answer(client, run_id, token)
    done = [e for e in finish(run_id)["events"] if e["type"] == "run_done"][-1]
    assert "final_error" not in done
    assert done["final"]["export"]["md"]
    resp = client.get(f"/api/runs/{run_id}/document?fmt=md", headers=auth(token))   # served to its owner
    assert resp.status_code == 200 and "THE CV BODY" in resp.text


# --- the stub is held to the real graph -------------------------------------------------
def _graph_calls_in_worker() -> set[str]:
    tree = ast.parse((_REPO / "backend" / "runs" / "worker.py").read_text(encoding="utf-8"))
    return {n.func.attr for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and isinstance(n.func.value, ast.Name) and n.func.value.id == "graph"}


def test_the_stub_answers_every_call_the_worker_makes_on_the_real_graph():
    """Catches the worker starting to use a graph method the stub lacks (tests would then pass on an except path)."""
    from langgraph.pregel import Pregel

    calls = _graph_calls_in_worker()
    assert {"stream", "get_state"} <= calls
    for name in calls:
        assert callable(getattr(StubGraph, name, None)), name
        assert callable(getattr(Pregel, name, None)), name
    assert {"config", "stream_mode"} <= set(inspect.signature(Pregel.stream).parameters)
    build = next(n for n in ast.parse((_REPO / "agents" / "supervisor.py").read_text(encoding="utf-8")).body
                 if isinstance(n, ast.FunctionDef) and n.name == "build_graph")
    assert "checkpointer" in [a.arg for a in build.args.args]               # worker calls BUILD_GRAPH(checkpointer=...)


def test_the_stub_pauses_with_exactly_the_payload_the_real_gate_sends(monkeypatch):
    """Catches a stub payload missing a key the real gate sends (gate 4's diff), or one it never sends."""
    from state.state import GraphState
    from utils import human_gate as gate_mod

    sent = {}

    def capture(payload):
        sent[payload["gate"]] = set(payload)
        return {"decision": "approve"}

    monkeypatch.setattr(gate_mod, "log_state_snapshot", lambda state, label: "(not written)")
    monkeypatch.setattr(gate_mod, "interrupt", capture)
    for gate in worker.GATES:
        gate_mod.human_gate(GraphState(), gate)
    stub = {payload["gate"]: set(payload) for _, payload in StubGraph.SEGMENTS if payload}
    assert stub == sent


# --- the frontend's calls, read as text ---------------------------------------------------
_JS_CALL = re.compile(r"\b(get|post|put|del|upload|useFetch|downloadFromApi)\(\s*([`\"])(/[^`\"]*)\2")
_JS_METHOD = {"get": "GET", "useFetch": "GET", "downloadFromApi": "GET",
              "post": "POST", "upload": "POST", "put": "PUT", "del": "DELETE"}


def _frontend_calls() -> set[tuple[str, str, str]]:
    calls = set()
    for path in sorted((_REPO / "frontend" / "src").rglob("*.js*")):
        text = path.read_text(encoding="utf-8")
        for verb, _, url in _JS_CALL.findall(text):
            calls.add((_JS_METHOD[verb], url, path.name))
        for url in re.findall(r"new EventSource\(`/api(/[^`]*)`", text):
            calls.add(("GET", url, path.name))
    return calls


def _segments(url: str) -> list[str]:
    url = url.split("?")[0]
    parts = url.strip("/").split("/")
    return [p if p.startswith("${") else re.sub(r"\$\{[^}]*\}$", "", p) for p in parts]   # "events${query}"


def _served_by(method: str, url: str, routes: set[tuple[str, str]]) -> bool:
    mine = _segments(url)
    for m, path in routes:
        theirs = path[len("/api"):].strip("/").split("/")
        if m == method and len(theirs) == len(mine) and all(
                a.startswith("${") or b.startswith("{") or a == b for a, b in zip(mine, theirs)):
            return True
    return False


def test_every_call_the_frontend_makes_has_a_backend_route_with_that_method():
    """Catches a renamed or removed route the UI still calls (a 404/405 found only by clicking)."""
    from backend.app import app

    routes = {(m.upper(), p) for p, ops in app.openapi()["paths"].items() for m in ops}
    calls = _frontend_calls()
    assert len(calls) >= 20                                                    # the regex really found them
    missing = sorted((m, u, f) for m, u, f in calls if not _served_by(m, u, routes))
    assert missing == []


def test_every_agent_the_bridge_relays_has_a_title_in_the_ui():
    """Catches a node shown by its raw name (the cv_link gap of #41) or a title for a node that no longer exists."""
    src = (_REPO / "frontend" / "src" / "components" / "AgentGraph.jsx").read_text(encoding="utf-8")
    block = re.search(r"export const AGENT_TITLES = \{(.*?)\n\};", src, re.S).group(1)
    titled = set(re.findall(r"^\s*(\w+):", block, re.M))
    assert titled == set(worker.AGENTS)
