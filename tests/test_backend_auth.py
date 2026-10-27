"""
Auth store logic — pure file I/O, no server, no models.

config.KB_AUTH_DIR is redirected at a tmp_path per test, which is why every
path in backend/auth/store.py is resolved lazily inside the function rather
than captured at import time.

The second half covers the rest of the data layer the same way: the atomic JSON
helpers (backend/jsonstore.py), the gap-answer profile store
(learning/profile_store.py) and the learning store (learning/store.py,
learning/context_builder.py). Every path points into tmp_path; the vector store
is a fake. Logic, storage management, crash safety and writers that clash.

The auth store is also tested through its two consumers, called as plain
functions (no server): backend/deps.py (the 401-vs-403 doors) and
backend/routes/auth.py (AuthError -> HTTP status). The last section is the
export writer (utils/export.py) with its producer (utils/final_review.close_run)
and its reader (the GET /runs/{id}/document route), all under tmp_path.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import config
from backend import cv_store, deps, jsonstore, logplane
from backend import vectorstore as backend_vectorstore
from backend.auth import profiles, store
from backend.jsonstore import read_json, update_json, write_json
from backend.routes import auth as auth_routes
from backend.routes import logs as logs_routes
from backend.routes import profile as profile_routes
from backend.routes import runs as runs_routes
from backend.runs import registry
from learning import context_builder
from learning import profile_store
from learning import store as learning_store
from learning.store import LearningStore
from state.state import CVNode, CVTree, Document, GateFeedback, NodeKind, SectionType
from utils import export, final_review
from utils.cv_handling.cv_edit import render_markdown


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "KB_AUTH_DIR", tmp_path / "auth")
    monkeypatch.setattr(config, "ADMIN_TOKEN", "admin-secret")
    monkeypatch.setattr(config, "DEFAULT_RUN_ALLOWANCE", 2)
    # Every auth route now writes an audit line, and LOG_DIR is fixed at
    # import: without this, these tests append to the real logs/logplane/.
    monkeypatch.setattr(logplane, "LOG_DIR", tmp_path / "logplane")
    monkeypatch.setattr(config, "CV_UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path / "runs")


def test_request_lifecycle_and_token_issue():
    req = store.create_request("alice", "need access")
    assert req["status"] == "pending" and req["token_id"] is None

    token = store.approve_request(req["id"])
    assert token["runs_remaining"] == 2
    assert token["role"] == "user"
    assert len(token["token"]) > 20

    # list_requests must return resolved ones too: the admin UI splits on status
    # itself and renders a resolved table.
    listed = store.list_requests()
    assert len(listed) == 1
    assert listed[0]["status"] == "approved"
    assert listed[0]["token_id"] == token["id"]


def test_double_approve_raises_and_mints_only_one_token():
    req = store.create_request("bob")
    store.approve_request(req["id"])
    with pytest.raises(store.AuthError):
        store.approve_request(req["id"])
    from backend.jsonstore import read_json
    assert len(read_json(config.KB_AUTH_DIR / "tokens.json")) == 1


def test_reject_then_no_token():
    req = store.create_request("carol")
    store.reject_request(req["id"])
    assert store.list_requests()[0]["status"] == "rejected"
    assert store.resolve_token("anything") is None


@pytest.mark.parametrize("bad", ["", "   ", "x" * 65])
def test_request_input_floor(bad):
    with pytest.raises(store.AuthError):
        store.create_request(bad)


def test_duplicate_pending_request_refused():
    store.create_request("dave")
    with pytest.raises(store.AuthError):
        store.create_request("DAVE")  # case-insensitive


def test_admin_token_resolves_without_file_write():
    ident = store.resolve_token("admin-secret")
    assert ident["role"] == "admin"
    assert ident["runs_remaining"] is None  # frontend hides the pill on exactly this
    assert not (config.KB_AUTH_DIR / "tokens.json").exists()


def test_empty_admin_token_never_matches(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "")
    assert store.resolve_token("") is None
    assert store.resolve_token(None) is None


def test_consume_run_decrements_then_refuses():
    req = store.create_request("erin")
    token = store.approve_request(req["id"])
    assert store.consume_run(token["id"]) is True
    assert store.consume_run(token["id"]) is True
    assert store.consume_run(token["id"]) is False  # allowance spent

    assert store.resolve_token(token["token"])["runs_remaining"] == 0


def test_admin_run_never_decrements():
    for _ in range(5):
        assert store.consume_run(store.ADMIN_TOKEN_ID) is True


def test_refund_restores_one_run():
    req = store.create_request("frank")
    token = store.approve_request(req["id"])
    store.consume_run(token["id"])
    store.refund_run(token["id"])
    assert store.resolve_token(token["token"])["runs_remaining"] == 2


# =============================================================================
# backend/auth/store.py - record shapes, the state machine, leakage, races,
# crash safety, and the two layers that consume it (deps, routes/auth)
# =============================================================================
def _tokens() -> list[dict]:
    return read_json(config.KB_AUTH_DIR / "tokens.json")


def _requests() -> list[dict]:
    return read_json(config.KB_AUTH_DIR / "requests.json")


def _user(name: str = "user", note: str = "") -> dict:
    """Request + approve: the token record, raw token included."""
    return store.approve_request(store.create_request(name, note)["id"])


def _status(call) -> int:
    with pytest.raises(HTTPException) as exc:
        call()
    return exc.value.status_code


def _crash(src, dst):
    raise OSError("disk died")


def _all_at_once(target, args_list, timeout=10):
    """Start one daemon thread per args tuple behind a barrier, so they really overlap."""
    barrier = threading.Barrier(len(args_list), timeout=timeout)

    def run(*args):
        barrier.wait()
        target(*args)

    threads = [threading.Thread(target=run, args=args, daemon=True) for args in args_list]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout)
    assert not any(t.is_alive() for t in threads), "a store call never returned (lock held?)"


# --- access requests ---------------------------------------------------------
def test_a_request_record_has_the_full_shape():
    req = store.create_request("  alice  ", "  needs a CV  ")
    assert set(req) == {"id", "kind", "identifier", "note", "status", "created", "resolved", "token_id"}
    assert (req["kind"], req["identifier"], req["note"], req["status"]) == ("signup", "alice", "needs a CV", "pending")
    assert re.fullmatch(r"[0-9a-f]{8}", req["id"])
    assert req["resolved"] is None and req["token_id"] is None
    assert datetime.fromisoformat(req["created"]).tzinfo is not None        # UTC-aware, sortable
    assert _requests() == [req]                                             # what is returned is what is stored


@pytest.mark.parametrize("identifier, note, ok", [
    ("x" * store.MAX_IDENTIFIER, "", True),
    ("x" * (store.MAX_IDENTIFIER + 1), "", False),
    ("   " + "x" * store.MAX_IDENTIFIER + "   ", "", True),                  # measured after the strip
    ("bob", "n" * store.MAX_NOTE, True),
    ("bob", "n" * (store.MAX_NOTE + 1), False),
    ("bob", None, True),                                                    # a missing note is ""
    (None, "", False),
])
def test_the_input_floor_boundaries(identifier, note, ok):
    if ok:
        assert store.create_request(identifier, note)["note"] == (note or "")
        assert len(_requests()) == 1
    else:
        with pytest.raises(store.AuthError):
            store.create_request(identifier, note)
        assert _requests() == []                                            # a refused request writes nothing


def test_the_duplicate_rule_covers_only_pending_requests():
    first = store.create_request("gina")
    store.reject_request(first["id"])
    second = store.create_request("GINA")                                   # a rejected name may ask again
    assert second["id"] != first["id"]
    with pytest.raises(store.AuthError, match="already awaiting"):
        store.create_request(" gina ")                                      # ... once at a time: stripped, any case
    assert [r["status"] for r in _requests()] == ["rejected", "pending"]


def test_the_pending_cap_counts_only_pending_requests(monkeypatch):
    monkeypatch.setattr(store, "MAX_PENDING", 3)
    ids = [store.create_request(f"u{i}")["id"] for i in range(3)]
    with pytest.raises(store.AuthError, match="Too many"):
        store.create_request("overflow")
    store.reject_request(ids[0])
    store.create_request("now-fits")                                        # a resolved request frees a slot
    assert len(_requests()) == 4


def test_list_requests_is_newest_first(monkeypatch):
    stamps = iter(f"2026-10-10T00:00:{i:02d}+00:00" for i in range(20))
    monkeypatch.setattr(store, "_now", lambda: next(stamps))
    a, b, c = (store.create_request(n) for n in ("a", "b", "c"))
    store.approve_request(b["id"])                                          # resolving never reorders
    assert [r["identifier"] for r in store.list_requests()] == ["c", "b", "a"]


# --- approve / reject: the state machine -------------------------------------
def test_an_approved_token_has_the_full_shape_and_links_both_ways(monkeypatch):
    monkeypatch.setattr(config, "DEFAULT_RUN_ALLOWANCE", 5)                 # read at approval, not at import
    req = store.create_request("hana")
    tok = store.approve_request(req["id"])
    assert set(tok) == {"id", "token", "identifier", "profile_id", "role", "runs_remaining", "created", "request_id"}
    assert re.fullmatch(r"t-[0-9a-f]{8}", tok["id"]) and re.fullmatch(r"p-[0-9a-f]{8}", tok["profile_id"])
    assert profiles.profile_for("hana") == tok["profile_id"]                # the account was created with it
    assert re.fullmatch(r"[A-Za-z0-9_-]{43,}", tok["token"])                # token_urlsafe(32): 256 bits
    assert (tok["identifier"], tok["role"], tok["runs_remaining"], tok["request_id"]) == ("hana", "user", 5, req["id"])
    (stored,) = _requests()
    assert (stored["status"], stored["token_id"]) == ("approved", tok["id"])
    datetime.fromisoformat(stored["resolved"])
    assert _tokens() == [tok]


def test_tokens_and_ids_are_unique_and_never_the_admin_sentinel():
    toks = [_user(f"u{i}") for i in range(20)]
    assert len({t["token"] for t in toks}) == 20 and len({t["id"] for t in toks}) == 20
    assert store.ADMIN_TOKEN_ID not in {t["id"] for t in toks}
    for t in toks:
        assert store.resolve_token(t["token"])["id"] == t["id"]             # each token opens only its own record


@pytest.mark.parametrize("first, second", [
    ("approve", "approve"), ("approve", "reject"), ("reject", "approve"), ("reject", "reject"),
])
def test_a_resolved_request_is_final(first, second):
    req = store.create_request("ivan")
    getattr(store, f"{first}_request")(req["id"])
    before = (_tokens(), _requests())
    with pytest.raises(store.AuthError, match="already"):
        getattr(store, f"{second}_request")(req["id"])
    assert (_tokens(), _requests()) == before                               # a refused flip writes nothing


@pytest.mark.parametrize("action", ["approve_request", "reject_request"])
def test_an_unknown_request_id_is_refused_and_writes_nothing(action):
    store.create_request("jo")
    with pytest.raises(store.AuthError, match="No such request"):
        getattr(store, action)("deadbeef")
    assert not (config.KB_AUTH_DIR / "tokens.json").exists()
    assert _requests()[0]["status"] == "pending"


def test_a_rejected_request_mints_nothing():
    rec = store.reject_request(store.create_request("kai")["id"])
    assert (rec["status"], rec["token_id"]) == ("rejected", None) and rec["resolved"]
    assert not (config.KB_AUTH_DIR / "tokens.json").exists()


# --- resolve_token / identity_of: who a credential is, and what leaks --------
def test_resolve_token_matches_whole_tokens_only():
    tok = _user("lee")
    raw = tok["token"]
    assert store.resolve_token(raw)["id"] == tok["id"]
    wrong = [raw[:-1], raw + "x", raw.swapcase(), " " + raw, raw + "\n", tok["id"], tok["identifier"],
             "admin-secret ", "ADMIN-SECRET"]
    for w in wrong:
        if w != raw:
            assert store.resolve_token(w) is None, w


def test_a_blank_token_on_disk_is_never_matched(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "")
    write_json(config.KB_AUTH_DIR / "tokens.json",
               [{"id": "t-blank", "identifier": "x", "role": "admin"},
                {"id": "t-empty", "token": "", "identifier": "y", "role": "admin"}])
    for raw in ("", None):
        assert store.resolve_token(raw) is None


def test_the_admin_still_gets_in_when_tokens_json_is_corrupt():
    path = config.KB_AUTH_DIR / "tokens.json"
    path.parent.mkdir(parents=True)
    path.write_text("{oops", encoding="utf-8")
    assert store.resolve_token("admin-secret")["role"] == "admin"           # checked first: the file is not read
    with pytest.raises(json.JSONDecodeError):
        store.resolve_token("a-user-token")                                 # fails closed, never "no tokens, no check"


def test_identity_never_carries_the_raw_token():
    tok = _user("mo")
    for record in (tok, store.resolve_token(tok["token"]), store.resolve_token("admin-secret")):
        ident = store.identity_of(record)
        assert set(ident) == {"identifier", "role", "runs_remaining", "token_id", "profile_id"}
        assert tok["token"] not in json.dumps(ident) and "admin-secret" not in json.dumps(ident)
    assert store.identity_of(store.resolve_token("admin-secret")) == {
        "identifier": "admin", "role": "admin", "runs_remaining": None, "token_id": store.ADMIN_TOKEN_ID,
        "profile_id": store.ADMIN_PROFILE_ID}


def test_the_raw_token_lives_only_in_tokens_json():
    tok = _user("nia")
    tokens_text = (config.KB_AUTH_DIR / "tokens.json").read_text(encoding="utf-8")
    requests_text = (config.KB_AUTH_DIR / "requests.json").read_text(encoding="utf-8")
    assert tok["token"] in tokens_text                                      # plaintext by design (module docstring)
    assert tok["token"] not in requests_text
    assert tok["token"] not in json.dumps(store.list_requests())            # the admin list never re-shows it
    profiles_text = (config.KB_AUTH_DIR / "profiles.json").read_text(encoding="utf-8")
    assert tok["token"] not in profiles_text
    assert "admin-secret" not in tokens_text + requests_text + profiles_text   # the admin token is never persisted
    assert sorted(p.name for p in config.KB_AUTH_DIR.iterdir()) == ["profiles.json", "requests.json", "tokens.json"]


# --- consume_run / refund_run: the allowance ----------------------------------
@pytest.mark.parametrize("remaining", [0, -1, None])
def test_consume_refuses_an_empty_allowance_without_writing(monkeypatch, remaining):
    tok = _user("oz")
    tokens = _tokens()
    tokens[0]["runs_remaining"] = remaining
    write_json(config.KB_AUTH_DIR / "tokens.json", tokens)
    writes = []
    monkeypatch.setattr(store, "write_json", lambda *a: writes.append(a))
    assert store.consume_run(tok["id"]) is False
    assert writes == []


def test_unknown_and_admin_ids_never_touch_the_file(monkeypatch):
    _user("pat")
    writes = []
    monkeypatch.setattr(store, "write_json", lambda *a: writes.append(a))
    assert store.consume_run("t-00000000") is False
    store.refund_run("t-00000000")                                          # silently nothing, never an error
    assert store.consume_run(store.ADMIN_TOKEN_ID) is True
    store.refund_run(store.ADMIN_TOKEN_ID)
    assert writes == []


def test_consume_and_refund_touch_only_their_own_token():
    a, b = _user("qa"), _user("qb")
    store.consume_run(a["id"])
    after = {t["id"]: t for t in _tokens()}
    assert (after[a["id"]]["runs_remaining"], after[b["id"]]) == (1, b)     # b untouched, field for field
    assert {k: v for k, v in after[a["id"]].items() if k != "runs_remaining"} == \
           {k: v for k, v in a.items() if k != "runs_remaining"}            # only the counter moved
    store.refund_run(a["id"])
    assert {t["id"]: t["runs_remaining"] for t in _tokens()} == {a["id"]: 2, b["id"]: 2}


# --- races and crashes --------------------------------------------------------
def test_concurrent_starts_never_spend_more_than_the_allowance():
    tok = _user("race")                                                     # allowance 2
    results = []
    _all_at_once(lambda: results.append(store.consume_run(tok["id"])), [()] * 25)
    assert len(results) == 25 and results.count(True) == 2
    assert _tokens()[0]["runs_remaining"] == 0


def test_a_double_clicked_approve_mints_exactly_one_token_under_load():
    req = store.create_request("dbl")
    minted = []

    def approve():
        try:
            minted.append(store.approve_request(req["id"])["id"])
        except store.AuthError:
            minted.append(None)

    _all_at_once(approve, [()] * 10)
    winners = [m for m in minted if m]
    assert len(minted) == 10 and len(winners) == 1
    assert [t["id"] for t in _tokens()] == winners
    assert _requests()[0]["token_id"] == winners[0]


def test_concurrent_requests_keep_every_name_and_one_of_each_duplicate():
    names = [f"user{i}" for i in range(20)] + ["same"] * 10
    refused = []

    def ask(name):
        try:
            store.create_request(name)
        except store.AuthError:
            refused.append(name)

    _all_at_once(ask, [(n,) for n in names])
    assert sorted(r["identifier"] for r in _requests()) == sorted([f"user{i}" for i in range(20)] + ["same"])
    assert refused == ["same"] * 9


def test_a_crash_mid_write_keeps_the_queue_and_frees_the_lock(monkeypatch):
    store.create_request("kept")
    with monkeypatch.context() as m:
        m.setattr(jsonstore.os, "replace", _crash)
        with pytest.raises(OSError):
            store.create_request("lost")
    assert [r["identifier"] for r in _requests()] == ["kept"]
    _all_at_once(store.create_request, [("after",)])                        # another thread is not locked out
    assert [r["identifier"] for r in _requests()] == ["kept", "after"]


def test_the_store_follows_kb_auth_dir_at_call_time(tmp_path, monkeypatch):
    tok = _user("first-home")
    monkeypatch.setattr(config, "KB_AUTH_DIR", tmp_path / "elsewhere")
    assert store.resolve_token(tok["token"]) is None and store.list_requests() == []
    assert store.consume_run(tok["id"]) is False


@pytest.mark.xfail(strict=True, reason="bugs_audit_fixed.md #63: approval writes the profile and token before "
                                       "resolving the request")
def test_an_interrupted_approval_leaves_no_live_token_on_a_pending_request(monkeypatch):
    req = store.create_request("half")
    real_write = store.write_json

    def requests_write_dies(path, data):
        if path.name == "requests.json":
            raise OSError("disk died")
        real_write(path, data)

    with monkeypatch.context() as m:
        m.setattr(store, "write_json", requests_write_dies)
        with pytest.raises(OSError):
            store.approve_request(req["id"])
    # Either nothing was issued (rolled back), or the request reads approved.
    # Today: a live token and a profile beside a request still "pending", and
    # a retried Approve is refused because the profile now exists (409).
    rolled_back = _tokens() == [] and profiles.profile_for("half") is None
    assert rolled_back or _requests()[0]["status"] == "approved"


@pytest.mark.parametrize("raw", ["pässwörd", "token-✓"])   # #63 item 1, fixed 2026-10-24
def test_a_non_ascii_token_is_simply_unknown(raw):
    _user("uma")
    assert store.resolve_token(raw) is None


# --- the consumers: deps.py (401 vs 403) and routes/auth.py (AuthError -> status)
@pytest.mark.parametrize("header", [
    None, "", "Bearer", "Bearer   ", "Basic admin-secret", "admin-secret", "Token admin-secret", "Bearer wrong",
    "Bearer\tadmin-secret",                                                 # RFC 7235: the separator is a space
    "Bearer admin-secret extra",                                            # a second word is part of the credential
])
def test_require_auth_401s_every_bad_header(header):
    assert _status(lambda: deps.require_auth(header)) == 401


def test_require_auth_strips_and_accepts_any_bearer_case():
    tok = _user("val")
    assert deps.require_auth(f"bearer   {tok['token']}  ") == store.identity_of(tok)


def test_a_valid_non_admin_gets_403_never_401():
    ident = deps.require_auth(f"Bearer {_user('wes')['token']}")
    assert _status(lambda: deps.require_admin(ident)) == 403                # a 401 would sign them out of the app
    assert deps.require_admin(deps.require_auth("Bearer admin-secret"))["role"] == "admin"


def test_the_query_token_door_matches_the_header_door():
    tok = _user("xi")
    assert deps.identity_from_query_token(tok["token"]) == deps.require_auth(f"Bearer {tok['token']}")
    for raw in (None, "", "nope"):
        assert _status(lambda: deps.identity_from_query_token(raw)) == 401


def test_auth_routes_turn_every_store_refusal_into_a_4xx():
    admin = deps.require_auth("Bearer admin-secret")
    ask = lambda name: auth_routes.request_access(auth_routes.AccessRequest(identifier=name))   # noqa: E731
    assert _status(lambda: ask("   ")) == 400
    req = ask("yan")
    assert _status(lambda: ask("YAN")) == 400
    tok = auth_routes.approve(req["id"], admin)
    assert tok["token"] and tok["runs_remaining"] == 2                     # the one time the raw token is returned
    assert _status(lambda: auth_routes.approve(req["id"], admin)) == 409
    assert _status(lambda: auth_routes.reject(req["id"], admin)) == 409
    assert _status(lambda: auth_routes.approve("missing", admin)) == 409
    assert _status(lambda: auth_routes.login(auth_routes.LoginRequest(token="nope"))) == 401
    assert auth_routes.login(auth_routes.LoginRequest(token=tok["token"])) == store.identity_of(tok)
    assert auth_routes.list_requests(admin) == {"requests": store.list_requests()}


@pytest.mark.parametrize("door", ["login", "header", "query"])   # #63 item 1, fixed 2026-10-24
def test_a_non_ascii_credential_is_a_401_at_every_door(door):
    call = {
        "login": lambda: auth_routes.login(auth_routes.LoginRequest(token="é")),
        "header": lambda: deps.require_auth("Bearer é"),                    # Starlette decodes headers as latin-1
        "query": lambda: deps.identity_from_query_token("é"),
    }[door]
    assert _status(call) == 401


def test_the_admin_sentinel_is_one_value_across_layers():
    admin = deps.require_auth("Bearer admin-secret")
    assert admin["token_id"] == store.ADMIN_TOKEN_ID == registry.ADMIN_TOKEN_ID
    assert registry.owns({"owner": "t-someone"}, admin)                    # admin sees every run
    assert store.consume_run(admin["token_id"]) is True
    assert not (config.KB_AUTH_DIR / "tokens.json").exists()               # and is never written down


def test_every_real_owner_id_names_its_own_export_folder():
    # The run owner (the account's profile_id since 2026-10-10, "cli" for the
    # CLI) becomes the export folder through export._slug. For ids the system
    # mints the slug must be the identity map, or two owners share a folder.
    owners = [_user(f"o{i}")["profile_id"] for i in range(10)] + [store.ADMIN_PROFILE_ID, "cli"]
    assert [export._slug(o, "unknown") for o in owners] == owners


# =============================================================================
# backend/jsonstore.py - atomic writes, read defaults, the per-path lock
# =============================================================================
def test_read_json_defaults_and_never_shares_the_default(tmp_path):
    missing = tmp_path / "nope.json"
    first = read_json(missing)
    assert first == []
    first.append("leak")
    assert read_json(missing) == []                       # a NEW list per call
    assert read_json(missing, default={}) == {}
    blank = tmp_path / "blank.json"
    blank.write_text("  \n", encoding="utf-8")
    assert read_json(blank) == []                         # whitespace-only counts as empty


def test_read_json_surfaces_a_corrupt_file(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        read_json(bad)                                    # never silently treated as empty


def test_write_json_round_trips_unicode_and_creates_folders(tmp_path):
    path = tmp_path / "a" / "b" / "data.json"
    data = {"name": "José – data engineer", "skills": ["Python", "SQL"], "n": 3}
    write_json(path, data)
    assert read_json(path) == data
    assert "José" in path.read_text(encoding="utf-8")     # ensure_ascii=False: readable on disk
    assert not path.with_suffix(".json.tmp").exists()      # the temp file is gone


def test_a_failed_serialisation_leaves_the_old_file_intact(tmp_path):
    path = tmp_path / "data.json"
    write_json(path, {"v": 1})
    with pytest.raises(TypeError):
        write_json(path, {"v": object()})
    assert read_json(path) == {"v": 1}


def test_a_crash_before_the_rename_leaves_the_old_file_intact(tmp_path, monkeypatch):
    path = tmp_path / "data.json"
    write_json(path, {"v": 1})

    def crash(src, dst):
        raise OSError("disk died")

    monkeypatch.setattr(jsonstore.os, "replace", crash)
    with pytest.raises(OSError):
        write_json(path, {"v": 2})
    assert read_json(path) == {"v": 1}                    # readers never see a half-written file


def test_update_json_returns_the_result_and_can_skip_the_write(tmp_path):
    path = tmp_path / "data.json"
    assert update_json(path, lambda d: (None, "nothing")) == "nothing"
    assert not path.exists()                              # data None: no write at all
    assert update_json(path, lambda d: (d + ["a"], len(d) + 1)) == 1
    assert update_json(path, lambda d: (d + ["b"], len(d) + 1)) == 2
    assert read_json(path) == ["a", "b"]
    assert update_json(tmp_path / "obj.json", lambda d: ({**d, "k": 1}, d), default={}) == {}


def test_a_failing_update_writes_nothing_and_frees_the_lock(tmp_path):
    path = tmp_path / "data.json"
    write_json(path, ["a"])

    def boom(d):
        raise RuntimeError("bad edit")

    with pytest.raises(RuntimeError):
        update_json(path, boom)
    assert read_json(path) == ["a"]
    done = threading.Event()
    t = threading.Thread(target=lambda: (update_json(path, lambda d: (d + ["b"], None)), done.set()), daemon=True)
    t.start()
    assert done.wait(5), "the lock was never released"
    assert read_json(path) == ["a", "b"]


def test_two_spellings_of_one_file_share_one_lock(tmp_path):
    (tmp_path / "sub").mkdir()
    direct = tmp_path / "data.json"
    roundabout = tmp_path / "sub" / ".." / "data.json"
    assert jsonstore._lock_for(direct) is jsonstore._lock_for(roundabout)
    assert jsonstore._lock_for(direct) is not jsonstore._lock_for(tmp_path / "other.json")


def test_the_lock_is_reentrant_for_nested_updates(tmp_path):
    path = tmp_path / "data.json"
    result = {}

    def outer():
        result["v"] = update_json(path, lambda d: (d + ["outer"], update_json(path, lambda e: (None, "inner"))))

    t = threading.Thread(target=outer, daemon=True)
    t.start()
    t.join(5)
    assert not t.is_alive(), "nested update_json on one path deadlocked"
    assert result["v"] == "inner"


def test_concurrent_updates_never_lose_a_write(tmp_path):
    path = tmp_path / "data.json"
    n = 40

    def add(i):
        update_json(path, lambda d: (d + [i], None))

    threads = [threading.Thread(target=add, args=(i,), daemon=True) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert sorted(read_json(path)) == list(range(n))


def test_two_writers_never_share_a_temp_file(tmp_path, monkeypatch):
    # Outside update_json (registry logs, profile_store), two write_json calls on
    # one path both write <file>.tmp: one can rename the other's half-written
    # file, or find it already gone.
    temps = []
    real_replace = jsonstore.os.replace
    monkeypatch.setattr(jsonstore.os, "replace", lambda src, dst: (temps.append(str(src)), real_replace(src, dst)))
    path = tmp_path / "data.json"
    write_json(path, {"v": 1})
    write_json(path, {"v": 2})
    assert temps[0] != temps[1]


# =============================================================================
# learning/profile_store.py - gap answers: one JSON file + the profile index
# =============================================================================
class FakeVectorStore:
    def __init__(self, fail=False):
        self.adds = []
        self.fail = fail

    def add(self, collection, ids, texts, metas):
        if self.fail:
            raise RuntimeError("index unavailable")
        self.adds.append((collection, ids, texts, metas))


@pytest.fixture
def manual(tmp_path, monkeypatch):
    path = tmp_path / "profile" / "manual_entries.json"
    monkeypatch.setattr(profile_store, "MANUAL_ENTRIES", path)
    return path


def _answer(requirement="SQL", content="Queried 40M-row tables.", **extra):
    return {"requirement": requirement, "question": f"{requirement}?", "raw_answer": "typed by the human",
            "content": content, "category": "gap_answer", "skills": ["SQL", "Postgres"], **extra}


def test_nothing_usable_writes_nothing_and_indexes_nothing(manual):
    vs = FakeVectorStore()
    assert profile_store.save_gap_answers([_answer(content=""), _answer(content="   "),
                                           {"requirement": "x"}], store=vs) == []
    assert not manual.exists() and vs.adds == []


def test_a_saved_answer_has_the_full_record_shape(manual):
    vs = FakeVectorStore()
    (rec,) = profile_store.save_gap_answers([_answer(), _answer(content="")], store=vs, run_id="r1")
    assert re.fullmatch(r"[0-9a-f]{8}", rec["id"])
    assert (rec["section"], rec["source"], rec["run_id"]) == ("gap_answers", "gap_interview", "r1")
    datetime.fromisoformat(rec["created"])                 # a real ISO timestamp
    assert rec["record"] == {
        "gap_answer_id": rec["id"], "requirement": "SQL", "question": "SQL?",
        "raw_answer": "typed by the human", "content": "Queried 40M-row tables.",
        "category": "gap_answer", "skills": ["SQL", "Postgres"],
    }
    assert read_json(manual) == [rec]


def test_missing_optional_fields_get_safe_defaults(manual):
    (rec,) = profile_store.save_gap_answers([{"content": "Ran Airflow DAGs."}], store=FakeVectorStore())
    assert rec["record"]["requirement"] == "" and rec["record"]["skills"] == [] and rec["run_id"] is None


def test_a_save_appends_and_keeps_every_other_entry(manual):
    other = {"id": "u1", "section": "skills", "record": {"name": "Rust"}}
    write_json(manual, [other])
    profile_store.save_gap_answers([_answer()], store=FakeVectorStore())
    profile_store.save_gap_answers([_answer("Spark", "Used Spark for ETL.")], store=FakeVectorStore())
    entries = read_json(manual)
    assert entries[0] == other
    assert [e["record"]["requirement"] for e in entries[1:]] == ["SQL", "Spark"]


def test_the_index_gets_scalar_metadata_under_the_type_quota(manual):
    vs = FakeVectorStore()
    (rec,) = profile_store.save_gap_answers([_answer()], store=vs)
    ((collection, ids, texts, metas),) = vs.adds
    assert collection == "profile"
    assert ids == [f"gap_answer:{rec['id']}"]
    assert texts == ["Queried 40M-row tables."]
    assert metas == [{"type": "gap_answer", "source_id": rec["id"], "requirement": "SQL",
                      "category": "gap_answer", "skills": "SQL, Postgres"}]
    assert all(isinstance(v, (str, int, float, bool)) for v in metas[0].values())   # Chroma: scalars only


def test_index_gap_answers_with_nothing_touches_no_store():
    assert profile_store.index_gap_answers([], store=None) == 0      # never builds a real VectorStore


def test_ids_stay_unique_across_many_saves(manual):
    vs = FakeVectorStore()
    for i in range(50):
        profile_store.save_gap_answers([_answer(content=f"answer {i}")], store=vs)
    ids = [e["id"] for e in read_json(manual)]
    assert len(set(ids)) == 50


def _second_writer_during_first_write(monkeypatch, other):
    """Start `other` (a second writer, on its own thread) while the first write
    is between its read and its write. A writer holding the file's lock makes it
    wait; an unlocked one lets it land, then overwrites it. The 0.2 s is only the
    window in which an unlocked second writer would finish; the assertion is on data."""
    real_write = jsonstore.write_json
    second = threading.Thread(target=other, daemon=True)

    def write(path, data):
        if second.ident is None:                       # the first write only
            second.start()
            second.join(0.2)
        real_write(path, data)

    monkeypatch.setattr(jsonstore, "write_json", write)
    return second


def test_a_concurrent_profile_edit_is_not_lost(manual, monkeypatch):
    """Catches save_gap_answers writing manual_entries.json outside update_json's lock (#35)."""
    write_json(manual, [])
    route = _second_writer_during_first_write(
        monkeypatch, lambda: update_json(manual, lambda entries: (entries + [{"id": "ui1", "section": "skills"}], None)))
    profile_store.save_gap_answers([_answer()], store=FakeVectorStore())
    route.join(5)
    entries = read_json(manual)
    assert "ui1" in [e["id"] for e in entries] and len(entries) == 2


@pytest.mark.xfail(strict=True, reason="bugs_audit_fixed.md #62: a failed index leaves the answer half-saved")
def test_a_failed_index_does_not_leave_a_half_saved_answer(manual):
    with pytest.raises(RuntimeError):
        profile_store.save_gap_answers([_answer()], store=FakeVectorStore(fail=True))
    # Saved to JSON but missing from the index: never retrieved, and a retry duplicates it.
    assert read_json(manual) == []


# =============================================================================
# learning/store.py + learning/context_builder.py - per-agent learning records
# =============================================================================
@pytest.fixture
def learning_dir(tmp_path, monkeypatch):
    path = tmp_path / "learning"
    monkeypatch.setattr(config, "KB_LEARNING_DIR", path)
    return path


def test_an_agent_with_no_history_loads_empty(learning_dir):
    assert learning_store.load_learning("critic") == {"exemplars": [], "corrections": [], "feedback": []}


def test_exemplars_corrections_and_feedback_round_trip(learning_dir):
    ex = learning_store.save_exemplar("document", {"jd": "DE"}, "a CV", feedback="good")
    co = learning_store.save_correction("document", "old line", "new line", "too vague",
                                        extra={"run_id": "r1", "gate": "gate4_document"})
    fb = learning_store.append_feedback("document", {"score": 4, "note": "ok"})
    loaded = learning_store.load_learning("document")
    assert loaded == {"exemplars": [ex], "corrections": [co], "feedback": [fb]}
    assert (ex["input_context"], ex["generated_output"], ex["feedback"]) == ({"jd": "DE"}, "a CV", "good")
    assert (co["before"], co["after"], co["reason"], co["run_id"]) == ("old line", "new line", "too vague", "r1")
    for rec in (ex, co, fb):
        assert rec["agent_name"] == "document"
        datetime.fromisoformat(rec["timestamp"])
    assert learning_store.save_exemplar("critic", "i", "o")["feedback"] == ""      # None -> ""


def test_each_agent_keeps_its_own_history(learning_dir):
    learning_store.save_exemplar("critic", "i", "o")
    learning_store.save_correction("document", "a", "b", "r")
    assert learning_store.load_learning("critic")["corrections"] == []
    assert learning_store.load_learning("document")["exemplars"] == []
    assert (learning_dir / "critic" / "exemplars.json").is_file()


def test_records_append_in_order_and_survive_a_crash_before_the_rename(learning_dir, monkeypatch):
    for i in range(3):
        learning_store.save_exemplar("critic", f"in {i}", f"out {i}")
    with monkeypatch.context() as m:            # scoped: undo() would also drop the learning_dir patch
        m.setattr("os.replace", lambda src, dst: (_ for _ in ()).throw(OSError("disk died")))
        with pytest.raises(OSError):
            learning_store.save_exemplar("critic", "in 3", "out 3")
    assert [e["input_context"] for e in learning_store.load_learning("critic")["exemplars"]] == ["in 0", "in 1", "in 2"]


def test_a_single_object_file_and_blank_jsonl_lines_are_tolerated(learning_dir):
    d = learning_dir / "critic"
    d.mkdir(parents=True)
    (d / "exemplars.json").write_text('{"generated_output": "one"}', encoding="utf-8")
    (d / "corrections.json").write_text("", encoding="utf-8")
    (d / "feedback.jsonl").write_text('{"a": 1}\n\n   \n{"a": 2}\n', encoding="utf-8")
    loaded = learning_store.load_learning("critic")
    assert loaded["exemplars"] == [{"generated_output": "one"}]
    assert loaded["corrections"] == []
    assert loaded["feedback"] == [{"a": 1}, {"a": 2}]


def test_concurrent_feedback_appends_keep_every_line(learning_dir):
    n = 30
    threads = [threading.Thread(target=learning_store.append_feedback, args=("critic", {"i": i}), daemon=True)
               for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert sorted(r["i"] for r in learning_store.load_learning("critic")["feedback"]) == list(range(n))


def test_a_whitespace_only_learning_file_reads_as_empty(learning_dir):
    d = learning_dir / "critic"
    d.mkdir(parents=True)
    (d / "corrections.json").write_text("\n", encoding="utf-8")
    assert learning_store.load_learning("critic")["corrections"] == []


def test_a_concurrent_exemplar_is_not_lost(learning_dir, monkeypatch):
    """Catches _append_json_list's read-modify-write running without the file's lock (audit #12)."""
    path = learning_dir / "critic" / "exemplars.json"
    other = _second_writer_during_first_write(
        monkeypatch, lambda: learning_store._append_json_list(path, {"generated_output": "other run"}))
    learning_store.save_exemplar("critic", "mine", "mine")
    other.join(5)
    outputs = [e["generated_output"] for e in learning_store._read_json_list(path)]
    assert sorted(outputs) == ["mine", "other run"]


@pytest.mark.parametrize("save", ["correction", "feedback"])
def test_caller_fields_never_overwrite_the_core_keys(learning_dir, save):
    if save == "correction":
        rec = learning_store.save_correction("document", "old", "new", "why",
                                             extra={"after": "forged", "agent_name": "critic"})
        assert (rec["after"], rec["agent_name"]) == ("new", "document")
    else:
        rec = learning_store.append_feedback("document", {"agent_name": "critic", "timestamp": "1999"})
        assert rec["agent_name"] == "document" and rec["timestamp"] != "1999"


def test_the_run_log_store_appends_one_row_per_run(learning_dir):
    log = LearningStore()
    assert log.path == learning_dir / "records.jsonl"
    assert log.all_records() == []
    log.record({"run_id": "r1", "fit": 0.5, "note": "café"})
    log.record({"run_id": "r2"})
    assert [r["run_id"] for r in log.all_records()] == ["r1", "r2"]
    assert LearningStore(path=learning_dir / "other.jsonl").all_records() == []    # its own file


def test_context_builder_formatting_is_capped_and_empty_safe():
    assert context_builder._format([], []) == ""
    text = context_builder._format([{"generated_output": "x" * 500}],
                                   [{"before": "b" * 300, "after": "a" * 300, "reason": "r"}])
    lines = text.splitlines()
    assert lines[0] == "Relevant past examples:" and len(lines[1]) == len("  - ") + 200
    assert lines[2] == "Corrections to keep in mind:"
    assert lines[3] == "  - was: " + "b" * 120 and lines[4] == "    now: " + "a" * 120 + " (r)"
    assert context_builder.estimate_tokens("") == 1 and context_builder.estimate_tokens("x" * 400) == 100


@pytest.mark.xfail(strict=True, raises=NotImplementedError,
                   reason="learning/context_builder.build_context is not written yet (Instructions #20)")
def test_build_context_returns_a_small_relevant_slice_under_budget(learning_dir):
    for i in range(30):
        learning_store.save_exemplar("document", {"role": "data engineer"}, f"example {i} " * 20)
    full = context_builder._format(learning_store.load_learning("document")["exemplars"], [])
    out = context_builder.build_context("document", "data engineer", token_budget=200)
    assert out and context_builder.estimate_tokens(out) <= 200
    assert len(out) < len(full)                      # a subset, never the whole history



# =============================================================================
# utils/export.py - the approved CV on disk: naming, path safety, atomicity,
# the plain-text rendering; then its producer (final_review.close_run) and its
# reader (the GET /runs/{id}/document route), end to end under tmp_path
# =============================================================================
WHEN = datetime(2026, 10, 10, 23, 30, tzinfo=timezone.utc)


@pytest.fixture
def outputs(tmp_path, monkeypatch):
    path = tmp_path / "outputs"
    monkeypatch.setattr(config, "OUTPUTS_DIR", path)
    return path


def _doc(content: str = "# Ana Silva\n\n## Experience\n\n- Built **dbt** models\n", kind: str = "cv") -> Document:
    return Document(kind=kind, content=content)


def _export(doc=None, owner="t-ab12cd34", run_id="9f8e7d6c", role_title="Senior Data Engineer", when=WHEN):
    return export.export_document(doc or _doc(), owner=owner, run_id=run_id, role_title=role_title, when=when)


def _files(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


# --- naming and content ---------------------------------------------------------
def test_export_writes_the_md_as_delivered_and_a_plain_txt(outputs):
    doc = _doc()
    paths = _export(doc)
    assert set(paths) == {"md", "txt"}
    assert paths["md"] == outputs / "t-ab12cd34" / "2026-10-10_9f8e7d6c_senior-data-engineer.md"
    assert paths["txt"] == paths["md"].with_suffix(".txt")
    assert paths["md"].read_text(encoding="utf-8") == doc.content           # exactly what the run delivered
    assert paths["txt"].read_text(encoding="utf-8") == export.plain_text(doc.content)
    assert _files(outputs) == ["t-ab12cd34/2026-10-10_9f8e7d6c_senior-data-engineer.md",
                               "t-ab12cd34/2026-10-10_9f8e7d6c_senior-data-engineer.txt"]   # no .tmp left


def test_the_default_date_is_todays_utc_day(outputs):
    before = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    paths = _export(when=None)
    after = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert paths["md"].name.split("_")[0] in {before, after}                # a midnight tick can't flake it


def test_unicode_and_line_endings_survive_in_the_md(outputs):
    content = "# José Müller\r\n\r\n- Cut cost by 20 % — €40k\n"
    paths = _export(_doc(content))
    assert paths["md"].read_bytes() == content.encode("utf-8")              # the md is never reformatted
    txt = paths["txt"].read_text(encoding="utf-8")
    assert "\r" not in txt and "José Müller" in txt and "€40k" in txt


def test_missing_parts_fall_back_to_readable_names(outputs):
    assert _export(_doc(kind="cover_letter"), owner="", run_id="", role_title=None)["md"] == \
        outputs / "unknown" / "2026-10-10_run_cover_letter.md"
    assert _export(Document(kind="", content="x"), owner="cli", run_id="r1", role_title="   ")["md"].name == \
        "2026-10-10_r1_document.md"


@pytest.mark.parametrize("text, expected", [
    ("Senior Data Engineer", "senior-data-engineer"),
    ("ML/AI Engineer (m/f/d)", "ml-ai-engineer-m-f-d"),
    ("José Müller", "jos-m-ller"),
    ("C++ / C#", "c-c"),
    ("snake_case-ok", "snake_case-ok"),
    ("../../etc/passwd", "etc-passwd"),
    ("..", None),
    ("", None),
    (None, None),
    ("数据工程师", None),
])
def test_slug(text, expected):
    assert export._slug(text, "fallback") == (expected or "fallback")


def test_slug_is_capped_and_never_ends_on_a_dash():
    assert export._slug("a" * 100, "f") == "a" * 40
    assert export._slug("a" * 39 + " b", "f") == "a" * 39                   # the cut lands on the dash
    assert export._slug("x" * 10, "f", limit=4) == "xxxx"


# --- path safety and isolation -------------------------------------------------
@pytest.mark.parametrize("hostile", [
    "../../outside", "/etc/passwd", "..", "a/../../b", "~root", "C:\\Windows\\x", "\x00evil", ".hidden",
])
def test_no_caller_text_climbs_out_of_outputs(outputs, hostile):
    paths = _export(owner=hostile, run_id=hostile, role_title=hostile)
    root = outputs.resolve()
    for p in paths.values():
        assert p.resolve().parent.parent == root                            # exactly outputs/<owner>/<file>
        assert not p.parent.name.startswith(".")
    assert len(_files(outputs)) == 2
    assert all(f.startswith("outputs/") for f in _files(outputs.parent))    # nothing written beside outputs/


def test_two_owners_never_share_a_folder(outputs):
    a = _export(_doc("A's CV"), owner="t-aaaaaaaa")
    b = _export(_doc("B's CV"), owner="t-bbbbbbbb")                         # same run id, day and role
    assert a["md"].parent != b["md"].parent
    assert (a["md"].read_text(encoding="utf-8"), b["md"].read_text(encoding="utf-8")) == ("A's CV", "B's CV")


def test_re_exporting_a_run_replaces_its_pair_and_other_runs_stay(outputs):
    first = _export(_doc("v1"), run_id="r1")
    other = _export(_doc("other"), run_id="r2")
    again = _export(_doc("v2"), run_id="r1")
    assert first == again and again["md"].read_text(encoding="utf-8") == "v2"
    assert other["md"].read_text(encoding="utf-8") == "other"
    assert len(_files(outputs)) == 4


@pytest.mark.xfail(strict=True, reason="bugs_audit_fixed.md #63: the document.kind fallback is not slugged")
def test_the_kind_fallback_is_slugged_too(outputs):
    # The docstring promises every path part is slugged; with no role title the
    # file name falls back to Document.kind, used raw.
    paths = _export(_doc(kind="../../../escaped"), role_title=None)
    root = outputs.resolve()
    assert all(p.resolve().parent.parent == root for p in paths.values())


# --- crash safety ----------------------------------------------------------------
def test_a_crash_before_the_rename_keeps_the_previous_export(outputs, monkeypatch):
    first = _export(_doc("v1"))
    with monkeypatch.context() as m:
        m.setattr(export.os, "replace", _crash)
        with pytest.raises(OSError):
            _export(_doc("v2"))
    assert first["md"].read_text(encoding="utf-8") == "v1"
    assert first["txt"].read_text(encoding="utf-8") == export.plain_text("v1")


@pytest.mark.xfail(strict=True, reason="bugs_audit_fixed.md #63: a failed .txt write leaves an orphan .md")
def test_a_failed_export_leaves_no_half_pair(outputs, monkeypatch):
    real = export._atomic_write

    def txt_fails(path, text):
        if path.suffix == ".txt":
            raise OSError("disk full")
        real(path, text)

    monkeypatch.setattr(export, "_atomic_write", txt_fails)
    with pytest.raises(OSError):
        _export()
    assert not list(outputs.rglob("*.md"))                                  # no file a run event never points at


# --- plain_text ----------------------------------------------------------------
@pytest.mark.parametrize("md, txt", [
    ("# Ana Silva", "Ana Silva\n"),
    ("###### Deep", "Deep\n"),
    ("####### seven", "####### seven\n"),                                   # not a Markdown heading: kept
    ("#hashtag", "#hashtag\n"),                                             # no space: not a heading
    ("- Built **dbt** models", "• Built dbt models\n"),
    ("* star bullet", "• star bullet\n"),
    ("-5% churn", "-5% churn\n"),                                           # a minus sign, not a bullet
    ("a@b.c | github  ", "a@b.c | github\n"),                               # the Markdown line break goes
    ("- **Languages:** Python | SQL", "• Languages: Python | SQL\n"),
    ("\n\n# A\n\n\n", "A\n"),
    ("", "\n"),
])
def test_plain_text(md, txt):
    assert export.plain_text(md) == txt


def _cv_tree() -> CVTree:
    def n(node_id, kind, stype, depth, parent, text="", title="", attrs=None, children=None):
        return CVNode(node_id=node_id, kind=kind, section_type=stype, depth=depth, parent_id=parent,
                      title=title, text=text, raw_text=text, attrs=attrs or {}, children=children or [])

    S_, E_, B_, I_ = NodeKind.SECTION, NodeKind.ENTRY, NodeKind.BULLET, NodeKind.ITEM
    H, E, K = SectionType.HEADER, SectionType.EXPERIENCE, SectionType.SKILLS
    header = n("header", S_, H, 1, "cv", "Header", "Header", children=[
        n("header.i0", I_, H, 2, "header", "Ana Silva"),
        n("header.i1", I_, H, 2, "header", "ana@mail.com | github.com/ana"),
        n("header.i2", I_, H, 2, "header", "Berlin"),
    ])
    experience = n("experience", S_, E, 1, "cv", "Experience", "Experience", children=[
        n("experience.0", E_, E, 2, "experience", "Data Engineer | Acme | 2021 – 2024", "Data Engineer", children=[
            n("experience.0.b0", B_, E, 3, "experience.0", "Cut pipeline cost by 30% (€40k/yr)"),
            n("experience.0.b1", B_, E, 3, "experience.0", "Built dbt models for 12 teams"),
        ]),
        n("experience.i0", I_, E, 2, "experience", "Open to relocation"),
    ])
    skills = n("skills", S_, K, 1, "cv", "Technical Skills", "Technical Skills", children=[
        n("skills.0", E_, K, 2, "skills", "Languages: stale joined text", "Languages",
          attrs={"group": "Languages"}, children=[
              n("skills.0.i0", I_, K, 3, "skills.0", "Python"),
              n("skills.0.i1", I_, K, 3, "skills.0", "SQL"),
          ]),
    ])
    root = n("cv", NodeKind.CV, SectionType.OTHER, 0, None, title="cv.pdf", children=[header, experience, skills])
    return CVTree(source_file="cv.pdf", root=root)


def test_plain_text_strips_every_markup_render_markdown_emits():
    # Cross-layer: plain_text only knows the markup cv_edit.render_markdown
    # emits. If the renderer gains a new construct, this pins the drift.
    md = render_markdown(_cv_tree())
    assert export.plain_text(md) == (
        "Ana Silva\n"
        "\n"
        "ana@mail.com | github.com/ana\n"
        "Berlin\n"
        "\n"
        "Experience\n"
        "\n"
        "Data Engineer | Acme | 2021 – 2024\n"
        "• Cut pipeline cost by 30% (€40k/yr)\n"
        "• Built dbt models for 12 teams\n"
        "\n"
        "• Open to relocation\n"
        "\n"
        "Technical Skills\n"
        "\n"
        "• Languages: Python | SQL\n"
    )


def test_plain_text_is_idempotent_and_keeps_every_line():
    md = render_markdown(_cv_tree())
    once = export.plain_text(md)
    assert export.plain_text(once) == once
    assert len(once.splitlines()) == len(md.strip().splitlines())          # markup goes, lines never do


# --- the producer (final_review.close_run) and the reader (download route) -----
def _gate4(decision, revision=0, **kw) -> dict:
    return GateFeedback(gate="gate4_document", decision=decision, revision=revision, **kw).model_dump()


def _values(*answers, document="# Ana\n\n- Built **dbt** models\n", role="Data Engineer") -> dict:
    # Dicts, the way a checkpoint can hand them back: close_run must accept both.
    return {
        "gate_feedback": [GateFeedback(gate="gate1_requirements", decision="approve").model_dump(), *answers],
        "document": None if document is None else _doc(document).model_dump(),
        "requirements": {"role_title": role, "requirements": []},
    }


@pytest.fixture
def no_learning(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "KB_LEARNING_DIR", tmp_path / "learning")
    return tmp_path / "learning"


@pytest.mark.parametrize("answers, exported", [
    ([_gate4("approve")], True),
    ([_gate4("edit", edited_payload={"content": "x", "draft": "y"})], True),
    ([_gate4("reject", 0), _gate4("approve", 1)], True),                    # the latest answer decides
    ([_gate4("approve", 0), _gate4("reject", 1)], False),                   # a reject at the cap is not saved
    ([], False),                                                            # gate 4 never answered
])
def test_close_run_exports_only_an_approved_document(outputs, no_learning, answers, exported):
    final = final_review.close_run(_values(*answers), owner="t-owner001", run_id="r1", live=False)
    if not exported:
        assert final["export"] is None and not outputs.exists()
        return
    assert set(final["export"]) == {"md", "txt"}
    md, txt = (outputs / final["export"][k] for k in ("md", "txt"))
    assert re.fullmatch(r"t-owner001/\d{4}-\d{2}-\d{2}_r1_data-engineer\.md", final["export"]["md"])
    assert final["export"]["txt"] == final["export"]["md"][:-3] + ".txt"
    assert md.read_text(encoding="utf-8") == "# Ana\n\n- Built **dbt** models\n"
    assert txt.read_text(encoding="utf-8") == "Ana\n\n• Built dbt models\n"
    json.dumps(final)                                                       # rides on run_done: JSON-safe
    assert final["learning"].startswith("skipped") and not no_learning.exists()   # offline: no learning write


def test_close_run_with_no_document_or_no_role_still_behaves(outputs, no_learning):
    assert final_review.close_run(_values(_gate4("approve"), document=None),
                                  owner="o", run_id="r1", live=False)["export"] is None
    final = final_review.close_run(_values(_gate4("approve"), role=None), owner="o", run_id="r2", live=False)
    assert final["export"]["md"].endswith("_r2_cv.md")                      # falls back to the document kind


def _serve(monkeypatch, record):
    monkeypatch.setattr(runs_routes.registry, "get", lambda rid: record if rid == record["id"] else None)
    monkeypatch.setattr(runs_routes.registry, "load_log", lambda rid: None)


def test_the_download_route_serves_exactly_what_close_run_saved(outputs, no_learning, monkeypatch):
    owner = store.identity_of(_user("dl"))
    final = final_review.close_run(_values(_gate4("approve")), owner=owner["profile_id"], run_id="r1", live=False)
    _serve(monkeypatch, {"id": "r1", "owner": owner["profile_id"], "events": [{"type": "run_done", "final": final}]})
    for fmt, media in (("md", "text/markdown"), ("txt", "text/plain")):
        resp = runs_routes.download_document("r1", owner, fmt)
        assert Path(resp.path).resolve() == (outputs / final["export"][fmt]).resolve()
        assert resp.media_type.startswith(media)
    assert final["export"]["md"].startswith(owner["profile_id"] + "/")     # the owner's own folder
    stranger = store.identity_of(_user("stranger"))
    assert _status(lambda: runs_routes.download_document("r1", stranger, "md")) == 403
    runs_routes.download_document("r1", deps.require_auth("Bearer admin-secret"), "md")   # admin sees all


@pytest.mark.parametrize("events", [
    [],                                                                     # unfinished
    [{"type": "run_done", "final": None, "final_error": "OSError: disk full"}],
    [{"type": "run_done", "final": {"review": {"approved": False}, "export": None}}],
    [{"type": "run_done", "final": {"export": {"md": "../outside.md"}}}],   # forged: climbs out
    [{"type": "run_done", "final": {"export": {"md": "/etc/hosts"}}}],      # forged: absolute
    [{"type": "run_done", "final": {"export": {"md": "o/gone.md"}}}],       # recorded, then deleted
])
def test_the_download_route_404s_anything_not_saved_inside_outputs(outputs, monkeypatch, events):
    outputs.mkdir()
    (outputs.parent / "outside.md").write_text("not yours", encoding="utf-8")
    _serve(monkeypatch, {"id": "r1", "owner": "x", "events": events})
    admin = deps.require_auth("Bearer admin-secret")
    assert _status(lambda: runs_routes.download_document("r1", admin, "md")) == 404


# =============================================================================
# Backend storage, as of 2026-10-12: the account store (backend/auth/profiles.py),
# top-ups and the legacy-token backfill in backend/auth/store.py, the log plane
# (backend/logplane.py + routes/logs.py), CV storage (backend/cv_store.py), run
# logs (backend/runs/registry.py), Build-Profile entries (routes/profile.py),
# the shared vector store (backend/vectorstore.py) and path containment
# (backend/deps.py). Every path is redirected into tmp_path by isolated_store.
# =============================================================================
def _profiles() -> list[dict]:
    return read_json(config.KB_AUTH_DIR / "profiles.json")


def _audit() -> list[dict]:
    path = logplane.LOG_DIR / "audit.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def _scope(profile_id: str, role: str = "user") -> deps.Scope:
    return deps.Scope(profile_id=profile_id, role=role)


# --- backend/auth/profiles.py: one account per normalised name ---------------
@pytest.mark.parametrize("typed", ["Jane Doe", "jane  doe", "  JANE DOE ", "Ｊａｎｅ　Ｄｏｅ", "jane\tdoe"])
def test_every_spelling_of_a_name_normalises_to_one_key(typed):
    assert profiles.normalise_identifier(typed) == "jane doe"         # NFKC + casefold + collapsed whitespace


def test_casefold_not_lower_decides_sameness():
    assert profiles.normalise_identifier("Straße") == profiles.normalise_identifier("STRASSE")


@pytest.mark.parametrize("bad", ["", "   ", "x" * 65, "a:b", "admin", " ROOT ", "System", "ＡＤＭＩＮ"])
def test_unusable_or_reserved_names_are_refused(bad):
    with pytest.raises(profiles.ProfileError):
        profiles.normalise_identifier(bad)


def test_profile_for_finds_but_never_creates():
    assert profiles.profile_for("Jane Doe") is None
    assert not (config.KB_AUTH_DIR / "profiles.json").exists()
    pid = profiles.create_profile("Jane Doe")
    assert profiles.profile_for("JANE  doe") == pid


def test_a_profile_record_has_its_shape_and_a_minted_id():
    pid = profiles.create_profile("  Jane Doe  ")
    (rec,) = _profiles()
    assert set(rec) == {"profile_id", "identifier_norm", "display", "created"}
    assert re.fullmatch(r"p-[0-9a-f]{8}", pid) and rec["profile_id"] == pid
    assert (rec["identifier_norm"], rec["display"]) == ("jane doe", "Jane Doe")
    assert "jane" not in pid                                            # never derived from the typed name
    datetime.fromisoformat(rec["created"])


def test_create_refuses_any_spelling_of_an_existing_account():
    profiles.create_profile("Jane Doe")
    for other in ("jane doe", "JANE  DOE", "Ｊａｎｅ Ｄｏｅ"):
        with pytest.raises(profiles.ProfileError):
            profiles.create_profile(other)
    assert len(_profiles()) == 1


def test_get_or_create_is_idempotent_across_spellings():
    first = profiles.get_or_create_profile("Jane Doe")
    assert profiles.get_or_create_profile("jane   DOE") == first and len(_profiles()) == 1
    assert profiles.get_or_create_profile("Bob") != first


def test_concurrent_creates_of_one_name_make_one_account():
    created, refused = [], []

    def create():
        try:
            created.append(profiles.create_profile("Jane Doe"))
        except profiles.ProfileError:
            refused.append(1)

    _all_at_once(create, [()] * 12)
    assert len(created) == 1 and len(refused) == 11 and len(_profiles()) == 1
    got = []
    _all_at_once(lambda: got.append(profiles.get_or_create_profile("Bob")), [()] * 12)
    assert len(set(got)) == 1 and len(_profiles()) == 2


@pytest.mark.parametrize("name", ["admin", " ROOT ", "ＡＤＭＩＮ", "a:b", "ß" * 40],
                         ids=["admin", "root", "fullwidth-admin", "colon", "casefolds-past-64"])
def test_a_name_no_account_could_have_is_refused_at_request_time(name):
    with pytest.raises(store.AuthError):
        store.create_request(name)


def test_two_spellings_of_one_name_are_one_pending_request():
    store.create_request("Jane Doe")
    with pytest.raises(store.AuthError):
        store.create_request("jane  doe")


# --- backend/auth/store.py: signup -> profile, top-ups, the legacy backfill ---
def test_approving_a_second_spelling_of_an_account_is_refused_and_mints_nothing():
    _user("Jane Doe")
    req = store.create_request("JANE  DOE")                            # passes the queue's own .lower() check
    with pytest.raises(store.AuthError, match="already exists"):
        store.approve_request(req["id"])
    assert len(_tokens()) == 1 and len(_profiles()) == 1
    assert [r["status"] for r in _requests()] == ["approved", "pending"]   # the second is still the admin's to reject


def test_a_topup_request_has_its_shape_and_is_one_per_token():
    ident = store.identity_of(_user("tia"))
    req = store.create_topup_request(ident, "  need 3 more  ")
    assert (req["kind"], req["token_id"], req["identifier"], req["note"], req["status"]) == \
        ("topup", ident["token_id"], "tia", "need 3 more", "pending")
    with pytest.raises(store.AuthError, match="already awaiting"):
        store.create_topup_request(ident)
    with pytest.raises(store.AuthError):
        store.create_topup_request(store.identity_of(_user("tom")), "n" * (store.MAX_NOTE + 1))


def test_approving_a_topup_adds_to_the_same_token_and_mints_nothing(monkeypatch):
    tok = _user("uma2")
    store.consume_run(tok["id"])
    store.consume_run(tok["id"])
    req = store.create_topup_request(store.identity_of(tok))
    monkeypatch.setattr(config, "DEFAULT_RUN_ALLOWANCE", 3)
    result = store.approve_request(req["id"])
    assert "token" not in result                                        # the caller already holds it
    assert (result["id"], result["profile_id"], result["runs_remaining"]) == (tok["id"], tok["profile_id"], 3)
    assert len(_tokens()) == 1 and len(_profiles()) == 1
    (topup,) = [r for r in _requests() if r["kind"] == "topup"]
    assert (topup["status"], topup["token_id"]) == ("approved", tok["id"])


def test_a_topup_for_a_vanished_token_is_refused_and_stays_pending():
    tok = _user("val2")
    req = store.create_topup_request(store.identity_of(tok))
    write_json(config.KB_AUTH_DIR / "tokens.json", [])
    with pytest.raises(store.AuthError, match="no longer exists"):
        store.approve_request(req["id"])
    assert [r["status"] for r in _requests() if r["kind"] == "topup"] == ["pending"]


def _legacy_token(identifier: str, raw: str, token_id: str = "t-legacy01") -> dict:
    record = {"id": token_id, "token": raw, "identifier": identifier, "role": "user",
              "runs_remaining": 2, "created": "2026-09-01T00:00:00+00:00", "request_id": "r-old"}
    write_json(config.KB_AUTH_DIR / "tokens.json", read_json(config.KB_AUTH_DIR / "tokens.json") + [record])
    return record


def test_a_legacy_token_is_backfilled_once_and_persisted():
    _legacy_token("Old Timer", "LEGACY-RAW-TOKEN")
    first = store.resolve_token("LEGACY-RAW-TOKEN")
    assert re.fullmatch(r"p-[0-9a-f]{8}", first["profile_id"])
    assert _tokens()[0]["profile_id"] == first["profile_id"]            # written back, not recomputed per call
    assert store.resolve_token("LEGACY-RAW-TOKEN")["profile_id"] == first["profile_id"]
    assert len(_profiles()) == 1 and store.identity_of(first)["profile_id"] == first["profile_id"]


def test_a_legacy_token_never_lands_on_a_newer_account_with_the_same_name():
    """Catches approval minting a second account under a name a not-yet-backfilled legacy token holds (#68 item 1)."""
    _legacy_token("Jane", "LEGACY-JANE")                                # issued before profiles existed
    with pytest.raises(store.AuthError):
        _user("JANE")                                                  # refused, not split (backend/bugs.md 2026-10-15)
    legacy = store.resolve_token("LEGACY-JANE")
    assert legacy["profile_id"].startswith("p-") and len(_profiles()) == 1


def test_the_admin_has_its_own_sentinel_account_and_no_profile_row():
    admin = store.resolve_token("admin-secret")
    assert admin["profile_id"] == store.ADMIN_PROFILE_ID
    with pytest.raises(profiles.ProfileError):
        profiles.normalise_identifier(admin["identifier"])              # "admin" can never be typed into a signup
    assert not (config.KB_AUTH_DIR / "profiles.json").exists()


# --- backend/logplane.py: append-only, filtered, projected --------------------
def test_a_log_entry_has_its_shape_and_lines_append():
    logplane.write("audit", event="login_ok", actor="account", profile_id="p-1", run_id="r1", fields={"x": 1})
    logplane.write("audit", event="login_failed", actor="anonymous")
    first, second = _audit()
    assert set(first) == {"ts", "kind", "event", "profile_id", "run_id", "actor", "fields"}
    assert (first["kind"], first["event"], first["profile_id"], first["run_id"], first["fields"]) == \
        ("audit", "login_ok", "p-1", "r1", {"x": 1})
    assert datetime.fromisoformat(first["ts"]).tzinfo is not None
    assert (second["profile_id"], second["fields"]) == (None, {})


@pytest.mark.parametrize("kind, fields", [("bogus", None), ("audit", {"blob": object()})],
                         ids=["unknown-kind", "unserialisable"])
def test_a_failed_log_write_never_raises_and_writes_nothing(kind, fields):
    logplane.write(kind, event="e", actor="system", fields=fields)
    assert all(p.read_text(encoding="utf-8") == "" for p in logplane.LOG_DIR.glob("*.jsonl"))   # not one line


def test_a_log_write_never_raises_when_the_folder_is_unusable(monkeypatch, tmp_path):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(logplane, "LOG_DIR", blocker / "logplane")
    logplane.write("audit", event="login_ok", actor="account")         # mkdir fails underneath: swallowed


def test_reading_skips_blank_and_corrupt_lines():
    _stamped([("2026-10-12T01:00:00+00:00", "audit", "a", None)])
    with (logplane.LOG_DIR / "audit.jsonl").open("a", encoding="utf-8") as fh:
        fh.write("\n{not json\n   \n")                                   # one bad line never takes out the log
    _stamped([("2026-10-12T02:00:00+00:00", "audit", "b", None)])
    assert [e["event"] for e in logplane.query("audit")["entries"]] == ["b", "a"]


def _stamped(entries):
    """Write entries with chosen timestamps (ts, kind, event, profile_id)."""
    logplane.LOG_DIR.mkdir(parents=True, exist_ok=True)
    for ts, kind, event, pid in entries:
        with (logplane.LOG_DIR / f"{kind}.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": ts, "kind": kind, "event": event, "profile_id": pid,
                                 "run_id": None, "actor": "system", "fields": {"secret_field": "x"}}) + "\n")


def test_query_merges_kinds_filters_and_sorts_newest_first():
    _stamped([("2026-10-12T01:00:00+00:00", "audit", "login_ok", "p-a"),
              ("2026-10-12T03:00:00+00:00", "run", "run_start", "p-a"),
              ("2026-10-12T02:00:00+00:00", "audit", "login_ok", "p-b")])
    assert [e["ts"][11:13] for e in logplane.query(None)["entries"]] == ["03", "02", "01"]
    assert [e["profile_id"] for e in logplane.query("audit", profile_id="p-a")["entries"]] == ["p-a"]
    assert [e["event"] for e in logplane.query(None, event="run_start")["entries"]] == ["run_start"]
    assert len(logplane.query(None, since="2026-10-12T02:00:00+00:00")["entries"]) == 2     # inclusive


def test_paging_walks_every_entry_once_with_distinct_timestamps():
    _stamped([(f"2026-10-12T00:00:{i:02d}+00:00", "audit", "login_ok", "p-a") for i in range(7)])
    seen, cursor = [], None
    while True:
        page = logplane.query("audit", cursor=cursor, limit=3)
        seen += [e["ts"] for e in page["entries"]]
        if page["next_cursor"] is None:
            break
        cursor = page["next_cursor"]
    assert seen == sorted(seen, reverse=True) and len(seen) == len(set(seen)) == 7


@pytest.mark.parametrize("asked, got", [(0, 1), (-5, 1), (10_000, logplane.MAX_LIMIT)])
def test_the_limit_is_clamped(asked, got):
    _stamped([(f"2026-10-12T00:{i // 60:02d}:{i % 60:02d}+00:00", "audit", "e", None) for i in range(got + 1)])
    assert len(logplane.query("audit", limit=asked)["entries"]) == got


def test_paging_never_skips_entries_that_share_a_timestamp():
    _stamped([("2026-10-12T00:00:01+00:00", "audit", "e", None)]
             + [("2026-10-12T00:00:02+00:00", "audit", "e", None)] * 3
             + [("2026-10-12T00:00:03+00:00", "audit", "e", None)])
    seen, cursor = 0, None
    while True:
        page = logplane.query("audit", cursor=cursor, limit=2)
        seen += len(page["entries"])
        if page["next_cursor"] is None:
            break
        cursor = page["next_cursor"]
    assert seen == 5


def test_a_user_sees_only_their_own_allowlisted_projected_entries():
    _stamped([("2026-10-12T01:00:00+00:00", "audit", "login_ok", "p-a"),
              ("2026-10-12T02:00:00+00:00", "audit", "forbidden", "p-a"),
              ("2026-10-12T03:00:00+00:00", "audit", "some_new_event", "p-a"),     # no allowlist: hidden
              ("2026-10-12T04:00:00+00:00", "audit", "login_ok", "p-b"),
              ("2026-10-12T05:00:00+00:00", "audit", "login_failed", None)])
    entries = logplane.for_user("p-a")["entries"]
    assert [e["event"] for e in entries] == ["forbidden", "login_ok"]
    for e in entries:
        assert set(e) == {"ts", "kind", "event", "run_id", "fields"}      # no actor, no profile_id
        assert "secret_field" not in e["fields"]                          # only allowlisted fields survive


def test_the_allowlist_exposes_no_content_or_credential_field():
    exposed = set().union(*logplane._USER_VISIBLE_FIELDS.values())
    assert not exposed & {"token", "token_id", "identifier", "note", "content", "text", "answer", "cv", "ip"}


def test_every_event_the_backend_writes_has_a_projection_entry():
    # Fail-closed hides an unlisted event from its own account; this keeps the
    # design's "a user sees own logins, access decisions, exports" true as
    # events are added.
    written = set()
    for path in (config.BASE_DIR / "backend").rglob("*.py"):
        written |= set(re.findall(r'event="(\w+)"', path.read_text(encoding="utf-8")))
    assert written and written <= set(logplane._USER_VISIBLE_FIELDS), sorted(written - set(logplane._USER_VISIBLE_FIELDS))


def test_auth_routes_log_ids_never_names_notes_or_tokens():
    req = auth_routes.request_access(auth_routes.AccessRequest(identifier="Secret Person", note="call 555-0199"))
    tok = auth_routes.approve(req["id"], store.identity_of(store.resolve_token("admin-secret")))
    with pytest.raises(HTTPException):
        auth_routes.login(auth_routes.LoginRequest(token="typed-wrong-token-xyz"))
    ident = auth_routes.login(auth_routes.LoginRequest(token=tok["token"]))
    auth_routes.request_more(auth_routes.TopupRequest(note="private reason"), ident)
    text = (logplane.LOG_DIR / "audit.jsonl").read_text(encoding="utf-8")
    for secret in ("Secret Person", "555-0199", "typed-wrong-token-xyz", tok["token"], "private reason", "admin-secret"):
        assert secret not in text, secret
    events = {e["event"]: e for e in _audit()}
    assert set(events) == {"request_access", "request_approved", "login_failed", "login_ok", "request_more"}
    assert events["request_approved"]["profile_id"] == tok["profile_id"]  # about the approved account, not the admin
    assert events["login_ok"]["profile_id"] == events["request_more"]["profile_id"] == tok["profile_id"]


def test_the_log_routes_scope_users_and_open_everything_to_the_admin():
    _stamped([("2026-10-12T01:00:00+00:00", "audit", "login_ok", "p-a"),
              ("2026-10-12T02:00:00+00:00", "audit", "login_ok", "p-b")])
    mine = logs_routes.logs_mine(_scope("p-a"))
    assert [e["ts"][11:13] for e in mine["entries"]] == ["01"]
    admin = store.identity_of(store.resolve_token("admin-secret"))
    assert len(logs_routes.admin_logs(admin)["entries"]) == 2
    assert logs_routes.admin_logs(admin, profile_id="p-b")["entries"][0]["profile_id"] == "p-b"


def test_an_unknown_log_kind_is_a_client_error_not_a_500():
    try:
        logs_routes.logs_mine(_scope("p-a"), kind="bogus")
    except HTTPException as exc:
        assert 400 <= exc.status_code < 500


# --- backend/cv_store.py: one owner's CVs, two-step commit --------------------
PDF = b"%PDF-1.4 a test cv"


@pytest.fixture
def cv_parse(monkeypatch):
    """pypdf and the CV parser replaced: n pages, and a tree with these sections."""
    import pypdf
    from utils.cv_handling import cv_extract

    knobs = SimpleNamespace(pages=1, sections=[SectionType.HEADER, SectionType.EXPERIENCE], lines=["a line"],
                            unreadable=False)

    class FakeReader:
        def __init__(self, path):
            if knobs.unreadable:
                raise ValueError("EOF marker not found")
            self.pages = [None] * knobs.pages

    def fake_parse(path):
        kids = [CVNode(node_id=s.value, kind=NodeKind.SECTION, section_type=s, depth=1, parent_id="cv")
                for s in knobs.sections]
        root = CVNode(node_id="cv", kind=NodeKind.CV, section_type=SectionType.OTHER, depth=0, children=kids)
        return CVTree(source_file=path.name, root=root), knobs.lines

    monkeypatch.setattr(pypdf, "PdfReader", FakeReader)
    monkeypatch.setattr(cv_extract, "parse_cv", fake_parse)
    monkeypatch.setattr(cv_store, "_build_preview", lambda tree, lines: {"sections": [], "warnings": []})
    return knobs


def _cv_files(owner: str) -> list[str]:
    d = config.CV_UPLOADS_DIR / owner / "cv"
    return sorted(p.name for p in d.iterdir()) if d.exists() else []


@pytest.mark.parametrize("call", [
    lambda o: cv_store.current_summary(o), lambda o: cv_store.resolve_path(o),
    lambda o: cv_store.confirm(o, "x"), lambda o: cv_store.delete(o, "x"),
    lambda o: cv_store.ingest_pending(o, PDF, "cv.pdf", 4),
], ids=["summary", "resolve", "confirm", "delete", "ingest"])
@pytest.mark.parametrize("owner", ["", None])
def test_every_cv_store_door_refuses_a_missing_owner(call, owner):
    with pytest.raises(ValueError):
        call(owner)
    assert not config.CV_UPLOADS_DIR.exists()                          # never a shared, unnamespaced folder


def test_an_upload_is_pending_until_confirmed_and_stored_under_its_hash(cv_parse):
    summary, preview = cv_store.ingest_pending("p-a", PDF, "My CV (final).pdf", 4)
    sha = hashlib.sha256(PDF).hexdigest()[:12]
    assert set(summary) == {"id", "filename", "size_bytes", "pages", "uploaded_at"}
    assert (summary["id"], summary["filename"], summary["size_bytes"], summary["pages"]) == (sha, "My CV (final).pdf", len(PDF), 1)
    assert _cv_files("p-a") == sorted(["index.json", f"{sha}.pdf"])     # no .tmp left, no user text in the name
    assert cv_store.current_summary("p-a") is None and cv_store.resolve_path("p-a") is None
    assert cv_store.confirm("p-a", sha) == summary
    path, info = cv_store.resolve_path("p-a")
    assert path == config.CV_UPLOADS_DIR / "p-a" / "cv" / f"{sha}.pdf" and path.read_bytes() == PDF
    assert info == summary == cv_store.current_summary("p-a")
    assert "stored_name" not in json.dumps(info) and "status" not in info


def test_a_new_upload_evicts_the_old_pending_one_but_never_the_confirmed(cv_parse):
    a, _ = cv_store.ingest_pending("p-a", PDF + b"A", "a.pdf", 4)
    cv_store.confirm("p-a", a["id"])
    b, _ = cv_store.ingest_pending("p-a", PDF + b"B", "b.pdf", 4)
    c, _ = cv_store.ingest_pending("p-a", PDF + b"C", "c.pdf", 4)
    assert _cv_files("p-a") == sorted(["index.json", f"{a['id']}.pdf", f"{c['id']}.pdf"])
    assert cv_store.confirm("p-a", b["id"]) is None                     # evicted
    assert cv_store.current_summary("p-a")["id"] == a["id"]


def test_re_uploading_the_current_cv_is_a_no_op(cv_parse):
    a, _ = cv_store.ingest_pending("p-a", PDF, "a.pdf", 4)
    cv_store.confirm("p-a", a["id"])
    before = read_json(config.CV_UPLOADS_DIR / "p-a" / "cv" / "index.json")
    cv_store.ingest_pending("p-a", PDF, "renamed.pdf", 4)
    assert read_json(config.CV_UPLOADS_DIR / "p-a" / "cv" / "index.json") == before    # never demoted to pending
    assert cv_store.current_summary("p-a")["filename"] == "a.pdf"


@pytest.mark.parametrize("knob, error", [
    ({"unreadable": True}, cv_store.CvUnreadable),
    ({"pages": 5}, cv_store.CvTooManyPages),
    ({"lines": []}, cv_store.CvNoText),
    ({"sections": [SectionType.HEADER]}, cv_store.CvNoSections),
], ids=["unreadable", "too-many-pages", "no-text", "no-sections"])
def test_a_refused_upload_leaves_nothing_on_disk_and_the_index_untouched(cv_parse, knob, error):
    a, _ = cv_store.ingest_pending("p-a", PDF, "a.pdf", 4)
    cv_store.confirm("p-a", a["id"])
    before = read_json(config.CV_UPLOADS_DIR / "p-a" / "cv" / "index.json")
    for k, v in knob.items():
        setattr(cv_parse, k, v)
    with pytest.raises(error):
        cv_store.ingest_pending("p-a", PDF + b"new", "b.pdf", 4)
    assert _cv_files("p-a") == sorted(["index.json", f"{a['id']}.pdf"])
    assert read_json(config.CV_UPLOADS_DIR / "p-a" / "cv" / "index.json") == before


def test_a_failure_after_the_file_is_stored_leaves_no_orphan(cv_parse, monkeypatch):
    def broken_preview(tree, lines):
        raise RuntimeError("preview failed")

    monkeypatch.setattr(cv_store, "_build_preview", broken_preview)
    with pytest.raises(RuntimeError):
        cv_store.ingest_pending("p-a", PDF, "a.pdf", 4)
    assert not any(n.endswith(".pdf") for n in _cv_files("p-a"))     # "nothing partial is left on disk"


def test_one_owner_can_never_confirm_or_delete_anothers_cv(cv_parse):
    a, _ = cv_store.ingest_pending("p-a", PDF, "a.pdf", 4)
    before = _cv_files("p-a"), read_json(config.CV_UPLOADS_DIR / "p-a" / "cv" / "index.json")
    assert cv_store.confirm("p-b", a["id"]) is None and cv_store.delete("p-b", a["id"]) is False
    assert (_cv_files("p-a"), read_json(config.CV_UPLOADS_DIR / "p-a" / "cv" / "index.json")) == before
    assert not (config.CV_UPLOADS_DIR / "p-b" / "cv" / "index.json").exists()   # a refused write creates nothing


def test_deleting_the_current_cv_clears_it_everywhere(cv_parse):
    a, _ = cv_store.ingest_pending("p-a", PDF, "a.pdf", 4)
    cv_store.confirm("p-a", a["id"])
    assert cv_store.delete("p-a", a["id"]) is True
    assert _cv_files("p-a") == ["index.json"]
    assert cv_store.current_summary("p-a") is None and cv_store.resolve_path("p-a") is None
    assert read_json(config.CV_UPLOADS_DIR / "p-a" / "cv" / "index.json")["current_id"] is None


def test_a_cv_file_lost_from_under_its_index_is_no_cv(cv_parse):
    a, _ = cv_store.ingest_pending("p-a", PDF, "a.pdf", 4)
    cv_store.confirm("p-a", a["id"])
    (config.CV_UPLOADS_DIR / "p-a" / "cv" / f"{a['id']}.pdf").unlink()
    assert cv_store.resolve_path("p-a") is None                        # a run never starts on a missing file


@pytest.mark.skipif(not config.CV_DEFAULT_PATH.is_file(), reason="no sample CV PDF on this machine (git-ignored)")
def test_the_sample_cv_ingests_for_real():
    summary, preview = cv_store.ingest_pending("p-real", config.CV_DEFAULT_PATH.read_bytes(), "CV_test.pdf", 50)
    assert summary["pages"] >= 1 and preview["sections"]
    assert all({"type", "title", "entries"} <= set(s) for s in preview["sections"])


# --- backend/runs/registry.py: run logs on disk --------------------------------
def _run(run_id="r1", owner="p-a", started="2026-10-12T01:00:00+00:00", **extra) -> dict:
    return {"id": run_id, "job_description": "jd " * 60, "mode": "offline", "started": started, "owner": owner,
            "token_id": "t-1", "cv": {"id": "x"}, "sample_cv": False, "events": [], "cv_path": "/srv/uploads/p-a/cv/x.pdf",
            "lock": threading.Lock(), "gate_event": threading.Event(), "thread": None, **extra}


def test_a_saved_run_log_keeps_exactly_its_record_fields():
    registry.save_log(_run(events=[{"type": "run_done"}]))
    data = read_json(config.RUNS_DIR / "r1.json")
    assert set(data) == {"id", "job_description", "mode", "started", "owner", "token_id", "cv", "sample_cv", "events", "pace"}
    assert "cv_path" not in data                                        # no server path leaves the server
    assert registry.load_log("r1") == data


@pytest.mark.parametrize("crafted", ["../outside", "../../etc/passwd", "/tmp/outside", "..", "sub/../../outside"])
def test_a_crafted_run_id_never_reads_outside_the_runs_folder(tmp_path, crafted):
    config.RUNS_DIR.mkdir(parents=True)
    write_json(tmp_path / "outside.json", {"id": "outside", "owner": "p-a", "events": []})
    assert registry.load_log(crafted) is None


@pytest.mark.parametrize("damaged", ["", "  \n", '{"id": "r1", "owner": "p-'], ids=["empty", "blank", "truncated"])
def test_a_damaged_run_log_reads_as_unknown(damaged):
    config.RUNS_DIR.mkdir(parents=True)
    (config.RUNS_DIR / "r1.json").write_text(damaged, encoding="utf-8")
    assert registry.load_log("r1") is None


def test_list_for_scopes_by_profile_and_sorts_newest_first():
    for run_id, owner, hour in (("a1", "p-a", "01"), ("b1", "p-b", "02"), ("a2", "p-a", "03")):
        registry.save_log(_run(run_id, owner, f"2026-10-12T{hour}:00:00+00:00", events=[{"type": "run_done"}]))
    write_json(config.RUNS_DIR / "legacy.json", {"id": "legacy", "started": "2026-10-12T04:00:00+00:00", "events": []})
    (config.RUNS_DIR / "corrupt.json").write_text("{nope", encoding="utf-8")
    mine = registry.list_for({"role": "user", "profile_id": "p-a"})
    assert [r["id"] for r in mine] == ["a2", "a1"]                      # own only; no legacy, no corrupt
    assert set(mine[0]) == {"id", "started", "mode", "job_description", "events", "completed", "cv", "sample_cv",
                            "review", "saved", "outcome", "interrupted"}
    assert len(mine[0]["job_description"]) == 120 and mine[0]["completed"] is True
    admin = registry.list_for({"role": "admin", "profile_id": store.ADMIN_PROFILE_ID})
    assert [r["id"] for r in admin] == ["legacy", "a2", "b1", "a1"]


def test_ownership_is_the_profile_not_the_token():
    record = {"owner": "p-a", "token_id": "t-old"}
    assert registry.owns(record, {"role": "user", "profile_id": "p-a", "token_id": "t-new"})   # survives a re-issue
    assert not registry.owns(record, {"role": "user", "profile_id": "p-b", "token_id": "t-old"})
    assert not registry.owns(None, {"role": "admin", "profile_id": store.ADMIN_PROFILE_ID})
    assert not registry.owns({"id": "legacy"}, {"role": "user", "profile_id": "p-a"})


def test_pruning_keeps_every_live_run_and_the_newest_finished_ones(monkeypatch):
    monkeypatch.setattr(registry, "MAX_RETAINED", 2)
    monkeypatch.setattr(registry, "_runs", {})
    for i in range(5):
        registry._runs[f"d{i}"] = {"id": f"d{i}", "started": f"2026-10-12T0{i}:00:00", "done": True}
    registry._runs["live"] = {"id": "live", "started": "2026-10-11T00:00:00", "done": False}
    registry._prune()
    assert set(registry._runs) == {"d3", "d4", "live"}


def test_a_retried_start_is_remembered_per_owner_until_it_expires(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(registry.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(registry, "_seen", {})
    registry.remember("p-a", "req-1", "run-1")
    registry.remember("p-a", None, "run-x")                             # no client id: nothing to remember
    assert registry.seen("p-a", "req-1") == "run-1" and registry.seen("p-b", "req-1") is None
    clock[0] += registry._SEEN_TTL_SECONDS + 1
    assert registry.seen("p-a", "req-1") is None and registry._seen == {}


def test_each_owner_gets_one_start_lock():
    assert registry.owner_lock("p-a") is registry.owner_lock("p-a")
    assert registry.owner_lock("p-a") is not registry.owner_lock("p-b")


def test_an_admin_download_is_logged_against_the_documents_owner(outputs, no_learning, monkeypatch):
    owner = store.identity_of(_user("dlx"))
    final = final_review.close_run(_values(_gate4("approve")), owner=owner["profile_id"], run_id="r1", live=False)
    _serve(monkeypatch, {"id": "r1", "owner": owner["profile_id"], "events": [{"type": "run_done", "final": final}]})
    runs_routes.download_document("r1", store.identity_of(store.resolve_token("admin-secret")), "md")
    (entry,) = [e for e in _audit() if e["event"] == "document_downloaded"]
    assert entry["profile_id"] == owner["profile_id"]


# --- backend/routes/profile.py: Build-Profile entries -------------------------
@pytest.fixture
def entries(tmp_path, monkeypatch):
    path = tmp_path / "profile" / "manual_entries.json"
    monkeypatch.setattr(profile_routes, "MANUAL_ENTRIES", path)
    indexed = []
    monkeypatch.setattr(profile_routes, "_index_in_background", indexed.append)   # never load the embedder
    return SimpleNamespace(path=path, indexed=indexed)


def _entry(section="skills", **record):
    return profile_routes.ProfileEntry(section=section, record=record or {"name": "Rust"})


def test_a_saved_entry_belongs_to_its_account_and_is_indexed(entries):
    new = profile_routes.add_profile_entry(_entry(), _scope("p-a"))
    assert (new["owner"], new["section"], new["record"]) == ("p-a", "skills", {"name": "Rust"})
    assert re.fullmatch(r"[0-9a-f]{8}", new["id"]) and read_json(entries.path) == [new]
    assert entries.indexed == [new]


def test_each_account_sees_only_its_own_entries_and_the_admin_sees_all(entries):
    a = profile_routes.add_profile_entry(_entry(name="A"), _scope("p-a"))
    b = profile_routes.add_profile_entry(_entry(name="B"), _scope("p-b"))
    write_json(entries.path, read_json(entries.path) + [{"id": "gap1", "section": "gap_answers", "record": {}}])
    assert profile_routes.profile_entries(_scope("p-a")) == {"entries": [a]}
    assert profile_routes.profile_entries(_scope("p-b")) == {"entries": [b]}
    admin = profile_routes.profile_entries(_scope(store.ADMIN_PROFILE_ID, "admin"))["entries"]
    assert [e["id"] for e in admin] == [a["id"], b["id"], "gap1"]       # an ownerless entry is admin-only


def test_an_entry_is_edited_only_by_its_owner_or_the_admin(entries):
    a = profile_routes.add_profile_entry(_entry(name="A"), _scope("p-a"))
    before = read_json(entries.path)
    assert _status(lambda: profile_routes.edit_profile_entry(a["id"], _entry(name="hacked"), _scope("p-b"))) == 403
    assert read_json(entries.path) == before and len(entries.indexed) == 1
    assert _status(lambda: profile_routes.edit_profile_entry("nope", _entry(), _scope("p-a"))) == 404
    edited = profile_routes.edit_profile_entry(a["id"], _entry(name="A2"), _scope("p-a"))
    assert (edited["owner"], edited["record"]) == ("p-a", {"name": "A2"}) and "updated" in edited
    assert entries.indexed[-1] == edited                                # the correction reaches the index
    by_admin = profile_routes.edit_profile_entry(a["id"], _entry(name="A3"), _scope(store.ADMIN_PROFILE_ID, "admin"))
    assert by_admin["owner"] == "p-a"                                   # an admin edit never moves ownership


def test_concurrent_saves_from_two_accounts_all_land(entries):
    _all_at_once(lambda pid, i: profile_routes.add_profile_entry(_entry(name=str(i)), _scope(pid)),
                 [("p-a" if i % 2 else "p-b", i) for i in range(20)])
    saved = read_json(entries.path)
    assert len(saved) == 20 and len({e["id"] for e in saved}) == 20
    assert sorted(e["record"]["name"] for e in saved if e["owner"] == "p-a") == sorted(str(i) for i in range(20) if i % 2)


# --- backend/vectorstore.py + backend/deps.py: shared store, containment ------
def test_the_process_builds_one_vector_store_however_many_ask(monkeypatch):
    import time as _time
    import vectordb.store as store_mod

    built = []

    class CountingStore:
        def __init__(self, persist_dir=None):
            _time.sleep(0.05)                                           # widen the race
            built.append(persist_dir)

    monkeypatch.setattr(store_mod, "VectorStore", CountingStore)
    monkeypatch.setattr(backend_vectorstore, "_store", None)
    got = []
    _all_at_once(lambda: got.append(backend_vectorstore.get_vector_store()), [()] * 8)
    assert len(built) == 1 and built[0] == config.VECTORDB_DIR and len({id(s) for s in got}) == 1


def test_contained_path_allows_inside_and_refuses_every_way_out(tmp_path):
    root = tmp_path / "root"
    (root / "p-a").mkdir(parents=True)
    assert deps.contained_path(root, "p-a", "cv", "x.pdf") == (root / "p-a" / "cv" / "x.pdf").resolve()
    (root / "link").symlink_to(tmp_path)                                # a symlink that points back out
    for parts in (("..",), ("../outside",), ("p-a", "..", "..", "x"), ("/etc/passwd",), ("link", "x")):
        with pytest.raises(deps.ScopeError):
            deps.contained_path(root, *parts)


def test_a_scope_reaches_only_its_own_subtree(tmp_path):
    root = tmp_path / "root"
    assert _scope("p-a").own(root, "cv") == (root / "p-a" / "cv").resolve()
    with pytest.raises(deps.ScopeError):
        _scope("../p-b").own(root, "cv")


def test_a_scope_is_built_only_from_an_identity_with_a_profile():
    assert deps.require_scope({"role": "user", "profile_id": "p-a"}) == _scope("p-a")
    with pytest.raises(RuntimeError):
        deps.require_scope({"role": "user", "profile_id": None})        # fail closed, never a scope keyed on None


# =============================================================================
# Backend authentication, as of 2026-10-13: who a credential is (the role
# check, a fresh identity per call), the top-up lifecycle beside signups, the
# legacy backfill under load, and the audit line each auth decision leaves.
# Called as plain functions; tests/test_backend_api.py has the HTTP side.
# =============================================================================
_MISSING = object()


def _odd_token(role) -> None:
    """One token on disk with a chosen role (or none); profile_id already set, so no backfill runs."""
    record = {"id": "t-0dd00001", "token": "ODD-ROLE-TOKEN", "identifier": "odd", "profile_id": "p-0dd00001",
              "runs_remaining": 1, "created": "2026-10-13T00:00:00+00:00", "request_id": "r-odd"}
    if role is not _MISSING:
        record["role"] = role
    write_json(config.KB_AUTH_DIR / "tokens.json", [record])


@pytest.mark.parametrize("role", ["Admin", "ADMIN", " admin", "admin ", "superuser", "", None, _MISSING],
                         ids=["Admin", "ADMIN", "lead-space", "trail-space", "superuser", "empty", "null", "missing"])
def test_only_the_exact_admin_role_opens_admin_routes(role):
    _odd_token(role)
    ident = deps.require_auth("Bearer ODD-ROLE-TOKEN")
    assert ident["role"] == ("user" if role is _MISSING else role)          # what is on disk, never upgraded
    assert _status(lambda: deps.require_admin(ident)) == 403
    assert not registry.owns({"owner": "p-someone"}, ident)                 # and no admin reach over runs either


def test_every_identity_is_a_fresh_dict_so_one_request_cannot_poison_the_next():
    first = deps.require_auth("Bearer admin-secret")
    first.update(role="user", profile_id="p-hijacked")                      # a route that mutates what it was handed
    assert deps.require_auth("Bearer admin-secret")["profile_id"] == store.ADMIN_PROFILE_ID
    tok = _user("fresh")
    mine = deps.require_auth(f"Bearer {tok['token']}")
    mine["role"] = "admin"
    assert deps.require_auth(f"Bearer {tok['token']}")["role"] == "user"
    assert _tokens()[0]["role"] == "user"                                   # and nothing reached the disk


# --- top-ups beside signups ----------------------------------------------------
def test_rejecting_a_topup_grants_nothing_and_frees_the_token_to_ask_again():
    ident = store.identity_of(_user("rita"))
    first = store.create_topup_request(ident)
    store.reject_request(first["id"])
    assert _tokens()[0]["runs_remaining"] == 2                              # a rejection grants nothing
    second = store.create_topup_request(ident)
    assert second["id"] != first["id"] and (second["kind"], second["token_id"]) == ("topup", ident["token_id"])


def test_a_rejected_topup_keeps_the_account_it_was_for():
    tok = _user("una")
    req = store.create_topup_request(store.identity_of(tok))
    assert store.reject_request(req["id"])["token_id"] == tok["id"]


def test_a_topup_approval_racing_spends_loses_no_update():
    tok = _user("racer")                                                    # allowance 2
    req = store.create_topup_request(store.identity_of(tok))
    spent = []

    def act(what):
        if what == "approve":
            store.approve_request(req["id"])
        else:
            spent.append(store.consume_run(tok["id"]))

    _all_at_once(act, [("approve",), ("spend",), ("spend",)])
    assert spent == [True, True]                                            # 2 were there, whatever the order
    assert _tokens()[0]["runs_remaining"] == 2 - 2 + config.DEFAULT_RUN_ALLOWANCE


# --- the legacy backfill ----------------------------------------------------------
def test_a_legacy_backfill_under_load_makes_one_account():
    bystander = _user("bystander")
    _legacy_token("Old Timer", "LEGACY-RAW-TOKEN")
    got = []
    _all_at_once(lambda: got.append(store.resolve_token("LEGACY-RAW-TOKEN")["profile_id"]), [()] * 12)
    assert len(got) == 12 and len(set(got)) == 1
    by_id = {t["id"]: t for t in _tokens()}
    assert by_id["t-legacy01"]["profile_id"] == got[0]
    assert by_id[bystander["id"]] == bystander                              # field for field, raw token included
    assert sorted(p["identifier_norm"] for p in _profiles()) == ["bystander", "old timer"]


@pytest.mark.parametrize("name", ["admin", "Dr: Who", "ß" * 40], ids=["reserved", "colon", "casefolds-past-64"])
def test_a_legacy_token_whose_name_the_new_rule_refuses_still_resolves(name):
    _legacy_token(name, "LEGACY-ODD-NAME")
    ident = store.identity_of(store.resolve_token("LEGACY-ODD-NAME"))
    assert ident["role"] == "user" and re.fullmatch(r"p-[0-9a-f]{8}", ident["profile_id"])


# --- the audit line of each auth decision ----------------------------------------
def test_each_auth_decision_is_audited_once_with_its_actor_and_account():
    admin = deps.require_auth("Bearer admin-secret")
    signup = auth_routes.request_access(auth_routes.AccessRequest(identifier="ana"))
    tok = auth_routes.approve(signup["id"], admin)
    ident = auth_routes.login(auth_routes.LoginRequest(token=tok["token"]))
    topup = auth_routes.request_more(auth_routes.TopupRequest(), ident)
    auth_routes.approve(topup["id"], admin)
    turned_down = auth_routes.request_access(auth_routes.AccessRequest(identifier="ben"))
    auth_routes.reject(turned_down["id"], admin)
    for call in (lambda: auth_routes.approve(signup["id"], admin),
                 lambda: auth_routes.reject(turned_down["id"], admin),
                 lambda: auth_routes.request_more(auth_routes.TopupRequest(note="n" * (store.MAX_NOTE + 1)), ident)):
        assert 400 <= _status(call) < 500                                   # a refused call is not a decision
    pid = tok["profile_id"]
    assert [(e["event"], e["actor"], e["profile_id"], e["fields"]) for e in _audit()] == [
        ("request_access", "anonymous", None, {"request_id": signup["id"]}),
        ("request_approved", "admin", pid, {"request_id": signup["id"]}),
        ("login_ok", "account", pid, {}),
        ("request_more", "account", pid, {"request_id": topup["id"]}),
        ("request_approved", "admin", pid, {"request_id": topup["id"]}),    # about the topped-up account
        ("request_access", "anonymous", None, {"request_id": turned_down["id"]}),
        ("request_rejected", "admin", None, {"request_id": turned_down["id"]}),
    ]


# =============================================================================
# The clash matrix, completed (2026-10-14, Instruction-test.md §5.14)
# =============================================================================
# Two shared files had no two-writer test: corrections.json (two live gate-4 closes
# at once) and requests.json (an approve racing a reject of the same request).
def test_two_runs_closing_at_once_keep_both_runs_corrections(learning_dir, monkeypatch):
    """Catches a lost write on the file every live gate-4 edit appends to (audit #12)."""
    path = learning_dir / "document" / "corrections.json"
    other = _second_writer_during_first_write(
        monkeypatch, lambda: learning_store._append_json_list(path, {"before": "theirs", "after": "theirs, fixed"}))
    learning_store.save_correction("document", "mine", "mine, fixed", "gate 4 edit", extra={"run_id": "r1"})
    other.join(5)
    befores = [c["before"] for c in learning_store._read_json_list(path)]
    assert sorted(befores) == ["mine", "theirs"]


def test_an_approve_racing_a_reject_resolves_the_request_exactly_once():
    """Catches both decisions landing: a 'rejected' request holding a live token, or two answers recorded."""
    req = store.create_request("dana")
    outcomes = []

    def decide(fn):
        try:
            outcomes.append((fn.__name__, fn(req["id"])))
        except store.AuthError as exc:
            outcomes.append((fn.__name__, exc))

    _all_at_once(decide, [(store.approve_request,), (store.reject_request,)])
    won = [name for name, result in outcomes if not isinstance(result, Exception)]
    assert len(won) == 1 and len(outcomes) == 2
    (stored,) = [r for r in _requests() if r["id"] == req["id"]]
    tokens = [t for t in (_tokens() or []) if t.get("identifier") == "dana"]
    if won == ["approve_request"]:
        assert stored["status"] == "approved" and len(tokens) == 1 and stored["token_id"] == tokens[0]["id"]
    else:
        assert stored["status"] == "rejected" and tokens == [] and stored["token_id"] is None
