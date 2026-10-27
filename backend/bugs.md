# Backend build plan — what the frontend needs

> Written 2026-08-19 from the frontend side, by the assistant working in
> `frontend/`. This is the authoritative, backend-focused checklist — it
> consolidates and supersedes the scattered "backend contract" notes inside
> `frontend/bugs.md` (2026-08-09/2026-08-12 entries) and adds new requirements
> that a round of frontend resilience work (2026-08-19) introduced. Frontend
> architecture and rationale live in `frontend/context.md`; this file is
> deliberately just the checklist plus why each item matters to the frontend
> that already exists and is waiting on it.
>
> **Nothing in `frontend/` currently works end to end.** There is no
> `auth/` package, no `require_auth`, no `/api/auth/*` route, in
> `scripts/frontend_api.py` — confirmed 2026-08-19 (409 lines, no `Depends`/
> `Header` import at all). Every request the frontend makes now sends
> `Authorization: Bearer <token>` and the app cannot render past a boot
> screen without at least a stub of this.

## Fastest path to something viewable

`require_auth` doesn't have to be real to unblock frontend testing. Stub it to
return a fixed identity:
```python
{"identifier": "dev", "role": "admin", "runs_remaining": None, "token_id": "__admin__"}
```
That alone gets past the boot screen. Real `/api/auth/*` routes can follow.

---

## Open bugs, ordered by criticality (added 2026-10-10)

> Every 🔴/🟠/🟡 item still open in this file, in one ranked list. Full detail
> stays at each item's own dated section below — **this is a pointer list,
> not a rewrite of the file's chronological order**, which the rest of this
> doc and every cross-reference into it from `context.md`, `frontend/bugs.md`
> and `bugs_audit_fixed.md` depend on (they point by section name + item
> number, e.g. `"gate 4" item 2`, never by position). A few items are ranked
> above their original emoji where this session's work changed what's
> actually at stake — each one says why. Six items were fixed in-session on
> 2026-10-10; listed at the bottom for reference, not because they still need
> ranking.
>
> **Where it stands, 2026-10-22.** Nine changes landed this session (listed
> under "Fixed this session (2026-10-21)" and "(2026-10-22)" below). After
> them **every remaining row needs another lane, the frontend, or a product
> decision — there is no item left that `backend/` can close alone.** Each was
> re-checked in the tree this session rather than taken from its row, and two
> rows turned out to be wrong: the `gate_wait` round number is **already
> relayed** (corrected below), and A3's producer is `utils/human_gate.py`, not
> this package. `#42`, `#45`, `#51`, `#68`, `#69` and `#70` are now fixed in
> code in full.

> **2026-10-24 — Backend test pass (Claude):** suites green (`test_backend_auth.py` 257 passed / 12 xfail, `test_backend_api.py` 207 / 1), smoke ✅, new `scripts/probe_backend.py` ✅ (refusals on the real graph, upload limits, two accounts at once, token scan, restart survival). Fixed: bug#63 item 1 (non-ASCII token was a 500, DEC-164). Detail: "2026-10-24 (backend test pass)" at the end of this file, `context/testing/backend/`.

### 🔴 Critical — open

| Item | Why it's still open |
|---|---|
| Runs carry the scope into the graph (retriever, `cv_link`, Document, the plan cache, snapshots, exports) | `"2026-10-09 (design)"` §3. **The backend's half — setting the scope — is built 2026-10-22** (`config.set_profile_id` on the worker thread + `GraphState.profile_id`; see `"2026-10-22 (scope into the graph)"`). Still open, and not backend's to build alone: every *consumer* (the retriever's collection, profile writes, the plan cache, snapshot and export folders) resolves globally, and the vault-storage bullets (one checkpointer per vault, the run trail in the vault) are a migration not started |

*(Every other 🔴 in this file — `#9`, `"2026-10-08"` §1–§2, `"CV upload (later)"` §1–§3, `"gate 4"` §1, and all of `"2026-10-09 (design)"` §1–§2 — is fixed. See "Fixed this session" below and each item's own ✅ note.)*

### 🟠 High — open

| Item | Why it's still open |
|---|---|
| Every data route scoped by the caller's own account, not by convention | `"2026-10-09 (design)"` §4. **The `/profile/entries` + `/kb/profile/manual_entries` slice is now built 2026-10-10** (see ✅ below — this was the interim fix §4's own text calls for, which didn't actually depend on §2–§3 the way this row previously said). Still unscoped: `/search` (needs vector-metadata work, deferred — see the dated entry). `routes/runs.py` hasn't moved onto `Scope` either, though — see that file's own module docstring — every route there besides `start_run` only ever passes `identity` to `registry.owns()`, which already resolves by `profile_id` internally, so there's nothing left for `Scope` to actually replace; kept open as a style question, not a known live gap |
| The log plane — `llm`/`retrieval` kinds | `"2026-10-09 (design)"` §5. **The `audit` kind is now built 2026-10-12, and the `run` kind 2026-10-14** (see ✅ below — neither depended on §3 the way this row previously said). Still open: `llm`/`retrieval` — other lanes' writes into the same module, not backend's to build alone |
| ~~No round number on `gate_wait`~~ — **not blocked on backend** | `"gate 4"` §3. **Re-checked 2026-10-22: the payload already carries `revision`/`max_revisions`.** `utils/human_gate.py` sends both and `worker._PAYLOAD_NOT_PASSED` excludes neither, so `_park` relays them onto `gate_wait`. What is left is the frontend rendering the warning and `StubGraph` matching the real payload — neither is this package's. Its own "finish item 3" (`gate_done` carrying `gate`) was built 2026-10-15 |
| Demo mode saves a fixed fake answer into the real profile and the real vector index | `"Round 8-10"` §2. **Not this folder's fix** — `learning/profile_store.py`, Data Storage/Agents lane — flagged here only because the user-visible risk routes through this folder's gate-2 form |

### 🟡 Medium — open

| Item | Why it's still open |
|---|---|
| Each change's cited records aren't on `gate_wait.changes` (added 2026-10-14, from the frontend) | `"2026-10-14 (frontend, Rounds 27–42)"` A3. The final review rebuilds them from the stream's `node_done` events; works today, including after a `resume` (the persisted log replays), so ⚪-leaning |
| ~~A `cv_link` re-run on a loop-back sends `{stage}` as if it were a real result~~ | `"Round 8-10"` §6. **✅ Fixed 2026-10-22** — `unchanged: true`, no artifact key; generic, so `profile_enrich` gets it too |
| `corrections.json` writes have no lock | `"gate 4"` §6. **Not this folder's fix** — needs a move to `utils/jsonstore.py`, outside `backend/` |
| Per-line CV text in `gate_wait.changes` and `line_links` still isn't behind its own route | `"gate 4"` §8 / the CV-privacy note. **Deferred by design, not forgotten** — an explicit product decision, not a gap |
| Proposals needing the Agents lane first (undo-single-change, a `discard` decision, a required reason on reject) | `"gate 4"` §9. Blocked |
| No ~~self-export or~~ account-delete route | `"2026-10-09 (design)"` §6. **Export ✅ built 2026-10-22** (`GET /api/me/export`). **Delete still open and blocked:** step 3 is "drop its collection", but collections are not per-profile yet and `VectorStore` has no `delete`, so an account's embedded evidence would stay searchable after its account was "deleted" |

### ✅ Fixed this session (2026-10-10) — for reference, not ranking

1. Gate double-answer race, 🔴 — `"gate 4"` §1
2. Two starts from one owner + idempotency key, 🟠 — `"Round 8-10"` §4
3. An approved CV lost when a step after gate 4 fails, 🟠 — `"gate 4"` §2
4. `cv_link` privacy leak — header section + `raw_text`, 🟠 (partial fix; per-line text is the open 🟡 above) — `"CV upload (later)"` §4
5. `gap_answers` unbounded / accepted at any gate / kept on reject, 🟠 — `"Round 8-10"` §1
6. `feedback` unbounded, 🟠 — `"gate 4"` §4
7. §1 of `"2026-10-09 (design)"` — identity is now an account, not a credential, 🔴 — see `"2026-10-10 (identity) "` below
8. §2 of `"2026-10-09 (design)"`, partially — `Scope`, containment, fail-closed, and a real path-traversal fix in `load_log`, 🔴 (partial — route migration beyond `cv.py` and the admin audit path are still open) — see `"2026-10-10 (scope)"` below
9. The `/profile/entries` + `/kb/profile/manual_entries` cross-user read+write leak — any authenticated user could read and silently overwrite any other user's Build-Profile data, 🟠 (promoted in practice: this was the live, exploitable half of §4) — see `"2026-10-10 (profile scope)"` below
10. §2 of `"2026-10-09 (design)"`, route migration completed — `routes/runs.py`'s `start_run` now reads `scope.profile_id`/`scope.role` instead of the raw identity dict, and `download_document` now shares `contained_path()` instead of its own independently-maintained containment check, 🔴 (closes everything in §2 except the admin cross-vault route, which needs §5) — see `"2026-10-12 (scope, runs.py)"` below
11. §5 of `"2026-10-09 (design)"`, the `audit` kind — new `backend/logplane.py`, `GET /api/logs/mine` + `GET /api/admin/logs`, every 403 captured automatically, 🟠 (partial — `run`/`llm`/`retrieval` kinds are still open) — see `"2026-10-12 (log plane)"` below
12. §2 of `"2026-10-09 (design)"`, fully closed — the admin cross-vault route (`GET /api/admin/users/{profile_id}/{profile,cv}`), audit-write-first with a real refuse-on-failure path, 🔴 (this was §2's last open piece — §2 is now complete end to end) — see `"2026-10-12 (admin vault)"` below

### ✅ Fixed this session (2026-10-13) — for reference, not ranking

1. `"gate 4"` §7, restart survival — a run parked at any gate now survives a server restart: the log is persisted the moment a gate opens, and `POST /api/runs/{id}/resume` rebuilds the run from that log and re-parks it on the exact same gate without re-spending its allowance, 🟠 — see `"2026-10-13 (restart survival)"` below
2. `"gate 4"` §5b/§5c, saved CVs — `list_for` now reports `review`/`saved` per run, and `DELETE /api/runs/{id}/document` removes both saved files and nulls the export, 🟠 (part (a), a mounted volume for `OUTPUTS_DIR`, is infra/deployment, not this file's code to fix) — see `"2026-10-13 (saved CVs)"` below

### ✅ Fixed this session (2026-10-14) — for reference, not ranking

1. §5 of `"2026-10-09 (design)"`, the `run` kind — `backend/runs/worker.py` now writes `run_started`/`node_done` (with duration)/`gate_opened`/`gate_decided` (decision only)/`run_done`/`run_stopped`/`run_error` to the log plane, and `backend/routes/runs.py` writes `allowance_spent`/`allowance_refunded`, 🟠 (this closes the `run` kind in full — `llm`/`retrieval` are still open, other lanes' writes into the same module) — see `"2026-10-14 (log plane, run kind)"` below

### ✅ Fixed this session (2026-10-15) — for reference, not ranking

1. `"Round 8-10"` §3 / `"gate 4"` §3's "finish item 3" — `gate_done` now carries `gate` too, matching `gate_wait`, 🟠 (one field; the `revision`/`max_revisions` half of `"gate 4"` §3 stays open, blocked on `utils/human_gate.py`, the Agents lane) — see `"2026-10-15 (gate name on gate_done)"` below
2. `"CV upload (later)"` §5 — the `cv_link` `node_done` event now carries a `match_counts: {matched, partial, unmatched}` summary off `line_links`, so the frontend can warn a new user with an empty profile without walking the whole list itself, 🟠 — see `"2026-10-15 (match counts)"` below
3. `"2026-10-14 (frontend, Rounds 27–42)"` A1 — `download_document`, `delete_document` and `list_for`'s `saved`/`review` all read `final` off whichever of `run_done`/`run_error` actually carries it now, through one new shared `registry.current_export()` instead of three independent (and two stale) lookups, 🟠 — see `"2026-10-15 (final on run_error too)"` below
4. `"2026-10-08"` §5 / `"Round 8-10"` §7 — `list_for`'s summary gained `outcome: "done" | "stopped" | "error" | null`, so a crashed run no longer reads identically to a superseded one, 🟡 — see `"2026-10-15 (outcome field)"` below
5. `bugs_audit_fixed.md` #68 item 1 — a legacy token could be backfilled onto a newer, different person's account with the same normalised name; approval now refuses that name, 🟠 — see `"2026-10-15 (legacy token collision)"` below
6. `bugs_audit_fixed.md` #69 item 1 — on a case-insensitive filesystem `/api/kb/profile/MANUAL_ENTRIES` served every account's Build-Profile entries unscoped; now exact-name only + same-file scope check, 🟠 — see `"2026-10-15 (manual_entries case variant)"` below
7. `bugs_audit_fixed.md` #45 (+ #64 item 4) — `POST /api/search` took any collection name and any `k`; now an allowlist, `k` 1–50, and an unbuilt index is a 404 not a 500, 🟡 — see `"2026-10-15 (search boundary)"` below
8. `bugs_audit_fixed.md` #70 item 1 — a token approved before the typed-name rule existed was a **500 at every door** (login, every `Authorization` route, the `?token=` stream), locking its holder out of their own runs, CV and entries; the backfill now keeps that account under a system key instead of refusing it, 🟠 (ranked above its own 🟡 label: a full lockout of a valid credential) — see `"2026-10-15 (legacy token lockout)"` below

### ✅ Fixed this session (2026-10-16) — for reference, not ranking

1. `bugs_audit_fixed.md` #68 item 4 — an admin's download **or delete** of someone else's saved CV was audited against the admin's own account, so it never appeared in the owner's `/logs/mine` and `?profile_id=<owner>` could not find it; both routes now attribute to the run's owner with `actor="admin"`, 🟠 — see `"2026-10-16 (document audit attribution)"` below
2. `bugs_audit_fixed.md` #68 item 3 — the log plane's cursor was `ts` alone, so entries sharing a timestamp across a page boundary were **silently dropped** from a paginated walk; and an unknown `?kind=` was a 500. Now paged on `(ts, count-at-that-ts)`, and a 400, 🟠 — see `"2026-10-16 (log paging and kind)"` below
### ✅ Fixed this session (2026-10-17) — for reference, not ranking

3. `bugs_audit_fixed.md` #70 item 2 — rejecting a top-up overwrote its `token_id` with `None`, erasing the request's only link to the account, and the `request_rejected` audit line carried `profile_id: None`, so that account's own `/logs/mine` never showed the decision although approvals did. `_resolve` no longer clears `token_id`, and `reject` attributes through `store.profile_id_for_token()`, 🟡 — see `"2026-10-17 (rejected top-up attribution)"` below
2. `bugs_audit_fixed.md` #69 item 3 — a 403 on `GET /api/runs/{id}/events` was audited as `anonymous` with `profile_id: null`, because the app-wide handler read only the `Authorization` header while that route authenticates by `?token=`; one account opening another's run stream — the attempt this log exists to record — was therefore unattributable, and the refused user never saw it in `/logs/mine`. The handler now falls back to the query token, 🟠 — see `"2026-10-17 (403 attribution on the events route)"` below
1. `bugs_audit_fixed.md` #69 item 2 — an unknown Build-Profile `section` was accepted, saved and **silently never indexed**, so the user was told their entry was in while retrieval could never reach it; now a 422 at the door, validated against `SECTION_TYPES` itself, 🟠 — see `"2026-10-17 (unindexable profile section)"` below

4. `bugs_audit_fixed.md` #68 item 2 — the request-access queue never applied the account's identity rule, so a reserved/`:`/fullwidth name, or one that only fits the length bound before casefolding, was queued and then refused with a 409 at approval, after the person had been told their request was in; and the pending-duplicate check used `.lower()`, so two spellings of one name were two requests. Now normalised at the door (400) and deduped on the normalised key, 🟠 — see `"2026-10-16 (request queue identity rule)"` below
3. `bugs_audit_fixed.md` #68 item 6 — a damaged run log (empty, truncated, or any JSON that isn't an object) was an uncaught `AttributeError`/`JSONDecodeError` at `/runs/{id}/log`, `/document` and `/resume`, and — wider than logged — a **500 on `GET /api/runs` for the admin**, taking the whole Runs view down on one bad file; `load_log` now reads any such file as "unknown run" and `list_for` goes through it, 🟡 — see `"2026-10-16 (damaged run log)"` below

### ✅ Fixed this session (2026-10-21) — for reference, not ranking

1. `bugs_audit_fixed.md` #68 item 5 — a CV upload that failed after its PDF was moved into place (preview build, index write) left the file on disk with no index entry, unlisted and out of reach of the owner's own delete; a failed write could also leave the index naming already-evicted files. Preview now builds before the move, and move + index write + evictions happen as one step under the index lock, removing the file on failure only if this upload created it, 🟡 — see `"2026-10-21 (orphan CV on upload)"` below
2. `"2026-10-14 (frontend, Rounds 27–42)"` A2 — `run_error` named no step, so the frontend inferred the failed step from whichever was left "working", and an error outside a step left nothing to mark. It now carries `node`: the agent that was running, or `null` when the error came from outside one (Supervisor, a gate, graph build); the log plane's `run_error` carries it too, 🟡 — see `"2026-10-21 (failed step on run_error)"` below
3. `bugs_audit_fixed.md` #70 item 3 — `POST /auth/request-more` with the admin token queued a top-up for `__admin__`, which has no `tokens.json` row: approving it 409s, so it sat pending forever holding one of the 100 `MAX_PENDING` slots that gate every signup. Refused at the door with a 400, 🟡 — see `"2026-10-21 (admin top-up)"` below

### ✅ Fixed this session (2026-10-22) — for reference, not ranking

4. `bugs_audit_fixed.md` #42 — nothing checked the CV file existed before `consume_run`, so a missing one surfaced as a `run_error` at `cv_link`, the sixth node, after two answered gates and four live LLM calls, with the allowance already spent (`refund_run` covers failure to *start* only). Now a 503 before anything is charged, plus boot-time warnings for the missing sample CV and an unbuilt profile index, 🟡 — see `"2026-10-22 (CV preflight)"` below
5. `bugs_audit_fixed.md` #51 (Backend's two items) — the KB browser counted `do_not_claim.json` by its three wrapper *keys* ("3 records" for 22 claims) while `kb_file` returned the wrapper as one record; and the live-mode key check demanded `GROQ_API_KEY` specifically, refusing a live run any other keyed provider could serve. Both routes now read records through one function, and the key check asks what `agents/base._live_answer` asks: can every pipeline agent reach *some* provider, 🟡 — see `"2026-10-22 (hygiene: KB counts, live keys)"` below
6. `"2026-10-09 (design)"` §3, **the backend half** — nothing below the worker could tell whose data a run was allowed to touch. A run now carries its account: `config.set_profile_id()` on the worker thread (a ContextVar, like the fake-LLM switch) plus `GraphState.profile_id` for a resume in a new process. **The consumers are still global** and are the Agents/KB lanes' work, 🔴 — see `"2026-10-22 (scope into the graph)"` below
7. `"Round 8-10"` §6 — a node that ran and changed nothing (a `cv_link` re-read skipped on a gate-3 loop-back, `profile_enrich` with no answers) emitted `{stage}` as its artifact, which reads as an empty *result*; the frontend carries a `cv_link`-shaped special case for it. `node_done` now carries `unchanged: true` and no `artifact` key at all, 🟡 — see `"2026-10-22 (a node that changed nothing)"` below
8. `"2026-10-09 (design)"` §6, **the export half** — an account had no way to get its own data out. New `GET /api/me/export` returns a zip of the caller's account: identity, Build-Profile entries, CV index + PDFs, run trails, saved CVs, and its own projected audit log. **The delete half stays open and is blocked** (no per-profile collections, no `VectorStore.delete`), 🟡 — see `"2026-10-22 (account export)"` below
9. **New, found and fixed 2026-10-22** — a present-but-**empty** `profiles.json` / `tokens.json` / `requests.json` read as "no records", which in these three stores is a *decision* ("no account has that name", "no token is valid", "no request is waiting") and then became the base for the next write, so one transient empty file destroyed every row. Reproduced: an empty `profiles.json` let `create_profile` mint a second profile for a name that already had one — the guard #68 item 1 exists for — and the next write left only that row. Now `jsonstore.read_records()`: `[]` only when the file is **absent**, 🟠 — see `"2026-10-22 (an empty auth store)"` below

---

## 1. Gate → artifact wiring fix (independent of auth — do this first, it's small)

`scripts/frontend_api.py`'s `GATE_AFTER` (currently ~line 78) is a flat
`node -> title` map, and its last entry pairs the title "Final document
review" with the **verifier** node, not the **document** node whose output
the user is actually meant to approve. Restructure to a dict-of-dicts:

```python
GATE_AFTER = {
    "jd_analysis": {"title": "Requirements review", "artifact_node": "jd_analysis"},
    "profile":     {"title": "Evidence review",      "artifact_node": "profile"},
    "matching":    {"title": "Fit review",            "artifact_node": "matching"},
    "verifier":    {"title": "Final document review", "artifact_node": "document"},
}
```

In `_run_worker`, the `gate_wait` emit needs the new field added:
```python
gate = GATE_AFTER[node]
run["gate"] = {"after": node, "title": gate["title"]}
_emit(run, "gate_wait", node=node, title=gate["title"], artifact_node=gate["artifact_node"])
```

The frontend (`PipelineView.jsx`) already reads `ev.artifact_node` and falls
back to `ev.node` when absent, so this is additive — old saved run logs keep
replaying correctly either way. Without this fix, the final gate keeps
showing the fact-check report instead of the generated CV, and there is no
way to fix that from the frontend side.

## 2. `config.py` — additive, ~15 lines

- `KB_AUTH_DIR = KB_DIR / "auth"` (sibling of the existing `KB_*_DIR` constants)
- `ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")`
- `DEFAULT_RUN_ALLOWANCE = int(os.getenv("DEFAULT_RUN_ALLOWANCE", "2"))`
- A thread-local fake-LLM switch:
  ```python
  import threading
  _fake_local = threading.local()
  def set_fake_llm(value: bool) -> None: _fake_local.value = value
  def fake_llm_active() -> bool: return getattr(_fake_local, "value", USE_FAKE_LLM)
  ```
  **Why:** `frontend_api.py` currently does `config.USE_FAKE_LLM = ...` from
  inside a worker thread — a process-global mutation. That's masked today
  because only one run exists at a time; per-owner run slots (§6 below) make
  it a real bug — two concurrent runs in different modes corrupt each other,
  and an "offline" run can silently start making real, billed provider calls.
  `agents/base.py`'s two reads of `config.USE_FAKE_LLM` need to become
  `config.fake_llm_active()` for this to have any effect — that's inside
  `agents/`, which may be outside this checklist's scope; flag it as a
  decision rather than skip it silently.

Add to `.env.example`: `ADMIN_TOKEN=` and `DEFAULT_RUN_ALLOWANCE=2`.

Add to `.gitignore`: `knowledge_base/auth/` — `tokens.json` holds plaintext
credentials and `knowledge_base/` is otherwise committed.

## 3. New package `auth/` — `auth/__init__.py` + `auth/store.py`

Pure file I/O, no FastAPI import. Mirror `learning/store.py`'s atomic-write
pattern (tmp file + `os.replace`), plus a module-level `threading.Lock()` —
that file doesn't need one (CLI-driven); this one is hit by concurrent HTTP
handlers, so every read-modify-write must be serialised.

Two JSON-array files under `config.KB_AUTH_DIR`: `requests.json`,
`tokens.json`. `mkdir(parents=True, exist_ok=True)` on write.

| function | behaviour |
| --- | --- |
| `create_request(identifier, note)` | `{id, identifier, note, status:"pending", created, resolved:None, token_id:None}` |
| `list_requests()` | **all** requests, not just pending — the admin UI splits on `status` client-side |
| `approve_request(id)` | `secrets.token_urlsafe(32)`; appends to `tokens.json` with `runs_remaining = config.DEFAULT_RUN_ALLOWANCE`; flips the request to `approved` + `resolved` + `token_id`; returns a dict **containing the raw `token`** (shown exactly once by the UI). Raise if already resolved — a double-click must not mint two tokens. |
| `reject_request(id)` | flips to `rejected` + `resolved` |
| `resolve_token(raw)` | `config.ADMIN_TOKEN` checked first (only when non-empty) → synthetic `{"id": "__admin__", "identifier": "admin", "role": "admin", "runs_remaining": None}`, no file write; else scan `tokens.json`. Compare with `secrets.compare_digest`. |
| `consume_run(token_id)` | under the lock: `__admin__` → `True`, no write; else `False` if `runs_remaining <= 0`; otherwise decrement, persist, `True` |

`request-access` is open to the world (see §4), so give it a floor here or in
the route: reject empty/oversized `identifier`/`note`, refuse a second
pending request for the same identifier. Otherwise it's an unbounded
append-to-disk from any origin.

## 4. `scripts/frontend_api.py` — auth dependencies and routes

**Dependencies:**
- `require_auth(authorization: str = Header(None)) -> dict` — parse
  `Bearer <token>` case-insensitively; **401** on missing/malformed/unknown;
  return `{identifier, role, runs_remaining, token_id}`, `runs_remaining=None`
  for admin (the frontend hides the runs-left pill on exactly that value).
- `require_admin(identity = Depends(require_auth))` — **403** if
  `role != "admin"`.

**Routes** (exact paths and shapes — the frontend already calls these):

| route | guard | response |
| --- | --- | --- |
| `POST /api/auth/request-access` | open | `{identifier, note}` in → the created request |
| `POST /api/auth/login` | open | `{token}` in → `{identifier, role, runs_remaining, token_id}`, or 401 |
| `GET /api/auth/me` | auth | same identity shape |
| `GET /api/auth/requests` | admin | `{"requests": [...]}` — **all**, not filtered |
| `POST /api/auth/requests/{id}/approve` | admin | object containing raw `token` |
| `POST /api/auth/requests/{id}/reject` | admin | anything JSON |

Thread `identity: dict = Depends(require_auth)` through **every** existing
handler except `health()` — `config_view`, `kb_overview`, `kb_file`, `search`,
all `/runs*`, all `/profile/entries*`. Note `GET /api/config` currently leaks
`keys_present` and the full model map unauthenticated; it needs the guard too.

**`POST /api/runs`:** after any existing checks,
```python
if identity["role"] != "admin" and not auth_store.consume_run(identity["token_id"]):
    raise HTTPException(403, "No runs remaining")
```
Must be **exactly 403** — `PipelineView.jsx` special-cases that status to show
"No runs remaining on your token — ask an admin to issue a new one." Consumed
on every run, offline or live.

## 5. ⚠️ New, hard requirement since 2026-08-19: 401 vs 403 discipline

The frontend now has **central 401 handling**: any response with status 401,
from any endpoint (except `/auth/login` and the boot `/auth/me`), triggers an
automatic client-side logout with a "your session ended" message. This is new
as of the 2026-08-19 frontend round — it did not exist when the routes above
were originally scoped, and it changes the cost of getting a status code wrong.

**Concretely:**
- 401 = "this token is not valid or not present" — the only case that should
  ever end a session.
- 403 = "this token is valid, but you can't do this specific thing" — wrong
  role, not your run, out of runs. **Never** 401 for these. Getting this wrong
  logs a legitimate, authenticated user out of the whole app over what should
  have been one failed request.

This applies to every ownership/permission check below, not just the ones
already called out as 403 in earlier notes.

## 6. Per-owner run slots

`_active_run` (currently a single module-level `dict | None`) needs to become
`_active_runs: dict[str, dict]` keyed by `token_id`. `start_run` should abort
only the **caller's own** previous run (`_abort` + `thread.join`), never
another user's — today a new run supersedes *whichever* run was active,
regardless of who started it. Stamp `run["owner"] = identity["token_id"]`
before the worker thread starts (the thread has no request context, so this
is the only place to capture it).

Add ownership checks — **403, per §5**, not 404 (a prior draft of this note
said 404 "so run existence doesn't leak"; that reasoning was written before
central 401 handling existed as a concern, and 403 is simpler to reason about
consistently with everything else here) — to `answer_gate`, `run_events`,
`run_log`. Filter `list_runs` by owner unless admin; this needs `owner`
persisted into the run-log JSON in `_run_worker`'s `finally` block (also:
that write is currently a plain `write_text`, not the atomic `_write_json` —
worth fixing while touching it). Old logs without an `owner` field should be
treated as admin-only-visible, not crash `list_runs`.

**Consumed by two frontend views now, not one:** `RunsView.jsx` (all runs,
admin) and the new `Account.jsx` (the caller's own runs, both roles) both
call plain `GET /api/runs` and expect owner-filtering to already be correct
server-side — there's no separate "my runs" endpoint, by design.

## 7. SSE token

`GET /api/runs/{run_id}/events` — `EventSource` cannot set headers, so accept
`token: str | None = None` as a query param on **this route only**, validated
through the same `resolve_token` + ownership path as everything else.

## 8. Smoke test

`curl` (or a `scripts/smoke_auth.sh`): request-access → log in as admin via
`ADMIN_TOKEN` → list requests → approve → log in with the issued token →
`/auth/me` → 2 offline runs → 3rd returns **403** → confirm a second token's
run is invisible to the first via `GET /api/runs`. Plus one
`USE_FAKE_LLM=1` run through all 4 gates asserting the final `gate_wait`
carries `artifact_node: "document"`.

## 9. Optional, nice-to-have: a real "is this a placeholder" flag

Not blocking. The frontend's `stubs.js` currently *guesses* whether an
artifact is fabricated stub output (e.g. `matching` returning a non-zero
score with an empty `matches` list — a combination only the hardcoded stub in
`agents/matching.py` produces) purely from the response shape, because it has
no other way to know. If/when convenient, adding an explicit `"stub": true`
(or similar) to a placeholder agent's artifact would let the frontend drop
the heuristics file entirely instead of maintaining guesses that need to be
deleted by hand as each agent becomes real.

## Cross-references

- `context/bugs.md` — has the original gate→artifact mismatch (#2) and global
  `USE_FAKE_LLM` (#3) findings from earlier auditing.
- `context/audit.md` finding #6 — closed by a join-before-start workaround
  that §6 above replaces; reopen/rewrite it once per-owner run slots land, or
  the two mitigations will be silently fighting each other.
- `frontend/bugs.md` — the frontend-side implementation history (what's
  already built, what it looks like, how to verify it once this lands).
- `frontend/context.md` — frontend architecture, including exactly how each
  response shape above gets consumed.

---

## Status 2026-08-19 — plan approved, build not started

Read against the real current code (`scripts/frontend_api.py` still 409 lines, no
`Depends`/`Header` import — unchanged from the confirmation at the top of this file)
and turned into a concrete build plan. **Nothing in this checklist is implemented
yet.** Full rationale and the planned file layout are in the new `backend/context.md`
— this entry is just the delta against what this file specifies.

Two decisions, both made and locked in:

1. **Structure.** Not a single grown `frontend_api.py` + top-level `auth/` as this
   file's route table implies — a `backend/` package (`app.py`, `deps.py`,
   `jsonstore.py`, `auth/store.py`, `runs/{registry,worker}.py`, `routes/*.py`), with
   `scripts/frontend_api.py` reduced to a two-line re-export shim so the documented run
   command and `frontend/nginx.conf`/`vite.config.js` proxying need no changes. See
   "Where this sits" / "Planned layout" in `backend/context.md`.
2. **§2's `threading.local()` is wrong — using `contextvars.ContextVar` instead.**
   Verified against the installed `langgraph`: `pregel/_runner.py` runs a node inline
   only when it's the single runnable task that step; otherwise `pregel/_executor.py`
   submits it to a `ContextThreadPoolExecutor` on a *different* thread via
   `copy_context()`. A thread-local set in the API worker is invisible there — the
   fake-LLM switch would silently fail open under exactly the concurrent-run scenario
   §2 exists to guard against, letting an "offline" run place a real billed call. A
   `ContextVar` propagates through `copy_context()` correctly, confirmed with a
   throwaway LangGraph node before committing to this. Full detail in
   `backend/context.md`'s "The one deviation" section. `ADMIN_TOKEN` will be generated
   (`secrets.token_urlsafe(32)`) and appended to `.env` as part of the build, so the
   §8 smoke test can run end to end without a manual setup step.

Everything else in this file — routes, response shapes, 401/403 discipline, the
per-owner run-slot design, the SSE query-token exception — stands as written and is
being built to exactly as specified.

`frontend/bugs.md` has been updated to point here as the authoritative status; its own
2026-08-09/2026-08-12 backend sections are superseded by this plan for structure and
the ContextVar point, unchanged everywhere else (routes, response shapes, status
codes).

---

## BUILT + VERIFIED 2026-08-19 — every item above is now implemented

Full end-to-end verification run: **52 automated tests pass** (49 + 3 isolation),
**33 live checks pass** against a running server driving the real LangGraph
pipeline, and the frontend loads in Chrome against it. Details below.

### What landed

| § | item | status |
|---|---|---|
| 1 | Gate → artifact wiring (`artifact_node`) | ✅ `backend/runs/worker.py` |
| 2 | `config.py` constants + fake-LLM switch | ✅ (ContextVar, see below) |
| 2 | `.env.example`, `.gitignore`, `.env` `ADMIN_TOKEN` | ✅ generated + appended |
| 3 | `auth/store.py` | ✅ `backend/auth/store.py` |
| 4 | `require_auth`/`require_admin` + 6 routes + auth on every handler | ✅ |
| 5 | 401-vs-403 discipline | ✅ tested explicitly |
| 6 | Per-owner run slots + ownership checks | ✅ `backend/runs/registry.py` |
| 7 | SSE `?token=` | ✅ |
| 8 | Smoke test | ✅ `scripts/smoke_backend.py` |
| 9 | "is this a placeholder" flag | ✅ done, see below |

Structure is the `backend/` package from `backend/context.md`, with
`scripts/frontend_api.py` reduced to a re-export shim — the documented uvicorn
command, `nginx.conf` and `vite.config.js` needed no edits.

### Fixes and decisions made during the build

**§2's `threading.local()` would not have worked — shipped `contextvars.ContextVar`.**
Already flagged in the status note above; now proven rather than argued.
`tests/test_backend_mode_isolation.py` runs a real LangGraph node through
`agents/base.py` on two genuinely overlapping threads (a `threading.Barrier`
forces the overlap), one offline and one live, and asserts neither sees the
other's mode. It also asserts a run's mode does not leak back into the process.
Live confirmation: the smoke run completed in `offline` mode and produced fake
output **while `GROQ_API_KEY` was present and `USE_FAKE_LLM` was `False`** — i.e.
the override held on the real path where the old global would have billed.

**Server boot was ~25s; now under 1s.** `agents/profile.py:18` instantiates
`Retriever(reranker=Reranker())` at *module* scope, so importing the graph pulls
in PyTorch and loads two ~440MB models. The old `frontend_api.py` imported
`agents.supervisor` at module scope, so that cost was paid on every server start,
every test collection, every `--help`. `backend/runs/worker.py` now imports the
graph lazily behind `BUILD_GRAPH`, moving the cost to the first run that actually
needs it. (The module-scope instantiation in `agents/profile.py` is untouched —
that is agent code, and the lazy import makes it a non-issue for the API.)

**§9 implemented, backend-side only.** `node_done` now carries `stub: true` for
the five agents whose `node()` is still a placeholder — `STUB_NODES` in
`backend/runs/worker.py`. Note this is **five, not the three** `stubs.js` guesses
at: `critic` and `verifier` are also placeholders (both return a hardcoded PASS),
which the frontend's shape heuristics cannot detect at all. The frontend still
uses its heuristics until it is changed to read `ev.stub`; nothing breaks either
way.

**Run-log writes are now atomic.** As §6 noted in passing, the `finally` block
used a bare `write_text`. It now goes through `backend/jsonstore.write_json`
(tmp + `os.replace`), so a crash mid-write cannot truncate the audit trail.

**Refund on failed start.** `POST /runs` consumes the allowance *before*
starting; if the run then fails to start at all, `store.refund_run` puts it back.
Without this a thread-spawn failure would silently cost a user one of two runs.

**Additional hardening not in the checklist**, all covered by tests:
- `request-access` floor: 1–64 char identifier, ≤500 char note, no duplicate
  pending request per identifier (case-insensitive), global pending cap of 100.
  It is an unauthenticated write endpoint, so it needed a bound.
- Double-approve returns **409** and mints exactly one token.
- `secrets.compare_digest` for every token comparison; an empty `ADMIN_TOKEN`
  can never be matched by an empty/missing header.
- In-memory run records pruned past 50 (every run is on disk regardless).
- Startup logs a loud warning when `ADMIN_TOKEN` is empty, rather than serving a
  system where no request can ever be approved.
- Switched `@app.on_event("startup")` → `lifespan` (deprecated in this FastAPI).

### One bug found in the smoke test itself, not the backend

The first smoke run reported the final gate as `jd_analysis`. The backend was
right and the script was wrong: the SSE endpoint **replays the full event history
on every connect** — deliberate, it is what lets the frontend fold the whole
trail — so reconnecting once per gate re-counted the first gate four times. The
script now holds one stream open and answers gates on a second client. Worth
knowing before writing any other SSE client against this API.

### Verification performed

```
.venv/bin/python -m pytest tests/ -q          # 52 passed, 2 skipped (opt-in model tests)
.venv/bin/python -m uvicorn scripts.frontend_api:app --port 8000
.venv/bin/python scripts/smoke_backend.py     # 33 checks, ALL PASSED
```

Live smoke covers: health open / all other routes 401 without a token · admin
identity shape (`runs_remaining: null`) · request → approve → login → `/auth/me` ·
double-approve 409 · bad-token login 401 · user-on-admin-route **403** · a full
offline pipeline through all four gates on the real graph · final gate carrying
`artifact_node: "document"` · run completes and the document artifact is in the
trail · `stub: true` present · 2 runs allowed, 3rd **403** · another user cannot
read the log, list it, or open its SSE stream, while owner and admin both can ·
`/kb` reachable · path traversal blocked.

Test suite additionally covers: legacy run logs with no `owner` are admin-only
(not a crash, not a leak) · a new run does not abort a *different* owner's run ·
malformed `Authorization` headers · case-insensitive `Bearer` · unknown gate
decision 422 · gate rejection stops the run · profile entry CRUD.

### Known gaps, honestly

- **`/api/search` was never exercised live** — the first call loads the embedding
  model and Chroma (~20s). The route is auth-tested but its result shape is not
  covered end to end.
- **`live` mode was never run.** Everything used `offline`. Live mode would spend
  real Groq quota; the mode-isolation test constructs the live model object but
  never calls a provider.
- **No test for two runs by the *same* owner** — the supersede-and-join path is
  exercised only by the allowance test, which does not assert the first run
  aborted.
- Parked runs hold a worker thread until answered or superseded. Restarting the
  server drops them (daemon threads); they are not resumable — an `interrupt()` +
  checkpointer is still the deferred proper fix.

---

## ⚠️ 2026-08-22 — the verification above is STALE; the bridge now breaks at gate 1

`agents/supervisor.py` gained a real `gate` node on 2026-08-20 (LangGraph
`interrupt()` + a SQLite checkpointer, `context/context.md` 2026-08-20). The
bridge's own gate mechanism — `GATE_AFTER` + `threading.Event` in
`backend/runs/worker.py` — is still in place, and the two are incompatible.

Every UI run now fails right after the first gate:

```
node_start jd_analysis → node_done → gate_wait (Requirements review)
→ gate_done approve → routing supervisor -> profile → node_start profile
→ run_error  AttributeError: 'tuple' object has no attribute 'items'
```

`route()` sends the run to the `gate` node; `interrupt()` yields
`{"__interrupt__": (Interrupt(...),)}`; the worker's loop assumes every update
value is a dict of state fields and calls `.items()` on a tuple. LangGraph does
not raise — it ends the stream — so it surfaces as a mid-run crash.

Also: the worker calls `build_graph()` with `checkpointer=None`, and `interrupt()`
cannot resume without durable storage, so fixing the tuple crash alone only moves
the failure.

**The tests did not catch it** because `tests/test_backend_api.py` substitutes
`StubGraph`, which has no `gate` node and never interrupts — it was written
against the graph as it stood on 2026-08-19.

Full analysis, both fix options, and why this is a design call rather than a
patch: **`context/bugs.md` #9**. Nothing in this file's checklist is wrong; what
changed is who owns pausing. The §1 gate→artifact fix (`artifact_node:
"document"`) remains correct on the wire.

---

## 2026-08-31 — #9, #28, #29, #30 fixed. Written, **not run**.

Scope was "critical and medium only", i.e. `context/bugs.md`'s 🔴 and 🟠 entries
in this lane. Nothing below has been executed — no pytest, no server, no run.
The verification list is at the bottom.

### #9 🔴 — the bridge now relays the graph's gates instead of owning its own

Option 1 of the two recorded in `context/bugs.md` #9, the one that entry calls
"the real fix". `backend/runs/worker.py` is rewritten:

- `build_graph(checkpointer=make_checkpointer())`, **one checkpointer per run**
  rather than one per process. `SqliteSaver` wraps a single `sqlite3` connection
  and runs execute concurrently on their own threads; a fresh connection per run
  is cheaper than reasoning about sharing one. Closed in the `finally`.
- `run["id"]` is the `thread_id`, so a paused UI run is resumable by id — the
  same contract `scripts/run_gated_graph.py` already drives from the CLI.
- The stream loop watches for `__interrupt__` and **returns the payload** instead
  of calling `.items()` on the tuple. Answering resumes with
  `graph.stream(Command(resume=answer), …)`.
- `GATE_AFTER` is gone. `GATES` replaces it, keyed by the gate name the graph
  puts in the interrupt payload (`gate1_requirements` …), carrying `after`,
  `title` and `artifact_node`. **All four positions are identical to the old
  table** — gate 1 after `jd_analysis`, 2 after `profile`, 3 after `matching`,
  4 after `verifier` with `artifact_node: "document"` — so the frontend contract
  and §1 of this file are unchanged on the wire.
- `node_start` is no longer emitted optimistically from the previous node's
  `stage`. It comes from `supervisor_decision.next_node` — the Supervisor's
  recorded decision — so the UI can no longer be told a node started on a run
  that died before it ran (which is exactly what #9 reproduced).

**Two consequences worth stating plainly.** A paused UI run now survives process
death, which it never has. And **`reject` no longer stops the run at the bridge**
— it is forwarded to the graph, which sends the work back to `GATE_PRODUCER`
and reopens the gate. That is the behaviour `context/bugs.md` #10 built and the
bridge was overriding.

Superseding a run therefore needed its own signal: `registry.abort` used to fake
a `"reject"` gate answer, which under the new semantics would keep the superseded
run alive instead of retiring it. It now sets `run["aborted"]` and the worker
exits with `run_stopped`.

### #28 🟠 — the three stale lists

- `STUB_NODES` is `{"document", "verifier", "evaluation"}`. Dropped `matching`
  (real since 2026-08-30) and `critic` (real as of the Stage C build, 2026-08-31,
  `bugs.md` #22–#26). Genuine Matching output was being labelled fabricated.
- `AGENTS` gained `profile_enrich` in dispatch order, so the stage stops running
  invisibly.
- `GATE_AFTER` re-keying is moot — it no longer exists; `GATES` is keyed by the
  graph's own gate names, which is one fewer thing to keep in sync by hand.

Not done, deliberately: the entry's *lesson* argues for deriving "is this a stub"
from the agent module instead of restating it here. Every derivation I could
write (marker attribute; "does the module call `structured_call`") either needs
an edit inside `agents/`, which is outside this workspace, or can mislabel a real
agent that makes no LLM call — the same failure direction as the stale list, but
harder to notice. Left as a hand-maintained set with a loud comment.

### #29 🟠 — a UI run can answer the gap interview

`GateAnswer` gained `gap_answers: dict[str, str] = {}`; `answer_gate` forwards
it into `run["gate_answer"]`, and the worker passes the whole answer dict to
`Command(resume=…)`, which is what `human_gate()` reads. `gate_wait` now also
carries `gap_questions`, passed straight through from the interrupt payload
rather than re-derived, so the UI asks exactly what the gate asked.

**Backend half only.** No form exists in the frontend yet, so gate 2 still cannot
actually be answered from a browser — written up as item 1 of the 2026-08-31
section in `frontend/bugs.md`.

### #30 🟠 — profile writes reach the vector index

`POST` and `PUT /profile/entries` now embed into the `profile` collection.
`SECTION_TYPES` maps each Build-Profile section to the record `type` the
collection already uses (`projects → project`, `internships → work_experience`,
…), because `agents/profile.py`'s `QUOTAS` filters retrieval on exactly those
values — a new type invented here would be indexed and never found. The id is
`"{type}:{entry_id}"`, stable across edits, and `VectorStore.add` is an upsert,
so a correction overwrites rather than adding a rival.

New `backend/vectorstore.py` holds the process's one lazy `VectorStore`;
`routes/kb.py` now uses it instead of its own private singleton, which would
otherwise have meant two copies of a ~440MB model in memory.

Indexing runs on a **daemon thread**, not in the request: the first call loads
the embedder (~20s), and keeping that out of the request path is the 2026-08-19
boot fix. Trade-off, stated: a save returns before the entry is searchable, and
a process killed mid-embed leaves the JSON written and the vector missing — the
same state as today, logged rather than silent.

No delete route was added. `VectorStore` exposes no `delete`, and nothing calls
one; that is still open.

### Known consequences and things left alone

- **`tests/test_backend_api.py` will fail at `StubGraph`.** It is patched in as
  `lambda: StubGraph()` and its `stream(self, state, stream_mode=None)` takes no
  `config`. The worker now calls `BUILD_GRAPH(checkpointer=…)` and
  `graph.stream(input, config=…, stream_mode=…)`, and the stub has no `gate` node
  and never interrupts, so it cannot exercise the new path at all. The stub needs
  rewriting to model an interrupt — tests are the user's to write.
  `MAKE_CHECKPOINTER` is exposed as a module global next to `BUILD_GRAPH` so it
  can be stubbed the same way.
- Outside `backend/`, so untouched: #25 🔴 (`critic.node()` returns the `Critique`
  class), #27 🟠, #14 🟠, #16 🟠, #17 🟠.

*(#31, #32, #35 and #37 were deferred in this pass as 🟡 and fixed immediately
after — see the section below.)*

---

## 2026-08-31 (later) — the remaining 🟡s in this lane. Also **not run**.

Everything `context/bugs.md` still had open against `backend/`, i.e. the four
skipped by the 🔴/🟠 scope above. Same caveat: written, not executed.

**#31 — `registry.list_for` sorted by random hex.** It sorted `Path` objects, and
a run's filename *is* its id (`uuid4().hex[:8]`), so "newest first" was random
order in the one screen whose job is chronology. Now builds the list first and
sorts on each record's `started` (ISO-8601, sorts correctly as a string).

**#32 — UI runs wrote every snapshot into `logs/no_run_id/`.** The worker's
`GraphState(...)` now passes `run_id=run["id"]`. One keyword; it was flagged in
the section above as left in a line I had just rewritten. `log_state_snapshot`
still defaults rather than raising on a missing `run_id` — that half of the
proposed solution is in `state/state_utils.py`, outside this workspace, and would
break existing callers that legitimately have none.

**#35 — `manual_entries.json` had two concurrent writers and no lock.** New
`jsonstore.update_json(path, fn, default=None)` holds a per-path `RLock` across
read → modify → write; `fn` returns `(data_to_write, result)` and may return
`None` as the data to skip the write (which is how the PUT's not-found path
avoids rewriting the file identically). Both profile routes go through it.

**Half a fix, stated plainly.** A lock only serialises callers that use it, and
the third writer — `learning/profile_store.save_gap_answers`, hit from a graph
worker thread on this same file — still does its own `read_json`/`write_json`.
It already imports from `backend.jsonstore`, so closing this is a small edit
*in that file*: wrap its read-append-write in `update_json`. Outside this
workspace, so left alone and noted here and in `update_json`'s own docstring.
`backend/auth/store.py` deliberately keeps its module-level `RLock` — its
critical sections span *two* files (`approve_request` reads requests, writes
tokens, then resolves), which a per-path lock cannot cover.

**#37 — `POST /runs` accepted any `pace_seconds` and any `job_description`.**
Now `Field(0.8, ge=0, le=5)` and `Field(min_length=1, max_length=20_000)`, so
both become a 422 at the boundary before an allowance is spent.

**Found in passing, same model, not in #37:** `mode: str = "offline"` was
unvalidated while being compared against two literals. A typo'd `"Live"` is not
`"live"`, so it skipped the `GROQ_API_KEY` check, and it is not `"offline"`
either, so `set_fake_llm(False)` ran it against real providers — an unkeyed,
billed live run off a one-character mistake. Now
`Literal["offline", "live"]`, the same fix audit #10 applied to
`GateAnswer.decision` for the same reason.

### Still open against `backend/` after this

- **#30's delete route.** `VectorStore` exposes no `delete`, so a removed profile
  entry would leave its vector behind. Needs a change in `vectordb/`, outside
  this workspace. Nothing calls a delete route today.
- **#36** (`log_state_snapshot` builds a path from an unsanitised `run_id`) and
  **#38** (hygiene: `main.py`'s stale docstring, `Hit.score` bounds,
  `SupervisorDecision.inject_critic`, `Retriever.keyword`'s full rescan,
  `utils/trace.py`) — every one lives outside `backend/`.
- The **`StubGraph` rewrite** in `tests/test_backend_api.py`, per the section
  above. Yours.

### What to run

Unchanged from the section above, plus: `GET /api/runs` should now come back
newest-first, `POST /api/runs` should 422 on `pace_seconds: -1`, `mode: "Live"`
and an empty `job_description`, and a gate's snapshot should land in
`logs/<run_id>/` rather than `logs/no_run_id/`.

### What to run

```
.venv/bin/python -m pytest tests/ -q          # expect test_backend_api.py to fail at StubGraph
.venv/bin/python -m uvicorn scripts.frontend_api:app --port 8000
.venv/bin/python scripts/smoke_backend.py
```

`smoke_backend.py` drives the real graph through all four gates and is the check
that matters for #9 — it will now exercise interrupt/resume rather than the
bridge's own gates. Worth watching for specifically: the final `gate_wait` still
carrying `artifact_node: "document"`, and a **rejected** gate producing a second
`gate_wait` for the same node instead of `run_stopped`. Neither has been run.

---

## 2026-10-08 — what the 2026-10 agent work owes the frontend

Written from `frontend/` after auditing the frontend against the real backend
(full findings: `frontend/bugs.md` → Round 6). Commits `4ffe544` and `c63fa4f`
added `agents/CV_Link.py` and rewrote `document`, `matching`, `supervisor` and
`state`. Four of the five items below are in `backend/`; nothing here is a
frontend-side fix.

Good news first, so it is on the record: **no response shape the frontend
renders broke.** `Document(kind, content, unsupported_flags)`, `FitReport`,
`ProfileBlock`, `GapQuestion`, all four gate titles, every `artifact_node`
pairing, `gap_questions`, and `GateAnswer.decision`'s literals are all intact,
checked field by field. `matching.py` grew 220 lines without changing
`FitReport`. The §1 `artifact_node: "document"` contract still holds.

### 1. 🔴 `cv_link` is missing from `AGENTS`, so it emits no `routing`/`node_start`

> **✅ Fixed 2026-10-08** (with #2 and #3, as P2 in `context_Agents+Orchestration.md`
> §D): `"cv_link"` inserted between `matching` and `document`. Not done: inverting
> `_emit_routing`'s whitelist. The frontend half (`AGENT_TITLES`, renderer) was
> written 2026-10-09 (`frontend/bugs.md` → Round 9) and has not been built yet.

`agents/supervisor.py:212` adds a ninth graph node, `cv_link`, between `matching`
and `document`. `AGENTS` in `backend/runs/worker.py:45` still lists eight.

That list gates `_emit_routing`, which returns early for any node not in it — so
the step emits **no `routing` and no `node_start`**. `_drain` is not gated the
same way, so `node_done` still arrives. The UI therefore shows a node
*finishing* that never started, and the activity log prints its raw id.

```python
AGENTS = [..., "matching", "cv_link", "document", ...]   # one line
```

This is the exact `profile_enrich` miss that #28 fixed on 2026-08-31, in the same
table, nine weeks later. The frontend half (two label-map entries plus a renderer
for the artifact) is this folder's and is tracked in `frontend/bugs.md`; **the
missing events can only be fixed here.**

While there: `cv_link`'s `node_done` artifact is `{cv_tree, line_links}`, where
`cv_tree` is a recursively nested `CVNode` carrying both `text` and `raw_text`
per line. It is comfortably the largest thing the SSE stream now sends, and it
is persisted into every run log. Not asking for a change — flagging that if run
logs start looking enormous, this is why.

### 2. 🔴 `document` is real but still flagged `stub: true`

> **✅ Fixed 2026-10-08:** `STUB_NODES = {"verifier", "evaluation"}`. Both stub
> modules' docstrings now point back to the set.

`STUB_NODES` in `backend/runs/worker.py:77` is still
`{"document", "verifier", "evaluation"}`. `agents/document.py` is now a full
writer — plan → per-section packets → LLM edit sets → `_guard_edits` →
`apply_edits` → `render_markdown`.

So `node_done` carries `stub: true` for `document`, and the frontend stamps
**"placeholder output — this agent is not implemented yet"** on the genuine,
tailored CV, in both the live state panel and the final-output card.

```python
STUB_NODES = {"verifier", "evaluation"}
```

`verifier` and `evaluation` are confirmed still placeholders (hardcoded `PASS`
and an empty `EvalRecord`, both with `TODO` docstrings). `critic` is real and
already correctly excluded.

This matters more than a one-line table edit usually would: it is the same
failure mode that got the frontend's `stubs.js` heuristics deleted on
2026-09-24. The frontend now trusts this set completely and has, deliberately,
no way to second-guess it — which was the point of §9, and is why a stale entry
here is now worse than it was in August.

**§9's build note (2026-08-19) is stale** in two ways, for anyone reading it as
current: it says `STUB_NODES` covers "five agents" including `critic`, and that
"the frontend still uses its heuristics". Both were true then; neither is now.

### 3. 🟠 `GATES["gate3_fit"]["after"]` is one node behind

> **✅ Fixed 2026-10-08:** `"after": "cv_link"`, `artifact_node` stays `matching`.
> Until the frontend lists `cv_link`, the gate-3 "waiting" dot has no node to sit on.
> The frontend has listed it since 2026-10-09. Side effect: `GateScreen`'s
> final-gate check (`node !== artifact_node`) now also fires at gate 3. See the
> 2026-10-09 section below, "First".

`STAGE_GATE` in `agents/supervisor.py:51` is keyed on *the stage about to run*
("pause before entering this stage"), and `gate3_fit` is keyed on
`Stage.DOCUMENT`. With `cv_link` now sitting between `matching` and `document`,
gate 3 opens **after `cv_link`**, while `worker.GATES` still says
`"after": "matching"`.

Contained, and the review screen is unaffected: it renders `artifact_node`,
which is still `matching` — still the right artifact to approve. The only
visible effect is the pulsing "waiting" dot sitting on Matching while the run is
parked a node later. Worth correcting next time that table is touched; not worth
a commit on its own.

### 4. 🟠 There is no way to supply a CV

`backend/runs/worker.py:212-219` passes `cv_path=str(config.CV_DEFAULT_PATH)`
with an explicit comment that it is "never taken from the request", and
`RunRequest` still accepts only `{job_description, mode, pace_seconds}`. So
every run started from a browser tailors `knowledge_base/input/CV_test.pdf`.

Runs are **not** broken — that file exists, and both `cv_link` and `document`
raise without it, so the default is doing real work. But the product has changed
shape: the pipeline now edits an existing CV rather than writing one, and
"Start run" silently means "tailor the server's sample CV". No frontend change
can fix that; it needs an upload route (or `cv_path` accepted on the request,
sanitised — it becomes a filesystem path) before there is anything for a file
picker to talk to.

Flagging rather than specifying: the shape of that endpoint is a backend call,
and whether this is even in scope yet is the user's.

### 5. 🟡 Two small fields the frontend cannot synthesise

Both were raised in `frontend/bugs.md` Round 5 and are blocked here:

- **An errored run is indistinguishable from a cancelled one.**
  `registry.list_for` returns only `completed: any(type == "run_done")`, so the
  Runs list and the Account page render a crashed run and a superseded run
  identically ("stopped", in red). An `error: bool` or
  `outcome: "done" | "stopped" | "error"` on the summary would fix both screens;
  the events are already on disk to derive it from.
- **A reopened gate carries no round number.** `decide()` compares
  `latest.revision` against `state.revision_count` to decide a gate must reopen,
  so the number exists in state — it is simply not on the `gate_wait` event.
  One keyword on that emit lets the gate screen say "reviewing the revised
  version" instead of silently showing the same question twice.

### Still open from the 2026-08-31 sections, unchanged

- The `StubGraph` rewrite in `tests/test_backend_api.py`. It cannot exercise
  interrupt/resume, and now also knows nothing about `cv_link` — so the two
  stale-list bugs above are exactly the class of thing it would never catch.
- Nothing in either 2026-08-31 section has been run. That remains true.

---

## 2026-10-09 — what frontend Rounds 8–10 need from the backend

Written from `frontend/` after building three things (full write-ups in
`frontend/bugs.md` → Rounds 8, 9, 10):
- **Round 8:** the gate-2 answer form. The browser now actually sends
  `gap_answers`.
- **Round 9:** `cv_link` shown as "CV Reader", with a renderer for its artifact.
- **Round 10:** a single in-flight guard on the Start button.

None of the three has been built or run in a browser yet. Everything below was
checked against the backend source on 2026-10-09, not taken from earlier notes.
Items are ordered by severity; each says what the frontend changes once it lands.

### First: 2026-10-08 items 1–3 are confirmed fixed in code

- `AGENTS` includes `cv_link` (`backend/runs/worker.py:51`), so CV Reader gets
  its `routing` and `node_start`.
- `STUB_NODES = {"verifier", "evaluation"}` (`:81`), so the tailored CV is no
  longer labelled a placeholder.
- `GATES["gate3_fit"]["after"] == "cv_link"` (`:69`), so the waiting dot sits on
  CV Reader, which the frontend now draws.

The frontend's own docs still described all three as open. That has been
corrected in `frontend/bugs.md` → Round 9.

**One consequence lands on the frontend, not here.** `GateScreen` decided "this
is the final gate, show the fact check too" from `node !== artifact_node`. That
was true only of gate 4 until gate 3 moved. Gate 3 is now `cv_link` vs
`matching`, so the fit review shows an empty "Fact check · output of CV Reader"
block. That is a one-line frontend fix, tracked in `frontend/bugs.md`. Item 4
below is what would let the frontend stop inferring this altogether.

### 1. 🟠 `gap_answers` is accepted unbounded, at any gate, and kept on reject

> **✅ Fixed 2026-10-10, all three holes plus the "better" version of (b).**
> `routes/runs.py`: `gap_answers: dict[GapKey, GapText] = Field(default_factory=dict, max_length=20)`
> with `GapKey`/`GapText` exactly as specced (`StringConstraints`, key
> 1–200 chars, value ≤2000 chars, ≤20 keys). `worker.py`'s `_wait_for_gate`
> now keeps `gap_questions` on the parked `run["gate"]` itself (not only in
> the emitted event), so `answer_gate` can validate against what *this* gate
> actually asked rather than trusting the client: non-empty `gap_answers`
> at any gate but `gate2_evidence` is 422, and any key not among the open
> gate's own `requirement` strings is 422 (`Unknown gap_answers key(s)`) —
> the key-drift protection the "better" option called out, closing the
> `profile.enrich()` "QUESTION: No question found" near-duplicate it was
> flagged for. `gate_answer["gap_answers"]` is now `{}` whenever
> `decision == "reject"`, server-side, not only in the one client that
> happened to send `{}` already. `gate_done`'s existing echo of
> `gap_answers` is untouched, per the "keep, please" note. Checked by
> `py_compile`, an import-only load, a direct pydantic check (21 keys →
> `too_long`, a 2001-char value → `string_too_long`, an empty key →
> `string_too_short` — the exact error types this entry predicted), and an
> in-process call of `answer_gate` against fake run records: wrong-gate →
> 422, unknown key → 422, a known key → accepted and stored, a reject with
> a valid key → accepted but stored as `{}`, plus a regression check that
> the double-answer 409 from item 1 of the "gate 4" section still holds.
> **Not run**: pytest, uvicorn, or a real `enrich()` call.

Until now no client ever filled this field, so none of this was reachable from
a browser. As of Round 8 it is. There are three holes, all fixable at the
boundary in `backend/routes/runs.py`.

**(a) No size limit.** `gap_answers: dict[str, str] = {}` (`runs.py:56`) takes
any number of keys of any length. The values reach:
- the `profile_enrich` prompt;
- a state snapshot;
- `manual_entries.json`;
- the `profile` Chroma collection.

That is #37's reasoning exactly, and `job_description` already got a cap for it.
The frontend's `maxLength={2000}` per box is a courtesy, not enforcement. The
following was tested against the installed pydantic 2.13.4: 21 keys, a
2001-character value and an empty key each return 422 (`too_long`,
`string_too_long`, `string_too_short`).

```python
from typing import Annotated
from pydantic import StringConstraints

GapKey = Annotated[str, StringConstraints(min_length=1, max_length=200)]
GapText = Annotated[str, StringConstraints(max_length=2000)]

class GateAnswer(BaseModel):
    ...
    gap_answers: dict[GapKey, GapText] = Field(default_factory=dict, max_length=20)
```

**(b) Accepted at any gate.** `human_gate()` stores `gap_answers` whatever gate
is open (`utils/human_gate.py:91-92`), and `answer_gate` does not check which
gate that is. The frontend only sends answers when the open gate carried
questions, which is gate 2 only. Nothing server-side holds that line.
- Minimum fix: 422 when `answer.gap_answers` is non-empty and
  `run["gate"]["gate"] != "gate2_evidence"`.
- Better: keep the questions on the parked run, in `_wait_for_gate`:
  `run["gate"]["gap_questions"] = payload.get("gap_questions") or []`. Then 422
  any key that isn't one of the open gate's `requirement` strings.
- The better version also catches key drift. `enrich()` matches by exact string
  (`agents/profile.py:105`). A mismatched key sends the model
  `QUESTION: No question found` and saves a near-duplicate `gap_answer:{key}`
  block (`profile.py:129`).

**(c) Kept on reject.** The graph stores answers whatever the decision. A
rejected round's answers therefore stay in state through the loop-back, and
`enrich()` saves them after the next approve, even if nothing was typed the
second time. The frontend sends `{}` on reject for this reason
(`PipelineView.answerGate`), but that rule should not live only in one client:
`curl`, the smoke script or a future client can still send them. One line in
`answer_gate`:

```python
"gap_answers": {} if answer.decision == "reject" else answer.gap_answers,
```

The deeper fix, `human_gate()` dropping them on reject, is in `utils/`, the
Agents lane. The route-level line is worth having regardless.

**Keep, please:** `gate_done` echoes `gap_answers` (`worker.py:195`). `RunLog`
counts its keys to print "you approved · answered 2 questions", for live runs
and for past runs opened from Runs. If the echo is ever slimmed (for example
under the same privacy rule as `pasted_text`), keep the keys, or send
`gap_answers_count`.

**Checks:**
- 21 answers → 422;
- a 2001-character answer → 422;
- non-empty answers at gate 1 → 422;
- a reject with answers → `gate_done.gap_answers == {}`, and after the re-opened
  gate 2 is approved empty, `enrich()` saves nothing.

### 2. 🟠 Demo mode saves a made-up answer into the real profile (not `backend/`, but the UI now has to warn about it)

`learning/profile_store.save_gap_answers` (`:37`) has no offline check. In demo
mode, `enrich()`'s stand-in model returns one fixed answer, "Wrote SQL queries
for business reporting.", whatever was typed (`agents/profile.py:38-43`). That
answer is then:
- appended to `manual_entries.json`;
- embedded into the **real** `profile` collection;
- findable as evidence by later live runs.

Round 8 makes this reachable from a browser for the first time, so `GateScreen`
now shows an amber stopgap (`GAP_DEMO_NOTE`): "demo mode doesn't read what you
type — one fixed example answer is saved to your profile in its place".

- **Owner:** Data Storage / Agents, not this folder. Recorded here because it is
  something the frontend needs.
- **Fix:** skip the save when `config.fake_llm_active()`. The ContextVar is per
  run (§2's 2026-08-19 decision), so the check is exact even with a live run in
  flight beside it.
- **Frontend change once landed:** the note becomes "demo mode — answers are not
  saved", or goes away.
- **Until then:** there is no delete route and no vector delete (#30), so a
  demo-mode test entry can only be removed by hand from the JSON plus an index
  rebuild.

### 3. 🟠 Put the gate's name on the wire: `gate` on `gate_wait` / `gate_done`, checked on answer

The worker knows which gate is open (`run["gate"]["gate"]`, `worker.py:170`) but
never sends it. The frontend identifies a gate by `node` and `title`. That broke
once already today and is about to stop being enough:

1. **Inferring the final gate from a node mismatch broke** when gate 3 moved
   (see "First" above). The frontend will fix its check locally. An explicit
   name is the contract that would not have broken.
2. **A stale screen can answer the wrong gate.** Answers posted from a second
   tab, or a slow POST that arrives after the run moved on, land on whatever
   gate is open. Under 1(b), any gate stores them. With the name echoed back,
   the route can refuse a mismatch.
3. **Stage 0's intake gate opens at the same position as gate 2** (after
   `profile`), so the title string would be the only way to tell them apart
   (`frontend/bugs.md` → Round 7, item 4).

```python
# worker._wait_for_gate
emit(run, "gate_wait", gate=gate_name, node=gate["after"], title=..., ...)
emit(run, "gate_done", gate=gate_name, node=gate["after"], decision=..., ...)

# routes/runs.py
class GateAnswer(BaseModel):
    gate: str | None = None      # optional, so old clients keep working
    ...

# answer_gate, after the "no gate is waiting" check
if answer.gate and answer.gate != run["gate"]["gate"]:
    raise HTTPException(409, "That checkpoint is no longer open")
```

It must be **409**, not 401 or 403. A 401 would log the user out (status-code
discipline, §5).

**Frontend change once landed:** store `ev.gate` in `applyEvent` and send it
back from `answerGate`. Key the final-gate check on
`gate === "gate4_document"`. Show the 409 inline as "this checkpoint has moved
on". Old logs without `gate` keep replaying through the existing fallbacks.

### 4. 🟠 Two starts from one owner can spend two runs and leave two live runs

> **✅ Fixed 2026-10-10.** `registry.py` gained `owner_lock(owner)` (one
> `threading.Lock` per owner, created on first use) and `seen`/`remember`
> (an `(owner, client_request_id) -> run_id` map, 10-minute TTL). `RunRequest`
> gained optional `client_request_id`. `start_run` (`routes/runs.py`) now does
> the dedup lookup, `consume_run`, `registry.start` and `remember` all inside
> one `with registry.owner_lock(owner):` block, in that order — fixing both
> (a) and (b): a duplicate request (same owner + id) is handed back the
> existing `run_id` before anything is charged, and two genuinely different
> starts from one owner can no longer both pass the "no active run" check at
> once, because the whole sequence (including `registry.start`'s abort+join
> of the previous run) now runs under one lock per owner. Other owners are
> never blocked by it. Checked by `py_compile`, an import-only load, and a
> scratch concurrency test (10 threads, same owner + same
> `client_request_id` → exactly 1 charge and one agreed `run_id`; 10 threads,
> same owner + distinct ids → 10 independent charges) exercising the new
> `owner_lock`/`seen`/`remember` primitives directly. **Not run**: pytest,
> uvicorn, or a test through the real `registry.start`/worker path.

Round 10 stopped a double-click from sending two `POST /runs`. It cannot stop
two tabs, a script, or a request retried after a network timeout. Two separate
problems sit behind that.

**(a) No idempotency.** `start_run` calls `consume_run` (`runs.py:66`) before
anything could recognise a duplicate, so every POST costs a run. A fresh user
has two.

**(b) `registry.start` is not atomic per owner. This one is a real bug, not a
UX nicety.**
1. It reads `_active[owner]` under `_LOCK`, then releases the lock.
2. It aborts and joins the previous run outside the lock.
3. It takes the lock again to create the new run and write `_active[owner]`
   (`registry.py:95-120`).

Two concurrent starts from one owner can both read the same `previous`, and both
create a run. The second then overwrites `_active[owner]`, so:
- the first new run is never aborted: nothing points at it any more;
- it runs to its first gate and parks there, holding a worker thread and a
  SQLite connection, and in live mode it spends provider quota on the way;
- the owner has two live runs, which is the invariant per-owner slots exist to
  prevent.

The 2026-08-19 "Known gaps" list already noted there is no test for two runs by
the same owner.

One per-owner lock fixes (b) and makes (a) cheap:

```python
class RunRequest(BaseModel):
    ...
    client_request_id: str | None = Field(None, min_length=8, max_length=64)

# registry: one lock per owner, plus recently-seen request ids
# (owner, client_request_id) -> run_id, kept ~10 minutes

@router.post("")
def start_run(req: RunRequest, identity: Identity):
    ...live-key check...
    owner = identity["token_id"]
    with registry.owner_lock(owner):          # serialises THIS owner's starts only
        if req.client_request_id:
            seen = registry.seen(owner, req.client_request_id)
            if seen:
                return {"run_id": seen}       # a duplicate: same run, nothing consumed
        if identity["role"] != "admin" and not store.consume_run(owner):
            raise HTTPException(403, "No runs remaining")
        try:
            run = registry.start(req.job_description, req.mode, req.pace_seconds, identity)
        except Exception:
            store.refund_run(owner)
            raise
        registry.remember(owner, req.client_request_id, run["id"])
    return {"run_id": run["id"]}
```

- **Order matters.** The duplicate lookup must come before `consume_run`, and
  lookup → consume → start → remember must all happen under one lock. Otherwise
  two duplicates both pass the lookup before either is remembered.
- **The lock is held across `registry.start`'s join of the previous run (up to
  15 s).** That only delays the same owner's other starts, which is the point.
  Other owners are unaffected.
- **A duplicate gets 200 with the original `run_id`, not 409.** A request
  retried after a network blip should get its run back, not an error.
- **Admin is never charged,** but still needs (b): two concurrent admin starts
  leave two live runs just the same.

**Frontend change once landed:** generate `crypto.randomUUID()` once per Start
attempt and send it as `client_request_id`. `RunRequest` uses pydantic's default
`extra="ignore"` (verified: an unknown key is silently dropped), so sending it
early breaks nothing, but it protects nothing either until this lands.

**Checks:**
- two concurrent POSTs with the same id → one run, one charge, the same
  `run_id` twice;
- two concurrent POSTs with different ids from one owner → two charges, and
  exactly one live run afterwards, the other `run_stopped`;
- no orphan thread is left parked at a gate.

### 5. 🟡 The whole parsed CV rides every `cv_link` event and run log (becomes 🟠 once uploads exist)

What the CV Reader card and drawer actually read:
- `cv_tree.source_file`;
- `cv_tree.root.children[].{node_id, title}`, the CV's own section headings;
- `line_links[].{node_id, kind, section_type, text, status, source_ids}`.

`score` is unused.

What is sent instead: the full recursive `CVNode` tree, with every node carrying
both `text` and `raw_text`, including the header section (name, email, phone).
It is persisted in `logs/frontend_runs/{id}.json` and replayed on every SSE
connect, and the frontend keeps every event for the session.

`frontend/design.md`'s 2026-10-09 addendum sets the rule "CV text never goes
into SSE events, run logs or URLs". The current artifact breaks that rule
already. It is harmless only because every run uses the shared sample CV.

**Proposed:** in the event, replace `cv_tree` with a summary, and keep the full
tree in the checkpoint, which is where `document` reads it from:

```python
"cv": {"source_file": tree.source_file,
       "sections": [{"node_id": s.node_id, "title": s.title, "section_type": s.section_type}
                    for s in tree.root.children]}
```

That is either a filter in `_drain` for `node == "cv_link"`, or a change to what
`CV_Link.node` returns (the Agents lane). **Tell the frontend when it lands:**
its renderer reads `a.cv_tree.source_file` and `a.cv_tree.root.children`, so it
needs a two-line change, and old logs would keep the old shape.

**A decision that isn't the frontend's to make.** `line_links` carry each line's
text, and so must `document`'s artifact, because the tailored CV *is* CV text.
So the addendum's rule cannot hold literally for events. Recommendation:
- **for now:** apply the rule to the raw upload and the header section only, and
  let per-line text stay in owner-checked events and logs;
- **before real uploads ship:** decide whether the per-line list moves behind an
  owner-checked `GET /api/runs/{id}/cv-links`, with only counts in the event.
  The drawer would then fetch it on open.

**Also, if `contradicted` becomes a `MatchStatus`** (the comment at
`state/state.py:330` anticipates it), say so. The card counts only
`matched` / `partial` / `unmatched`, so a new status would silently drop out of
the totals. The drawer would show it, under its raw name.

### 6. 🟡 A `cv_link` re-run sends `{stage}` as if it were a result

> **✅ Built 2026-10-22** exactly as asked: `node_done` with `unchanged: true`
> and no `artifact`, applied to any node whose update is nothing but `stage`.
> See `"2026-10-22 (a node that changed nothing)"` below.

After a rejected fit review:
1. Matching re-runs.
2. `cv_link` runs again, sees the same CV already read
   (`agents/CV_Link.py:37-38`), and returns only `{"stage": Stage.DOCUMENT}`.
3. `_drain` emits that as the artifact (`worker.py:154`).

The frontend now special-cases `cv_link` in `applyEvent` to keep the earlier
read rather than blank the card.

**Ask:** make "no change" explicit rather than an artifact that looks like an
empty result. When `fields` holds nothing but `stage`, emit `node_done` with
`unchanged: true` and no artifact.
- It must still be a `node_done`. `node_start` is now emitted for `cv_link`, so
  skipping the done would leave CV Reader "working" forever.
- The frontend would then use one generic rule (keep the previous artifact when
  there is one) instead of a `cv_link` special case.
- `profile_enrich`'s no-answers return is the same `{stage}` shape. The frontend
  would keep rendering "nothing added" for it, since there is no previous
  artifact to keep.

### 7. 🟡 Two fields already asked for, now more visible

Both are in the 2026-10-08 section, item 5, unchanged. Repeated here only
because Round 8 made one of them more visible:

- **A round number on `gate_wait`.** A rejected gate 2 now reopens with an
  **empty form**, possibly with different questions, because Profile re-ran.
  With no round number the user gets no explanation. The frontend resets the
  form on `ts`; it needs `revision` (`state.revision_count`) to say "revised
  version — new questions". This can share an emit with item 3's `gate` field.
- **`outcome` on the run summary**, so a crashed run stops reading identically
  to a superseded one. Unchanged.

### 8. Not needed from the backend (recorded so nobody builds it)

- **The free "add or correct anything" box** (DELIVERABLES §18) was deliberately
  not built. `GateAnswer` has no `free_text`, and FastAPI drops unknown keys, so
  a box today would silently lose what was typed. §17 already plans the field.
  When it lands, apply the same three rules as item 1: a cap, gate 2 only, and
  dropped on reject. Tell the frontend; the form is one textarea and one key.
- **The Start guard needs nothing from here to work.** Item 4 is about the cases
  a button cannot cover.

### What to run (yours)

```
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m uvicorn scripts.frontend_api:app --port 8000
.venv/bin/python scripts/smoke_backend.py
```

- **Items 1, 3 and 4** each have a check list above. New tests go into
  `tests/test_backend_api.py`, which still needs its `StubGraph` rewrite before
  any of it can run.
- **Items 2 and 5** are outside `backend/` code, apart from the optional `_drain`
  filter in item 5.
- **From the frontend side, once built:** a demo run that answers one gate-2
  question should show "answered 1 question" in the activity log and a filled
  "Answers added to your profile" card. The fit review should show **no** "Fact
  check" block once the frontend's gate-3 fix is in.


---

## 2026-10-10 — items 1–3 built (the upload routes, storage, run resolution)

> **✅ Built, verified in-process (TestClient + a real PDF), not run via uvicorn/pytest.**

`backend/cv_store.py` (new) + `backend/routes/cv.py` (new): `GET/POST /api/profile/cv`,
`POST /api/profile/cv/{id}/confirm`, `DELETE /api/profile/cv/{id}`, exactly as specced
below — 413/415/422 `no_text|no_sections|too_many_pages`, 403 never 401, `GET` answers
`{"cv": null}` never 404. Storage is `uploads/{owner}/cv/{sha256[:12]}.pdf` + one
`index.json` per owner, through `backend.jsonstore.update_json`.

`backend/routes/runs.py` `POST /runs` now resolves the caller's current CV before
`consume_run`: 409 `"Add your CV to start a run."` for a non-admin with none, sample-CV
fallback for admin only (design.md D-CV2), response carries `cv`/`sample`. A run keeps
its resolved `cv_path` (`backend/runs/registry.py` `start()` gains `cv_path`/`cv_info`/
`sample_cv` params; `worker.py` reads `run["cv_path"]` instead of
`config.CV_DEFAULT_PATH`, and emits a new `run_started` event carrying `{cv, sample}` —
never CV text). `list_for` summaries now carry `cv`/`sample_cv` too.

Also: `config.CV_UPLOADS_DIR`, `.gitignore` entry, `python-multipart` added to
`requirements.txt` (was installed, undeclared).

**Verified against a real PDF** (`knowledge_base/input/CV_test.pdf`) via `TestClient`,
redirecting `config.CV_UPLOADS_DIR`/`KB_AUTH_DIR`/`RUNS_DIR` to a tmp dir: upload →
preview (7 sections, 0 warnings) → confirm → `GET` returns it → a run resolves its real
path, not the sample → bad-PDF upload 415 → unknown `cv_id` confirm/delete 403 → delete →
`GET` back to null. Two-owner isolation checked: a second token's CV lives under its own
`uploads/{token}/cv/`, and neither can touch the other's `cv_id` (403, never a leak of
which error it is). Not run: uvicorn, pytest's own fixtures, a browser.

**⚠️ Flips 10 tests in `tests/test_backend_api.py` from pass to `KeyError: 'run_id'`.**
Confirmed by stubbing `cv_store.resolve_path` to always succeed: with CV resolution
neutralized, the full suite (22 tests) passes clean — so the `StubGraph`/checkpointer
mismatch §6 above describes is **no longer the suite's blocker** (something since
2026-10-06 already fixed it; that section is stale). The 409 is the sole new cause: every
`issue_token(client, name)` identity in these tests has no uploaded CV, and a plain user
now correctly can't start a run without one (D-CV2 is doing its job). Not fixed here —
tests are the user's per the working split. The fix is small: give each test identity a
confirmed CV (`POST /profile/cv` + `.../confirm`, same shape as the verification script
above) before it starts a run, or route the ownership-only tests through `ADMIN` where
the CV doesn't matter.

**Not done in this pass** (items 4 and 5 below, next most critical): stripping CV text
out of the `cv_link` SSE/run-log artifact, and exposing the unmatched-line count for
gate 4.

---

## 2026-10-09 (later) — what the backend must build for a user-supplied CV. **Not built.**

Scoping only. This edits this file and nothing else. It is the backend half of
`frontend/bugs.md` → Round 11, and it follows `frontend/design.md`'s "Your CV"
addendum. It closes **2026-10-08 item 4** ("there is no way to supply a CV") as a
decision: **an upload route is the direction**, not a `cv_path` field on the request.

Re-checked in source today, not taken from earlier notes:
- `RunRequest` still has `{job_description, mode, pace_seconds}`, and the worker
  still passes `config.CV_DEFAULT_PATH` (the sample `knowledge_base/input/CV_test.pdf`)
  as `cv_path`.
- `backend/routes/` has `auth, kb, profile, runs, system`. There is no CV route.
- `requirements.txt` has no `python-multipart`, and `frontend/nginx.conf` sets no
  `client_max_body_size` on `location /api/`.
- `agents/CV_Link.node` reads `state.cv_path` and skips re-linking when
  `state.cv_tree.source_file == pdf.name`.
- `utils/cv_handling/cv_extract.parse_cv(pdf)` returns `(CVTree, lines)`. It raises
  nothing for a scanned PDF or a PDF with no sections: it just returns a thin tree.
  The route has to detect both itself.

Items 1, 3 and 4 of the section above this one (gap answers, the `gate` field,
idempotent starts) were not re-verified here.

### 1. 🔴 The upload routes (nothing exists)

> **✅ Built 2026-10-10** (see the dated section above): `backend/routes/cv.py`, all four routes.

Every route is guarded by `require_auth` and scoped to the caller. **No route ever
takes a path from the client.**

| Route | Request | Response |
|---|---|---|
| `POST /api/profile/cv` | `multipart/form-data`, one field `file` | `201 {cv: CvSummary, preview: CvPreview}`, stored as **pending** |
| `POST /api/profile/cv/{cv_id}/confirm` | none | `200 {cv: CvSummary}`, makes it the current CV |
| `DELETE /api/profile/cv/{cv_id}` | none | `204` |
| `GET /api/profile/cv` | none | `{cv: CvSummary \| null}`, the current CV |

- `CvSummary = {id, filename, size_bytes, pages, uploaded_at}`
- `CvPreview = {sections: [{type, title, entries: [{header, lines: [str]}]}], warnings: [str]}`,
  built from the `CVTree` that `parse_cv` returns.
- **Status codes** (the frontend shows specific text for each):

| Status | When |
|---|---|
| 413 | over 5 MB, enforced while reading |
| 415 | fails the `%PDF-` magic-byte check, whatever the extension says |
| 422 `no_text` | the PDF has no text layer (scanned or image-only) |
| 422 `no_sections` | text was read but the tree holds only the header section |
| 422 `too_many_pages` | more than 4 pages |
| 403 | the CV exists but is not the caller's. **Never 401** (§5 above): a 401 logs the user out |

- **Read in chunks** and stop at the cap. Never load the whole body and then check.
- **Parse on a worker thread**, not the event loop. `parse_cv` has no model load, so
  it should take about a second, but it is CPU work. Check that importing
  `utils.cv_handling.cv_extract` does not pull in torch (`agents/profile.py` did once
  and cost 25 s of boot).
- **Preview warnings** come from the parse: sections not found ("No Skills section
  found") and `line_problems(tree, lines)` ("3 lines could not be placed").
- **Pending vs current.** An upload is pending until confirmed. Replacing keeps the
  old CV current until the new one is confirmed. A pending upload that is never
  confirmed is removed.

### 2. 🔴 Storage, ownership and what a run keeps

> **✅ Built 2026-10-10:** `backend/cv_store.py`. Not done: the "CV no run references" check on delete (deletes unconditionally today, after clearing `current_id` if it was current).

- **File name.** `uploads/{owner}/cv/{sha256[:12]}.pdf`, a server-chosen name, never the
  uploaded one. The original name is display metadata only.
  - This is what keeps `CV_Link`'s skip-if-same-CV check correct (it keys on
    `source_file == pdf.name`): a different upload is a different name. It would break
    if files were stored under the user's own filename.
  - The folder is git-ignored and sits on the persisted volume.
- **`owner`** is `token_id` today. It becomes `profile_id` when Stage 0 §13.1 lands.
  Known caveat until then: a re-issued token cannot see its old CV.
- **The index** (which CV is current, which are pending, their summaries) is one small
  JSON per owner, written through `backend/jsonstore.update_json` so the confirm and
  delete paths are serialised the way `manual_entries.json` is.
- **A run keeps its CV.** The worker passes the resolved, server-side path as
  `cv_path`, replacing `config.CV_DEFAULT_PATH` at `worker.py` (the `cv_path=` line near
  the `GraphState(...)` call). A run in progress is unaffected by a later replace.
- **A CV a run log references is not deleted** while that log exists. Deleting the
  current CV only clears the pointer.
- **Delete** (`DELETE`) removes pending uploads and CVs no run references. It must
  check ownership first and return 403, not 404.

### 3. 🔴 `POST /api/runs` resolves the CV, and refuses before charging

> **✅ Built 2026-10-10:** `backend/routes/runs.py`, in the order specced below. Flips 10 tests — see the dated section above.

- No new field on `RunRequest`. The server looks up the caller's **current** CV.
- **`409` if there is none, checked before `consume_run`**, so no allowance is spent.
  Order: live-key check, resolve CV (409), then `consume_run`, then `registry.start`.
- **The run record and the `run_started` event carry `cv: {id, filename}`.** That is
  also what the run log and `list_for` need, so Runs and Run log can show the file name
  for an old run after the CV is replaced.
- **Admin** is never charged but still needs a current CV like anyone else.
- **Until uploads ship,** keep the sample CV as a fallback only if the product decision
  (design.md D-CV2) allows it, and then the run record must say `sample: true` so the
  UI can label it "sample CV (not yours)". If the decision is no fallback, the 409 is
  unconditional.

### 4. 🟠 Privacy: CV text must not leak through events or logs

> **✅ Partly fixed 2026-10-10** (the "at minimum" bullet below; the per-line
> decision is still open). `backend/runs/worker.py` gained `_scrub_cv_tree`,
> applied in `_drain` to the `cv_link` artifact right after `_jsonable`
> converts it: it drops the header section (`section_type == "header"`:
> name, email, phone) outright and blanks `raw_text` on every remaining
> node. It is a pure subtraction, not a wire-shape change — the frontend's
> own documented reads of this artifact (`node_id`/`title` off
> `cv_tree.root.children`, `text` off the separate `line_links`, never
> `cv_tree`'s own `text`/`raw_text`) are all untouched, so nothing already
> rendered breaks. The upload routes (`backend/routes/cv.py`,
> `backend/cv_store.py`) were checked and already don't log or emit CV text
> or the `CvPreview` anywhere — that part of this item needed no change. The
> "`gate_done` must not echo CV text" bullet was also already true (`gate_done`
> only ever carries `decision`/`feedback`/`gap_answers`/`edited`). **Left
> open, by design:** per-line text in `line_links` and in `document`'s own
> artifact — the "decision for the user" this item itself defers (an
> owner-checked `GET /api/runs/{id}/cv-links` route, or keep it on the
> owner-checked stream as today). Checked by `py_compile`, an import-only
> load, and a scratch test building a real `CVTree`/`CVNode` with a header
> section holding a name/email/phone and a skills section: the scrubbed
> output has no trace of any of the three, the header section is gone from
> `root.children`, and `node_id`/`title`/non-header `text` all survive
> unchanged. **Not run**: pytest, uvicorn, or a real upload through the live
> pipeline.

`frontend/design.md` sets the rule "CV text never goes into SSE events, run logs or
URLs." The `cv_link` artifact already breaks it (see item 5 of the section above): it
sends the whole `CVNode` tree with `text` and `raw_text` per line, including the header
section (name, email, phone), and it is persisted in `logs/frontend_runs/{id}.json`.
That is harmless only while every run uses the shared sample CV.

- **Before real uploads ship,** at minimum drop the header section and `raw_text` from
  what the event and the run log carry. The earlier proposal (a section summary in the
  event, the full tree left in the checkpoint) still stands.
- **The upload routes themselves** must not log the file's text, and `CvPreview` goes only
  to the owner in the response, not into any event.
- **`gate_done` must not echo CV text**, same rule as `pasted_text`.
- **Decision for the user, not the frontend:** per-line text has to stay somewhere the
  Document step and the review screen can read it. Recommended: owner-checked
  `GET /api/runs/{id}/cv-links`, with only counts in the event. The frontend drawer would
  fetch it on open.

### 5. 🟠 Expose the unmatched count so the UI can warn at gate 4

A new user with an empty profile gets every CV line back unmatched, so Document has no
evidence to edit with and the CV returns mostly unchanged. The frontend wants to say so
rather than look broken.
- Put `{matched, partial, unmatched}` counts on the `cv_link` `node_done` event (or on
  `run_done`). The counts are derivable from `line_links` already in state.
- If `contradicted` ever becomes a `MatchStatus` (a comment in `state/state.py`
  anticipates it), tell the frontend: its totals count only the three current statuses.

### 6. 🟡 Dependencies and proxy (small, but each one fails the feature)

- Add **`python-multipart`** to `requirements.txt`. It is installed in `.venv` only, and
  FastAPI file uploads need it.
- Set **`client_max_body_size 6m;`** on `location /api/` in `frontend/nginx.conf`.
  nginx's default is 1 MB, so a 1–5 MB PDF would fail at the proxy with nginx's HTML
  error page, not the API's JSON, and the UI could not show the right message.
- Add the upload directory to `.gitignore`, and to `DATA_DIR` handling when Stage 0 §15
  lands.

### 7. Out of lane, but blocks the feature being meaningful

- **`cv_link` links against the shared synthetic `profile` collection**
  (`agents/CV_Link.py`, `Matcher(*_get_parts())`). A real user's CV would link to
  synthetic records until profile-scoped linking lands (Stage 0 §13.3/§13.5, KB+RAG
  lane).
- **An empty profile** (item 5) stays until the intake gate (Stage 0 §4) fills it.
- **Match quality** was not re-measured here. The 09-29 run showed most bullets
  `unmatched` because bullet text was not in the indexed records; whether that was fixed
  in the `utils/cv_handling` rewrite is unverified.

### What to run (yours), once built

```
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m uvicorn scripts.frontend_api:app --port 8000
.venv/bin/python scripts/smoke_backend.py
```

New tests go into the existing `tests/test_backend_api.py` (no new test files), which
still needs its `StubGraph` rewrite before the run-related ones can work. Checks:
- upload a valid PDF, then confirm, then `GET` returns it as current;
- a non-PDF renamed `.pdf` → 415; a 6 MB file → 413 (also through nginx, not just
  uvicorn); a 5-page PDF → 422 `too_many_pages`; a scanned PDF → 422 `no_text`;
- user B cannot read, confirm or delete user A's CV (403, never 401);
- `POST /runs` with no current CV → 409 and `runs_remaining` unchanged;
- a run keeps its CV after the owner replaces it mid-run;
- no CV text in any SSE event or run log for a run started from an upload.

## Verification status: **not run, nothing built**

Only this file changed. Facts come from reading `backend/routes/runs.py`,
`backend/runs/worker.py`, `backend/runs/registry.py`, `agents/CV_Link.py`,
`utils/cv_handling/cv_extract.py`, `config.py`, `requirements.txt`,
`frontend/nginx.conf` and `frontend/design.md`. No server, no pytest, no request.

### Addendum, same day: the frontend half is written (`frontend/bugs.md` → Round 12)

The frontend now calls the four routes above exactly as specified. Five points
pin down details this section left open. Each one changes frontend behaviour if
it isn't held:

1. **"No CV" must be `200 {cv: null}`, never a 404.** The frontend reads a 404
   (or 405) on `GET /api/profile/cv` as "this backend has no CV routes". In that
   state it unblocks Start and labels every run "sample CV (not yours)". That is
   how it works against today's backend. A 404 for "no CV yet" would wrongly
   unblock a user who has none.
2. **The 422 code goes in `detail`.** The frontend matches `no_text`,
   `no_sections` or `too_many_pages` anywhere in the detail, so either
   `{"detail": "no_text"}` or `{"detail": {"code": "no_text", ...}}` works. Any
   other 422 detail is shown to the user as sent.
3. **Which CV a run used** is read from `run_started.cv`, or from an optional
   `cv` on the `POST /runs` reply, which is the cheapest place to add it. For
   §3's fallback case, it reads `sample: true` from either place. The Runs list
   reads `cv` on each `list_for` summary.
4. **Admin.** The frontend follows design.md D-CV2's recommendation: an admin
   with no CV can press Start, labelled "sample CV (not yours)". If the backend
   instead 409s admins too (§3 above), the frontend shows "Add your CV to start
   a run." and re-checks. Both are handled, but the two documents should agree,
   so this decision belongs to the user.
5. **Unconfirmed uploads.** The frontend sends `DELETE` for a pending upload on
   Cancel, when another file replaces it before confirming, and when the strip
   is unmounted (starting a run does that). These calls are fire-and-forget,
   and a closed tab sends nothing, so §1's "a pending upload that is never
   confirmed is removed" still needs a server-side sweep.

**§6's nginx item is done:** `frontend/nginx.conf` now sets
`client_max_body_size 6m;` on `location /api/`, since that file belongs to the
frontend. `python-multipart` in `requirements.txt` and the `.gitignore` entry
are still the backend's.

---

## 2026-10-09 (gate 4) — what the final review needs from the backend

Written by **Agents + Orchestration (Claude)** after wiring gate 4 end to end (work log:
`context/context.md` → 2026-10-09 "Gate 4 wired end to end"; open items:
`context/bugs_audit_fixed.md` #55). Part of that work landed **in this folder**, so this
section starts with what is already here, then what is still needed. Severity scale as above.

### First: what is already built in `backend/` (fixed in code, not run)

| Where | What |
|---|---|
| `worker._wait_for_gate` | `gate_wait` now carries **`gate`** (the gate's name) and **every extra key of the interrupt payload**: gate 2's `gap_questions`, gate 4's `changes`. Event keys can't be overwritten by a payload key (`_PAYLOAD_NOT_PASSED`). A new gate extra needs no edit here. |
| `worker._wait_for_gate` | `gate_done` carries **`edited: bool`**, never the edited text. It does **not** carry `gate` yet (item 3). |
| `worker._drain` | When the `gate` node writes `document` back (a gate-4 edit), that is relayed as a new event **`document_edited {artifact: {document}}`**. Not a `node_done`, because the Writer did not produce it. |
| `worker._close` + `run_worker` | `run_done` carries **`final`** = `utils/final_review.close_run(...)`, or `final: null` plus `final_error` if closing failed. A closing failure never turns into `run_error`. |
| `routes/runs.GateAnswer` | **`edited_content`**: at most 50,000 chars, accepted only with `edit` at `gate4_document`, else 422. Relayed as `edited_payload.content`. **`gate`**: optional; 409 if it isn't the open gate. This is the answer half of **item 3 of the 2026-10-09 section above**. |
| `routes/runs.download_document` | **`GET /api/runs/{id}/document?fmt=md\|txt`**: owner-checked (403); the path comes from the run's own `run_done.final.export`, never from the request, and must resolve inside `OUTPUTS_DIR` (else 404); 404 when nothing was saved. |

**How gate 4 routes now.** Routing is `agents/supervisor.decide()`, which is unchanged.
The gate node only records the answer and, for an edit, writes the text back.

```
verifier → supervisor → gate(gate4_document) ─ interrupt ─► gate_wait {gate, changes, ...}
                                                                │  POST /api/runs/{id}/gate
 approve ───────────────────────────────────────────────────────┼─► evaluation → END → run_done.final {approved, export}
 edit + edited_content ─► gate returns {document} ─► document_edited ─► evaluation → END → run_done.final {approved, edited, export}
 reject, revision < max_revisions ─► supervisor: redo `document` (+1 revision) → critic → verifier → gate_wait again (new ts, new changes)
 reject, revision ≥ max_revisions ─► decide() stops honouring it → evaluation → END → run_done.final {approved: false, export: null}
```

**The `run_done.final` contract**, which the frontend reads:

```
final = null                                   # closing failed: see final_error; or an old log
final = {
  "review":   null | {"decision": "approve|edit|reject", "approved": bool, "edited": bool,
                      "revision": int, "rounds": int},       # latest gate-4 answer; rounds = answers given
  "export":   null | {"md": "<owner>/<date>_<run>_<role>.md", "txt": "...txt"},   # relative to OUTPUTS_DIR
  "learning": {"feedback_rows": n, "corrections": n} | "skipped: <why>"         # live runs only
}
```

### 1. 🔴 Two answers can land on one open gate; at gate 4 the second silently wins

> **✅ Fixed 2026-10-10.** `registry.start` now gives every run its own
> `threading.Lock()`. `answer_gate` (`routes/runs.py`) holds it across the
> gate-existence check, the new "already answered" check, the gate-name and
> `edited_content` checks, and the write of `run["gate_answer"]`; it marks
> `run["gate"]["answered"] = True` before releasing the lock and only then
> calls `gate_event.set()`. A second POST to the same open gate now gets 409
> ("This review was already answered") instead of silently overwriting the
> first answer. No cleanup needed: `_wait_for_gate` builds a fresh `gate`
> dict per pause, so the flag resets by itself at the next gate. Checked by
> `py_compile` and an import-only load of both modules; **not run** — pytest,
> uvicorn and a concurrent-POST test are still the user's to do.

`answer_gate` checks `run["gate"]`, writes `run["gate_answer"]`, then sets the event. The
worker wakes, then clears `run["gate"]`, then reads `run["gate_answer"]`. A second POST
that arrives between the first POST's `set()` and the worker's read passes the "a gate is
open" check and **overwrites** the first answer. Both callers get 200.
- **At gate 4 this decides what the run delivers.** Approve in one tab and reject in
  another (or a slow retry), and the run follows whichever arrived second. The other
  caller is told it succeeded.
- `GateScreen` disables its buttons while sending, so one tab can't do it by itself. Two
  tabs, the smoke script or a retried request can.

**Fix: one lock per run, and mark the gate answered under it.**

```python
# registry.start: give each run its own lock
run["lock"] = threading.Lock()

# routes/runs.answer_gate
with run["lock"]:
    open_gate = run["gate"]
    if not open_gate:
        raise HTTPException(409, "No gate is waiting on this run")
    if open_gate.get("answered"):
        raise HTTPException(409, "This checkpoint was already answered")
    ...the existing gate-name and edited_content checks...
    run["gate_answer"] = {...}
    open_gate["answered"] = True
run["gate_event"].set()
```

- `_wait_for_gate` builds a fresh `run["gate"]` dict per pause, so `answered` resets by
  itself at the next gate. No cleanup is needed.
- **409, not 200, for a duplicate**, even an identical retry. The frontend treats 409 as
  "this checkpoint has moved on" (`frontend/bugs.md` → Round 13, item 3), which is true.
- **Never 401** (§5): a 401 logs the user out.

**Checks:** two concurrent POSTs to one open gate give one 200 and one 409, and
`gate_done.decision` is the 200's. After the next `gate_wait`, a POST is accepted again.

### 2. 🟠 An approved CV is lost when a step after gate 4 fails

> **✅ Fixed 2026-10-10.** `run_worker` (`worker.py`) now initialises
> `checkpointer = graph = cfg = None` before the `try`, and its `except`
> branch calls `_close(run, graph, cfg)` and merges its result into
> `run_error`'s fields whenever `graph`/`cfg` were actually assigned (i.e.
> the graph built, so a checkpoint exists to read back). If `_build_graph()`
> itself is what failed, `graph` stays `None` and the branch skips `_close`
> entirely - no `UnboundLocalError`, no spurious close attempt. `_close`
> already swallows its own failures (`final: None` + `final_error`), so this
> can't mask the original error, and `run_stopped` (a superseded, parked
> run) is a separate branch untouched by this - it never closes, matching
> the note below that gate 4 was never answered there. Checked by
> `py_compile`, an import-only load, and a scratch test that monkeypatches
> `_build_graph`/`_drain`/`_close` to simulate (a) a failure after the graph
> builds — `run_error` now carries `final` with the approved review and
> export paths — and (b) a failure building the graph itself — `run_error`
> has no `final` key and `_close` is never called. **Not run**: pytest,
> uvicorn, or a real `evaluation.node()` exception through the full graph.

Gate 4 is followed by `evaluation`, which is being built right now (`evaluation/checks.py`,
ATS). If it raises, `run_worker` emits `run_error` and **never calls `_close`**:
- the CV the human approved (or edited) is not saved;
- the review is not written to the learning store;
- the UI shows a failed run, although the final review is done.

The checkpoint still holds the gate-4 answer and the final `document`, so the CV can be
closed out anyway:

```python
def run_worker(run, on_finish=None):
    ...
    checkpointer = graph = cfg = None
    try:
        graph, checkpointer = _build_graph()
        cfg = {...}
        ...
    except Exception as exc:
        fields = {"error": f"{type(exc).__name__}: {exc}"}
        if graph is not None:
            # A failure after gate 4 must not lose the CV the human approved.
            # Before gate 4 there is no review: close_run returns review=None and saves nothing.
            fields.update(_close(run, graph, cfg))
        emit(run, "run_error", **fields)
```

- `_close` already swallows its own errors (`final: null` + `final_error`), so it can't
  mask the original error.
- `run_stopped` (superseded while parked) must **not** close: gate 4 was never answered.
- **Frontend change once landed:** read `final` on `run_error` as well as `run_done`
  (Round 13, item 7). It's a one-liner and harmless before then.

**Check:** make `evaluation.node` raise in a test. Approving gate 4 then gives
`run_error` with `final.review.approved == true` and `final.export.md` set, and the
download returns the file.

### 3. 🟠 The UI can't tell that a gate-4 reject is the last one: round info on `gate_wait`

`decide()` honours a reject only while `revision_count < max_revisions`. The Critic's
REVISE and the Verifier's FAIL spend the **same** budget, so gate 4 can open with the
budget already gone. A reject then does not redo anything: it ends the run, and nothing
is saved. Today the screen can't warn about that.

- **Add `revision` and `max_revisions` to every gate's interrupt payload.**
  - This is one line in `utils/human_gate.py` (Agents lane; Claude can add it on
    request). The worker needs nothing, because extras pass through.
  - This also covers item 7's "round number on `gate_wait`" from the section above.
- **The frontend's rule:** `revision >= max_revisions` means "rejecting now ends the run
  without saving". The rule lives in `decide()` (`agents/supervisor.py`). If it changes,
  this contract changes with it, so name the rule in a comment at both ends.
- **Finish item 3 of the section above:** `gate_done` should carry `gate` too, so a replayed
  log needs no guessing.

**Check:** with `max_revisions=1`, gate 4's first `gate_wait` has `revision: 0,
max_revisions: 1`. After one reject the reopened gate has `revision: 1`, and a second
reject ends with `final.review.approved == false`.

### 4. 🟠 `feedback` is unbounded, and now reaches more places

> **✅ Fixed 2026-10-10.** `GateAnswer.feedback` is now
> `Field("", max_length=2000)` (`routes/runs.py`), same cap size as one gap
> answer. Checked by `py_compile`, an import-only load, and a direct
> pydantic check: a 2,001-character value → `string_too_long` (the exact
> check this entry specified), 2,000 chars accepted, and the default empty
> string on a caller that omits the field entirely is unchanged. **Not
> run**: pytest, uvicorn, or a real gate-4 reject with oversized feedback
> through the live graph.

`GateAnswer.feedback: str = ""` (`routes/runs.py`) has no cap. The text now reaches:
- `GateFeedback` in the checkpoint and the state snapshots;
- the echo on `gate_done`, persisted in the run log and replayed on every SSE connect;
- at gate 4 on live runs, `knowledge_base/learning/document/feedback.jsonl` and the
  `reason` of every correction record;
- **soon, the Document prompt**, once the writer reads the human's reason
  (`bugs_audit_fixed.md` #55.1). That makes it prompt input, with #37's reasoning.

**Fix:** `feedback: str = Field("", max_length=2000)`. That's the same size as one gap
answer (item 1 of the section above) and enough for a reason.

**Check:** a 2,001-character feedback → 422 (`string_too_long`).

### 5. 🟠 Saved CVs have no list, no delete, and won't survive a redeploy

Today, a file is written to `outputs/<owner>/{date}_{run_id}_{role}.md|.txt` and served
by one route. Missing:

- **(a) Where the files live.** `config.OUTPUTS_DIR` is `BASE_DIR / "outputs"`, inside the
  app folder. In the Docker image it's lost on every redeploy unless that path is a
  mounted volume. Stage 0 §15 already plans `OUTPUTS_DIR` under `DATA_DIR`. Until then,
  mount it in the compose file next to `logs/`. It's git-ignored already.
- **(b) A list.** Extend `registry.list_for`'s summaries (it already reads every log)
  rather than adding a route:

  ```python
  done = next((e for e in reversed(events) if e.get("type") == "run_done"), None)
  final = (done or {}).get("final") or {}
  summary["review"] = final.get("review")                 # null for old logs
  summary["saved"] = bool((final.get("export") or {}).get("md"))
  ```

  Runs and Account can then show a "saved" badge and a download per row (Round 13,
  item 14).
- **(c) A delete.** `DELETE /api/runs/{id}/document`:
  1. Owner-checked: 403, never 401.
  2. Deletes both files.
  3. Rewrites the log under `update_json(_log_path(id), ...)`: set
     `final.export = null` and `final.export_deleted_at` on the `run_done` event.
  4. Returns 204.

  After that, `GET` gives 404 "deleted" rather than "missing on the server".
- **(d) Owner key.** `<owner>` is the token id until Stage 0 §13.1's `profile_id`. The route
  reads the path from the run's own log, so files saved under a token id keep downloading
  after the switch.
  - Same caveat as the CV-upload section: a re-issued token gets a new token id, so it
    can't see its old runs or files.
  - Deleting a profile, when that exists, should delete `outputs/<profile_id>/`.

**Checks:** after a redeploy (compose `down`/`up`) the file still downloads; user B gets
403 on A's `DELETE`; after `DELETE`, `GET` → 404 and `list_for` shows `saved: false`.

### 6. 🟡 `corrections.json` writes need the lock that lives in this folder

`utils/final_review.record_learning` now calls `learning/store.save_correction` on every
live gate-4 edit. Its `_append_json_list` is a read-modify-write with no lock (audit #12).
Two live runs finishing together can each read the old list, so one record is lost.
`feedback.jsonl` is safe, because it appends lines.

The lock already exists in `backend/jsonstore.update_json`, but `learning/` must not
import from `backend/`. **Proposal:**
1. Move the module to **`utils/jsonstore.py`**.
2. Leave `backend/jsonstore.py` as a two-line re-export, so no import in this folder changes.
3. Point `learning/store._append_json_list` at it:

```python
from utils.jsonstore import update_json

def _append_json_list(path, record):
    update_json(path, lambda records: ([*(records if isinstance(records, list) else [records]), record], None),
                default=[])
```

- The same move lets `learning/profile_store.save_gap_answers` stop bypassing the lock
  (#35).
- The lock is per process. Stage 0 runs one uvicorn worker. With more than one, it would
  need a file lock (`fcntl.flock`).

### 7. 🟡 A run parked at gate 4 does not survive a server restart

Gate 4 is where a run has spent everything: the allowance, and in live mode all the
model calls. Today a restart while it is parked there loses it:
- `_runs` is in memory;
- the run log is written only on finish (`registry.save_log` via `on_finish`), so a
  killed process leaves **no log at all**;
- the graph's checkpoint survives (`logs/checkpoints.sqlite`), parked at the interrupt,
  but nothing can reach it.

**Design: a Resume route.** This is the DELIVERABLES §18 stretch goal, made concrete.
1. **Persist while parked.** `save_log(run)` right after emitting `gate_wait`, so a parked run
   has a log on disk.
2. **On boot,** a log whose last event is `gate_wait` with no `gate_done`, `run_done`,
   `run_error` or `run_stopped` after it is "interrupted". `list_for` returns
   `interrupted: true`.
3. **`POST /api/runs/{id}/resume`.** Owner-checked; 409 if a live worker already owns the
   id; never charges a run. It:
   - rebuilds the run dict from the log, keeping its events;
   - reads the pending interrupt the way `scripts/run_gated_graph._pending_interrupt`
     does (`graph.get_state(cfg).tasks[*].interrupts[0].value`);
   - starts a worker that **begins at `_wait_for_gate(run, payload)`** instead of
     `_drain(GraphState(...))`.
4. **The frontend** then reopens the same review screen from the replayed `gate_wait`, with
   a "Resume" action on the Runs row.

**Check:** park a demo run at gate 4, kill uvicorn, and restart. The run is listed as
interrupted; Resume shows the same gate-4 screen; approving finishes it with `final` set.

### 8. 🟡 Per-line CV text in `gate_wait.changes` falls under the CV-privacy decision

`changes[]` carries `before` / `after` for every edited line (CV text), and
`document_edited` carries the whole edited CV. Both are owner-checked and persisted in
the run log, like the `document` artifact always was.
- This is the same bucket as `line_links` in **item 4 of the CV-upload section above**.
  Whatever is decided there applies here too.
- If per-line text moves behind an owner-checked route (`GET /api/runs/{id}/cv-links`),
  move the diff with it: `GET /api/runs/{id}/changes`, with only `changes_count` on
  `gate_wait`.
- The final CV itself has to reach the browser to be shown. Recommend it stays on the
  owner-checked stream (`document_edited`, `node_done`) as today.
- **Never** echo the edited text on `gate_done` (it isn't today: `edited` is a flag).

### 9. 🟡 Proposals that need the Agents lane first (recorded so the API shape is ready)

None of these is built. Each needs a change in `utils/human_gate.py` or `decide()`
(the Agents lane, where the routing is the user's to write), and then a field here.

- **(a) Undo single changes: `reverted_changes: list[str]`.** Node ids taken from the open
  gate's `changes[].node_id`; accepted with `approve` at gate 4.
  - *Graph:* the gate rebuilds the CV as
    `render_markdown(apply_edits(cv_tree, [e for e in patches.edits if e.target_id not in reverted]))`.
    That's deterministic, with no model call. The reverted ids are recorded in
    `edited_payload`, and the learning step writes them as "rejected edit" feedback,
    the signal the writer most needs.
  - *API:* keep the open gate's ids on the parked run
    (`run["gate"]["change_ids"] = [c["node_id"] for c in payload.get("changes", [])]`,
    the same pattern item 1(b) above proposes for gap questions) and 422 on any id not in
    it. 422 if sent together with `edited_content`, because a full edit already decides
    every line.
- **(b) A fourth decision, `discard`, at gate 4 only.** It ends the run now and saves
  nothing, **without** spending a redo and another Writer, Critic and Verifier round
  when the human just wants out.
  - *Graph:* `decide()` routes a gate-4 `discard` to `END` (or to `evaluation`, if
    discarded runs should still be scored).
  - *API:* `decision: Literal["approve", "edit", "reject", "discard"]`, 422 at other gates.
    `final.review.approved = false`.
- **(c) A reason with a gate-4 reject.** Once Document reads the human's reason (#55.1), an
  empty reject gives the writer nothing to act on. Then:
  `422 reason_required` when `decision == "reject"`, the gate is `gate4_document` and
  `feedback` is blank. Until Document reads it, keep it optional: a required field that
  nothing reads is a tax.

### Tests to add (in `tests/test_backend_api.py`, no new files)

Redirect `config.OUTPUTS_DIR` and `config.KB_LEARNING_DIR` to `tmp_path` in every one of
these.
- **`StubGraph` gains `get_state(cfg)`** returning `.values` with `gate_feedback` (a
  `GateFeedback` for `gate4_document`), `document` and `requirements`. Without it, every
  stub run ends with `final: null` and `final_error: "AttributeError…"`, and the closing
  step is never exercised.
- **Approve at gate 4:** `run_done.final.review.approved`; both files exist;
  `GET /document` → 200 with an `attachment; filename=` header; `?fmt=txt` → the Markdown
  stripped.
- **Edit with `edited_content`:**
  - a `document_edited` event arrives before `run_done`;
  - `gate_done.edited == true` and `gate_done` has no CV text;
  - the saved `.md` is the edited text.
- **Refusals:**
  - `edited_content` at gate 1 → 422;
  - `edited_content` with `approve` → 422;
  - a stale `gate` → 409;
  - item 1's double answer → one 409.
- **Reject at the cap:** `final.review.approved == false`, `final.export == null`, and
  `GET /document` → 404.
- **Ownership:** another user → 403 on `GET /document`. A hand-edited log whose export
  path climbs out of `OUTPUTS_DIR` → 404.
- **Offline run:** `final.learning` starts with `"skipped"`, and the redirected learning
  folder stays empty.

### What to run (yours)

```
.venv/bin/python -m pytest tests/test_backend_api.py -q
.venv/bin/python -m uvicorn scripts.frontend_api:app --port 8000
.venv/bin/python scripts/smoke_backend.py
```

Then one demo run through the UI for each gate-4 path:
- approve: you get the saved file;
- edit: your text, saved;
- reject until the limit: "not approved", nothing saved.

### Verification status: **built parts checked in-process only; items 1–9 not built**

- **The built rows:** `py_compile` and import checks pass, plus an in-process
  `TestClient` check of `answer_gate` and `download_document` with a fake identity.
  Results: a stale gate gives 409; misplaced `edited_content` gives 422; the content is
  relayed as `edited_payload`; the owner's download gives 200 with a filename; another
  user gets 403; a path escape, a missing file and an unapproved run each give 404.
- **Not run:** pytest, uvicorn, the smoke script, a browser.

---

## 2026-10-09 (design) — one vault per user, and a separate log plane. **Not built.**

Design only, from the Backend role, at the user's request. No code changed. The
storage half (folder layout, databases, retention, migration) is in
`context/context_Data Storage+Handling.md` → "Per-user vaults and the log plane".
This section is what the backend has to enforce and expose.

### The model

There are three kinds of data, kept apart:

- **The user data plane: one vault per account.** It holds everything a user put
  in, or a run produced for them:
  - profile records and their history;
  - their vectors;
  - their CV uploads;
  - their runs (job description, gate answers, artifacts, checkpoints, the run
    trail);
  - their outputs.

  After authentication, a user can reach **only their own** vault. Nothing
  routes one user's data into another user's run.
- **The log plane: records *about* what happened, stored apart from every
  vault.** It covers auth and admin events, run operations, LLM calls,
  retrievals and errors.
  - The **system admin sees all of it**.
  - A user sees a **filtered view of the entries about themselves**.
  - The graph never reads it.
- **Shared data**, read-only for every user: the documents store, prompts,
  instructions and seed fixtures. It must never hold user content.

The rule that makes "admin sees all logs" safe: **logs carry ids, not content.**
A log entry names `run_id`, `record_id` and `cv_id`, never the CV text, a profile
record's text, a prompt, or an answer. That content lives in the owner's vault.
So the log plane can be fully visible to the admin, and can outlive a deleted
account, without copying anyone's data.

### What breaks this model today (checked in source 2026-10-09)

| Where | Today | Why it breaks the model |
|---|---|---|
| `backend/runs/registry.py` `_active`, `owns()` | keyed on `token_id` | a re-issued token is a different owner, so one account splits in two |
| `logs/frontend_runs/{id}.json` | one folder for all users; holds `job_description` and every event with its full artifact (the `cv_link` tree includes the header: name, email, phone) | user content sits in what should be the log plane, mixed across users |
| `logs/<run_id>/` (`log_state_snapshot`) | the full `GraphState` at every gate, in a shared folder | same as above |
| `logs/checkpoints.sqlite` | one database with every user's full run state | user data in one shared file |
| `logs/plan_cache/` | Document planner answers keyed by an input hash, and the input includes the user's CV | user-derived content in a shared folder |
| `outputs/<token_id>/` | already per owner, but keyed on `token_id` | splits on token re-issue |
| `GET`/`PUT /profile/entries`, `/kb`, `/kb/{store}/{file}`, `/search` | read and edit `manual_entries.json` and the shared `profile` collection | every user sees, and can edit, everyone's records |
| The graph: Profile retrieval, `cv_link`, Document's `profile_blocks`, `save_gap_answers` | read and write the shared `profile` collection and `manual_entries.json` | B's run uses A's records as evidence |
| `learning/store.py` (agent memory) | shared by design; no writers yet | the first writer would carry user A's text into user B's prompts |

### 1. 🔴 Identity first: an account is not a credential

This is a prerequisite. The vault key is `profile_id` (Stage 0 §13.1), so this
has to land **before** the vaults, or the first vault inherits the takeover bug
(October scoping §5, items 1 and 4).

- Add `normalise_identifier()` (NFKC, casefold, collapse whitespace; reject `:`
  and reserved names). Approving an identifier that already has an account
  returns **409**.
- Top-ups go through an authenticated `POST /api/auth/request-more`. It mints no
  new token and takes the account from the caller, never from a typed name.
- Token records gain `profile_id`. `resolve_token` returns it in the identity.
  `/auth/me` gains `profile_id`, which is a wire change: tell the frontend.
- `registry._active` and `owns()` key on `profile_id`. `token_id` stays only for
  audit entries.

### 2. 🔴 One `Scope`, resolved from auth, is the only way to reach user data

- **`backend/deps.py`** gains `require_scope`, which returns
  `Scope(profile_id, role, root, collection)`. It is built **only** from the
  verified token, never from a path, query or body value.
- **Every data route takes `Scope`,** not `Identity`. It calls store functions
  whose first argument is the scope. No store function accepts a raw path or a
  `profile_id` that came from a request.
- **Paths:** `scope.path(*parts)` resolves the path and checks it stays under
  the vault root. This is the same containment as the `kb_file` hardening. A
  crafted `run_id` or `cv_id` cannot climb out.
- **Fail closed.** A store call without a scope raises. There is no default
  profile and no fallback to shared data.
- **Admin access to a vault** goes only through `/api/admin/users/{profile_id}/…`.
  Building a scope for another user's vault writes an `admin_data_access` audit
  entry **first**. If that audit write fails, access is refused.
- **Status codes:**
  - "not yours" is **403, never 401**; a 401 logs the user out;
  - an unknown `profile_id` on an admin-only route is 404, since only the admin
    can reach it and nothing leaks.

### 3. 🔴 Runs carry the scope into the graph

> **✅ The backend's half is built 2026-10-22** — `config.set_profile_id()` /
> `current_profile_id()` / `require_profile_id()` (a ContextVar beside the
> fake-LLM switch), `GraphState.profile_id`, and `worker._drive` binding the
> run's account on its own thread before the graph is built. **The consumers
> are still unscoped** — the retriever's collection, `save_gap_answers`,
> the plan cache, the snapshot and export folders all still resolve globally,
> and that is Agents/KB+RAG work (this item's own text says so). The vault
> storage bullets below (checkpointer per vault, run trail into the vault)
> are untouched. See `"2026-10-22 (scope into the graph)"` below.

- **At run start,** `profile_id` goes into `GraphState` and into a `ContextVar`
  (`current_scope`) set on the worker thread. That is the same mechanism as
  `config.set_fake_llm`, and it propagates through LangGraph's `copy_context()`
  pool threads, as proved for the fake-LLM switch on 2026-08-19.
- **Everything the graph touches resolves through that scope:**
  - the retriever's collection;
  - profile writes (`save_gap_answers`, `profile_commit`);
  - `cv_path`;
  - the plan-cache folder;
  - the snapshot folder;
  - the export folder.

  A missing scope raises. The consumers are agent and KB code (other lanes); the
  backend's job is to set the scope.
- **One checkpointer file per vault.** `make_checkpointer(scope)` opens
  `<vault>/checkpoints.sqlite`. The worker already builds a checkpointer per run,
  so this is a path change. The CLI's resume needs `--profile`.
- **The run record and run trail move into the vault:**
  `<vault>/runs/<run_id>/record.json`, `events.json` and `snapshots/`.
  - `list_for` reads only the caller's vault.
  - The admin's list comes from the log plane's run index (§5).
  - SSE replay reads the vault's `events.json`, after the ownership check.
- **Naming, to stop the two from blurring:**
  - the **run trail** is the event history with artifacts. It is user data and
    lives in the vault. `GET /runs/{id}/log` serves it today and keeps doing so.
  - **logs** are the log plane.

### 4. 🟠 Every route, scoped

| Route | User | Admin |
|---|---|---|
| `/profile/entries` (GET/POST/PUT) | own vault only | via `/admin/users/{pid}/profile`, audited |
| `/kb`, `/kb/{store}/{file}` | own profile store, plus the shared stores read-only. **Not** agent memory, never another user | everything, via admin routes |
| `/search` | own collection, plus the shared `documents` | any profile, via an admin route |
| `/profile/cv*` | own vault (the CV section above) | audited |
| `/runs*`, `/runs/{id}/document` | own vault | all; see decision D-T2 |
| `/runs/{id}/retrievals` | own runs, user view | full |
| **`GET /api/logs/mine`** (new) | the user view of their own log entries | — |
| **`GET /api/admin/logs`** (new) | 403 | the full log plane |
| **`GET /api/admin/users`** (new) | 403 | accounts, status, run counts |

**Interim, before `profile.db` exists:** stamp `owner = profile_id` (or
`token_id` until §1 lands) on every Build Profile entry. Filter `GET` by it, and
return 403 on a `PUT` that isn't the caller's. This closes the cross-user leak
the same week, without waiting on the storage work.

### 5. 🟠 The log plane: what is logged, and who sees what

**Log kinds** (where each is stored is in the Data Storage file):

| Kind | Examples | Written by |
|---|---|---|
| `audit` | login ok/failed, request-access, approve/reject, token revoke, every 403, admin vault access, export, account delete | backend |
| `run` | run start/end, node start/done with timings, gate opened, gate decision (the decision only, never the typed text), supersede/abort, allowance spent/refunded, run error | backend worker |
| `llm` | agent, provider, model, latency, token counts, cost, fallback taken, error class | `agents/base.structured_call` (Pipeline Infra lane) |
| `retrieval` | `retrieval_log.db` from Stage 0 §13.6 | the retriever (KB+RAG lane) |
| `system` | startup checks, config warnings, unhandled exceptions with stack traces | app |

**Every entry carries:**
- `ts`, `kind`, `event`;
- `profile_id` (or `"system"`), and `run_id` where there is one;
- `actor`: the account, `admin` or `system`;
- `fields`.

**Who sees what:**

| Kind | A user sees (own entries only) | A user never sees | The admin sees |
|---|---|---|---|
| `audit` | own logins (time, ok/failed), own access decisions, own exports | other accounts, IP addresses, which admin acted, any 403 detail about someone else | all |
| `run` | own run timeline, node durations, gate decisions, error **message** | stack traces, server paths, internal state | all |
| `llm` | agent name and duration per call | prompts, raw responses, provider error bodies, cost, the fallback chain | all |
| `retrieval` | own queries, the record ids returned from own profile and from shared documents, scores | other profiles' ids | all |
| `system` | nothing | everything | all |

**Rules:**
- **Projected on the server.** `GET /api/logs/mine` runs each entry through a
  per-event allowlist of user-visible fields.
  - An event type with no allowlist is **hidden** from users (fail closed), so a
    new log event can't leak by default.
  - The user filter is `profile_id == scope.profile_id`, applied in the query,
    never after it.
- **Content rules apply to the admin too.**
  - Never log secrets: no token, no API key. Log `token_id` only.
  - Never log CV, profile or answer text: log the id.
  - This is what lets the admin see "all the data of logs" without the logs
    being a second copy of every vault.
- **The graph never reads the log plane,** so nothing logged can flow into a
  prompt.
- **Routes:**
  - `GET /api/logs/mine?kind=&run_id=&since=&cursor=&limit=`
  - `GET /api/admin/logs?kind=&profile_id=&run_id=&event=&since=&cursor=&limit=`
  - Both use a cursor on `ts`, with `limit` capped at 500.
  - A user calling the admin route gets 403, never 401.

### 6. 🟡 Export and delete

> **Export ✅ built 2026-10-22**; delete blocked on the KB lane. See
> `"2026-10-22 (account export)"` below.

- **User export:** `GET /api/me/export`, a zip of the caller's vault (D-T6).
- **Admin deletes an account:**
  1. revoke its tokens;
  2. delete the vault folder;
  3. drop its collection;
  4. mark the account `deleted`;
  5. write an `account_deleted` audit entry.

  The log plane keeps its entries. They are content-free by the rule above, and
  `profile_id` is a random pseudonym, not the identifier.

### Order of work

| Step | What | Lane |
|---|---|---|
| P0 | §1 identity (account ≠ credential) | Backend |
| P1 | §2 `Scope`; vault paths for what the backend writes: run record and trail, outputs, CV uploads, checkpoints; the interim owner stamp on entries | Backend, plus Data Storage for the layout |
| P2 | §5 log-plane writer, `audit` + `run` kinds, user projection, admin routes | Backend + Data Storage |
| P3 | `profile.db` per vault, one collection per profile, scoped `/kb` and `/search` | Data Storage (M1) + KB+RAG |
| P4 | the graph reads `current_scope`: retriever, `cv_link`, Document, `save_gap_answers`, plan cache, snapshots; `llm` and `retrieval` log kinds | Agents, KB+RAG, Pipeline Infra |

P0–P2 can ship and be tested on their own. Until P3–P4 land, runs still read the
shared `profile` collection, so "isolated" is only true at the HTTP edge. The
Pipeline screen should not claim isolation before then.

### Open decisions (recommendation first)

| # | Decision | Recommendation |
|---|---|---|
| D-T1 | Per-user database file, or one `profiles.db` with a `profile_id` column | **Per-user file in the vault.** Isolation by construction, and delete/export is one folder. Detail in the Data Storage file. Changes the approved "two files" row |
| D-T2 | Can the admin open user *content* (runs, profile, CV), not just logs? | **Yes, but only through admin routes, every access audited.** Note: today `RunsView` shows the admin every run with full content. Keeping that is the alternative; changing it is a frontend contract change |
| D-T3 | Does a user see model, provider or cost for their runs? | No for cost and prompts. Agent name and duration only |
| D-T4 | Log retention | `audit` 365 days, `run` and `llm` 90, `retrieval` 30 (D9), `system` 30 |
| D-T5 | Agent memory (`learning/`) once it has writers | Per-user memory in the vault. A shared memory only for entries the admin approves and that hold no user text |
| D-T6 | User self-export in Stage 0 | Yes. It's cheap once the vault is one folder, and it proves isolation in the showcase |

### What to run (yours), once built

New tests go into the existing `tests/test_backend_api.py` and
`tests/test_backend_auth.py`, not new files.
- **B cannot reach A's data:** B gets 403 on A's run, trail, CV, output and
  retrievals; B's `/kb`, `/search` and `/profile/entries` never contain A's ids.
- **A re-issued token** for the same account sees the same vault and the same
  run history.
- **Fail closed:** a store call with no scope raises; a crafted `run_id` or
  `cv_id` (`../x`) cannot leave the vault.
- **Log projection:**
  - `/logs/mine` returns only the caller's entries and only allowlisted fields;
  - an unknown event type is hidden;
  - `/admin/logs` returns everything;
  - a user on `/admin/logs` gets 403 and stays logged in.
- **No content in logs:** after an offline run, grep the log-plane files for the
  run's JD text, a CV line and the token. None should be found.
- **Admin vault access** writes its audit entry before returning data.

## Verification status (this design): §1 built 2026-10-10 (below); §2–§6 not built

Only this file and `context/context_Data Storage+Handling.md` changed at design
time. Facts came from reading `backend/runs/registry.py`, `backend/routes/*`,
`state/state_utils.py`, `utils/export.py`, `config.py` and the earlier sections
of this file.

---

## 2026-10-10 (identity) — §1 built: an account is not a credential

> **Scope + authorship:** asked to build the single most important open item
> in this file's criticality index, restricted to editing `backend/` only.
> That's this section's §1 — the other two 🔴s (§2 `Scope`, §3 runs carrying
> it into the graph) explicitly depend on this landing first, so building one
> of the three meant building this one. Claude wrote it. Checked: `py_compile`,
> an import check (`backend.app` builds clean), the real `tests/test_backend_auth.py`,
> `tests/test_backend_api.py` and `tests/test_backend_mode_isolation.py` suites
> run before and after (171 passed either time; the 6 new failures are exact-
> shape pins this change deliberately moves — listed in "What to run" below,
> not fixed here per the tests-are-yours split), and a scratch functional
> script against a tmp `KB_AUTH_DIR` (never the real `knowledge_base/auth/`)
> covering every path below. **Not run:** uvicorn, a browser, the frontend
> (untouched — out of jurisdiction for this pass).

**New: `backend/auth/profiles.py`.** A fourth flat JSON store
(`profiles.json`, same pattern as `requests.json`/`tokens.json`), not the
`profiles.db` SQLite store Stage 0 §13.1 eventually wants — this module's
contract (`profile_for` / `get_or_create_profile` / `create_profile` →
`profile_id`) is what the rest of the backend now calls; swapping the storage
underneath is this module's own business later, not a wire change for
anyone calling it.

- `normalise_identifier()`: NFKC + casefold + collapsed whitespace, rejects
  empty/oversized/`:`-containing/reserved (`admin`/`system`/`root`) input.
- `create_profile(identifier)`: a fresh `profile_id` (`p-<8hex>`), or raises
  `ProfileError` if the normalised identifier already has one — this is the
  identifier-takeover fix (October scoping §5 item 1): approving a second
  request under an existing user's exact (or confusable) name is now refused,
  never silently merged into that user's account.
- `get_or_create_profile(identifier)`: idempotent lookup-or-create, for call
  sites where seeing the same identifier again is expected and safe (a
  backfill, or the admin bootstrap) — never for a fresh public approval.

**`backend/auth/store.py`:**
- `approve_request` now also creates the profile (409 via `AuthError` on a
  colliding identifier) and stamps `profile_id` onto the new token record.
- `resolve_token` backfills `profile_id` onto any pre-existing token record
  that predates this field (idempotent — confirmed the 3 real records in
  `knowledge_base/auth/tokens.json` all backfill cleanly on next use; nothing
  touched them in this session).
- `identity_of` — and therefore `/auth/me` and `/auth/login` — now carries
  `profile_id`. **Wire change, flagged for the frontend.** It also flips
  `tests/test_backend_api.py::test_admin_identity_shape`'s exact-equality
  assertion, same as `"2026-10-09 (design)"` §1 said it would; not fixed here
  — tests are the user's per the working split.
- New `ADMIN_PROFILE_ID` sentinel (`"p-__admin__"`), same treatment as
  `ADMIN_TOKEN_ID`: the admin account has no `profiles.json` row either, and
  isn't run through `normalise_identifier` (which reserves `"admin"` for
  exactly this reason — so a typed signup can never collide with it).
- New `create_topup_request(identity, note)` + an `approve_request` branch
  for `kind == "topup"`: adds `DEFAULT_RUN_ALLOWANCE` to the caller's own
  existing token and mints nothing. This is the re-issue-splits-the-account
  fix (October scoping §5 item 4) — paired with the new route below.

**New route: `POST /api/auth/request-more`** (authenticated). Takes only a
`note`; the account it tops up comes from the caller's bearer token, never
from typed text. **The frontend's `Account.jsx` "request more runs" button
still calls `/request-access`** (mints a second token under the same typed
name) **— not changed here, flagged for the frontend side.**

**`backend/runs/registry.py` + `backend/routes/{runs,cv}.py`:** every
ownership key (`_active`, `owns()`, `start()`'s owner slot, CV storage in
`cv_store.py` via `routes/cv.py`) now reads `identity["profile_id"]`, not
`identity["token_id"]`. `token_id` still rides on the run record for audit
(`registry.start` stamps it; `save_log` persists it) but is never compared
for ownership again. **One subtlety caught in review:** `store.consume_run`/
`refund_run` key on the token's own `id` (the allowance is a property of the
credential, not the account — a top-up adds to that same token), so
`routes/runs.py` now keeps `owner` (profile_id) and `token_id` as two
separate variables instead of reusing one for both.

**Not touched, by design (kept to one item):** `backend/deps.py` (no
`Scope` yet — that's §2), any graph/agent code (§3), `backend/routes/{profile,kb}.py`
(the Build-Profile/KB cross-user leak is §4, a separate 🟠), and the log
plane (§5). The three 🔴s in the criticality table are now two — §2 and §3 —
both now actually buildable, since their blocker is this section.

**What to run (yours).** This flips 6 tests — confirmed by running all three
backend test files together before and after: 171 passed either way, and the
failing set grows by exactly these 6 over the pre-existing baseline:

- `tests/test_backend_api.py::test_admin_identity_shape` — exact-dict assert,
  needs `"profile_id": "p-__admin__"` added.
- `tests/test_backend_auth.py::test_a_request_record_has_the_full_shape` —
  `set(req)` assert, needs `"kind"` added.
- `tests/test_backend_auth.py::test_an_approved_token_has_the_full_shape_and_links_both_ways` —
  `set(tok)` assert, needs `"profile_id"` added.
- `tests/test_backend_auth.py::test_identity_never_carries_the_raw_token` —
  two exact-dict/`set()` asserts, same as `test_admin_identity_shape`.
- `tests/test_backend_auth.py::test_the_raw_token_lives_only_in_tokens_json` —
  asserts `KB_AUTH_DIR` holds exactly `["requests.json", "tokens.json"]`; now
  three files (`profiles.json` too).
- `tests/test_backend_auth.py::test_the_download_route_serves_exactly_what_close_run_saved` —
  builds its fake run record as `{"owner": identity["token_id"], ...}`, the
  pre-this-session convention. Production code no longer does that
  (`registry.start` stamps `run["owner"] = identity["profile_id"]`, and
  `worker.py:256` passes that same `run["owner"]` on to `close_run` — so the
  real path, `outputs/<profile_id>/...`, is already self-consistent end to
  end); only this test's own fixture is stale. Swap its `owner["token_id"]`
  for `owner["profile_id"]` in the two spots that build the fake record.

The 10 pre-existing CV-related failures in `test_backend_api.py`
(`KeyError: 'run_id'`) are unrelated to this change, confirmed the same way —
already logged above under `"2026-10-10 — items 1–3 built"`.

---

## 2026-10-10 (scope) — §2 partially built: `Scope`, containment, fail-closed

> **Scope + authorship:** asked to build the next most critical open item
> after identity (§1, above), excluding anything needing heavy live testing,
> restricted to editing `backend/` only. That's `"2026-10-09 (design)"` §2.
> Built in full: the `Scope` type itself, the containment check, and the
> fail-closed guards. **Deliberately not built in full** (see "What's still
> open" below) — the parts that either need a storage-layout call this role
> doesn't own alone, or depend on the log plane (§5), which doesn't exist
> yet. Claude wrote it. Checked: `py_compile`, an import check, the full
> `tests/test_backend_auth.py` + `tests/test_backend_api.py` +
> `tests/test_backend_mode_isolation.py` run before and after (identical 16
> failures, 171 passed, both times — zero regressions from this session), and
> a scratch script against tmp `RUNS_DIR`/`CV_UPLOADS_DIR` that reproduces and
> confirms the fix for the vulnerability below. **Not run:** uvicorn, a
> browser, the frontend.

**A real, confirmed path-traversal gap, found while scoping this item — not
hypothetical.** `backend/runs/registry.py`'s `_log_path()` built
`config.RUNS_DIR / f"{run_id}.json"` with no containment check, and `run_id`
reaches it straight off the URL at `GET /runs/{id}/log` and
`GET /runs/{id}/document` the moment `registry.get()` (an in-memory dict
lookup, already safe) misses and it falls back to `load_log()` (a file read,
not safe). Reproduced before this fix:
`registry._log_path("../../../../etc/passwd")` resolved to a path entirely
outside `RUNS_DIR`. Worse than a generic 404-vs-403 leak: `registry.owns()`
returns `True` unconditionally for an admin identity regardless of a
record's content, so for that role this was a working arbitrary-`*.json`-file
read (scoped to files whose name plus `.json` an attacker could predict/reach
via traversal — not everything on disk, but not nothing either). Fixed by
routing `load_log()` through the new `contained_path()` helper; a path that
escapes `RUNS_DIR` is now treated exactly like an unknown run_id (`None`,
same as "not found" — no distinction that would tell an attacker which it
was).

**New in `backend/deps.py`:**
- `contained_path(root, *parts)` — resolves `root/*parts` and raises
  `ScopeError` if the result isn't under `root`. Pulled out of
  `backend/routes/kb.py`'s existing inline `path.is_relative_to(store_dir)`
  check (§2: "the same containment as the kb_file hardening") so every other
  profile_id/run_id/cv_id-keyed lookup can share one checked implementation
  instead of re-deriving its own.
- `Scope(profile_id, role)` — a frozen dataclass, and `Scope.own(root, *parts)`
  (shorthand for `contained_path(root, self.profile_id, *parts)`), the shape
  every existing per-owner store already uses.
- `require_scope` — the dependency that builds a `Scope` from `require_auth`
  alone, never from a path/query/body value. Fails closed with a bare
  `RuntimeError` (a 500, not a 403 — this is a broken invariant, not a
  caller's mistake) if `identity` somehow has no `profile_id`, which §1
  guarantees it always will.
- `Caller = Annotated[Scope, Depends(require_scope)]`, parallel to the
  existing `Identity`/`AdminIdentity` aliases.

**`backend/routes/cv.py` fully migrated onto `Caller`/`Scope`** — every route
there was purely profile_id-keyed with nothing else needed, so this is one
complete, low-risk proof of the pattern end to end, not a partial rename.

**`backend/cv_store.py` fails closed:** `_cv_dir()` now raises `ValueError`
on a falsy owner, instead of silently resolving to
`CV_UPLOADS_DIR/cv` — a real shared path every such caller would have landed
on together. (`cv_id` itself was already safe — confirmed by reading
`confirm`/`delete`: both look it up as a dict key into `index.json`, never
join it into a filesystem path, so a crafted `cv_id` just misses and 403s,
the same as an unknown one. No fix needed there.)

**What's still open, and why it's not in this pass:**
- `backend/routes/runs.py` still pulls `identity["profile_id"]` /
  `identity["token_id"]` by hand instead of depending on `Scope` — its routes
  genuinely need both `role` (the admin sample-CV fallback) and `token_id`
  (the allowance counter, which is the credential's property, not the
  account's — see `"2026-10-10 (identity)"` above), which don't fit `Scope`'s
  deliberately thin shape. `registry.owns()` is unaffected either way — it
  already takes the full identity dict and already compares `profile_id`.
- `backend/routes/{profile,kb}.py` don't scope their reads/writes by caller
  at all yet (the pre-existing Build-Profile/KB cross-user leak, §4 — a
  separate 🟠, not touched here).
- The admin cross-vault route (`/api/admin/users/{profile_id}/...`) and its
  "write the audit entry first, refuse if that write fails" rule aren't
  built — §2's own text requires an audit write this role has nowhere to
  make yet (the log plane is §5, explicitly the *next* item after this one,
  not before it).

**What to run (yours):** nothing new flips. Same 16 pre-existing failures as
`"2026-10-10 (identity)"` lists, confirmed identical before and after this
session's edits.

---

## 2026-10-10 (profile scope) — the Build-Profile read+write leak, closed

> **Scope + authorship:** asked to build the next most critical open item,
> excluding anything needing heavy live testing, restricted to editing
> `backend/` only. §2's own plumbing (`routes/runs.py` onto `Scope`, the
> admin-audit path) was the literal next line in the ranked list, but while
> reading `"2026-10-09 (design)"` §4 to scope it, found that its *own* text
> already specifies an interim fix — "stamp `owner`... closes the cross-user
> leak the same week, without waiting on the storage work" — that this
> file's criticality table had wrongly marked as blocked on §2–§3 (that was
> this session's own mistake, made two entries ago; corrected above). That
> interim fix is a live, exploitable, full read+write cross-user data
> exposure on data a real person typed about themselves — more acutely
> dangerous right now than continuing §2's internal plumbing — so it's what
> got built. Claude wrote it. Checked: `py_compile`, an import check, the
> full three-file backend suite before/after (identical 16 pre-existing
> failures, 171 passed, both times), `tests/test_vectordb.py` before/after
> (identical: the same 12 pre-existing, unrelated Chroma-collection-naming
> failures both times — confirmed unrelated by checking they trace into
> `vectordb/store.py`, untouched this session or last), and a scratch
> `TestClient` script exercising the exploit and the fix end to end. **Not
> run:** uvicorn, a browser, the frontend.

**The bug, confirmed real, not hypothetical.** `GET /api/profile/entries`
returned the entire shared `manual_entries.json` to every authenticated user,
and `PUT /api/profile/entries/{id}` had no ownership check at all — found by
reading the handler, then confirmed live against a scratch two-user run:
Bob's `PUT` on Alice's `entry_id` (an id her own `GET` response had just
handed him, since it comes back unredacted) silently overwrote her text with
no error of any kind. `GET /api/kb/profile/manual_entries` and the `/api/kb`
overview's per-file counts exposed the exact same file through a second
route. This already carries real PII today — the field is free-text
("projects", "skills", "achievements", etc.) and every one of the three
pre-existing fixture records in the real `knowledge_base/profile/
manual_entries.json` is someone's actual CLI-run gap-interview answer.

**Fix — the interim `owner` stamp `"2026-10-09 (design)"` §4 itself
specifies, now unblocked since §1 landed:**
- **`backend/routes/profile.py`**: new `visible_entries(scope)` — admin sees
  every entry; otherwise only entries this account owns. An entry with no
  `owner` field is treated as **admin-only**, the same convention
  `backend/runs/registry.owns()` already uses for run logs written before
  ownership existed — never shown to everyone, never a `KeyError`.
  `add_profile_entry` now stamps `"owner": scope.profile_id` on every new
  record (never from the request body — the same principle as `Scope`
  itself: the account comes only from the verified token).
  `edit_profile_entry` checks ownership **inside** the same
  `update_json` read-modify-write as the edit, under the file's own lock —
  not as a separate read beforehand, which would leave a TOCTOU window for a
  concurrent edit to land in between the check and the write. Mismatch is
  403; a genuinely unknown id stays 404 — the same split `backend/routes/
  runs.py` already uses, so the two codes keep meaning the same thing
  everywhere in this package.
- **`backend/routes/kb.py`**: `kb_file` and `kb_overview` now special-case
  the one file that isn't actually curated/shared data —
  `profile/manual_entries.json` — and call the SAME `visible_entries()`
  rather than re-deriving the rule, so this second route onto the file can't
  quietly drift back out of sync with `profile.py`'s own scoping the way
  `AGENTS`/`GATES`/`STUB_NODES` have drifted from the graph three times
  already (noted in the October scoping pass). Every other KB store
  (`documents`, `do_not_claim`, `learning`) is genuinely shared and stays
  exactly as it was.
- Both routes now depend on `Caller`/`Scope` (`backend/deps.py`, built last
  session) instead of pulling `identity["profile_id"]` by hand — the same
  migration `routes/cv.py` got, now covering two more files.

**A real cross-lane gap, flagged loudly, not fixed here (outside
`backend/`):** `learning/profile_store.save_gap_answers` — the gate-2 answer
path, called from the graph — writes into this exact same file with no
`owner` field. Confirmed: the 3 real fixture records in `knowledge_base/
profile/manual_entries.json` all came from there (`run_id`s, no `owner`).
Under `visible_entries()`'s admin-only rule for ownerless entries, **a real
user's own gate-2 answers will stop appearing in their own Build-Profile
list** until that module stamps `owner` too, the same one-line pattern
`backend/auth/store.py` now uses for tokens. This is a real, user-visible
behavior change for that one path, traded deliberately for closing a full
read+write leak everywhere else — written up in both this file and `backend/
routes/profile.py`'s own module docstring so it isn't lost.

**Deliberately not touched, and why:** `POST /api/search` still queries the
shared `profile` Chroma collection unfiltered — the October scoping pass
already named this as the same underlying gap reached through a third route.
Closing it needs metadata (not filesystem) work: stamping `owner` into each
entry's *vector* metadata at index time, backfilling the vectors that
predate it, and confirming a `where=` filter at query time doesn't also
exclude the genuinely shared/curated vectors mixed into the same collection.
That's real design work with a real chance of quietly breaking retrieval
quality if rushed, not a mechanical repeat of this fix — left as its own
next item rather than bolted on here.

**What to run (yours):** nothing new flips. Same 16 pre-existing
`test_backend_*` failures as before, confirmed identical. `tests/
test_vectordb.py`'s existing `kb_file`/`kb_overview` tests
(`test_the_kb_browser_*`, `test_the_kb_overview_counts_records_and_vectors`)
still pass unchanged — they call the route functions directly with a plain
`ADMIN` dict rather than a `Scope`, but none of their fixtures include a
`manual_entries.json`, so the new scoped branch is never exercised by them.
**Worth knowing before writing a new direct test of either function**: both
now expect a `Scope` (`.profile_id`/`.role` attributes) in that position, not
an identity dict — `Scope(profile_id="p-x", role="user")`, not
`{"role": "user", ...}`.

---

## 2026-10-12 (scope, runs.py) — §2's route migration completed

> **Scope + authorship:** asked to build the next most critical open item,
> excluding anything needing heavy live testing, restricted to editing
> `backend/` only. The top 🔴 (`Scope`, §2) had one piece left that's both
> backend-only and small: `routes/runs.py` still pulled `identity["profile_id"]`/
> `identity["role"]` by hand in `start_run`, and `download_document` kept its
> own independently-maintained path-containment check instead of the shared
> `contained_path()` the previous two sessions introduced and already used
> elsewhere. Closing this finishes everything in §2 except the admin
> cross-vault route, which genuinely can't be built without §5 (the log
> plane) under it — correctly the next item after this, not before it.
> Claude wrote it. Checked: `py_compile`, an import check, the full
> `test_backend_*` + `test_vectordb` suites before/after (identical 28
> pre-existing failures, 267 passed, both times), and a scratch script
> (reusing the project's own `StubGraph` pattern from `tests/
> test_backend_api.py` — no live model, no live graph) exercising both
> changed code paths end to end, including forging a traversal attempt in a
> run's own persisted `export` path to confirm `download_document` still
> refuses it. **Not run:** uvicorn, a browser, the frontend.

**`backend/routes/runs.py`:**
- `start_run` now takes `scope: Caller` alongside `identity: Identity`.
  `owner = scope.profile_id` and the admin-sample-CV-fallback check now reads
  `scope.role`; `identity` is kept for exactly one remaining purpose —
  `token_id`, which `store.consume_run`/`refund_run` key on, since the
  allowance is the credential's property, not the account's (same reasoning
  as the `"2026-10-10 (identity)"` session's fix to this same route).
- `download_document` now calls `contained_path(config.OUTPUTS_DIR,
  export[fmt])` instead of its own inline `resolve()` + `root not in
  path.parents` check. **Not a behavior change** — that check was already
  correct, confirmed again this session — but it was the third independent
  copy of the exact containment logic in this package (after
  `routes/kb.py`'s `kb_file()` and the pre-fix `registry.load_log()`), and
  that's precisely the shape of drift this project has already been bitten
  by three times on a different table (`AGENTS`/`GATES`/`STUB_NODES` lagging
  the graph — October scoping pass). One shared implementation now backs
  all three call sites.

**Everything else in `routes/runs.py` deliberately left alone:** `run_events`,
`answer_gate`, `run_log` never pulled a field off `identity` themselves —
they pass it straight to `registry.owns()`, which already resolves ownership
by `profile_id` internally (fixed two sessions ago). There was nothing in
them for `Scope` to replace.

**What to run (yours):** nothing new flips. Same 28 pre-existing failures
(16 `test_backend_*`, 12 unrelated `test_vectordb.py` Chroma-naming issues)
as the last two sessions, confirmed identical before and after.

**What's left of §2, carried forward:** the admin cross-vault route
(`/api/admin/users/{profile_id}/...`) and its "write the audit entry first,
refuse if that write fails" rule. §5 (the log plane) is its hard
prerequisite — building the log plane is the natural next critical item
after this one.

---

## 2026-10-12 (log plane) — §5's `audit` kind built

> **Scope + authorship:** asked to build the next most critical open item,
> excluding anything needing heavy live testing, restricted to editing
> `backend/` only. §5 (the log plane) was the hard prerequisite the previous
> session named for finishing §2's admin cross-vault route, and its own
> design text splits cleanly into kinds backend owns (`audit`, `run`) versus
> kinds other lanes write into the same module (`llm`, `retrieval`,
> `system`). Built the `audit` kind in full; `run` is a separate, larger
> `backend/runs/worker.py` instrumentation pass, deliberately not done here
> (see "What's still open" below). Claude wrote it. Checked: `py_compile`,
> an import check, the full `test_backend_*` + `test_vectordb` suites
> before/after (identical 28 pre-existing failures, 267 passed, both times),
> and a scratch `TestClient` script exercising every route and the global
> handler end to end — isolation, fail-closed projection, correct
> `profile_id` attribution on an admin-performed action, and a direct check
> that no raw token ever reaches a log-plane file on disk. **Not run:**
> uvicorn, a browser, the frontend.

**New `backend/logplane.py`:** one append-only JSONL file per kind
(`config.BASE_DIR/logs/logplane/<kind>.jsonl` — already covered by the
existing blanket `logs/` gitignore entry, confirmed, nothing added there).
Append rather than `jsonstore`'s read-modify-write-replace: a log line is
O(1) to add and a crash mid-write can corrupt at most the last line, never
the history before it, which is the opposite trade of rewriting the whole
array on every single line. `write()` never raises into its caller's own
request — a failed log write must not fail the operation it was recording,
same stance `backend/routes/profile.py` already takes for a failed vector
embed. `query()` filters + paginates on `ts`; `for_user()` additionally
projects through `_USER_VISIBLE_FIELDS`, a per-event-type allowlist where
**an event with no entry is hidden from a non-admin entirely** — fail
closed, so a future event type can't leak a field just by being written and
forgotten about here.

**New `backend/routes/logs.py`:** `GET /api/logs/mine` (any caller, their
own entries, projected) and `GET /api/admin/logs` (admin only — 403, never
401, for anyone else, same discipline as every other admin route in this
package).

**Wired into `backend/routes/auth.py`:** `login_ok`/`login_failed`,
`request_access`, `request_more`, `request_approved`, `request_rejected`.
`actor` is one of `"account"` (the caller acting on their own behalf),
`"admin"` (approve/reject are inherently admin-performed), or `"anonymous"`
(a signup request or a login with no resolvable identity) — a pragmatic
reading of the design's three-category `actor` field for the case it didn't
explicitly cover (no account exists yet). `profile_id` on `request_approved`
is the **newly approved or topped-up account's own** id, read back off
`store.approve_request()`'s return value — not the approving admin's — so
that account sees "I was approved" in their own `/logs/mine`, confirmed by a
direct check in the scratch script (not just asserted from reading the
code).

**Wired into `backend/routes/runs.py`:** `document_downloaded` on a
successful `download_document` — this is the design's "export" audit
example.

**Wired into `backend/app.py`:** a global `HTTPException` handler that logs
`event="forbidden"` on every 403, app-wide, automatically — exactly the
design's "every 403" requirement, without hand-instrumenting each of the
several dozen ownership checks already in this package (and every one added
later, for free). Delegates to FastAPI's own default handler for the actual
response, so the response shape is unchanged — confirmed by asserting the
exact body on an existing 403 test case before and after.

**What's still open, and why it's not in this pass:**
- **`run` kind** — the design calls for it to cover run start/end, node
  timings, gate opened/decided, supersede/abort, allowance spent/refunded,
  run error. That's `backend/runs/worker.py` and `backend/runs/registry.py`
  instrumentation, a meaningfully larger and riskier change than a handful
  of one-line audit calls in request handlers — it touches the run
  lifecycle state machine directly. Left as its own next increment rather
  than rushed in alongside `audit`.
- **`llm`/`retrieval` kinds** — `agents/base.structured_call` (Pipeline
  Infra) and the retriever (KB+RAG), both outside `backend/`. This module's
  `write()`/`query()` already support any kind in `KINDS`, so either lane
  can start calling `logplane.write("llm", ...)` without this file changing
  again.
- **The admin cross-vault route** (`/api/admin/users/{profile_id}/...`)
  itself — `"2026-10-09 (design)"` §2's last open piece. Its audit-write-
  first DEPENDENCY now exists (`logplane.write("audit", ...)`); the route
  that would call it still doesn't.
- **Retention** (D-T4: audit 365 days, run/llm 90, retrieval/system 30) —
  no pruning job exists yet. Append-only files only grow; fine at Stage 0
  synthetic-data scale, not forever.

**A judgment call worth flagging, not a gap:** the design's entry shape
says `actor: the account, admin or system`, read here as three *categories*
rather than three *specific identifiers* (i.e., not "which admin", just
"an admin did this") — `fields`/`profile_id` already carry the specifics
that matter for the "who sees what" rules, which key on `profile_id` alone,
never on `actor`. "Anonymous" is this session's own fourth value, for the
case the three-category list didn't name (no account exists yet to be the
actor). Worth confirming this matches intent before more events get added
against it.

**What to run (yours):** nothing new flips. Same 28 pre-existing failures
(16 `test_backend_*`, 12 unrelated `test_vectordb.py` Chroma-naming issues)
as every session since 2026-10-10, confirmed identical before and after.

---

## 2026-10-12 (admin vault) — §2's last piece: the admin cross-vault route

> **Scope + authorship:** asked to build the next most critical open item,
> excluding anything needing heavy live testing, restricted to editing
> `backend/` only. This was the literal last open piece of the top 🔴
> (`"2026-10-09 (design)"` §2) — its audit-write-first dependency
> (`logplane.write`) already existed from the log-plane session, so this
> was the route itself, plus one small addition `write()` was missing to
> honour its own spec ("if that audit write fails, access is refused" —
> `write()` as built couldn't actually refuse anything, since it swallows
> every failure by design). Claude wrote it. Checked: `py_compile`, an
> import check, the full `test_backend_*` + `test_vectordb` suites before
> and after, and a scratch `TestClient` script exercising every route,
> including a forced write failure to confirm the refusal is real, not just
> asserted. **Not run:** uvicorn, a browser, the frontend.

**Worth noting up front:** by the time this session's own test run
finished, the backend test suite had gone fully green on its own — the
user updated `tests/test_backend_auth.py` and `tests/test_backend_api.py`
in parallel while this was being built (confirmed by file mtimes), closing
the `profile_id`/`kind` shape-pin failures and the CV-fixture gap flagged in
the last several sessions. **187 passed, 16 xfailed, 0 failed** across
`test_backend_auth.py` + `test_backend_api.py` + `test_backend_mode_isolation.py`
— the only remaining failures anywhere are the 12 pre-existing, unrelated
`test_vectordb.py` Chroma-collection-naming ones. Not this session's doing,
recorded here because it's the new, true baseline every session after this
one should compare against instead of the old "28 pre-existing failures"
figure repeated above and in several earlier entries.

**New `backend/routes/admin.py`:** `GET /api/admin/users/{profile_id}/profile`
and `GET /api/admin/users/{profile_id}/cv`, both admin-only. Each:
1. Resolves the target account's display name via the new
   `profiles.display_for(profile_id)` — **404, not 403**, if it doesn't
   match a real account (§2: only the admin can reach this route, so
   nothing leaks by refusing an unknown id the same way as a real one).
   This lookup is also the route's entire input-validation boundary: a
   `profile_id` only reaches a filesystem path afterward (`cv_store`'s
   `CV_UPLOADS_DIR/<profile_id>/`) once it has already matched one of the
   handful of server-generated `p-<8hex>` strings `profiles.json` itself
   minted — a path-traversal-shaped value just fails to match and 404s
   before ever touching the filesystem.
2. Writes `admin_data_access` to the audit log **first**, `critical=True`
   — see below.
3. Builds a `Scope(profile_id=<target>, role="user")` — deliberately
   `role="user"`, not the caller's own `"admin"`, since this scope
   describes *whose* vault to open, not who's opening it; passing the
   caller's real role through here would make `visible_entries()` return
   *everyone's* entries instead of this one targeted account's.
4. Reuses `backend/routes/profile.py`'s `visible_entries()` and
   `backend/cv_store.py`'s `current_summary()` unchanged — no new storage
   logic, just a new, audited way to point the existing ones at someone
   else's account.

**`backend/logplane.py` gained the one thing it was missing to make §2's
"refuse on audit-write failure" real:** `write(..., critical: bool = False)`.
Every existing call site keeps today's behaviour (never raise into the
caller's request) by leaving it `False`; `admin.py`'s two routes pass
`critical=True`, so a failed write re-raises instead of being logged and
swallowed, and the route turns that into a 503 rather than silently letting
the access through unaudited. Checked directly: broke the log directory on
purpose and confirmed `critical=True` raises while `critical=False` on the
exact same broken path does not.

**New `backend/auth/profiles.py` function:** `display_for(profile_id)` — the
reverse of the existing `profile_for(identifier)`, and (see above) doing
double duty as the route's path-traversal guard.

**Deliberately not built: `GET /api/admin/users/{profile_id}/runs`.**
`GET /api/runs` already shows the admin every run with full content,
unaudited (`registry.list_for`) — the design's own open decision D-T2 is
explicitly whether to keep that or replace it with an audited, per-account
route, and building one here would have answered that decision by default
instead of leaving it for the user to make. `RunsView.jsx`'s existing
behaviour is untouched either way.

**Two real bugs this session's own code introduced, caught by the user's new
tests while verifying this round (not asked for, not written here — just
fixed once they surfaced a real defect in code from this same session):**

1. `logplane.write()` serialised its entry *inside* an already-open file's
   `.write()` call, so an unserialisable `fields` value (a caller's
   mistake) still created the log directory and an empty `<kind>.jsonl`
   before the `TypeError` fired — contradicting `write()`'s own contract of
   leaving nothing behind on a failed write. Fixed by serialising to a
   string first, opening nothing until that succeeds. Confirmed directly:
   the same failing input now leaves `LOG_DIR` itself unlinked, not just
   "an empty file in it".
2. `admin_data_access` (this session's own new event, `admin.py`) had no
   entry in `_USER_VISIBLE_FIELDS`, so fail-closed hid it from the very
   account it's about. Added, visible with `resource` only — deliberately
   shown rather than hidden: a user should be able to see *that* an admin
   opened their vault, just not *which* admin (`actor` is never included by
   `_project()`) or anything from the access's own content.

**What to run (yours):** nothing flips from this session specifically, net
of the two fixes above. See "Worth noting up front" above for the
actually-new baseline.

---

## 2026-10-13 (restart survival) — "gate 4" §7 built: a parked run survives a server restart

> **Scope + authorship:** asked to build the most important open item,
> restricted to editing `backend/` only. The top 🔴 (scope into the graph)
> is explicitly not backend's to build alone; this was the next-ranked 🟠,
> and Stage 0's exit criteria name "restart survival" explicitly. Claude
> wrote it. Checked: `py_compile`, an import check, the full
> `test_backend_*` suite before/after, and two scratch scripts — one against
> the **real** LangGraph + SqliteSaver stack (not a stub): parked a run at
> gate 1, closed its connection to simulate a crash, recovered the pending
> interrupt cold on a brand-new connection, and resumed it via
> `Command(resume=...)` through to gate 2. **Not run:** uvicorn, a browser,
> the frontend.

**`backend/runs/worker.py`:** a new `_persist()` saves the run log the
moment a gate opens (`_park`), not only at the end — before this, a run
parked at any gate had **no log on disk at all**, so a restart while a human
was slow to answer lost it with nothing to resume from. `gate_info(payload)`
factors the `run["gate"]` shape out of `_park` so it can be computed before a
worker thread even exists. `pending_interrupt(run_id)` reads a thread's
parked interrupt straight off a fresh checkpointer connection — the same
technique `scripts/run_gated_graph.py` already uses from the CLI.
`run_worker_resume` re-enters the drive loop at `resuming=True` instead of
rebuilding `GraphState`, skipping straight to `_await_answer` for the first
gate rather than re-`_park`-ing it: re-parking would both duplicate the
`gate_wait` event already on disk from before the crash, and silently drop
an "answered" flag if a POST had already raced in before the resumed thread
got scheduled.

**`backend/runs/registry.py`:** new `resume(run_id, identity)` — loads the
saved log, checks ownership, then does every state-changing step under the
same `owner_lock` `start()` already uses (closing a TOCTOU window where a
concurrent `start()` could install a run into `_active[owner]` that
`resume()` then silently clobbers). Installs `run["gate"]`
**synchronously, before the worker thread is even started** — so
`POST .../gate` is answerable the instant `resume()` returns, not only once
that thread gets scheduled and reaches the same computation itself, which on
a cold process can be the ~20s embedding-model load. `list_for` now reports
`interrupted: true` for a run whose last persisted event is `gate_wait` with
no live worker driving it — RunsView/Account use this to show a Resume
action. `save_log` now persists `pace` too (read via `.get()`, not the hard
`run[k]` every other field uses — a hand-built run dict, e.g. in tests,
doesn't need to carry it).

**`backend/routes/runs.py`:** new `POST /api/runs/{run_id}/resume`, mapping
`KeyError→404`, `PermissionError→403`, `RuntimeError→409`, with a
`logplane.write("audit", event="run_resumed", ...)` on success (`"run_resumed"`
added to `logplane._USER_VISIBLE_FIELDS` so the owner can see it in their own
`/api/logs/mine`).

**What to run (yours):** `test_the_route_table_is_exactly_the_classified_routes`,
`test_a_saved_run_log_keeps_exactly_its_record_fields` and
`test_list_for_scopes_by_profile_and_sorts_newest_first` now fail — all
three are exhaustive-set guards that need the new route (`resume`) and the
new `pace`/`interrupted` fields added to their own expected sets, by design
(the same class of failure the route-table test is written to force on
purpose). No other regressions: same failures before and after everywhere
else.

---

## 2026-10-13 (saved CVs) — "gate 4" §5b/§5c built: a list and a delete

> **Scope + authorship:** asked to build the most important open item again
> immediately after the one above, same constraints (backend/ only). This
> was the next-ranked 🟠. Part (a) of §5 — moving `OUTPUTS_DIR` onto a
> mounted volume so it survives a redeploy — is a `docker-compose.yml`
> change, outside `backend/`, and is not built here. Claude wrote it.
> Checked: `py_compile`, an import check, the full `test_backend_*` suite,
> a scratch script calling `registry.delete_document` directly against a
> hand-built run log (wrong owner refused, unknown run refused, files
> actually removed, `export` nulled + `export_deleted_at` stamped on disk,
> a second delete correctly refused), and a second scratch `TestClient`
> script driving the real HTTP routes end to end (403 for another account,
> 404 for an unknown run, 204 on delete, the files gone from disk, a
> re-download 404ing, `list_for`'s `saved` flipping to `false`, a second
> `DELETE` 404ing, and the `document_deleted` audit entry visible via
> `GET /api/logs/mine`). **Not run:** uvicorn, a browser, the frontend.

**`backend/runs/registry.py`:** `list_for`'s summaries gained `review`
(gate 4's verdict dict, or `null` if the run never reached it) and `saved`
(`bool`), read straight off the already-loaded `run_done` event — no new
route needed, matching the design's own note that this didn't need one.
New `delete_document(run_id, identity)`: finds the current export off
whichever record is available (the in-memory one if the run is still live,
else the saved log), unlinks both files under `OUTPUTS_DIR` via
`contained_path()`, then nulls `final.export` and stamps
`final.export_deleted_at` on the `run_done` event — **in memory** (if a
record is still live) **and on disk**, through the existing
`backend/jsonstore.update_json` lock. Raises `KeyError`/`PermissionError`/
`RuntimeError` for unknown/not-mine/nothing-saved, same shape as `resume()`
above.

**`backend/routes/runs.py`:** new `DELETE /api/runs/{run_id}/document`,
204 on success, mapping `KeyError→404`, `PermissionError→403`,
`RuntimeError→404` (same "deleted" and "never saved" are indistinguishable
on the wire as every other not-found here), with a
`logplane.write("audit", event="document_deleted", ...)` on success
(`"document_deleted"` added to `logplane._USER_VISIBLE_FIELDS`).

**Not built, flagged rather than silently skipped:** part (a) (the mounted
volume) and part (d)'s original concern (the owner key) — (d) is now moot:
`<owner>` has been `profile_id`, not a token id, since the 2026-10-10
identity migration, which already survives a token re-issue.

**What to run (yours):** same three exhaustive-set guard failures as the
restart-survival session above, now also including `saved`/`review` in the
`list_for` shape-pin assertion's missing set. No other regressions.

---

## 2026-10-14 (log plane, run kind) — §5's `run` kind built

> **Scope + authorship:** asked to build the most important open item again,
> same constraints (backend/ only). With restart survival and saved CVs
> closed, this was the next-ranked 🟠: `run`/`llm`/`retrieval` kinds of
> `"2026-10-09 (design)"` §5, of which `run` is explicitly backend's own
> (`backend/runs/worker.py` instrumentation; `llm`/`retrieval` are other
> lanes' writes into the same already-generic module). Weighed against the
> other remaining 🟠 (`routes/runs.py` not on `Scope`) and judged more
> important: that one turned out, on rereading the file's own module
> docstring, to already be argued as not a live gap — every route there but
> `start_run` only ever hands `identity` to `registry.owns()`, never pulls a
> field off it directly, so there's nothing for `Scope` to replace. `run`
> kind, by contrast, is a named, concrete, unbuilt capability directly tied
> to Stage 0's "the audit trail" exit criterion. Claude wrote it. Checked:
> `py_compile`, an import check, the full `test_backend_*` suite before/after
> (identical to the 2026-10-13 baseline: same 3 exhaustive-set guard
> failures, no new ones), and two scratch `TestClient` scripts against the
> real worker code (stub graph for one, a no-op stream for the other) — one
> driving a full run through all 4 gates and asserting every `run`-kind
> event fires exactly once per occurrence, is scoped to the right
> `profile_id`/`run_id`, carries no typed text on `gate_decided`, and
> projects correctly (and only the allowlisted fields) through
> `GET /api/logs/mine`; the other confirming `allowance_spent`/
> `allowance_refunded` fire for a non-admin account and not for admin, and
> that a 403 from an exhausted allowance logs nothing extra. **Not run:**
> uvicorn, a browser, the frontend.

**`backend/runs/worker.py`:** new `_log_run(run, event, **fields)` — one
`logplane.write("run", ...)` call, `actor="account"` throughout (every event
here is either a direct account answer or a consequence of a run that
account started), `profile_id=run["owner"]`, `run_id=run["id"]`. Wired at
six points, matching the design's example list exactly:
- `run_worker`: `run_started`, alongside the existing SSE `run_started`
  event (fields: `mode`).
- `_drain`/`_emit_routing`: `node_done`, with a `duration_s`. `_emit_routing`
  now returns the node it just announced so `_drain` can record a start
  time (`time.monotonic()`) keyed by node name, read back when that node's
  own update arrives. Nodes run strictly sequentially in this single-
  threaded stream, so one dict entry at a time is enough — no node ever
  starts before the previous one's `node_done` fires. The raw elapsed time
  is reduced by `run["pace"]` before logging: the same update that carries
  `node_done` already paid one `time.sleep(run["pace"])` earlier in the
  same loop iteration (every update does, for UI presentation pacing), so
  logging the raw delta would report every node as taking "at least
  `pace_seconds`" regardless of real work — actively misleading for an
  observability log whose whole point is real durations. Clamped at 0.0 for
  the inevitable timing jitter at small paces.
- `_park`: `gate_opened` (fields: `gate`). Not re-logged on a resumed run's
  first gate, for the same reason `_park` itself isn't called there (it was
  already logged before the crash this run just resumed from).
- `_await_answer`: `gate_decided` (fields: `gate`, `decision` — **the
  decision only**, matching §5's content rule word for word: `feedback`,
  `gap_answers` and the edited CV text never reach this call).
- `_run_loop`: `run_done` (fields: `approved`, read off `close_run`'s own
  `review.approved` so the log doesn't need to re-derive gate 4's verdict a
  second way) and `run_stopped` (fields: `reason="superseded"` — the only
  way `_run_loop` currently reaches this branch).
- `_drive`'s except clause: `run_error` (fields: `error`, the same short
  `f"{type(exc).__name__}: {exc}"` string the existing SSE `run_error` event
  already carries — never a traceback, since nothing in this codebase's
  `run_error` path captures one to begin with, confirmed by reading it
  rather than assumed).

**`backend/routes/runs.py`:** `start_run` now writes `allowance_spent`
(fields: none beyond the standard `profile_id`/`run_id`) right after
`registry.start()` succeeds, and `allowance_refunded` in the existing
`except Exception: store.refund_run(...)` branch — both gated on a new
`spent` flag so an admin start (which never calls `consume_run`) logs
neither, matching what actually happened rather than a blanket write.

**`backend/logplane.py`:** nine new entries in `_USER_VISIBLE_FIELDS` —
`run_started`, `node_done`, `gate_opened`, `gate_decided`, `run_done`,
`run_stopped`, `run_error`, `allowance_spent`, `allowance_refunded` — each
allowlisting exactly the fields §5's "who sees what" table names as
run-kind-visible (node/gate names, a decision, a duration, an error
*message*, an approval flag, a supersede reason), confirmed by direct
projection check in the scratch script rather than just read off the code.

**A judgment call worth flagging, not a gap:** §5's `actor` field is
specified as "the account, admin or system"; every write here uses
`"account"`, including `run_stopped` (a run getting superseded is a
consequence of the *same* account starting a new one, not something the
system did independently of them) and `node_done`/`run_error` (consequences
of a run that account owns, even though no single click of theirs produced
that exact event). Same reading the 2026-10-12 log-plane session already
applied to `audit`-kind events; recorded here again since it now also
governs a different kind.

**Not built, flagged rather than silently skipped:**
- **`llm`/`retrieval` kinds** — `agents/base.structured_call` (Pipeline
  Infra) and the retriever (KB+RAG), both outside `backend/`. Nothing here
  needs to change again for either to start writing: `logplane.write()`
  already accepts any kind in `KINDS`.
- **A per-run `run`-kind view** (`GET /api/runs/{id}/retrievals`'s sibling
  for this kind) — not asked for by this row, and §5 doesn't name one
  either; `GET /api/logs/mine?run_id=...` already does the job generically.
- **Retention/pruning** — unchanged from the 2026-10-12 log-plane session's
  own note: append-only growth is fine at Stage 0 scale, not forever.

**What to run (yours):** same 3 exhaustive-set guard failures as every
session since 2026-10-13 (`test_the_route_table_is_exactly_the_classified_routes`,
`test_a_saved_run_log_keeps_exactly_its_record_fields`,
`test_list_for_scopes_by_profile_and_sorts_newest_first`). No other
regressions; nothing in this session touched a route table, a run-log
shape, or `list_for`'s own summary fields.

---

## 2026-10-15 (gate name on `gate_done`) — `"Round 8-10"` §3's "finish item 3" built

> **Scope + authorship:** asked to build the most important open item again,
> same constraints (backend/ only). Of the two remaining backend-buildable
> 🟠s (this one and the unmatched-CV-line count), this ranked above it in
> the file's own list. Checking first against the live code rather than
> trusting the ranked row's one-line description: `gate_wait` already
> carried `gate`, `GateAnswer.gate` and `answer_gate`'s 409 stale-answer
> check were already built (an earlier session's work, not dated in this
> row) — the entire remaining gap was the one field this entry names.
> Claude wrote it. Checked: `py_compile`, an import check, the full
> `test_backend_*` suite before/after (identical to the 2026-10-14
> baseline), and a scratch `TestClient` script driving a stub run through
> two real gates: a stale answer naming gate 1 while gate 2 is open still
> 409s (that path was already built and still works), and the saved log's
> `gate_done` events now carry `gate1_requirements`/`gate2_evidence` in the
> same order as their `gate_wait` counterparts, never `null`. **Not run:**
> uvicorn, a browser, the frontend.

**`backend/runs/worker.py`:** one field. `_await_answer`'s `emit(run,
"gate_done", ...)` now includes `gate=gate["gate"]`, the same value
`_park`'s `gate_wait` emit already carries. `gate` was captured into a
local at the top of `_await_answer` before this (`gate = run["gate"]`,
needed for `gate["after"]` regardless), so this cost nothing beyond
reading it a second time.

**Not touched, because already built:** `GateAnswer.gate: str | None`
(`backend/routes/runs.py`) and `answer_gate`'s `409` on a mismatch — both
already present in the live code, confirmed by reading it rather than
assuming the ranked row's description was current. This entry closes
exactly what the row said was still open and nothing else.

**Still open, deliberately not touched here:** the `revision`/
`max_revisions` half of `"gate 4"` §3 (the UI's "this reject ends the run
unsaved" warning) — needs a line in `utils/human_gate.py` first, the
Agents lane, per that section's own note ("the worker needs nothing,
because extras pass through" once it exists).

**What to run (yours):** same 3 exhaustive-set guard failures as every
session since 2026-10-13. No other regressions; this touched one emit call
and nothing else.

---

## 2026-10-15 (match counts) — `"CV upload (later)"` §5 built

> **Scope + authorship:** asked to build the most important open item
> again, same constraints (backend/ only). Picked this one first, before
> rechecking the ranked table against the newer `"2026-10-14 (frontend,
> Rounds 27–42)"` entry — see the next section's own note for what changed
> once that check happened. Built and verified in full regardless; kept,
> not reverted, since it is correct, small and independently useful.
> Claude wrote it. Checked: `py_compile`, an import check, the full
> `test_backend_*` suite before/after (identical to the 2026-10-15 gate-name
> baseline), and a scratch `TestClient` script driving a stub run with a
> hand-built, mixed `line_links` list (1 matched, 1 partial, 2 unmatched)
> through to gate 3, confirming the `cv_link` `node_done` event carries
> exactly `{"matched": 1, "partial": 1, "unmatched": 2}` and that no other
> node's `node_done` carries the field at all. **Not run:** uvicorn, a
> browser, the frontend.

**`backend/runs/worker.py`:** new `_match_counts(line_links)` - a plain
tally over `state/state.py`'s three current `MatchStatus` values
(`matched`/`partial`/`unmatched`; `contradicted` isn't one yet). Wired into
`_drain` only for the `cv_link` node, as a top-level `match_counts` field on
that one `node_done` event (sibling of `artifact`/`stub`, not nested inside
`artifact` - it's a derived summary, not new state). Put at `cv_link`
rather than `run_done` (the row's own parenthetical alternative): it's
available far earlier, and the frontend already carries earlier `node_done`
artifacts forward to later gate screens (gate 4 is where the row says this
should warn), so nothing new is needed on the consuming side to reach it.

**What to run (yours):** same 3 exhaustive-set guard failures as every
session since 2026-10-13. No other regressions.

---

## 2026-10-15 (final on run_error too) — `"2026-10-14 (frontend, Rounds 27–42)"` A1 built

> **Scope + authorship:** asked to build the most important open item
> again. Built the match-counts item above first, then re-read the full
> current ranked table before stopping - it had gained a new row since the
> last session (`"2026-10-14 (frontend, Rounds 27-42)"` A1, added by the
> frontend lane, no ✅ yet) that outranks match counts on actual impact: a
> real correctness bug in three routes this same lane built across the last
> two sessions (`download_document`, `delete_document`, `list_for`'s
> `saved`/`review`), not a missing proactive warning. Built this one too,
> same session, rather than leave it for a future "most important" prompt
> to rediscover. Claude wrote it. Checked: `py_compile`, an import check,
> the full `test_backend_*` suite before/after (identical baseline), and a
> scratch `TestClient` script against a hand-built run log whose *only*
> terminal event is `run_error` (carrying an approved, exported `final`,
> exactly `"gate 4"` §2's shape) - confirming `list_for` reports
> `saved: true`/`review.approved: true`, `GET .../document` serves the file
> (200, not 404), `DELETE .../document` removes it (204) and nulls the
> export **on the `run_error` event itself** (`export_deleted_at` stamped
> there, not on a `run_done` that was never written), and a second
> `list_for` call afterward correctly reports `saved: false`. **Not run:**
> uvicorn, a browser, the frontend.

**The root cause, confirmed by reading, not assumed:** `worker._drive`'s
`except` clause calls the same `_close()` → `close_run()` as the clean
path, specifically so a step failing after gate 4 approved doesn't lose the
CV (`"gate 4"` §2, already built) - and attaches the result to `run_error`.
Three readers had only ever checked `run_done` for it.

**`backend/runs/registry.py`:** `_find_run_done` is now `_find_final_event`,
matching `(run_done, run_error)` instead of `run_done` alone. New public
`current_export(record)` wraps it - the **one** place this lookup lives
now, exported so `routes/runs.py` doesn't need its own copy (a second,
independently-maintained copy of the same lookup is exactly how A1 happened
in the first place - one reader, `delete_document`'s `_strip_export`, was
already correct-by-construction through the shared private helper;
`download_document` and `list_for` were the two that had each grown their
own). `_strip_export` and `list_for` now go through the renamed/shared
lookup, so both pick up the fix with no logic change of their own beyond
the rename.

**`backend/routes/runs.py`:** `download_document` drops its own inline
`next(... "run_done" ...)` traversal entirely in favour of
`registry.current_export(record)`.

**Deliberately not touched:** `list_for`'s `completed` flag, which still
checks `run_done` only. That's the separate, already-tracked 🟡 item ("no
`outcome`/`error` field, so a crashed run reads identically to a superseded
one") - A1 names `final`/`export`/`review` specifically, not `completed`,
and conflating the two risks fixing one thing by half-fixing a different
one.

**What to run (yours):** same 3 exhaustive-set guard failures as every
session since 2026-10-13. No other regressions.

---

## 2026-10-15 (outcome field) — `"2026-10-08"` §5 / `"Round 8-10"` §7 built

> **Scope + authorship:** asked to complete the fix of the next most
> critical item, continuing the same session. With every remaining 🔴/🟠
> either blocked on another lane or already judged not a live gap (see
> their own rows' notes), this was the top of the 🟡 tier and the older of
> its two halves — the companion "round number on `gate_wait`" half of the
> same two-field ask is the part still blocked on `utils/human_gate.py`
> (the Agents lane), tracked separately in the 🟠 table. Claude wrote it.
> Checked: `py_compile`, an import check, the full `test_backend_*` suite
> before/after (identical baseline - the one new failure that appeared
> this session, `test_every_call_the_frontend_makes_has_a_backend_route_with_that_method`,
> predates this fix too; confirmed unrelated, see the previous session's
> note), and a scratch script writing four hand-built run logs - one each
> ending `run_done`, `run_error`, `run_stopped`, and parked mid-`gate_wait`
> - confirming `list_for` reports `outcome` as `"done"`, `"error"`,
> `"stopped"` and `null` respectively, with `completed`/`interrupted`
> unchanged alongside it. **Not run:** uvicorn, a browser, the frontend.

**`backend/runs/registry.py`:** a four-entry `_OUTCOME` map
(`run_done`→`"done"`, `run_error`→`"error"`, `run_stopped`→`"stopped"`) and
one new field on `list_for`'s summary, `outcome: _OUTCOME.get(last_type)`
- `last_type` was already computed for the `interrupted` field, so this
cost nothing to derive. `None` for a run still in progress, including one
parked at an open gate (that's `interrupted`, a different question: *has
it ended*, not *why*).

**Deliberately additive, not a replacement:** `completed` is untouched -
still `any(type == "run_done")`, exactly what it always meant. The ranked
row asked to stop a crashed run reading *identically* to a superseded one,
not to redefine what "completed" means to whatever already consumes it.

**What to run (yours):** same 3 exhaustive-set guard failures as every
session since 2026-10-13 (now 4, counting the unrelated one noted above).
No other regressions.

---

## 2026-10-15 (legacy token collision) — `bugs_audit_fixed.md` #68 item 1 fixed

> Backend API + Auth, Claude, on the user's grant ("fix the bug, one at a
> time"). Written in `backend/auth/store.py` only. Checked by `py_compile` +
> `import backend.auth.store`. **Not run:** pytest, uvicorn, any request.

**The bug.** `resolve_token` backfills `profile_id` onto a pre-10-10 token
lazily, by name, through `get_or_create_profile`. Until that token is next
used it has no `profiles.json` row, so approving a new request whose name
normalises the same ("Jane" → "JANE") passed `create_profile`'s collision
check and minted a fresh profile. The legacy holder's next login then
backfilled onto *that* profile: two people, one account, each seeing the
other's runs, CVs and Build-Profile entries.

**The fix.** New `_name_held_by_a_token(identifier)`. Under `_LOCK`, it
normalises the request's name and every `tokens.json` identifier, and returns
True on a match. The signup branch of `approve_request` calls it before
`create_profile` and raises `AuthError("An account already exists for that
name.")`, which the route already turns into a 409.

- **Why refuse rather than split.** It's the same answer approval already
  gives once the legacy token *has* been backfilled. The outcome no longer
  depends on whether the old holder happened to log in first.
- **No race with the backfill.** The check reads `tokens.json`, which holds
  the legacy record whether or not it's been backfilled yet. Both paths
  serialise on `store._LOCK`.
- **Lock order** is store → profiles in `approve_request`. `_with_profile_id`
  takes profiles, releases it, then takes store, so the two never nest the
  other way.
- **Names that can't be normalised.** A token name the rule now refuses
  (#70 item 1's case) is skipped: it can never equal a name that passes the
  rule. A request name that fails the rule returns False here, so
  `create_profile` still refuses it with its own, specific reason.

**Test impact (the user's).**
`test_a_legacy_token_never_lands_on_a_newer_account_with_the_same_name` is a
strict xfail that expects `_user("JANE")` to *succeed* with a distinct
profile. Under this fix that approval raises `AuthError`, so the test still
"fails" (it stays xfailed) for a reason that's now outdated. Suggested rewrite:
drop the xfail; `pytest.raises(store.AuthError)` around `_user("JANE")`; then
`resolve_token("LEGACY-JANE")` gets a fresh `p-<8hex>` and `len(_profiles()) == 1`.

**Not touched (still open in #68 / #70):**
- Two *legacy* tokens whose names normalise the same still merge onto one
  account at backfill. That's a migration decision, not this bug.
- The request queue still doesn't normalise (#68 item 2).
- A legacy token under a now-refused name still 500s (#70 item 1).

---

## 2026-10-15 (manual_entries case variant) — `bugs_audit_fixed.md` #69 item 1 fixed

> Backend API + Auth, Claude, on the user's grant. `backend/routes/kb.py`
> only. Checked by `py_compile` + `import backend.routes.kb`. **Not run:**
> pytest, uvicorn, any request.

**The bug.** `kb_file` applied Build Profile's owner scope only when the
resolved path *equalled* `_MANUAL_ENTRIES_RESOLVED`. On macOS (APFS is
case-insensitive, and `resolve()` keeps the typed case),
`GET /api/kb/profile/MANUAL_ENTRIES` existed, was inside the store, was not
equal, and fell through to a bare `read_json` — every account's entries to
any authenticated caller. Linux 404'd, so the deploy target was safe, but a
dev or demo box on a Mac wasn't.

**The fix, two layers:**
1. **Exact on-disk names only.** `kb_file` now takes the file from the
   store's own `glob("*.json")` listing, matching `f.stem == file`
   case-sensitively, so any case variant 404s on every OS. The same lookup
   also means no traversal: a `..` or `/` can never equal a listed stem. The
   `is_relative_to(store_dir)` check stays, against a symlink inside the
   store that points out.
2. **Scope by same file, not same spelling.** New `_is_manual_entries(path)`
   uses `os.path.samefile(path, _MANUAL_ENTRIES_RESOLVED)` (False if either
   side is missing). It's used in both `kb_file` and `kb_overview`'s
   `_record_count`, so a symlink or hard link onto the file is scoped as
   well. It reads the module global at call time, so the test fixture's
   existing patch of `kb_routes._MANUAL_ENTRIES_RESOLVED` still applies.

No wire change: the exact name `/api/kb/profile/manual_entries` and every
other file serve as before.

**Test impact (the user's).** `test_no_spelling_of_manual_entries_skips_the_owner_scope`
is `xfail(_case_insensitive_fs(), strict=True)`. On macOS it now gets a 404 →
XPASS → a strict-xfail failure. Remove the marker; the assertion itself
(`404 or "alice-only" not in resp.text`) is already right. The traversal
tests (`test_the_kb_browser_never_serves_outside_its_stores_over_http`) should
still 404.

**Not touched (still open in #69):** item 2 (an unknown Build-Profile
`section` is stored but never indexed) and item 3 (a `?token=` 403 is
audited as anonymous).

---

## 2026-10-15 (search boundary) — `bugs_audit_fixed.md` #45 (and #64 item 4) fixed

> Backend API + Auth, Claude, on the user's grant. `backend/routes/kb.py`
> only. Checked by `py_compile`, `import backend.routes.kb`, and building
> `SearchRequest` with good and bad values. **Not run:** pytest, uvicorn,
> any request, the vector store.

**The bug.** `SearchRequest` was `{query: str, collection: str, k: int}` with
no bounds, so any token holder could:
- name any collection. Before 10-14 that created an empty one in the real
  index. Since the KB lane's store fix it raises `CollectionNotFound`, which
  reached the client as a **500**.
- send `k ≤ 0`, which makes Chroma raise `TypeError` (a 500), or a huge `k`.

**The fix:**
- `collection: Literal["profile", "documents", "learning"]` (alias
  `Searchable`). It's the same set as the frontend's `SearchPanel` options
  and `vectordb.ingest.COLLECTIONS`; anything else is a 422. **Why an
  allowlist** and not just the 404: Stage 0 puts one collection per profile
  into this same index, and a free name would then let any user search
  another user's vault.
- `k: Field(5, ge=1, le=50)`.
- `query: Field(min_length=1, max_length=2000)`. The same input-boundary
  discipline as #37: the string is embedded on every call. The frontend
  already blocks an empty query.
- `search()` catches `CollectionNotFound` and returns a **404**, "The
  '<name>' index hasn't been built yet." That covers a listed but unbuilt
  collection, such as `learning` on a fresh deploy. The import is local, so
  module import stays light (chromadb isn't loaded at boot).

No wire change for the frontend: it sends `{query, collection ∈ the three,
k: 5}`.

**Test impact (the user's):**
- `test_vectordb.py::test_search_refuses_a_non_positive_k_before_the_store`
  (strict xfail, `raises=TypeError`) now gets the `ValidationError` it
  already accepts, so it XPASSes. Remove the marker.
- `test_vectordb.py::test_the_search_route_returns_the_store_hits_in_its_wire_shape`
  builds `SearchRequest(collection="kb_test")`, which now fails validation.
  Seed and search an allowed name (`"profile"`) in the in-memory store.
- `test_a_read_never_creates_a_collection[api_search]` uses `"never_built"`.
  It now fails at validation, which the test's `except Exception` already
  allows, so it still passes.
- `test_backend_api.py`'s `/api/search` tests send `{}`, `k: "five"` (both
  still 422) and `collection: "profile", k: 5` (unchanged).

**Not touched:** `/search` is still unscoped *within* the shared `profile`
collection. That's design §3 / §4, the vector-metadata work.

---

## 2026-10-15 (legacy token lockout) — `bugs_audit_fixed.md` #70 item 1 fixed

> Backend API + Auth, Claude, on the user's grant ("fix the most critical bug
> listed"). `backend/auth/profiles.py` + `backend/auth/store.py` only. Checked
> by `py_compile`, `import backend.app`, a 45-assertion scratch script against
> a tmp `KB_AUTH_DIR` (never `knowledge_base/auth/`), a direct reproduction of
> the pre-fix 500, and the full `test_backend_*` suite with the fix reverted
> and then restored. **Not run:** uvicorn, a browser, the frontend.

**Why this one.** Every remaining 🔴/🟠 in the ranked table above is blocked on
another lane or already argued as not a live gap. Of what's left to this role,
this outranks its own 🟡 label on the file's own ordering (someone else's data
in the wrong account → a cross-user read → lasting damage to shared state → a
500 or lockout): it is a **total, silent lockout of a valid credential**, where
every other candidate is a narrower 500 or a cosmetic gap. It is live rather
than theoretical, too — 5 of the 10 records in the real `tokens.json` still
carry no `profile_id`, so every one of them takes the lazy-backfill path on
next use.

**The bug.** `resolve_token` backfills `profile_id` onto a pre-10-10 token
through `profiles.get_or_create_profile`, which applies
`normalise_identifier`. That rule is newer than the tokens it gets applied
to, so a token approved under a reserved name (`admin`/`system`/`root`), a
name holding `:`, or a name that casefolds past `MAX_IDENTIFIER`
(`create_request` measures the raw string, so 40×`"ß"` queues at 40 chars and
then doubles to 80) raises `ProfileError`. Nothing caught it, so it escaped
`resolve_token` uncaught and became a **500** — where `deps.py` promises 401
only for an *unknown* token, and this one is known. Reproduced before fixing,
by restoring the old `_with_profile_id` body verbatim and driving the real
app: `GET /api/auth/me` → 500, `POST /api/auth/login` → 500,
`GET /api/runs` → 500. The holder gets no explanation and cannot reach their
runs, CV or entries.

**The fix.** New `profiles.get_or_create_system_profile(key, display)`: an
idempotent lookup-or-create that takes its uniqueness key **verbatim** and
refuses any key without a `:`. That one character is the whole guarantee —
`normalise_identifier` rejects `:` in typed input, so a system-keyed account
can never be collided with, or taken over by, anything a human types at
`request-access`. It builds its row through the existing `_new_record`, so
there is still exactly one place that shapes a profile row.

`store._with_profile_id` now catches `ProfileError` and falls back to
`get_or_create_system_profile(f"legacy:{record['id']}", identifier)`.

- **Why keyed on `token_id`, not the name:** the name is precisely what can't
  be used. `token_id` never changes for an existing record, so the account is
  stable and the fallback runs once — the row is then written back onto the
  token like any other backfill.
- **Why not refuse (#68 item 1's answer):** that was right for an *approval*,
  where the typed name is the input being judged. Here the credential is
  already approved and sitting in `tokens.json`; the only two outcomes are
  "give it an account" or "lock a legitimate holder out".
- **Why not eager backfill at startup** (the recorded alternative):
  `normalise_identifier` would raise there instead, turning one holder's
  lockout into a boot failure for everyone.
- **Lock order unchanged:** profiles → (release) → store, exactly as
  `_with_profile_id` already did, so this still can't nest against
  `approve_request`'s store → profiles order.
- **`record.get("identifier", "")`** replaces `record["identifier"]`: a token
  record missing that field raised `KeyError` — the same 500-lockout shape,
  one line earlier. It now normalises to `""`, fails the rule, and takes the
  legacy path.
- **One `log.warning` per affected token** (new `logging` import; stdlib only,
  so the module stays FastAPI-free and sub-second to boot). A fallback that
  silently keys an account differently shouldn't be invisible. Deliberately
  **no** log-plane entry: `auth/store.py` is pure file I/O by design, and
  importing `logplane` for one line isn't worth the coupling — flagged here
  rather than decided alone.

**Checked, beyond the happy path:**
- All four refusal shapes (reserved, `:`, casefold overflow, empty) resolve,
  stay stable across calls, persist to `tokens.json`, create exactly one
  `profiles.json` row keyed `legacy:t-…`, and keep the raw name as `display`
  so the admin can still recognise the account.
- `profile_for("admin")` does **not** find the legacy account — unreachable by
  typed name, which is the point of the `:`.
- A normal legacy name still backfills **by name** (`"Jane  DOE"` →
  `jane doe`), so the ordinary path is untouched.
- **No takeover path opened:** with a legacy `jane:doe` token already
  backfilled, a fresh `request-access` for `jane:doe` is still refused at
  approval (`Name may not contain ':'`), and #68 item 1's guard still refuses
  `JANE DOE` against a legacy `Jane Doe`.
- **Two** unnormalisable legacy tokens get **separate** accounts, not one.
  That's the fail-safe direction (it never merges two people), and it leaves
  #70's "two legacy names that normalise the same get merged" note exactly as
  it was — that case needs a normalisable name, which this path never sees.
- An actually-unknown token is still **401**, not swept up by this.

**Test impact (the user's).** The four strict xfails pinning this item now
XPASS, so they report as failures until their markers come off — that is the
fix landing, confirmed by your tests and not only by mine:
- `test_backend_auth.py::test_a_legacy_token_whose_name_the_new_rule_refuses_still_resolves`
  (`reserved`, `colon`, `casefolds-past-64`)
- `test_backend_api.py::test_a_legacy_token_under_a_name_the_new_rule_refuses_can_still_sign_in`

Worth adding while there: that two unnormalisable legacy tokens stay separate
accounts, and that `profile_for` can't reach a system-keyed one.

**What to run (yours).** Full `test_backend_*` run with the fix reverted and
then restored: `20 failed, 529 passed, 42 xfailed` → `24 failed, 529 passed,
38 xfailed`. The set diff is **exactly** the four xfails above, nothing else.
The 20 pre-existing failures are unchanged: the 4 exhaustive-set guards
standing since 10-13, `test_no_spelling_of_manual_entries_skips_the_owner_scope`
(yesterday's #69 XPASS, already owed), and 15 in
`test_backend_mode_isolation.py` — the never-run LLM-door tests (#71), the
Agents/Pipeline Infra lane, untouched by this.

**Still open in #70:** item 2 (a rejected top-up loses its account, so that
account's own `/logs/mine` never shows the rejection) and item 3 (the admin
can queue an ungrantable top-up that holds a `MAX_PENDING` slot). Both are
smaller than this was.

---

## 2026-10-16 (document audit attribution) — `bugs_audit_fixed.md` #68 item 4 fixed

> Backend API + Auth, Claude, on the user's grant ("the next most critical
> bug"). `backend/routes/runs.py` + `backend/runs/registry.py` only. Checked
> by `py_compile`, `import backend.app`, a 26-assertion scratch script against
> tmp `RUNS_DIR`/`OUTPUTS_DIR`/`logplane.LOG_DIR`, and the full
> `test_backend_*` suite before/after. **Not run:** uvicorn, a browser, the
> frontend.

**Why this one.** Everything 🔴/🟠 left in the table above is blocked on
another lane. Of what's left to this role, this sits at the top of the file's
own ordering — an action against account A recorded against account B — and it
is the audit trail specifically, the mechanism that makes admin access to a
user's vault accountable rather than merely possible. Ranked above the other
#68 remainders (an orphan PDF, a 500 on a damaged log, a 500 on a bad query
param) because those damage one run or one request; this one silently
misattributes every cross-account document action there will ever be.

**The bug, and it is wider than the logged one-liner.** `registry.owns()`
returns True unconditionally for an admin, so both saved-document routes can
act on a document belonging to someone else. Both logged
`profile_id=identity["profile_id"]` with `actor="account"`:

- the **owner's** `GET /api/logs/mine` never showed that their CV had been
  downloaded, and — the part not in the logged summary — never showed that an
  admin had **deleted** it. `document_deleted` had the identical defect, so a
  user's saved CV could vanish with no trail anywhere in their own view.
- `GET /api/admin/logs?profile_id=<owner>` could not find either action, which
  is the one lookup an account-keyed audit trail exists to answer.
- `actor="account"` actively asserted the account had done it to itself.

Both contradicted a decision this package had already made: `routes/admin.py`'s
`admin_data_access` was deliberately built to log the **target** account with
`actor="admin"`, and is deliberately user-visible ("a user should be able to
see *that* an admin opened their vault"). These two routes were the same
situation reaching the opposite answer.

**The fix.** New `routes/runs._audit_document(event, owner, identity, run_id,
**fields)` — `profile_id` is the run's own `owner`, `actor` is `"admin"`
whenever the caller is not that owner. Both call sites go through it, on
purpose: two independently-written `logplane.write()` calls carrying the same
attribution rule is exactly how `AGENTS`/`GATES`/`STUB_NODES` each drifted
from the graph.

`registry.delete_document` now **returns** the run's `owner` (it was returning
None). The route needs the owner and the registry already had the record in
hand; re-reading the log in the route would cost a second disk read and could
disagree with the record the ownership check actually passed.

- **An ownerless log** (written before ownership existed) gives
  `profile_id: None`. Those logs are admin-visible only by `owns()`, so there
  is no account to attribute to and `None` is the honest record — checked
  that it neither crashes nor becomes visible in any user's projected view.
- **A pre-10-10 log** carries a `token_id` in `owner`, not a `profile_id`.
  That is the same string `owns()` itself decides ownership by, so the entry
  stays consistent with the check that allowed it. Noted, not separately
  fixed: migrating those logs is #68's own "also noted" item.
- **No allowlist change needed:** `document_downloaded` (`{"fmt"}`) and
  `document_deleted` (`frozenset()`) were already in
  `logplane._USER_VISIBLE_FIELDS` — they were simply never landing on the
  account that could see them. `actor` is still never projected to a user, so
  the owner learns *that* it happened, not *which* admin did it, exactly as
  `admin_data_access` already behaves.

**Checked, beyond the happy path:** an admin download and an admin delete each
land on the owner with `actor="admin"`, appear in the owner's projected view,
do **not** appear in the admin's own, and are findable by
`?profile_id=<owner>`; the owner's own download/delete still read
`actor="account"`; an ownerless log doesn't crash and stays hidden from every
user view; a stranger still gets 403 from both routes with **nothing**
audited as a download or delete and the files untouched; a run with nothing
saved 404s from both with no entry written.

**Test impact (the user's).** The strict xfail pinning this item now XPASSes,
so it reports as a failure until the marker comes off:
`test_backend_auth.py::test_an_admin_download_is_logged_against_the_documents_owner`.
Worth adding while there: the same assertion for `document_deleted` (the half
this fix covers that the test doesn't), and that `actor == "admin"`.

**What to run (yours).** Full `test_backend_*` before/after:
`24 failed, 529 passed, 38 xfailed` → `25 failed, 529 passed, 37 xfailed`. The
set diff is **exactly** that one xfail flipping, nothing else.

**Still open in #68:** item 2 (the request queue doesn't normalise), item 5
(an orphan PDF when `ingest_pending` fails after the move), item 6 (a damaged
run log is a 500). Item 3 was fixed the same day — see the next section.

---

## 2026-10-16 (log paging and kind) — `bugs_audit_fixed.md` #68 item 3 fixed

> Backend API + Auth, Claude, on the user's grant ("the next most critical
> one"). `backend/logplane.py` + `backend/routes/logs.py` only. Checked by
> `py_compile`, `import backend.app`, a 34-assertion scratch script (including
> 60 randomised paging trials), and the full `test_backend_*` suite
> before/after. **Not run:** uvicorn, a browser, the frontend.

**Why this one.** Both remaining halves of #68 item 3 sit above its siblings
on the file's own ordering: the cursor bug is **silent loss of records from a
user's own audit view** — no short page, no error, nothing to notice — where
item 5 is disk litter and item 6 is a visible 500 on one run. A log plane
that quietly drops entries is worse than one that fails loudly.

**Bug 1: the cursor dropped tied timestamps.** `query()` minted
`next_cursor = page[-1]["ts"]` and the next page took `ts < cursor`. Every
remaining entry sharing that timestamp was therefore skipped. A tie group
straddling a page boundary lost its tail, and the client had no way to tell:
the pages were full, so it looked like a complete walk. Ties are ordinary
here, not exotic — the `run` kind writes `node_done` in a tight loop, and
`kind=None` merges five files whose timestamps are unrelated to each other.

**The fix:** page on `(ts, how many entries at that exact ts were already
sent)`, serialised as `"<ts>|<n>"`. For that count to mean anything the order
has to be total and reproducible, so entries are now carried as
`(ts, kind, line-number, entry)` and sorted on that whole key:
append-only files mean a line never moves, and `KINDS` is iterated in a fixed
order, so the same request yields the same order every time. Reversing the
full key also puts the latest-appended entry first *within* one timestamp,
which is the right reading of "newest first" for a tie.

- **Past tie groups are immutable**, which is what makes a count safe: a new
  entry can only be appended with a `ts` at or after the newest, so a group
  the client has already paged into cannot grow behind it.
- **Why not `(ts, seq)`** (the alternative the entry records): it means a
  schema change to an append-only log whose existing lines have no `seq`, and
  a per-file counter still wouldn't order a `kind=None` merge across five
  files. The count needs no migration and no new field.
- **A malformed cursor degrades rather than raises** — worst case it re-sends
  a page. A cursor is an opaque token this module minted, so a broken one is
  a client error, and this round's whole point is that a hand-typed query
  param can't 500 these routes. Checked against 8 hostile cursor shapes.
- **Wire note:** `next_cursor`'s format changed from a bare timestamp to
  `"<ts>|<n>"`. It is opaque and fed straight back, and nothing in
  `frontend/src` calls either route yet (checked), so no consumer breaks. A
  cursor is only valid against the filters it was minted under — documented
  on `query()`.

**Bug 2: an unknown `?kind=` was a 500.** `_path()` raises `ValueError` for a
kind outside `KINDS`, and it escaped both routes uncaught. New
`_checked_kind()` in `routes/logs.py`, used by both: **400**, naming the
valid kinds.

- **400, not an empty result:** "no such kind" and "you have no entries of
  that kind" are different answers, and returning the second for the first
  hides a client's typo.
- **400, not 404** (the route exists; the argument doesn't), and never
  401/403 — `deps.py` reserves those, and a 401 would sign the caller out
  over a typo.
- **Checked in the body, not as a FastAPI `Literal`** on the signature: both
  functions are also called directly in-process, including by the test that
  pins this, where an annotation validates nothing at all. The guard has to
  be where it actually runs.

**Checked:** the pinned tie case (5 entries, limit 2); 7 distinct timestamps;
a tie group larger than the page at limits 1/2/3/7/10; **60 randomised trials**
(1–25 entries over 5 timestamps, limits 1–6) asserting every entry arrives
exactly once, per-timestamp counts match, and order stays newest-first; ties
**across** kinds under `kind=None`; page order and cursor reproducible across
identical requests; `profile_id`/`event`/`since` filters still correct and
composing with paging; `for_user()` paging over tied, projected entries; 8
malformed cursors; both routes 400 on `kind="bogus"` while all five real kinds
and `None` are still accepted.

**Test impact (the user's).** Two strict xfails now XPASS, so they report as
failures until their markers come off:
- `test_backend_auth.py::test_paging_never_skips_entries_that_share_a_timestamp`
- `test_backend_auth.py::test_an_unknown_log_kind_is_a_client_error_not_a_500`
  (it already asserts `400 <= status < 500`, so only the marker needs removing)

`test_paging_walks_every_entry_once_with_distinct_timestamps` and
`test_the_limit_is_clamped` still pass unchanged.

**What to run (yours).** Full `test_backend_*` before/after:
`25 failed, 529 passed, 37 xfailed` → `28 failed, 528 passed, 35 xfailed`. Two
of the three new failures are the XPASSes above. **The third is not from this
change** — see the note below.

### ⚠️ Not this change: `revision`/`max_revisions` have landed in `utils/human_gate.py`

`test_backend_api.py::test_the_stub_pauses_with_exactly_the_payload_the_real_gate_sends`
started failing during this session, and it is nothing to do with the log
plane. `utils/human_gate.py` was edited at 14:51 today (before this session's
own edits at 14:56) and now puts **`revision` and `max_revisions` on every
gate's interrupt payload**. The test's `StubGraph` (last touched 10-14)
doesn't model them, so the "stub sends exactly what the real gate sends"
assertion fails on exactly those two keys — confirmed by driving
`human_gate` directly, with no log-plane code in the path.

**This is the Agents-lane line `"gate 4"` §3 and the frontend's B1 have been
blocked on, and it unblocks them.** The backend half needs **no code change**:
`_PAYLOAD_NOT_PASSED` doesn't exclude either key, so `_park` already relays
both onto `gate_wait` as extras — verified by computing the relayed set
directly (`['changes', 'gap_questions', 'max_revisions', 'revision']`).

So: that 🟠 row in the table above is satisfiable now. What's left is
**`StubGraph` gaining the two keys** (the user's, as a test), a run to confirm
them end to end on the wire, and then telling the frontend it can replace
Round 19/18/23's three approximations with the real fields. `honoured: false`
on `gate_done` (the third part of frontend B1) is still unbuilt and still
needs a decision in `decide()`'s lane.

---

## 2026-10-16 (damaged run log) — `bugs_audit_fixed.md` #68 item 6 fixed

> Backend API + Auth, Claude, on the user's grant ("the next most critical
> one"). `backend/runs/registry.py` only. Checked by `py_compile`, an import
> of the package, a pre-fix reproduction, a 130-assertion scratch script, and
> the full `test_backend_*` suite before/after. **Not run:** uvicorn, a
> browser, the frontend.

**Why this one.** Of #68's three open items, this is the one a user actually
sees: a 500 on their own run trail. Item 2 (the request queue not
normalising) is refused correctly at approval, so its damage is a duplicate
pending row, and item 5 is an orphan PDF — disk litter nobody is blocked by.
And the reproduction turned this into the widest of the three (below).

**Bug.** `registry.load_log` trusted whatever was in the file:
- an **empty or whitespace-only** file came back as `[]` — `read_json`'s
  `default=None` means "a new list", not "None" — and `owns([], identity)`
  then raised `AttributeError` on `[].get`;
- a **truncated** file raised `JSONDecodeError` straight out of the read.

Both escaped `/runs/{id}/log`, `/runs/{id}/document`, `DELETE .../document`
and `POST .../resume` uncaught: a **500**, for a damaged file rather than a
bad request.

**Wider than logged, in both directions — confirmed by reproduction, not
inferred:**
- The entry says `list_for` skips both. **It doesn't.** Its `except Exception`
  wrapped only the read, and its own `if not data` guard passed a non-empty
  non-dict log (`[{"id": ...}]`, a hand-edit or a half-migration) through to
  `owns()`, where an admin clears the role check and `data.get` then raises.
  `GET /api/runs` was therefore a **500 for the admin** — the entire Runs
  view down on one bad file in the folder, not one unreadable row.
- For an admin, `/runs/{id}/log` on an empty file was not a 500 at all but a
  **200 carrying `[]`** as that run's record (admin short-circuits `owns()`
  before the `.get`). A wrong answer is worse than an error here: it reads as
  "this run has no events" rather than "this file is broken".

**The fix.** `load_log()` returns None for anything that isn't a readable
JSON **object**: a `ValueError` (which covers both `JSONDecodeError` and
`UnicodeDecodeError`) or `OSError` from the read, or a parse that yields a
non-dict. `list_for()` now reads through `load_log(path.stem)` instead of
calling `read_json` itself.

- **"Unknown run" (404), not a 5xx:** the caller can do nothing about a
  half-written file, and a 404 says exactly what the admin's own Runs list
  already says about it. The alternative — a dedicated 5xx "this log is
  damaged" — would leak the state of the server's disk to whoever asks and
  give the caller nothing to act on.
- **Logged, not silent.** Each skip writes a `log.warning` naming the file and
  why, so a damaged log stays findable by whoever can repair or delete it.
  Registry gained `logging` + `log = logging.getLogger("backend")`, the same
  logger `logplane.py` and `auth/profiles.py` already use.
- **One reader, one verdict.** A list that skipped a file while `/log` 500'd
  on the same file is exactly how this stayed invisible; two independently
  tolerant readers of one format is the same drift that produced `AGENTS`/
  `GATES`/`STUB_NODES` and the three `final`-lookup copies of A1. The file is
  now read in one place.
- **Containment is unchanged and still tested** — the `contained_path()`
  check runs before anything is opened, so a crafted `run_id` is still None
  for the original reason, not the new one. `list_for` passing `path.stem`
  back through it is a no-op (the path came from a glob inside `RUNS_DIR`),
  kept for the single reader rather than bypassed.
- **A legacy dict still loads.** The guard is "is it a dict", not "does it
  have an `owner`" — a pre-ownership log is still a valid record that
  `owns()` deliberately shows to the admin only.

**Checked** (130 assertions): all ten damaged shapes — empty, whitespace,
truncated, a JSON list, `[]`, a JSON string, `null`, a number, non-JSON, and
non-UTF-8 bytes — read as None from `load_log`, and 404 from all four routes
for **both** an owner and an admin, with nothing audited and the file left
byte-for-byte alone; a healthy log still loads unchanged and `/log` still
returns it to its owner and the admin while a stranger still gets 403 (the
fix must not blur 403 into 404); a legacy dict with no `owner` still loads and
stays admin-only; the five crafted-`run_id` traversal cases still None;
`list_for` returns only its caller's healthy runs, newest first, with its row
shape and 120-char truncation unchanged, and does not crash the admin on any
damaged shape; and a sweep asserting `load_log` and `list_for` agree about
every file in the folder.

**Test impact (the user's).** Three strict xfail cases now XPASS, so they
report as failures until the marker comes off:
- `test_backend_auth.py::test_a_damaged_run_log_reads_as_unknown`
  (`empty`, `blank`, `truncated`)

Worth adding while that marker goes: a fourth case for a file whose JSON
parses to a **non-dict** (`[{"id": "r1"}]`), asserting `load_log` is None
*and* `registry.list_for({"role": "admin", ...})` still returns the healthy
runs — that is the admin-500 half, which no current test covers.
`test_list_for_scopes_by_profile_and_sorts_newest_first` passes unchanged (it
already seeds a `{nope` file).

**What to run (yours).** Full `test_backend_*` before/after:
`28 failed, 528 passed, 35 xfailed` → `31 failed, 528 passed, 32 xfailed`.
The set difference is exactly the three XPASSes above; `passed` did not move.

**Still open in #68:** item 5 (`ingest_pending` can leave an orphan PDF).

---

## 2026-10-16 (request queue identity rule) — `bugs_audit_fixed.md` #68 item 2 fixed

> Backend API + Auth, Claude, on the user's grant ("fix the next most critical
> bug"). `backend/auth/store.py` only. Checked by `py_compile`, `import
> backend.app`, a 47-assertion scratch script, and the full `test_backend_*`
> suite before/after. **Not run:** uvicorn, a browser, the frontend.

**Why this one.** The last of #68 besides item 5 (an orphan PDF — disk litter
nobody is blocked by). This one is user-facing in the worst small way: a
person types a name, is told their request is queued, waits for review, and
*then* it is refused — for a reason the server knew at the moment they typed
it. It also leaves rows in `requests.json` that can never become accounts, and
double rows for one person.

**Bug.** `create_request` never called `profiles.normalise_identifier`, even
though `profiles.py` states these names are "rejected at normalisation so none
of these can ever be queued". So `admin`, ` ROOT `, `ＡＤＭＩＮ` (NFKC-folds to
`admin`), `a:b`, and a name that passes the length bound raw but not folded
(40×"ß" measures 40 and folds to 80) all queued, and were refused only at
approval with a 409. And the pending-duplicate check compared `.lower()`, not
the normalised key, so "Jane Doe" and "jane  doe" sat in the queue as two
separate requests for what is one account.

**The fix.** `create_request` normalises, mapping `ProfileError` to
`AuthError` so `routes/auth.py`'s existing handler returns the same 400 it
already returns for an empty or overlong name — with the same message text the
approval path was surfacing, just at the door. The pending check now compares
a new `_queue_key()`.

- **The raw length bound stays in front of the normalised one.** This route
  takes no auth, so the cheap check on the typed string runs before any NFKC
  work; the normalised check then catches what folding expands. Both messages
  are kept.
- **`_queue_key()` falls back to a casefold** for a pending row the rule now
  refuses. Only rows written before this change can be in that state, and
  without the fallback they would stop de-duplicating against anything at all
  — the opposite of the fix. Verified against a seeded legacy `"A:B"` row.
- **Also closes #70's "also noted" length edge** (the request queue measuring
  name length before casefolding), which shared this root.
- **Deliberately not moved to the queue:** whether the name already *has* an
  account or an issued token. That check stays at approval
  (`_name_held_by_a_token`, item 1) because answering it on an open,
  unauthenticated route would tell the world which names are registered.
  `test_approving_a_second_spelling_of_an_account_is_refused_and_mints_nothing`
  depends on exactly that split and still passes unchanged.
- **Top-ups are untouched.** `create_topup_request` never takes a typed name —
  its identifier comes off the caller's own bearer token — so there is nothing
  to normalise there.

**Checked** (47 assertions): eight refused shapes (`admin`, ` ROOT `,
`SYSTEM`, `ＡＤＭＩＮ`, `a:b`, 40×"ß", blank, whitespace-only) each raise
`AuthError` and queue nothing, with the raw-overlong case still reporting the
raw message; the route turns three of them into **400s**, not 500s, and audits
nothing on refusal; five spellings of one name (whitespace, case, padding,
NFKC, tab) are each refused as duplicates with exactly one row left, while a
genuinely different name still queues; a rejected request frees its name
again; a legacy unnormalisable pending row still de-duplicates and still lets
an unrelated name through; the happy path still stores the stripped display
text, still mints a token and profile at approval, and the profile is still
keyed on the normalised name; item 1's approval-time guard still refuses a
second spelling of an existing account (and that name still queues); top-up
queue/dedupe behaviour unchanged; `MAX_PENDING` still enforced, with an
invalid name refused by the rule before the cap is consulted.

**Test impact (the user's).** Six strict xfail cases now XPASS, so they report
as failures until their markers come off:
- `test_backend_auth.py::test_a_name_no_account_could_have_is_refused_at_request_time`
  (all five cases — note the marker says 4, the parametrize has 5)
- `test_backend_auth.py::test_two_spellings_of_one_name_are_one_pending_request`

**What to run (yours).** Full `test_backend_*` before/after:
`31 failed, 528 passed, 32 xfailed` → `37 failed, 528 passed, 26 xfailed`. The
set difference is exactly the six XPASSes above; `passed` did not move.

**Still open in #68:** item 5 only (`ingest_pending` can leave an orphan PDF).

---

## 2026-10-17 (unindexable profile section) — `bugs_audit_fixed.md` #69 item 2 fixed

> Backend API + Auth, Claude, on the user's grant ("fix the next most critical
> bug"). `backend/routes/profile.py` only. Checked by `py_compile`, `import
> backend.app`, a 33-assertion scratch script, the pinned test over HTTP, and
> the full `test_backend_*` suite before/after. **Not run:** uvicorn, a
> browser, the frontend.

**Why this one.** Ranked above the rest of the open list because it is the
only remaining item where a user's **own typed data is quietly lost**: the
save answers 200, the record sits in `manual_entries.json`, and nothing will
ever retrieve it. Everything else left is an audit-attribution gap (#69 item
3, #70 item 2), a pending row nobody can grant (#70 item 3), or disk litter
(#68 item 5).

**Bug.** `ProfileEntry.section` was a free string. `_index_entry` looks the
section up in `SECTION_TYPES` (the Build-Profile section → the record `type`
`agents/profile.py`'s `QUOTAS` filters retrieval on), and for anything else
logs a warning and returns. So `{"section": "hobbies"}` was stored and never
embedded — invisible to retrieval forever, with a 200 telling the user
otherwise. `SECTION_TYPES`' own docstring warns that an invented type "would
be a record that is indexed and never retrieved"; this was worse — not even
indexed.

**The fix.** A `field_validator("section")` on `ProfileEntry`: a section
outside `SECTION_TYPES` raises `ValueError`, which FastAPI renders as a
**422** naming the valid sections. Both routes take the same model, so `PUT
/profile/entries/{id}` is covered as well as `POST`.

- **Validated against `SECTION_TYPES`, not a `Literal[...]` on the field.**
  The entry's own proposed fix was the `Literal`; it gives the same 422 but
  hand-copies the six keys, so adding a section to the table would leave the
  check behind — the exact drift that produced `AGENTS`/`GATES`/`STUB_NODES`
  and A1's three `final` lookups. Checked by adding and removing a table key
  at runtime and watching the validator follow it.
- **A 422, not a 400 or a coerced "extras".** It is a request-body validation
  failure like every other one these routes raise, and silently filing an
  unrecognised section under `extras` would put the record in the index under
  a type the user never chose.
- **`_index_entry`'s warning stays**, now explicitly as defence in depth
  rather than as the gate: rows written before this validator, and the gate-2
  answers `learning/profile_store.save_gap_answers` writes into the same file
  without coming through these routes, can still carry an unknown or missing
  section, and must keep skipping the index instead of raising inside a
  background thread.

**Checked** (33 assertions): all six real sections still build and each maps
to a record type; eight refusals (`hobbies`, empty, `Skills`, `skill`,
`" skills "`, the internal `work_experience`, punctuation, a fullwidth
spelling) each raise with a message listing every valid section; nothing is
written to disk by a refusal; the `POST` route still saves, stamps `owner`,
and indexes under `skill:<id>` with `type`/`section` metadata intact; `PUT`
can't even be called with a bad section and a valid edit still re-indexes
under the same id; and `_index_entry` on a legacy row with a bad or missing
section still skips silently without a `KeyError`.

**Test impact (the user's).** One strict xfail now XPASSes:
- `test_backend_api.py::test_an_unknown_profile_section_is_refused`

`test_profile_entry_roundtrip` (which already asserts a 422 for a missing
`record`) passes unchanged.

**What to run (yours).** Full `test_backend_*` before/after:
`37 failed, 528 passed, 26 xfailed` → `38 failed, 528 passed, 25 xfailed`. The
set difference is exactly that one XPASS; `passed` did not move.

**Still open in #69:** item 3 (a 403 on the `?token=` events route is audited
as anonymous) — fixed next, below.

---

## 2026-10-17 (403 attribution on the events route) — `bugs_audit_fixed.md` #69 item 3 fixed

> Backend API + Auth, Claude, on the user's grant ("fix the next most critical
> bug"). `backend/app.py` only. Checked by `py_compile`, `import
> backend.app`, a 24-assertion scratch script over a real `TestClient`, the
> pinned test, and the full `test_backend_*` suite before/after. **Not run:**
> uvicorn, a browser, the frontend.

**Why this one.** The last open item in #69, and the one with a security
reading: the 403 it fails to attribute is *one account trying to open
another's run stream*. That is precisely the event the log plane exists to
record, and it was being filed against nobody. Of what remains, #70 item 2 is
a missed rejection notice, #70 item 3 a pending row nobody can grant, #68
item 5 disk litter.

**Bug.** `app._audit_every_403` resolved the caller from the `Authorization`
header only. `GET /api/runs/{id}/events` authenticates by `?token=` because
`EventSource` cannot set headers, so a 403 there had no header to read and was
written as `actor: "anonymous"`, `profile_id: null`. The refused user could
not see their own refusal in `/logs/mine` (the projection is by `profile_id`),
and the admin could not attribute it with `?profile_id=`. Same class as #68
item 4 (an admin's download filed against the admin), fixed 10-16: an audit
line naming the wrong account, or none.

**The fix.** Fall back to `request.query_params.get("token")` when the header
is absent.

- **The header still wins** when both are present — the header is the
  supported credential everywhere else, so a query param can't be used to
  point an audit line at someone else's account. Pinned by a test case.
- **Not confined to the events route**, unlike `deps.identity_from_query_token`
  itself. That confinement is about *authentication* (keeping tokens out of
  logs and browser history); this is *attribution*, and whoever presents a
  token is its holder either way. A second SSE route would be covered with no
  second fix here.
- **Nothing new reaches the log plane.** Only the resolved `profile_id` is
  written, and `fields["path"]` is `request.url.path`, which excludes the
  query string — so the token never lands in `audit.jsonl`. Asserted
  directly: the raw token appears nowhere in the serialised entry.
- **The attribution resolve is now wrapped.** A read failure while working out
  *who* to blame must not turn an ordinary ownership 403 into a 500; it
  degrades to `anonymous` and logs the exception.

**Checked** (24 assertions, over a real `TestClient` — this handler only runs
there): bob opening alice's stream gets a 403 audited against **bob** with
`actor: "account"`, appearing in bob's own `/logs/mine`, absent from alice's,
findable by `?profile_id=<bob>`, with the path recorded query-free and the raw
token absent from the whole entry; the header path unchanged; the header
winning over a conflicting query token; an unknown `?token=` still **401**,
not 403, and audited as neither; the owner and the admin both still stream
with nothing audited; a non-admin's 403 on `/admin/logs` still attributed.

**Test impact (the user's).** One strict xfail now XPASSes:
- `test_backend_api.py::test_a_403_on_the_events_route_is_attributed_to_its_caller`

**What to run (yours).** Full `test_backend_*` before/after:
`38 failed, 528 passed, 25 xfailed` → `39 failed, 528 passed, 24 xfailed`. The
set difference is exactly that one XPASS; `passed` did not move.

### ⚠️ Found while checking this, not fixed: a damaged `tokens.json` is a 500 at every door

Section 8 of the scratch script pins it. `store.resolve_token` reads
`tokens.json` through `jsonstore.read_json`, so a truncated or non-UTF-8 file
raises `JSONDecodeError` straight out of `deps.require_auth` — **every**
authenticated request, every role, `/auth/login` included. It is the same
shape as #68 item 6 (a damaged run log), fixed on 10-16, and worse in reach: a
run log takes out one run, this takes out everyone, with a 500 where `deps.py`
promises a 401.

The fix is the same treatment `registry.load_log` got — a `ValueError`/`OSError`
or a parse that isn't a list reads as "no tokens", which is fail-closed (401,
the honest answer for "this credential cannot be verified"), plus a
`log.exception` so the file is findable. `profiles.json` and `requests.json`
are read the same way and want the same look. Logged in
`context/bugs_audit_fixed.md` under #69's "also noted"; **not** fixed in this
change, which was scoped to one item.

**#69 is now fully closed.** Still open elsewhere: #68 item 5 and #70 item 3.
(#70 item 2 was fixed next — below. The "finding" above turned out to be a
pinned decision, not a bug: see the correction in that section.)

---

## 2026-10-17 (rejected top-up attribution) — `bugs_audit_fixed.md` #70 item 2 fixed

> Backend API + Auth, Claude, on the user's grant ("fix the next most critical
> bug"). `backend/auth/store.py` and `backend/routes/auth.py` only. Checked by
> `py_compile`, `import backend.app`, a 29-assertion scratch script (store
> level and over a real `TestClient`), and the full `test_backend_*` suite
> before/after. **Not run:** uvicorn, a browser, the frontend.

**What I tried first, and withdrew.** The finding logged with #69 item 3 — a
damaged `tokens.json` being a 500 at every door — looked like the most
critical thing left, and I built the #68-item-6 fix for it: a shared
`jsonstore.read_json_or_empty()` used by `resolve_token` and
`profiles.profile_for`/`display_for`, fail-closed to 401, with write paths
deliberately left raising so a damaged file could never be rewritten from an
empty list (133 assertions, all passing). Then the suite showed
`test_the_admin_still_gets_in_when_tokens_json_is_corrupt` going from pass to
fail: that test **pins the raise on purpose**. `ADMIN_TOKEN` is compared
before the file is ever read, so the admin door survives a corrupt
`tokens.json` and can repair it, while a user token raises — "fails closed,
never 'no tokens, no check'", in the test's own words. That is a decision,
stated in a test, not an oversight, so the change was reverted in full rather
than flipped quietly; the entry in `bugs_audit_fixed.md` has been corrected
to say so. If it is ever revisited it is one tolerant read plus that test —
and `profiles.json`/`requests.json` want the same look, where an
empty-*looking* admin queue would be the dangerous reading.

**Why this one instead.** Of what was actually open, #70 item 2 is the only
item where a user is told nothing about a decision made on their own account.
#70 item 3 is a pending row nobody can grant; #68 item 5 is disk litter.

**Bug.** A top-up carries its account's `token_id` from creation — that is
the whole difference between a top-up and a signup. `reject_request` called
`_resolve(request_id, "rejected")`, whose `token_id` parameter defaults to
None, and the record's own `token_id` was overwritten with it. Two
consequences: the resolved request could no longer be tied to an account at
all (only to a display name), and `routes/auth.py`'s `reject` had nothing to
attribute its audit entry to, so `request_rejected` was written with
`profile_id: None`. The account's own `/logs/mine` therefore never showed the
rejection, although `request_approved` carried the account and did show —
against the design's own visibility table ("a user sees their own access
decisions").

**The fix.**
- `_resolve` only ever *sets* `token_id`: `token_id or record.get("token_id")`.
  A rejected signup still ends with `token_id: None` — it never had one, and
  there is no account to point at. (`test_a_rejected_request_mints_nothing`
  and the approve/reject race test both pin that and still pass.)
- `reject` attributes through a new `store.profile_id_for_token()`, the same
  rule `approve` already follows: `profile_id` is the account the entry is
  *about*, `actor` is who acted. `_USER_VISIBLE_FIELDS` already allowed
  `request_rejected`, so nothing had to open up for the user to see it.
- **Resolved at audit time, not stored on the request.** The request records
  which credential asked; the account is looked up through it when the entry
  is written. A later token re-issue therefore doesn't rewrite history, and
  the request still says which credential made the ask.
- **Looked up for any request carrying a `token_id`, not branching on
  `kind == "topup"`** (which the entry's proposed fix suggested): a `kind`
  check would be a second place that has to know which kinds carry a token,
  and "has a `token_id`" is the condition that actually matters.
- `profile_id_for_token` maps `ADMIN_TOKEN_ID` to `ADMIN_PROFILE_ID`, which
  has no `tokens.json` row to find. It is for attribution only, never a
  permission check — `Scope` is still the only way a route reaches
  profile-keyed storage.

**Checked** (29 assertions): at store level a rejected top-up keeps its
`token_id` in the returned record and on disk, grants nothing, and a rejected
signup still ends with None, while approval still sets it; the lookup handles
a real token, None, an unknown id and the admin sentinel. Over HTTP: the
reject response keeps the account link, the audit entry names the account with
`actor: "admin"` and the `request_id` intact, it appears in that account's own
`/logs/mine` next to its `request_more`, is absent from the admin's own view,
is findable by `?profile_id=`, and carries no raw token; a rejected signup
stays unattributed and hidden from every account; approval attribution is
unchanged; a double rejection is still a 409 that changes nothing and audits
nothing.

**Test impact (the user's).** Two strict xfails now XPASS:
- `test_backend_auth.py::test_a_rejected_topup_keeps_the_account_it_was_for`
- `test_backend_api.py::test_a_rejected_topup_shows_in_that_accounts_own_log`

**What to run (yours).** Full `test_backend_*` before/after:
`39 failed, 528 passed, 24 xfailed` → `41 failed, 528 passed, 22 xfailed`. The
set difference is exactly those two XPASSes; `passed` did not move. (A
`test_backend_mode_isolation.py` case appeared and disappeared between runs
either side of this change — those 15 never-run LLM-door tests are flaky in
this environment and are another lane's.)

**Still open in #70:** item 3 (the admin can queue a top-up nothing can
grant, holding a `MAX_PENDING` slot).

---

## 2026-10-21 (orphan CV on upload) — `bugs_audit_fixed.md` #68 item 5 fixed

> Backend API + Auth, Claude, on the user's grant (fix bugs in this role's
> jurisdiction, code in `backend/` only). `backend/cv_store.py` and
> `backend/jsonstore.py` only. Checked by `py_compile`, `import backend.app`,
> a 19-assertion scratch script against a tmp `CV_UPLOADS_DIR`, and the full
> `test_backend_*` suite before/after. **Not run:** uvicorn, a browser, the
> frontend.

**Why this one.** Weighed against #51's live-mode key check first, which the
index calls out alongside it. On reading `agents/base.py`'s lane logic that one
turned out to be a false *refusal* only: every lane in `config.FALLBACK_CHAINS`
ends in Groq, so the `GROQ_API_KEY` check is sufficient to stop a doomed,
charged run — it just also refuses some runs that would have worked. #68 item
5, by contrast, leaves a user's CV — personal data — on disk where nothing
lists it and the owner's own `DELETE /api/profile/cv/{id}` can't reach it (that
route only knows ids in the index). Remaining items: #70 item 3 (one stuck
pending row), #42 (since CV upload, only the admin's sample fallback is
unchecked, and the admin isn't charged), #51 hygiene.

**Bug.** `ingest_pending` moved the validated PDF to `{sha}.pdf` *before*
`_build_preview` and the index write. A failure in either left the file in
place with no index entry, contradicting its own docstring ("nothing partial
is left on disk"). Two more edges in the same code, found while fixing it:
- **Evictions ran before the write.** Older pending uploads were unlinked
  inside the `update_json` callback, so a failed write left the *unchanged*
  index naming files that were already gone — confirmable, then a "no CV"
  409 at run start.
- **A naïve cleanup would have deleted a real CV.** `{sha}.pdf` can already
  exist as an indexed CV with identical bytes; "unlink on failure" without
  knowing who created the file would remove it.

**The fix.**
- `_build_preview` and the summary now run inside the `try`, **before** the
  move. The `except: unlink; raise` became a `finally` that removes the tmp
  file — already moved on success, removed on every other path, including
  the confirmed-identical no-op, which no longer touches the stored file at
  all.
- New `_commit_pending()` does move + index write + evictions **as one step
  under the index's own lock**, and on a failed write removes the moved file
  **only if this upload created it**. Evicted pending files are deleted only
  after the write succeeds.
- `jsonstore.lock_for(path)` — a public name for the lock `update_json`
  already holds per path, rather than a second lock: `confirm`/`delete` still
  go through `update_json` on the same file and must serialise against this.
  Re-entrant, so nothing changes for them.
- **Order chosen so a lock-free reader is never wrong:** the file lands
  before the index names it, so `resolve_path` (which reads without the lock)
  can never see an indexed entry whose file isn't there yet.

**Checked** (19 assertions): a preview failure leaves no PDF, no tmp, no
index; a failed index write on a new upload leaves files and index
byte-for-byte as before, with the older pending upload still on disk and
still confirmable; a failed write on an identical re-upload of an indexed
pending CV keeps that file; the confirmed-identical no-op leaves index and
files unchanged and no tmp behind; eviction still works on success and never
touches the confirmed CV; 24 concurrent uploads from one owner end with
exactly one pending entry and the set of PDFs on disk equal to the set the
index names; `lock_for` is the same lock object `update_json` uses.

**Test impact (the user's).** One strict xfail now XPASSes:
`test_backend_auth.py::test_a_failure_after_the_file_is_stored_leaves_no_orphan`.
It only covers the preview half; an index-write-failure twin
(monkeypatch `cv_store.write_json` to raise, then assert no new `.pdf` and the
older pending file still present) would pin the other two edges.

**What to run (yours).** Full `test_backend_*` before/after:
`43 failed, 526 passed, 22 xfailed` → `44 failed, 526 passed, 21 xfailed`.
The set difference is exactly that one XPASS; `passed` did not move.

**#68 is now fully closed** (items 1–6). Still open in this role's lane:
#70 item 3, #42, #51 hygiene, naming the failed step on `run_error`, the
`cv_link` loop-back `{stage}` artifact, self-export / account-delete.

---

## 2026-10-21 (failed step on run_error) — `"2026-10-14 (frontend, Rounds 27–42)"` A2 built

> Backend API + Auth, Claude, on the user's grant ("fix the most critical bug
> listed"). `backend/runs/worker.py` and `backend/logplane.py` only. Checked by
> `py_compile`, `import backend.app`, a 9-assertion scratch script against stub
> graphs, and the full `test_backend_*` suite before/after. **Not run:**
> uvicorn, a browser, the frontend.

**Why this one.** It heads the ranked 🟡 list and is the top item this role
can build alone. #70 item 3 is one pending row the admin can still reject;
#42 now only touches the admin's uncharged sample fallback; #51's key check
only over-refuses (every lane ends in Groq).

**Bug.** `run_error` carried only `error`. The frontend (Round 33) marks
whichever step it last saw as "working" as failed. That's the only clue on
screen, and an error outside a step (the Supervisor, a gate, graph build)
leaves nothing to mark, so the user can't tell where the run died.

**The fix.**
- `run_error` gains `node`: the agent in flight when the graph raised, or
  `null` for an error outside any agent step. Additive. The frontend ignores
  unknown fields today, so nothing breaks before it reads this.
- **Tracked live, not reconstructed from the event trail** (which the ask
  proposed: "the last `node_start` without a matching `node_done`").
  `_drain_stream` sets `run["in_flight"]` when it emits `node_start` and clears
  it on **any** update from that node. Reconstruction would be wrong for a
  node that returns an empty update: it gets no `node_done`, so a later
  Supervisor failure would be blamed on it. `profile_enrich`'s no-answers path
  is close to that shape.
- `_drive` resets `in_flight` to None on entry. A resumed run starts parked at
  a gate, so there is nothing in flight.
- **`null` for non-agent steps, not `"gate"`/`"supervisor"`.** The frontend's
  step map is keyed by agent names only, so a non-agent name would match
  nothing there. `null` says "outside a step", which is the truth.
- `run["in_flight"]` is not persisted: `save_log` copies a fixed key list.
- Log plane: `run_error` entries carry `node` too, and `_USER_VISIBLE_FIELDS`
  lets the owner see it. Node names are already user-visible on `node_done`.

**Checked** (9 assertions): a step raising → `node` names it, `error` text
unchanged; the Supervisor raising after a step finished → `null`; a step with
an empty update followed by a Supervisor failure → `null`, not that step, and
still no `node_done` for it; a graph-build failure → key present, `null`; a
clean run still ends in `run_done`; the projected `/logs/mine` entry shows
`{error, node}`; `in_flight` absent from the saved log.

**Suite:** `44 failed, 526 passed, 21 xfailed` before and after, identical
failure set. No test pinned `run_error`'s shape.

**Owed (yours):** a test in `test_backend_api.py` (no new file): a `StubGraph`
that raises inside a node, asserting `run_error.node` names it. **Frontend
(tell them):** `run_error.node` is on the wire. `settle()` can mark exactly
that step failed and fall back to today's inference only for logs from
before 2026-10-21, which don't have the key.

---
## 2026-10-21 (admin top-up) — `bugs_audit_fixed.md` #70 item 3 fixed

> Backend API + Auth, Claude, on the user's grant ("fix the most critical bug
> in yellow range"). `backend/auth/store.py` only. Checked by `py_compile`,
> `import backend.app`, a 14-assertion scratch script against a tmp
> `KB_AUTH_DIR`, and `test_backend_api.py` + `test_backend_auth.py`
> before/after. **Not run:** uvicorn, a browser, the frontend.

**Why this one.** The last 🟡 in this role's lane with a real consequence
beyond cosmetics: #42 now only touches the admin's own uncharged sample
fallback, #51 is hygiene, and the `cv_link` loop-back artifact is already
worked around in the frontend. This one can wedge the signup queue.

**Bug.** `create_topup_request` keyed the request on
`identity["token_id"]`, which for the admin is the sentinel `__admin__` —
there is no `tokens.json` row behind it. `approve_request`'s top-up branch
looks that row up and raises "That account no longer exists" (409), so the
request could never be granted, only rejected. Until someone noticed and
rejected it, it held one of `MAX_PENDING`'s 100 slots — and that cap is
shared with anonymous `/auth/request-access`, so stuck rows eat the queue
every real signup has to fit into. The admin has `runs_remaining: None`
(unlimited), so there was never anything to top up in the first place.

**The fix.** `create_topup_request` raises `AuthError("The admin account has
no run limit.")` when the caller's `token_id` is `ADMIN_TOKEN_ID`. The
route's existing `except store.AuthError` turns that into the same 400 it
already returns for an overlong note.

- **In the store, not the route.** `routes/auth.py` is one caller; the rule
  is about what a valid request *is*, and a second caller (a CLI, a test)
  would otherwise bypass it. Same placement as the identity rule #68 item 2
  moved into `create_request`.
- **Before the note bound**, so a long note still gets the specific message
  rather than being refused for the wrong reason.
- **400, not 403.** The caller is authenticated and allowed here; the
  request itself is meaningless. 403 is reserved for "not yours" (and a 401
  would log the admin out).
- **`approve_request`'s "That account no longer exists" stays.** It is still
  the right answer for a token deleted *after* its top-up was queued, and
  for the rows already on disk from before this change.
- **Existing stuck rows are not migrated.** They stay pending and the admin
  can reject them, which frees the slot and (since 10-17) audits correctly.
  A startup sweep would be a write to the audit trail on boot for one or two
  rows an admin can clear in a click.

**Checked** (14 assertions): the admin is refused with that message and
queues nothing, including with a 10k note; a real account's top-up still
queues with the right `kind`/`token_id`, is still one-at-a-time, and still
approves into `+DEFAULT_RUN_ALLOWANCE` with the token withheld; a legacy
admin row seeded on disk still 409s on approve (backstop intact), rejects
cleanly keeping its `token_id`, and frees the pending slot;
`profile_id_for_token` still maps the sentinel.

**Suite:** `test_backend_api.py` + `test_backend_auth.py`:
`28 failed, 424 passed, 19 xfailed` with the one difference being
`test_the_admin_cannot_queue_a_topup_it_can_never_be_granted` XPASSing.
(The full-suite number moved a lot this session for an unrelated reason —
see the note below.)

**⚠️ Not mine, found while verifying:** `tests/test_backend_mode_isolation.py`
went from ~15 failures to ~69 between my previous run and this one, because
a new `agents/contracts.py` (written in the Agents lane at 15:57 today) added
`check_schema`, which refuses a registered agent being asked for a schema
other than its own — and that file's tests ask `jd_analysis` for a local
`Out` schema: `TypeError: Agent 'jd_analysis' answers with Requirements
(agents/contracts.py), but the call asked for Out.` Nothing to do with this
change (it is `backend/auth/store.py` only, and the API/auth files are
unaffected), but those tests need updating to the new contract.

**Owed (yours):** drop the strict xfail on
`test_the_admin_cannot_queue_a_topup_it_can_never_be_granted`.

**#70 is now fully closed** (items 1–3), as is #68. Still open in this lane:
#42, #51 hygiene, the `cv_link` loop-back `{stage}` artifact, self-export /
account-delete.

---
## 2026-10-22 (CV preflight) — `bugs_audit_fixed.md` #42 fixed

> Backend API + Auth, Claude, on the user's grant ("fix the most critical bug
> in yellow range"). `backend/routes/runs.py`, `backend/vectorstore.py`,
> `backend/app.py`. Checked by `py_compile`, `import backend.app`, a
> 14-assertion scratch script over a real `TestClient`, and
> `test_backend_api.py` + `test_backend_auth.py` before/after. **Not run:**
> uvicorn, a browser, the frontend.

**Why this one.** The 🟡s left in this lane were #42, #51 hygiene, the
`cv_link` loop-back `{stage}` artifact (already worked around in the
frontend) and self-export. #42 is the only one that costs a user something.

**Bug.** `start_run` spent an allowance before anything confirmed the run
could reach `cv_link`, which is the sixth node: `jd_analysis`, gate 1,
`profile`, gate 2, `profile_enrich` and `matching` all run first. A missing
CV file therefore appeared as a `run_error` after two answered gates and four
live LLM calls, and `refund_run` only covers a failure to *start*. The same
is true of an unbuilt profile index (`_get_parts` → `RuntimeError`).

**The fix, in two halves.**
1. **503 before `consume_run`** when the resolved CV path is not a file.
   `cv_store.resolve_path` already drops a confirmed CV whose file vanished,
   so in practice this catches the admin's shared sample
   (`config.CV_DEFAULT_PATH`), which is git-ignored and absent on a fresh
   clone. 503, never 401/403 (the entry says so explicitly): nothing is wrong
   with the caller or their token.
2. **Boot-time warnings**, beside the existing empty-`ADMIN_TOKEN` one, for a
   missing sample CV and for an unusable profile index — new
   `vectorstore.profile_index_problem()`, which names which of unbuilt /
   empty / wrong-embedding-model it is and how to fix it.

- **The index check does NOT go through `get_vector_store()`.** It opens
  Chroma directly and compares the collection's stamped `embedding_model`
  against `config.EMBEDDING_MODEL` (the same string the stamp is written
  from), so a readiness probe costs no ~440MB model load. Verified in the
  scratch run: under 3s, `torch` never imported, `_store` still None.
- **Read-only, via `get_collection`.** `VectorStore._collection` would be the
  natural call but needs an embedder; `get_or_create` would have the probe
  *create* the empty collection it is asking about. Asserted: asking about an
  empty directory leaves no `profile` collection behind.
- **Fails open, and says so.** An unreadable index returns a sentence naming
  the exception rather than claiming it is broken — a probe that cannot read
  is not proof of a fault.
- **Warnings, not a refusal to start.** The bridge still serves auth, the KB
  and saved runs without either, and a fresh deploy is expected to build the
  index after the API is up.
- **Deliberately NOT a 503 in `start_run` for the index.** It belongs there on
  the same argument as the CV file, but `tests/test_backend_api.py:175` points
  `config.VECTORDB_DIR` at an empty `tmp_path`, so every run-start test would
  get a 503 — dozens of currently-passing tests, and tests are the user's.
  This is the natural content of `/api/ready` (`context.md` §17), which can
  carry it with the fixture change made deliberately rather than as fallout.

**Checked** (14 assertions): an admin with no sample gets 503 "No CV is
configured on the server." and no run record is created; a user with no CV
still gets the unchanged 409 with their allowance intact; a user whose
confirmed CV was deleted from under the index is refused before `consume_run`
with the allowance intact; with the real sample present the admin is not
refused; `profile_index_problem()` returns None for the real index, cheaply,
with no torch and no `VectorStore`; an unbuilt directory is reported with the
fix named, and the probe creates nothing.

**Suite:** `test_backend_api.py` + `test_backend_auth.py`
`28 failed, 424 passed, 19 xfailed` — **identical** before and after. No test
covered #42.

**Owed (yours).** Two tests in `test_backend_api.py` (no new file): point
`config.CV_DEFAULT_PATH` at a nonexistent path and assert the admin's start is
a 503 that creates no run; and assert `profile_index_problem()` is not None
for a `tmp_path` index while `backend.vectorstore._store` stays None. The
`/api/ready` route is where the index check should become a refusal.

**Runbook note for deployment:** a deploy must supply the sample CV at
`config.CV_DEFAULT_PATH` (admin demo runs only) and build the profile index
before the first run; both are now stated in the log at boot.

---
## 2026-10-22 (hygiene: KB counts, live keys) — `bugs_audit_fixed.md` #51's two Backend items fixed

> Backend API + Auth, Claude, on the user's grant ("fix the most critical bug
> in yellow range"). `backend/routes/kb.py` and `backend/routes/runs.py` only.
> Checked by `py_compile`, `import backend.app`, a 30-assertion scratch script
> against the real KB files, one `TestClient` run, and
> `test_backend_api.py` + `test_backend_auth.py` before/after. **Not run:**
> uvicorn, a browser, the frontend.

**Why this one.** What is left in this lane is #51, the `cv_link` loop-back
`{stage}` artifact (already worked around in `applyEvent`, and the clean fix
is a wire change the frontend has to want) and self-export (a feature, not a
bug). So: #51's two Backend items, both of which are wrong answers a user can
see.

### Item 1 — the KB browser's record counts

`do_not_claim.json` is a wrapper, `{_comment, version, forbidden_claims}`.
`kb_overview` did `len(read_json(f))` and reported **"3 records"** for 22
forbidden claims; `kb_file` wrapped the dict in a list and reported
**"1 record"**. Two readers of one file, two wrong answers, neither agreeing
with the other.

**Fix.** One `_records(path, scope)` both routes read through: a wrapper's
first list value *is* its records; its scalar keys are metadata about that
list, not records beside it. `_record_count` is now `len(_records(...))`, so
the count and the listing cannot disagree — the same two-readers drift that
produced `AGENTS`/`GATES`/`STUB_NODES` and `load_log`'s three `final`
lookups.
- **A dict with no list at all stays one record**, which is what it is.
- **No frontend break:** `KnowledgeBase.jsx:32` unwraps
  `records[0].forbidden_claims` when it sees exactly one such record. It now
  receives 22 records and the unwrap simply doesn't fire. Its comment
  ("claim boundaries file wraps its list — flatten it for display") is
  **stale as of this change** and the dead branch can go — frontend's call,
  flagged not changed.

### Item 2 — the live-mode key check

`if req.mode == "live" and not config.GROQ_API_KEY` asked the wrong question
in both directions. Every lane in `config.FALLBACK_CHAINS` happens to end in
Groq today, so it was *sufficient* — but it refused a live run that
`USE_OPENAI`, or Cerebras/OpenRouter/Gemini keys, could serve perfectly well,
and it stops being sufficient the moment a lane's last entry changes.

**Fix.** New `_live_key_problem()` asks what `agents/base._live_answer`
asks: an agent runs if **any** entry in its own lane has a key (a keyless
provider is skipped, the primary included); the door raises only when none
does. The 400 now names the agents that can reach nothing and the keys that
would fix them.
- **Read off `config` attributes, not `os.getenv`** — the same source
  `base._has_key` uses, and where a key is overridden in-process.
- **`config.required_keys_for_mode()` was rejected**, though the entry
  proposes it: its live branch demands the key of every agent's *primary*
  (all four providers today), which would refuse runs the fallbacks exist to
  serve — and its first branch returns `[]` when `USE_FAKE_LLM` is the
  process default, which would remove the check entirely for exactly the
  deployment that most needs it (an offline-default server taking one live
  run).
- **An unknown provider in a lane counts as keyless**, so a config typo is a
  400 before the allowance is spent rather than a `ValueError` from
  `_has_key` mid-run. Verified it does not 500.
- **No key names or values are ever in the message** — only env var *names*,
  asserted.

**Checked** (30 assertions): the wrapper file counts 22 and lists the claims;
plain lists unchanged; a listless dict is one record; an empty file is zero,
not a crash; count == len(records) for **every** real KB file. For the keys:
all keys → allowed; none → refused naming agents + env vars, no key value in
the text; Groq alone → allowed (every lane ends there); Groq missing but
others present → allowed (**this was the false refusal**); Gemini only →
refused, listing the Groq/Cerebras-primary agents and *not* `document` or
`critic`; `USE_OPENAI` with only an OpenAI key → allowed; with nothing →
refused. Over HTTP with all five keys blanked: **400, allowance still 2, no
run created**.

**Suite:** `test_backend_api.py` + `test_backend_auth.py`
`28 failed, 424 passed` → `29 failed, 423 passed`. The one difference is
`test_live_mode_without_a_key_is_a_400_that_spends_nothing`, which blanks
**only** `config.GROQ_API_KEY` while this machine's `.env` holds Cerebras,
OpenRouter and Google keys — so the run it expects to be refused is now
genuinely servable and starts (200).

**Is that a decision a test pins?** Checked deliberately, after the 10-17
lesson. No: the decision is "a live run that cannot be served is a 400 that
spends nothing", and that still holds exactly — proven over HTTP above with
every key blanked. What changed is only which fixture counts as "without a
key", and the test's premise predates the four-provider lanes (config's own
comment dates that allocation 2026-10-19). On a machine holding only a Groq
key the test still passes unchanged.

**Owed (yours).** One line in that test: blank all five provider keys
(`GROQ_API_KEY`, `GOOGLE_API_KEY`, `CEREBRAS_API_KEY`, `OPENROUTER_API_KEY`,
`OPENAI_API_KEY`), not Groq alone — otherwise it asserts the old
Groq-specific rule and is environment-dependent. Worth adding beside it: with
only `CEREBRAS_API_KEY` set, a live start is **not** refused.

**Still open in this lane:** the `cv_link` loop-back `{stage}` artifact
(needs the `unchanged: true` wire shape the frontend asked for) and
self-export / account-delete. Everything else is blocked on another lane.

---
## 2026-10-22 (scope into the graph) — `"2026-10-09 (design)"` §3, backend half built

> Backend API + Auth, Claude. **Written partly outside `backend/` on an
> explicit grant**: the user approved exactly two carrier edits (`config.py`,
> `state/state.py`) after I reported that §3's backend half could not be
> written inside the fence. Also `backend/runs/worker.py`. Checked by
> `py_compile`, `import backend.app`, a 19-assertion scratch script against a
> **real LangGraph graph** (including two deliberately overlapping runs), and
> the suite. **Not run:** uvicorn, a browser, the frontend.

**Why this needed the grant, not a workaround.** The backend's own part of §3
is three lines, but neither carrier could live here:
- A ContextVar in `backend/` would have to be imported by `agents/` and
  `vectordb/`, reversing this package's "nothing imports `backend/`" rule and
  risking an import cycle (`worker` imports `agents.supervisor`).
- `GraphState` is `state/state.py`, which this role drives as a black box.
  Pydantic ignores unknown fields, so `GraphState(profile_id=…)` without the
  field would have been **silently dropped** — bug#72's exact shape.

**Bug.** Every run in one process looked identical to the graph. Nothing below
`worker` could tell whose data it was allowed to touch, so the retriever's
collection, `save_gap_answers`, the plan cache, the snapshot folder and the
export folder all resolve globally — the mechanism behind "B's Profile agent
retrieves A's gap answers as evidence".

**Built.**
- `config.set_profile_id()` / `current_profile_id()` / `require_profile_id()`
  — a `ContextVar` beside `set_fake_llm`, for the reason proved on 2026-08-19:
  LangGraph runs a node inline only while it is the single runnable task; any
  parallel step goes to a `ContextThreadPoolExecutor` via `copy_context()`,
  where a `threading.local` is invisible and a module global is shared.
- `GraphState.profile_id` — the checkpointed copy.
- `worker._drive` binds the account on the run's own thread before the graph
  is built, and `run_worker` puts it on the initial `GraphState`.

**Decisions.**
- **A bare `profile_id`, not `deps.Scope`.** `Scope` carries a role, and
  nothing in the graph may depend on the caller being an admin — an admin's
  run reads the admin's own vault like anyone else's. No role in the graph
  means no path for a privileged caller to widen what a node sees.
- **Both carriers, deliberately.** The ContextVar is what nodes read, and it
  reaches code that never receives state (the retriever). The field is what
  survives the process, so a resumed run restores its scope from its own
  state rather than guessing.
- **`require_profile_id()` raises; `current_profile_id()` does not.** The
  fallback to "no scope" is not a harmless default — it is the shared,
  everyone's-data behaviour §3 exists to end. Consumers touching user data
  call the raising one; a bare CLI driver may legitimately run unscoped.
- **Bound inside `_drive`'s `try`**, so an owner-less run is a visible
  `run_error` rather than a silently global run or a dead thread; and in
  `_drive` rather than the two entry points, so a resumed run is scoped
  exactly like a fresh one.

**A real bug this surfaced, fixed here.** `_log_run`'s docstring promises it
never raises — but it read `run["owner"]` in its own argument list, *before*
`logplane.write` could honour that. On the failure path that made the error
handler itself throw: the `run_error` being reported was lost and the
exception escaped the worker. Now `.get()`. A log line that cannot name its
account is still worth writing; a run that cannot report why it failed is not.

**Checked** (19 assertions): the carrier set/get/clear and the raise; the
state field set, defaulted and surviving a `model_dump` round trip; **two runs
driven through a real `StateGraph`, held inside the node together by a
`threading.Barrier`, each reading its own account and neither the other's**;
a node seeing the same value on `state.profile_id` and in the ContextVar; an
owner-less fresh run reporting `run_error` naming `owner` with nothing run
unscoped; the same on the resume path; and the resumed run still driving its
loop.

**Suite:** `test_backend_api.py` + `test_backend_auth.py`
`29 failed, 423 passed, 19 xfailed` — **identical** before and after, same
failure set. The checkpointer path was checked directly instead of through
pytest: `make_serde()` dumps and loads `profile_id` intact and `state_types()`
still resolves 41 types. `tests/test_routing.py` is the one file that
enumerates `GraphState`, and its guard is covered under "Owed" below; the rest
of that file was still running after 40 minutes in this environment (another
lane's territory — the whole suite took 158.8s on 10-15), so its total is not
reported here rather than guessed.

**What is NOT built — and is not this lane's.** Every consumer still resolves
globally: the retriever's collection, `save_gap_answers`/`profile_commit`, the
plan cache, the snapshot folder, the export folder. Until they call
`require_profile_id()`, **this change isolates nothing by itself** — it is the
carrier they were blocked on. §3's vault-storage bullets (one checkpointer per
vault, the run trail under the vault, `list_for` reading only the caller's)
are untouched: a storage migration with its own blast radius.

**Owed elsewhere:** the CLI drivers (`scripts/run_graph.py`,
`run_gated_graph.py`) set no scope, so a CLI run will raise at the first
consumer that requires one — §3 already calls for `--profile` there.

**Owed (yours), one of them required by a guard that is working as designed.**
`tests/test_routing.py:test_the_artifact_fixture_covers_every_field` asserts
`set(_artifacts()) == set(GraphState.model_fields) - NOT_ARTIFACTS`, with the
comment "A new GraphState field has to be added to `_artifacts()`". So this
change fails it until `_artifacts()` gains one line — `"profile_id":
"p-abc12345"`, beside its `"run_id": "r1"` — which then carries the field
through that file's checkpoint and snapshot tests, exactly where I want it.
(Adding it to `NOT_ARTIFACTS` instead would skip those, so: `_artifacts()`.)
**That guard is already red without this change**, for `prompt_versions` —
another lane's `GraphState` field, never registered in the fixture. Measured:
the fixture is missing `{profile_id, prompt_versions}` now, `{prompt_versions}`
with mine excluded. So this adds a second name to an existing failure rather
than breaking a green test; both are one line each.
Also worth adding: two overlapping runs never share a scope (the `StubGraph`
already runs on its own thread, so the barrier shape above ports directly).
I verified the round trip separately — `make_serde()` dumps and loads
`profile_id` intact, and `state_types()` still resolves 41 types.

---
## 2026-10-22 (a node that changed nothing) — `"Round 8-10"` §6 built

> Backend API + Auth, Claude, on the user's grant ("fix the next most critical
> bug, irrespective of colour"). `backend/runs/worker.py` only. Checked by
> `py_compile`, `import backend.app`, a 14-assertion scratch script over stub
> graphs, and `test_backend_api.py` + `test_backend_auth.py` before/after.
> **Not run:** uvicorn, a browser, the frontend.

**Why this one.** Re-checked the ranked list first, because two rows above it
have moved. The `revision`/`max_revisions` 🟠 **needs no backend code at all**:
`utils/human_gate.py:226-227` now puts both on every gate payload, and
`_PAYLOAD_NOT_PASSED` excludes neither, so `_park` already relays them — that
row is waiting on the frontend and on `StubGraph`, not on this package (the
10-16 note said as much; re-verified in the tree today). The other 🟠s are
`/search` (needs vector metadata, KB+RAG) and `llm`/`retrieval` (other lanes'
writes). So §6 is the most critical thing this lane can actually fix.

**Bug.** A node that runs and produces nothing new still returns its `stage` —
`cv_link` skipping a re-read of the same CV after a gate-3 reject
(`agents/CV_Link.py` returns `{"stage": Stage.DOCUMENT}`), `profile_enrich`
with no answers to add. `_drain` emitted that `{stage}` dict as the node's
**artifact**, so the UI saw an empty result where a full CV read had been, and
the frontend grew a `cv_link`-shaped special case to keep the earlier one
(`PipelineView.jsx:75`).

**The fix.** When an update holds nothing but `stage`, `node_done` carries
`unchanged: true` and **no `artifact` key at all**.

- **Still a `node_done`.** `node_start` was emitted for this node, so skipping
  the done would leave the step pulsing "working" forever.
- **Generic, not `cv_link`-cased.** `profile_enrich`'s no-answers return is the
  same shape and gets the same treatment; a future node does too. The special
  case this replaces is exactly how `AGENTS`/`GATES`/`STUB_NODES` drifted.
- **No key, rather than `artifact: null`.** Both read as falsy, but an absent
  key cannot be mistaken for "the node returned null".
- **`stub` and the duration log are unchanged**, so nothing else about the
  event moves.
- **Safe against today's frontend, checked before changing the wire** (its code
  is the thing that has to survive this):
  `rereadSkipped = ev.node === "cv_link" && !ev.artifact?.line_links &&
  run.artifacts.cv_link` still fires with the key absent, so cv_link keeps its
  earlier read; `StatePanel.jsx:260` filters cards on `artifacts[n]`, so a
  no-change node now hides its card instead of showing `{stage: "document"}`;
  and `renderArtifact` already guards falsy with "no output yet". The frontend
  can now drop its special case for the generic rule it asked for, but nothing
  breaks if it doesn't.

**Checked** (14 assertions): a skipped `cv_link` re-read gives one `node_done`,
`unchanged: true`, no `artifact`, `stub` still present; `profile_enrich`'s
no-answers return gives the same; a **real** `cv_link` result still carries its
artifact with `match_counts` and a scrubbed `cv_tree` and no `unchanged` flag;
a stub node with only a stage is still flagged a stub; an artifact that merely
*contains* `stage` beside a `fit_report` is still a real result; a genuinely
empty update still emits nothing (unchanged behaviour); and a `messages`-only
update counts as no change, since `messages` is stripped first.

**Suite:** `test_backend_api.py` + `test_backend_auth.py`
`29 failed, 423 passed, 19 xfailed` — identical before and after.

**Owed (yours):** a `StubGraph` loop-back case asserting the second `cv_link`
`node_done` has `unchanged: true` and no `artifact`. **Frontend:**
`PipelineView.jsx:75`'s `rereadSkipped` can become the generic "keep the
previous artifact when `ev.unchanged`" rule, and `AGENT_TITLES`-level copy can
say "no change" for it.

---
## 2026-10-22 (account export) — `"2026-10-09 (design)"` §6, export half built

> Backend API + Auth, Claude, on the user's grant ("fix the next most critical
> bug, irrespective of colour"). New `backend/routes/me.py`; helpers added to
> `backend/cv_store.py` and `backend/runs/registry.py`; registered in
> `backend/app.py`; one allowlist entry in `backend/logplane.py`. Checked by
> `py_compile`, `import backend.app`, a 28-assertion scratch script over a real
> `TestClient` with two accounts, and the backend suites before/after.
> **Not run:** uvicorn, a browser, the frontend.

**Why this one, and why only half.** What is left in this lane is §6 and the
A3 "cited records on `gate_wait.changes`" robustness ask, which the frontend
already satisfies from the stream and which survives a resume. §6 is the only
one where a user cannot do something at all: there was no way for an account
to get its own data out.

**The delete half is NOT built, and that is a finding, not a shortcut.** Step
3 of §6's own plan is "drop its collection". There are no per-profile
collections yet — every account's evidence is embedded into the shared
`profile` collection — and `vectordb/store.py` has **no `delete`** (checked:
`bugs_audit_fixed.md` #30's open half). Deleting the tokens, the vault folder
and the account row while the user's embedded text stayed searchable would be
a deletion that lies about itself, so it waits for the KB lane rather than
shipping a half-truth.

**Built:** `GET /api/me/export` → `application/zip`:
```
account.json          profile_id, identifier, role, runs_remaining, exported_at
profile_entries.json  this account's Build-Profile entries
cv/index.json         the CV index, with status and stored_name
cv/<sha>.pdf          every CV file the index still names
runs/<run_id>.json    every run trail this account owns, in full
documents/<name>      the CVs saved out of those runs
logs.json             this account's own audit entries, as /logs/mine projects them
```

**Decisions.**
- **An admin exporting itself gets only its own data.** `visible_entries` and
  `registry.owns()` both widen for role `"admin"` — correct for an admin tool,
  wrong for "export my account". The route builds `Scope(profile_id, "user")`
  over its own id, the same move `routes/admin.py` makes in the opposite
  direction. Asserted: the admin's own export carries no entry and no run of
  anyone else's.
- **A new `registry.records_for_owner()`, not `list_for`.** `list_for` answers
  "what may this caller see" (widens for admin, returns summaries); an export
  needs "what belongs to this account", in full. It reads through `load_log`,
  so a damaged file is skipped here exactly as everywhere else (#68 item 6).
- **An ownerless (pre-10-10) run log is never exported.** It belongs to no
  resolvable account, and exporting it would hand it to the first account that
  asked.
- **Saved CVs are found through each run's own `current_export()`**, not by
  guessing this owner's folder name under `OUTPUTS_DIR` (which `utils/export.py`
  slugs). Each path still goes through `contained_path()`, so a record naming
  something outside `OUTPUTS_DIR` is skipped rather than read.
- **`cv_store.export_files` walks the index, never the directory.** A stray
  file dropped in the folder cannot leave in an export, and `index.json` is not
  re-shipped as a CV.
- **A size ceiling (`MAX_EXPORT_BYTES`, 64 MB) → 413.** The zip is built in
  memory; CV PDFs are capped at 5 MB each but an old account with many saved
  CVs should fail loudly rather than take the process down.
- **No secret in the zip.** Not the bearer token, not `ADMIN_TOKEN`, not an API
  key — asserted by searching the whole archive for every real token value.
- **Audited as `account_exported` with `bytes` only**, user-visible. Naming the
  contents would copy this account's data into the log plane, which the log
  plane's own rule forbids.

**Checked** (28 assertions, two accounts + the admin): the zip's shape,
content-type and filename; Alice's entries/runs/documents present and correct;
**Bob's entry text, Bob's document text and the ownerless entry all absent from
Alice's archive**; no bearer token anywhere in it; exactly one CV PDF, Alice's;
the admin's self-export empty of user data; a damaged and an ownerless run log
skipped without error; an empty `profile_id` exporting nothing; the audit entry
present in `/logs/mine` with `bytes` only; unauthenticated 401; Bob's export
being Bob's; and a lowered ceiling producing 413.

**Suite:** `test_backend_api.py` + `test_backend_auth.py`
`29 failed, 423 passed, 19 xfailed` — identical before and after.

**Owed (yours).** `test_backend_api.py`'s `USER_ROUTES` needs
`("GET", "/api/me/export")` — but note those two route-table tests are
**already failing for an unrelated reason**: this FastAPI version wraps
included routers in `_IncludedRouter` objects with no flat `.path`, so the
test's own collector returns an empty set (that is `bugs_audit_fixed.md` #84's
"FastAPI version drift"). The route itself is registered — `app.openapi()`
lists `/api/me/export` among 28 API paths, and the scratch client gets 200.
**Frontend:** an Account-page "Download my data" button on this route.

---
## 2026-10-22 (an empty auth store) — new, found while ranking what was left

> Backend API + Auth, Claude, on the user's grant ("fix the next most critical
> bug, irrespective of colour"). `backend/jsonstore.py`, `backend/auth/store.py`,
> `backend/auth/profiles.py`. Checked by `py_compile`, `import backend.app`, a
> 26-assertion scratch script, and the backend suites before/after.
> **Not run:** uvicorn, a browser, the frontend.

**Why this one.** Everything left on the ranked list turned out to belong to
another lane, which I checked in the tree rather than trusting the rows:
`final_changes` — the producer A3 needs — is `utils/human_gate.py`; the
`revision`/`max_revisions` 🟠 is already relayed; `/search` needs vector
metadata; `corrections.json` needs a move out of `backend/`; §6's delete needs
a `VectorStore.delete` that does not exist. What *is* in this package is a gap
I flagged on 10-17 and left as "wants the same look", never logged as a bug.
Ranked by this lane's own rule — data reaching the wrong account, then a
cross-account read, then lasting damage to shared state — it sits at the top
of what is actually mine.

**Bug, reproduced before it was written up.** `read_json` returns `[]` for a
file that is absent, empty **or whitespace**. For a cache that is right. For
these three stores "no records" is a decision:

```
empty profiles.json:
  profiles.profile_for("Alice")   -> None          # "that account does not exist"
  profiles.create_profile("Alice") -> p-21166ea6   # a SECOND profile for a held name
  file now holds: ['p-21166ea6']                   # every other account's mapping, gone
empty requests.json:
  store.list_requests()           -> []            # the admin sees an empty queue
  create_request("Cara")          -> re-queued, and the file now holds only that row
empty tokens.json:
  store.resolve_token(<valid>)    -> None          # a valid credential reads as unknown
```
Two harms, not one. The answers are wrong, and because every writer here is a
read-modify-write, the empty read **becomes the next write** — so a transient
empty file turns into permanent loss of every row. `jsonstore.write_json` is
atomic (tmp + `os.replace`), so an empty auth file is never normal: it is
damage, and it was being read as consent.

**The fix.** New `jsonstore.read_records(path)`, used at all 18 read sites in
the two auth modules: `[]` **only** when the file does not exist (a genuine
first run); a present-but-empty or whitespace file raises; a parse that is not
a list raises.

- **The corrupt case is untouched, on purpose.** `json.loads` keeps raising
  `JSONDecodeError`, because `test_the_admin_still_gets_in_when_tokens_json_is_corrupt`
  pins exactly that — and pins that `ADMIN_TOKEN` is compared *before* the file
  is read, so the admin can still sign in and repair it. Both halves re-checked
  here, for the empty case as well as the corrupt one. This is the same test
  that made me revert a tolerant-read fix on 10-17; this change moves in the
  other direction, which is what that decision asks for.
- **Absent still means empty.** A first run has no files, and signup →
  approval → login still works end to end (asserted).
- **A real `[]` on disk is still fine** — that is a store with no rows, written
  deliberately.
- **Scoped to the auth stores.** Run logs have their own tolerant rule (#68
  item 6: a damaged log is an *unknown run*, 404) and `manual_entries.json` may
  legitimately be empty. Nothing else moved onto `read_records`.
- **Raising, not repairing.** The caller cannot know what the file held, so
  inventing a value is how data gets lost; the one thing worth guaranteeing is
  that nothing writes over it. Asserted: after every refusal the damaged file
  is byte-for-byte unchanged.

**Checked** (26 assertions): `read_records` over absent / rows / empty /
whitespace / corrupt / non-list / real `[]`; the reproduced `profiles.json`
damage now refused at `profile_for`, `create_profile`, `get_or_create_profile`
and `display_for`, with the file untouched and a repaired file working again;
`tokens.json` corrupt **and** empty both leaving the admin door open while a
user token raises; an empty `requests.json` refusing both the admin queue and a
re-queue; and a clean first run with no files at all.

**Suite:** `test_backend_api.py` + `test_backend_auth.py`
`29 failed, 423 passed, 19 xfailed` — identical before and after, the pinned
corrupt-tokens test included.

**Owed (yours):** a test per store that a present-but-empty file raises and
leaves the file unchanged — the natural twin of
`test_the_admin_still_gets_in_when_tokens_json_is_corrupt`.

---

## 2026-10-10 (frontend, Rounds 17–26) — what the latest frontend fixes need from auth, data handling and the API

Written by the **Frontend lane (Claude)** after ten small fixes in `frontend/src`
(`frontend/bugs.md` → Rounds 17–26; **none built yet**). Every item names the
frontend code that depends on it. Checked against the backend source on
2026-10-10 evening, after this morning's backend fixes (the CV routes; items 1,
2 and 4 of the gate-4 section; item 4 of the "Rounds 8–10" section). Severity
scale as above. Where the vault design above already covers something, this
section points at it instead of repeating it.

### Already provided, and now relied on — tell the frontend before changing any of these

| Contract (checked in code) | What depends on it |
|---|---|
| A refused gate answer is always **409** ("no gate waiting", "already answered", "moved on") | `GateScreen` retires the form on any 409 and sends nothing more (Round 17). A different status for "stale" would leave a dead form live. |
| `run_error` carries `final` once gate 4 was answered (`worker.py` 267–279) | `PipelineView.applyEvent` and `extractFinalArtifacts` read it, so a CV saved before a later failure shows as saved (Round 21). |
| The run log is saved for **every** ending (`on_finish` runs in the worker's `finally`) | A stopped or failed run's end line says "Everything up to that point is saved in Runs" (Round 21). |
| The backend never answers **502** itself (no `HTTPException(50x)` anywhere) | `api.js` reads a 502 whose body isn't JSON as the proxy (nginx, Caddy) saying the backend is down, i.e. status 0, "cannot reach the backend" (Round 24). If a route ever needs a 502, send JSON `{detail}`; it will then be shown as sent. |
| Gate-4 answers reach agent memory **on live runs only**; gates 1–3 never do (`utils/final_review.close_run` → `record_learning`) | The feedback label and the CV-editor text say exactly this (Rounds 25–26, strings in `copy.js`). Change either side and the other must follow. |
| `GET /profile/cv` → `{cv: null}`, never 404; 403 for another owner's `cv_id`; 409 on `POST /runs` with no CV, before any run is spent | `CvContext`, `CvStrip`, `PipelineView` (Round 12). Checked against `routes/cv.py` and `routes/runs.py` today: every path, shape and status matches. |

**401/403 discipline:** every route this round's code calls (CV routes, gate
answer, document download, run start) answers 403/409/422 for refusals, never
401. Nothing to do.

### Authentication

#### A1. 🟠 A re-issued token loses its CV — and since the CV routes landed, it can't start a run

> **✅ Fixed 2026-10-10, later the same day — "2026-10-10 (identity)" above.**
> `cv_store` is keyed on `scope.profile_id` now, not `token_id`
> (`routes/cv.py`, migrated in the same session that added `profile_id`).
> The check below passes as written. Kept verbatim for the record.

`cv_store` keys every CV on `token_id`. A user whose token is re-issued (lost
token, top-up) gets a new `token_id`, so `GET /profile/cv` answers `{cv: null}`:
the strip reads "CV · none yet", `POST /runs` answers 409, and the frontend keeps
Start disabled until they upload again. The old file stays on disk under the old
id, unreachable. Before today this cost a CV; now it also blocks the user.

- **Fix:** the vault design's §1 (`profile_id` on the identity; CVs, runs and
  outputs keyed on it).
- **Don't bridge it by identifier** in the meantime: identifiers aren't unique
  yet (§1's takeover bug), so moving `uploads/<old>/cv/` to the new token by
  name would hand one user's CV to another.
- **Check (once §1 lands):** upload a CV, re-issue the token, sign in with the new
  one → the strip shows the same CV and Start is enabled.

**The frontend owes one thing here:** the backend now accepts
`client_request_id` on `POST /runs` (item 4 of the "Rounds 8–10" section), but
`PipelineView.start()` doesn't send it yet. Until it does, the idempotency only
protects callers other than this UI. Frontend task, not backend.

### Data handling

#### D1. 🟠 Re-uploading a stored CV answers like a new pending upload, so the UI's Cancel deletes it

`cv_store.ingest_pending`: identical bytes give the same `sha` id. If that entry
is already confirmed, the index is left untouched (`return None, None`), but the
route still answers **201 `{cv, preview}`** with a fresh `uploaded_at`, exactly
like a new pending upload. The UI throws away an unconfirmed upload with
`DELETE /profile/cv/{id}` (on Cancel, on picking another file, and when Start
closes the strip), so that DELETE removed the **stored** CV and its file. On
Start, the run had just resolved that file and failed at CV Reader.

- **Frontend, Round 20:** `CvStrip` never deletes the id of the **current** CV.
  That covers the common case (re-uploading your CV to see "What we read"). It
  can't cover an **older** confirmed CV (replaced, kept per D-CV3): the client
  has no list of them, so re-uploading one and pressing Cancel still deletes it.
- **Fix:** the upload reply says what it stored, e.g.
  `{cv, preview, stored: "pending" | "current" | "kept"}`, and `cv` is the
  **stored** summary (original `uploaded_at`) when nothing new was written. The
  frontend will then say "This is already your CV" and skip the DELETE.
- **Check:** upload the current CV again → `stored: "current"`, its original
  date; replace it, upload the old one again → `stored: "kept"`; a new file →
  `stored: "pending"`.

#### D2. 🟠 Deleting a CV removes a file a run still needs

`cv_store.delete` unlinks the file unconditionally (the "CV no run references"
check is marked not built in item 2 of the CV section). Account → Delete while a
run is working on that CV: if CV Reader hasn't read it yet, the run fails with
`run_error`, and a paused run resumed after a restart (gate-4 section, item 7)
can't re-read it. `frontend/design.md` already sets the rule: "A CV referenced by
a run log is not deleted while that log exists. Deleting the current CV only
clears the pointer."

- **Fix:** `delete` clears `current_id` first, then removes the file only if no
  in-flight run's `cv_path` and no saved run log's `cv.id` names it. Otherwise it
  marks the entry `deleted` in `index.json`: hidden from `GET`, kept on disk.
- **Check:** start a run, delete the CV from Account before CV Reader runs → the
  run still completes; `GET /profile/cv` → `{cv: null}`; the file is still there
  until its run logs are gone.

#### D3. 🟠 Agent memory now holds users' CV lines — shared, unowned, and not git-ignored

The frontend now tells live users "The lines you change are also kept in agent
memory" (Round 26), because that is what happens: `record_learning` writes every
gate-4 answer to `knowledge_base/learning/document/feedback.jsonl` and each
changed CV line, before and after, to `corrections.json`. Known
(`context/bugs_audit_fixed.md` #55, vault decision D-T5), but now user-visible,
with two gaps:

- **Not git-ignored.** `git check-ignore` finds no rule for
  `knowledge_base/learning/`; the folder is untracked today, so the first
  `git add` of it commits real CV lines. `feedback.jsonl` holds only live
  records and can be ignored as it is. `corrections.json` also holds the seeded
  fixtures (`utils/setup_kb_prep.py`), so live corrections need their own file
  (ignored) before the seeds can stay tracked.
- **One folder for every user, no owner field.** D-T5's per-user memory in the
  vault is the fix; until then, at least stamp `owner` on every record so they
  can be moved or deleted later.
- **Tell the frontend** if D-T5 changes where memory lives, or lets demo runs
  write: `FEEDBACK_LABEL_*` and `FINAL_EDIT_HELP*` in `frontend/src/copy.js`
  state the current rule.

### Backend API and worker

#### B1. 🟠 Round info on every `gate_wait` — gate-4 item 3, still not built, and now three screens work around it

Checked: `GATE_EXTRAS` (`utils/human_gate.py`) adds only `gap_questions` and
`changes`, and `routing` events carry no reason or redo flag, so the browser
can't count the run's redos. Three frontend fixes approximate it:

- **Round 19:** the "round N · reopened with a redone version" label counts
  repeat `gate_wait`s for the same gate name in the browser.
- **Round 18:** the final review says a reject at the limit ends the run
  unsaved, but can't say when that is.
- **Round 23:** checkpoints 1–3 say that once the redos are used, rejecting
  lets the run carry on with that version. That is `decide()`'s rule: at the
  cap it stops honouring a reject and advances, so the run continues with the
  output the user just rejected, and the log reads "you rejected" followed by
  the next step starting.

**Asks (one line each, Agents lane for the first):**
- `revision` and `max_revisions` on **every** gate's interrupt payload, as item 3
  says. The worker passes extras through unchanged.
- `gate` on `gate_done` (item 3's other half).
- `honoured: false` on `gate_done` when a reject was not acted on
  (`decision == "reject" and revision >= max_revisions`), so the log and the
  screen can say "rejected, but no redos were left".

**Check:** with `max_revisions=1`, reject gate 1 twice. The second `gate_wait`
has `revision: 1, max_revisions: 1`, and the second `gate_done` has
`honoured: false`.

#### B2. 🟡 `run_error.error` is a raw exception string, and users now see it in two places

The Pipeline screen's end line (Round 21) and the activity log show `ev.error`
verbatim, for example `RateLimitError: Error code: 429 - {…}` or a
`FileNotFoundError` naming `uploads/<token_id>/cv/<sha>.pdf`. (`token_id` is the
token record's id, not the secret token, checked in `auth/store.py`, so no
credential leaks. Server paths and provider error bodies do.) The vault design's
log plane already says a user sees an error **message**, never stack traces or
server paths.

- **Ask:** `run_error` carries `message`, a plain sentence per known failure
  (rate limited, provider unreachable, CV file missing; otherwise "A step failed.
  The details are in the server log."). The raw `error` goes to the log plane.
- **Frontend side, once it lands:** prefer `message`, fall back to `error` for
  old logs.

#### B3. 🟡 `outcome` on run summaries — the last place a failed run still reads as "stopped"

Since Round 21 the Pipeline screen tells finished, stopped and failed apart.
Runs and Account still can't: `list_for` gives only `completed`, so both other
endings show "stopped". (This is `frontend/bugs.md` Round 5 item 5.)

- **Ask:** `outcome: "done" | "stopped" | "error"` from the last terminal event.
  `list_for` already scans the events. Do it in the same loop as gate-4 item
  5(b) (`review`, `saved`).
- **Check:** a superseded run lists as `stopped`, a crashed one as `error`, an
  old log with no end event as `null`.

### What the frontend owes back

- Send `client_request_id` (one `crypto.randomUUID()` per Start click) on
  `POST /runs` (A1's note).
- Read `revision` / `max_revisions` / `honoured` once B1 lands, and replace the
  three approximations it lists.
- Read `message` on `run_error` (B2), `stored` on the upload reply (D1), and
  `outcome` on summaries (B3).

### Verification status: **nothing run, nothing built**

This section is documentation only. Facts come from reading
`backend/routes/{runs,cv}.py`, `backend/cv_store.py`,
`backend/runs/{worker,registry}.py`, `backend/auth/store.py`,
`utils/{human_gate,final_review}.py`, `agents/supervisor.py`,
`state/state.py`, `.gitignore` and `git check-ignore`.

---

# 2026-10-10 — session close: five fixes landed; what they still need from Authentication and Data Handling

> Five items fixed this session, each logged in full at its own dated entry
> above: the gate double-answer race (🔴, "gate 4" #1), the two-starts-per-owner
> race + idempotency key ("Round 8-10" #4), an approved CV lost on a
> post-gate-4 failure ("gate 4" #2), the `cv_link` privacy scrub ("later" #4),
> `gap_answers` hardening ("Round 8-10" #1), and the `feedback` size cap
> ("gate 4" #4). All inside `backend/`; nothing run beyond `py_compile`, import
> checks and scratch tests, per each entry. This section is the two
> cross-lane follow-ups those fixes surface — not new bugs, but new
> dependencies on work this role doesn't own.

## Needed from Authentication / Identity

> **✅ Resolved 2026-10-10, later the same day — "2026-10-10 (identity)"
> above.** Restated below exactly as written at the time, for the record;
> don't act on it as still-open.

The per-owner concurrency fix added two new in-memory structures,
`registry._owner_locks` and `registry._seen`, both keyed on `owner =
identity["token_id"]` — the same key `_active` and `owns()` already use, and
the same key the per-user-vault design above (§1, "Identity first") already
flags as wrong long-term: **a re-issued token is a different `token_id`, so
it is a different owner to everything keyed on it.**

That existing finding now has two more things riding on it:
- A user who re-issues a token (`Account.jsx`'s "request more runs") gets a
  **new, empty** `owner_lock` and an **empty** `_seen` map. Their old token's
  in-flight run (if any) is invisible to the new token's start — the two
  could race each other exactly the way §1 above describes for `_active`,
  just one level removed, now that a second lock/dedup mechanism exists that
  also doesn't know they're the same account.
- `_seen`'s dedup is therefore only as durable as one token's lifetime. A
  retried request against a *new* token after a re-issue can't be recognised
  as a duplicate of anything the old token started.

**Nothing to do about this now** — it's the same root cause §1 already
schedules fixing (`profile_id` replacing `token_id` as the owner key), not a
new problem needing its own fix. Flagging it so that migration's checklist
gets two more call sites (`owner_lock`, `_seen`/`remember`) added to the ones
already named there (`_active`, `owns()`), rather than being rediscovered
after the fact.

**What actually happened:** neither needed its own code change.
`owner_lock()`/`seen()`/`remember()` are owner-agnostic by construction —
they take whatever string the caller passes as `owner`. The moment
`routes/runs.py`'s `start_run` started passing `scope.profile_id` instead of
`identity["token_id"]` (the identity session), both structures started
keying on accounts automatically, with zero lines touched in `registry.py`
itself. The race this section worried about — a re-issued token getting an
empty lock/dedup map invisible to the old token's in-flight run — can no
longer happen, because both tokens now resolve to the same `profile_id` and
therefore the same lock and the same dedup entry.

## Needed from Data Handling

Two of this session's fixes are explicitly partial, and the missing half in
both cases is storage-shaped, not code-shaped — it's the per-user vault /
log-plane design above (§13-§15), not a gap in what landed today:

- **The `cv_link` scrub reduces *content*, not *storage*.** `_scrub_cv_tree`
  stops the header section and `raw_text` from ever reaching an event or a
  run log. It does nothing about the fact that every run's log still lands
  in one shared `logs/frontend_runs/` folder (the design above, "What breaks
  this model today"), so a scrubbed-but-still-substantial CV tree for every
  user sits in one place rather than in a per-account vault. The scrub is
  the right stopgap for the PII that mattered most (name, email, phone); the
  isolation question is unchanged by it and still needs §13/§15.
- **`gap_answers` validation is correctness, not isolation.** The new caps
  and the wrong-gate/unknown-key 422s stop a malformed or stale answer from
  reaching `enrich()` at all. They do nothing about where a *valid* answer
  then goes: the same shared `manual_entries.json` file and the same shared
  `profile` Chroma collection every user's run reads from today (the design
  above, item 4's table row on `GET/PUT /profile/entries`). Tighter
  validation does not make that data any more isolated between users — the
  §13.1/§13.3/§13.5 work is still the actual fix, unaffected either way by
  this session.

  > **Partially closed 2026-10-10 — "2026-10-10 (profile scope)" above.**
  > `GET`/`PUT /api/profile/entries` (and the mirror route,
  > `GET /api/kb/profile/manual_entries`) are now owner-scoped: a non-admin
  > can no longer read or overwrite another account's entries through
  > either route. That closes the *access-control* half of this paragraph.
  > The *storage* half is exactly as true as it was written: the file is
  > still one physical `manual_entries.json` for everyone, and `/search`'s
  > `profile` Chroma collection is still unfiltered and shared — both still
  > need §13.1/§13.3/§13.5, unaffected by this. (A real wrinkle from the same
  > fix, flagged loudly in its own section rather than here: entries written
  > by `learning/profile_store.save_gap_answers` — gate-2 answers — have no
  > `owner` field, so they're now admin-only-visible to their own author
  > until that module stamps one too.)

**Unrelated to this session, restated only so it isn't lost:** `outputs/`
(the saved-CV files `GET /api/runs/{id}/document` serves) still lives inside
the app folder rather than a mounted volume, so it doesn't survive a
redeploy without the §15 persistence plan. Nothing this session touched
changes that either way.

---

## 2026-10-14 (frontend, Rounds 27–42) — what this session's frontend fixes need from the backend

> **Written by the Frontend lane**, on the user's request. No backend code
> was touched.
>
> - **Checked:** every item below against the backend code on 2026-10-14,
>   including this file's own 10-13 to 10-15 sections (restart survival,
>   saved CVs, the `run` log kind, `gate` on `gate_done`).
> - **Frontend detail:** `frontend/bugs.md`, its top list and one entry per
>   round for Rounds 27–42. All of them compile (last built 2026-10-14);
>   none has run in a browser.
> - **The same asks in architecture form:** `backend/context.md` → "What
>   the frontend needs from the backend — after frontend Rounds 27–38",
>   written 2026-10-13. Where the two differ, **this entry is newer**: its
>   §B item 3 (a probe route) is superseded by the restart-survival work,
>   see C1 below.

### A. New asks, most critical first

**A1. 🟠 Read `final` from `run_error` too, everywhere `final` is read.**
- Since `"gate 4"` §2 ("closing out on failure after gate 4"), a CV
  approved at the final review before a later step fails carries `final`,
  including `export`, on **`run_error`**, not `run_done`.
- Three readers still look only at `run_done`:
  - `routes/runs.py` → `download_document`, so it answers 404 for a file
    that exists;
  - `runs/registry.py` → `delete_document`, so it can't delete that file;
  - `runs/registry.py` → `list_for`'s new `review` and `saved`, so Runs and
    Account will show such a run as never reviewed and not saved.
- **What the user sees today:** the live page reads `final` off either
  event (frontend Rounds 21 and 36). So it says "approved — saved", offers
  "Download .md" / "Download .txt", gets the 404, saves the page's own copy
  instead, and says why (`finalDownloadFallback`). The file the server kept
  can't be fetched or deleted.
- **Fix:** read `final` off whichever end event the run has (the last
  `run_done` or `run_error`). One small helper would serve all three.
- (`frontend/bugs.md` top, item 26.)

**A2. 🟡 Name the failed step on `run_error`** (for example `node`).
- Frontend Round 33 settles the agent graph on a failure: the step left
  "working" turns red "failed". That inference is the only clue on screen.
- An error outside a step (the Supervisor, `_close`) leaves nothing
  "working", so nothing is marked.
- The data is already there: `emit()` appends every event to
  `run["events"]`, so in `worker._drive`'s `except`, the last `node_start`
  without a matching `node_done` names the step that was in flight.

**A3. ⚪ Optional: put each cited record's text on `gate_wait.changes`**
(for example `evidence: [{id, content}]`).
- Frontend Round 37's "records it cites" builds a `source_id → text` map
  from every `node_done` artifact's `evidence` on the stream.
- That works today, and still works after `POST /resume`, because the log
  persisted at gate open replays the earlier events.
- So this is only a robustness ask: the review would no longer depend on
  the full event history.

**A4. ⚪ Optional: clamp `/search` scores to 0–1, or document the range on
the route.**
- `score = 1 − cosine distance`, so it runs from −1 to 1.
- The frontend caps it to 0–100 for display (Round 35).

### B. Behaviour the frontend's code now relies on: keep it, or tell `frontend/` first

| Behaviour | Where | Frontend code that depends on it |
|---|---|---|
| A **401 means only a missing, malformed or unknown token**, never "wrong role", "not yours" or "out of runs" | `deps.py` | Round 42: `AuthContext.refresh()` now signs the user out on a 401 from `/auth/me`, and a dropped stream probes with it. Any other kind of 401 would now log users out from there too |
| `POST /auth/request-more {note}` tops up the caller's **own** token on approval, and a duplicate pending top-up is a 400 with a plain reason | `routes/auth.py`, `auth/store.py` | Round 39: Account's "request more runs", its wording ("same account, no new token, no new sign-in") and its error line (`err.detail`) |
| **Build Profile listing is owner-scoped:** a user sees and edits only their own entries; the admin sees all; a foreign `PUT` is 403; ownerless entries (all gate-2 answers today) are admin-only | `routes/profile.py` → `visible_entries` | Round 40: role-aware `BUILD_PROFILE_*`, a note that a user's checkpoint answers aren't listed, and a plain 403 sentence. **When `save_gap_answers` stamps an owner, tell the frontend:** the note becomes false |
| **Retrieval and `/search` are one shared, unscoped `profile` collection** | `agents/profile.py`, `cv_match`, `vectordb/lookup.py`, `routes/kb.py` | Rounds 27, 28 and 40: `EVIDENCE_SHARED*`, `GAP_HELP`, and the second half of `BUILD_PROFILE_HELP*` ("every run reads them, and evidence search can find them"). **When retrieval or `/search` is scoped (design §3), tell the frontend the same day** |
| `POST /runs` dedupe: remembers only **started** runs per (owner, `client_request_id`) for 10 minutes; a repeated id returns that run and **ignores the body** | `routes/runs.py`, `registry.seen` / `remember` | Round 29: one id per start, reused only while the job description and mode are unchanged, cleared on success |
| A **gate answer's 404 means only "this process doesn't hold the run"**. Stale, already answered and moved on are all 409; not-yours is 403 | `routes/runs.py` → `answer_gate` | Rounds 17 and 31: the form retires on either. See C1: what the 404 *means to the user* changed with restart survival |
| Answer caps: `feedback` ≤ 2,000, each `gap_answers` value ≤ 2,000, `edited_content` ≤ 50,000 | `GateAnswer` | Rounds 34, 38 and 41: each box stops at exactly its cap and shows a count. Change them together |
| `final.export` is `{md, txt}` and `GET /runs/{id}/document?fmt=md\|txt` serves either | `utils/final_review`, `routes/runs.py` | Round 36: "Download .md" / "Download .txt" and "saved on the server as …" |
| `gate_wait.changes[]` = `{node_id, where ("Section › Entry" or "Section"), before, after, reason, evidence_ids}`, with `evidence_ids` = `ProfileBlock.source_id` values carried in `node_done` artifacts' `evidence` | `utils/human_gate.final_changes`, `worker._drain` | Round 37: grouping, "was" / "now", word highlights, "records it cites" |
| `run_stopped` only while parked at a gate; `run_error` from the graph's `except` | `worker` | Round 33: `settle()` marks a "waiting" review as stopped, and a "working" step as failed or stopped |

### C. What changed under the frontend since 2026-10-13, and what that means

These are frontend work, listed so this lane knows the new routes have a
consumer coming, and which frontend wording they made false.

- **C1. Restart survival (10-13) makes frontend Round 31's wording false.**
  - On a gate answer's 404 the page says "This run is no longer on the
    server — that happens when the server restarts — so it can't continue",
    and "this run … can't be finished — start a new one" (`GATE_GONE`,
    `RUN_GONE`). With `POST /runs/{id}/resume` and `list_for`'s
    `interrupted`, the run **can** continue.
  - The stream-lost line's "reopen it from Runs once it finishes" is also
    off: a parked run's log is now persisted at gate open, and lists as
    `interrupted`.
  - The frontend needs **no new route** for this: on a 404, it can find the
    run in `GET /api/runs` (`interrupted: true`), offer Resume
    (`POST …/resume`, handling its 409s, including "Another run is already
    active for this owner"), and reopen the stream.
  - That supersedes `backend/context.md`'s §B item 3 (a probe route), and
    unblocks `frontend/bugs.md` items 10 and 21, plus item 9's last case
    (an edit lost to a session ending).
  - **One thing to keep:** there's no automatic resume at startup
    (`app.lifespan`), so a 404 on a gate answer still reliably means "not
    held by this process". Tell the frontend if that changes.
- **C2. Saved CVs (10-13):** `list_for`'s `review` / `saved` and
  `DELETE /runs/{id}/document` unblock `frontend/bugs.md` item 22 (a badge,
  a download and a delete on Runs and Account). Subject to A1.
- **C3. `gate` on `gate_done` (10-15):** nothing needed. The frontend keys
  rounds on `gate_wait`'s `gate` (`gateKey`), and doesn't read `gate_done`'s.

### D. Earlier frontend asks — status checked in code, 2026-10-14

| Ask | Status |
|---|---|
| A1 of `"2026-10-10 (frontend, Rounds 17–26)"`: key CVs on `profile_id` | ✅ Done (identity work) |
| B1: `revision` / `max_revisions` on `gate_wait`, `honoured` on `gate_done` | ⬜ Waits on a line in `utils/human_gate.py` (Agents lane). `gate` on `gate_done` is done, but isn't this ask |
| B2: a plain `message` on `run_error` | ⬜ Open (`frontend/bugs.md` item 19) |
| B3: `outcome` on run summaries | ⬜ Open: `list_for` gained `review`/`saved`/`interrupted`, not `outcome` (`frontend/bugs.md` item 18) |
| D1: say what an upload stored | ⬜ Open: a byte-identical re-upload of a confirmed CV still answers like a new pending upload under that CV's id |
| D2: keep CV files a run references | ⬜ Open: `cv_store.delete` still says "not built yet" |
| D3: agent memory holds real CV lines, shared and not git-ignored | Not `backend/` (`learning/`) |
| Build Profile owner scope | ✅ `/profile/entries`, `/kb` manual entries. ⬜ `/search`, and retrieval itself (design §3) |
| Gate-2 answers carry no `owner` | ⬜ `learning/profile_store.save_gap_answers`, not `backend/`. See B's Build Profile row |
| `cv_link` per-line CV text in the stream and log | ⬜ Deferred by design ("gate 4" §8) |
| Token management (`/api/auth/tokens*`), a revoke | ⬜ Open. The frontend now notices a dead token anyway (Round 42), so this is admin capability, not a frontend blocker |

---

## 2026-10-15 (admin tooling) — E1. 🟠 There is no server-side admin script: granting a token and watching users/network is hand-done over HTTP

**Found while** trying to spin up a run from the terminal: nothing wraps the admin
duties. `scripts/dev.py` only starts services and tails the access log
(`monitor`); `scripts/smoke_backend.py` approves a request but only as a test
step. To grant a token today the operator must curl `GET /api/auth/requests`
then `POST /api/auth/requests/{id}/approve` with `ADMIN_TOKEN` as a Bearer
header, or log into the UI with `ADMIN_TOKEN`.

**Wanted:** one admin script (e.g. `scripts/admin.py`, or a `dev.py admin`
subcommand) that runs **server-side only** and owns three jobs:

1. **Grant access.** List pending requests; approve (print the raw token once —
   it is never retrievable again) or reject; set or top up a user's run
   allowance; revoke a token. Operates on the auth store directly
   (`backend/auth/store.py`), so it needs no HTTP call and no `ADMIN_TOKEN`
   in a header.
2. **Monitor users.** Accounts, request queue, runs remaining, active/last runs
   per owner, paused (`interrupted`) runs, saved CVs.
3. **Monitor the network.** API calls with status per user — from the audit log
   (`logplane`, `GET /admin/logs`) rather than scraping uvicorn's access lines.

**Why server-side only:** admin power should not depend on an HTTP credential
that travels in a header and is already logged on 403s. A local script that
needs filesystem access to `knowledge_base/auth/` and the log directory cannot
be reached from the browser or the network at all.

**Open design points (the user's call):**
- Bypass the HTTP layer entirely, or call the running API with `ADMIN_TOKEN`
  read from `.env`? Direct store access is safer but races a live backend
  unless it takes the same per-path locks (`jsonstore.update_json`).
- Does the UI admin panel stay? If so it and the script must share the same
  store functions, not reimplement approval.
- Token revoke and management routes (`/api/auth/tokens*`) are listed as open
  in "D. Earlier frontend asks" above; this script is where they would land
  first.
- In a two-container deploy the script has to run inside the backend
  container (`docker compose exec backend …`), so it must not assume a host
  `.venv` or the `dev.py` log paths.

---

## 2026-10-15 (live run, LLM door) — F1. 🟡 `tool_use_failed` retry mapping has no test yet

**Change made:** `agents/base.py` `_classify` now maps Groq's 400 `tool_use_failed`
(the model wrote prose or JSON instead of calling the tool) to `EmptyOutputError`.
It rides the existing `none_attempts` retry (2 tries, no wait), then falls over to the
next provider with a key. Any other 400 (schema, auth) still passes through unchanged.
Seen live on run `fe92559c` (`gpt-oss-20b`) and `85169ee3` (`gpt-oss-120b`, Profile).
Checked by `py_compile` and one scratch call with Groq's own `BadRequestError`; not
exercised against Groq.

**Test owed (deferred by the user, 2026-10-15):** into the existing
`tests/test_backend_mode_isolation.py` (the retry and fallback door tests), no new file:
- a `groq.BadRequestError` with code `tool_use_failed` maps to `EmptyOutputError`;
- a plain 400 (`invalid_request_error`) is returned unchanged, not retried;
- `tool_use_failed` retries `none_attempts` times, then falls to the next keyed provider;
- with no keyed fallback, the run stops with the original error text, including
  `failed_generation`.

**Not covered by the change:** a deterministic failure, such as a prompt that asks for
prose when the schema wants fields (the stale Profile v1 prompt, #73), fails every try
and just doubles the wasted tokens.

**Status:** OPEN until the test is written.

## 2026-10-15 (frontend, Round 43 — Resume) — what the frontend's Resume relies on, and one ask

> Written by the **Frontend lane (Claude)**, 2026-10-15. No backend code touched.
> Frontend detail: `frontend/bugs.md` → "Round 43". Not compiled or run yet.

**B — behaviour now relied on (keep it, or tell the frontend):**
- B1. `GET /api/runs` → `interrupted` is true **only** for a run parked at a gate with no live worker. `PipelineView.resumeRun` POSTs `…/resume` only when it's true and otherwise just reconnects the stream.
- B2. `POST /api/runs/{id}/resume` never charges a run. The UI says "without using another run" (`RUN_GONE`, `RUNS_INTERRUPTED_HELP`).
- B3. The events route replays the **whole** saved trail after a resume, ending in the same open `gate_wait` with its **original `ts`**, and the worker doesn't re-emit it. The frontend keys the reopened review, and an unsaved final edit kept across Resume, on that `ts`. If a resume ever re-emits `gate_wait` with a new `ts`, the kept edit is silently dropped.
- B4. The 409 `detail` strings on `/resume` are shown to the user verbatim after "Couldn't resume this run:". Keep them plain sentences ("Another run is already active for this owner", etc.) and never put internal or exception text in them.
- B5. `POST …/gate` 404s **only** when the in-memory registry doesn't hold the run (restart). `GATE_GONE` now says "the server restarted… Resume picks it back up".

**A — ask:**
- A1. 🟡 **A run lost before its first gate can't be resumed or even explained.** `save_log` runs at gate-open and at the end, so a restart during `jd_analysis` or `profile` leaves no log. The run is missing from `GET /runs`, Resume can only reconnect (the stream 404s again), and the allowance has already been spent. Ask: save the log at `run_started` too, so the run at least shows up in the list. Better still, let `list_for` mark it as lost/interrupted-before-gate, so the UI can say so and an admin can refund the run.

---

> **2026-10-22 — KB + RAG (Claude), handed over from bug #80 item 2 (`vectordb/store.py` now raises `IndexModelMismatch`); nothing in `backend/` edited, nothing run:**
> - **B1. 🟡 `POST /api/search` 500s on a model mismatch.** `routes/kb.py:search` catches only `CollectionNotFound`. `store.query` now also raises `IndexModelMismatch` when the collection was built with another embedding model. Map it to a 409 (or 503) with the exception's own text ("rebuild it with scripts/build_vectordb.py"), as the 404 does for an unbuilt index. Sits beside #45.
> - **B2. 🟡 A Build-Profile save can be stored but never indexed, silently.** `routes/profile.py:_index_entry` runs on a daemon thread and only `log.exception`s a failure. A mismatch makes `store.add` raise there, so the entry is in `manual_entries.json` but unretrievable, and the user sees success. Needs a visible signal (an `indexed` flag on the entry, or a status the Build Profile screen can show).
> - **B3. 🟡 Readiness should check the stamp.** Stage 0 M6's `/api/ready` should call `get_vector_store().check_model(name)` for `profile`, `documents`, `learning` and report a mismatch, so a wrong-model index shows at deploy and not on the first run. `check_model` raises `CollectionNotFound` for an unbuilt collection.
> - Frontend: no change needed. A mismatch reaches the UI as an ordinary error string once B1 is done.

## From KB + Semantic Search + RAG — 2026-10-22: the delete primitive exists; `/api/search`'s `k` is still yours

> Written by the KB lane under its own grant. No `backend/` code edited. Full
> write-ups: `context/bugs_audit_fixed.md` #30, #64, #80. Not run.

- **B4 🟠 `VectorStore.delete(collection, ids)` and `drop_collection(name)` now
  exist** (`vectordb/store.py`). That was the missing primitive behind bug#30's
  open half: `PUT`/`POST /api/profile/entries` upsert under a stable
  `"{type}:{entry_id}"` id, so an *edit* already overwrites its vector, but a
  *removed* entry still leaves one behind. Removing it is now one call at the
  delete/edit site. `delete` raises `CollectionNotFound` on an unbuilt
  collection and treats unknown ids as a no-op; `drop_collection` returns False
  rather than raising when there is nothing to drop.
- **B5 🟡 `/api/search` still takes any `k`** (#64.4 / bug#45). The store side
  changed underneath you: `VectorStore.query`/`search` now return `[]` for
  `k <= 0` instead of letting Chroma raise `TypeError`, so that particular 500
  is gone — but the route still accepts `k=0`, `k=-3` and `k=10_000` and still
  has no collection allowlist. `k: int = Field(5, ge=1, le=50)` is still the
  fix, and it is still a 422 you want, not a silent empty result.

## From Pipeline Infra + Config + Testing — 2026-10-23: three edits touched your lane, three asks

> Written by the Pipeline Infra lane. Full write-ups: `context/bugs_audit_fixed.md` #84, #85, #86; `context/decisions.md` DEC-150, DEC-152. Nothing run, `py_compile` only.

- **B6 🟠 I edited one of your files: `backend/routes/system.py`.** `/api/health` now returns `started` (UTC process start, module-level `_STARTED`), so `scripts/dev.py smoke` can refuse a server older than the code on disk (bug#85.4; on 10-14 a stale server passed smoke and spent a real allowance run). One field, nothing else in the file changed. The pinned key set in `test_backend_api.py` grew to match. Review it, keep it, or move it; if you add `/api/ready` (§17), consider carrying `started` there too.
- **B7 🟡 `backend/logplane.py:LOG_DIR` is hardcoded** to `config.BASE_DIR/"logs"/"logplane"`. A smoke run against a server `dev.py` started now keeps accounts, uploads and run logs in a temp folder (config reads env `KB_AUTH_DIR`, `CV_UPLOADS_DIR`, `RUNS_DIR`), but the audit/run/llm lines of those smoke users still land in the real log plane. Fix is yours: a `config.LOGPLANE_DIR` read at call time, then `dev.py` adds it to the same temp set (one line). Audit lines carry no content (bug#68.3), so this is hygiene, not a leak.
- **B8 🟡 `scripts/smoke_backend.py` is still yours and still open on two things.** (a) It does not print the server's `started`/build id at the start of a run (#85.4's second half); `dev.py` refuses a stale server first, but a hand-run `python scripts/smoke_backend.py` is unguarded. (b) #86 item 4: once section 4 really runs on current code, recheck the 8 old-server failures #85 recorded. The script's own `logs/<run_id>/` snapshot check (`config.BASE_DIR/"logs"/run_id`) still reads the real folder; that is correct as long as `logs/` is not redirected.
- **B9 ⚪ Registry's comments claim list fields are used by the UI that grep does not find.** `registry.py:list_for` says `RunsView`/`Account` use `review` and `saved` per row; the frontend only reads `interrupted` and `completed` off a listed run (`review` is read from the `run_done` event's `final`). Not wrong, just ahead of its consumer; fix the comment or build the row UI. (Tests for the run-list shape were updated to include `review`, `saved`, `outcome`, `interrupted`, and the run log's `pace`.)
- Frontend: no change needed for any of these.

---

## 2026-10-23 (Agents + Orchestration, Claude) — four items from this session's gate and door work

Nothing in `backend/` was edited today. Three of these are small, one is a
divergence you should decide rather than inherit. Tests and live runs are
deliberately not listed.

**A1 🟡 One divergence, and it is new: the gate now normalises a gap-answer key, the route does not.**
`utils/human_gate.py:_scoped_gap_answers` (bug#74 item 5) keeps a gap answer only
when its key matches a question that was actually asked, compared the way
`matching._key` compares — whitespace collapsed, lower-cased — and then rewrites
the key to the requirement's exact asked text, because `profile.enrich` looks its
question up with `q.requirement == requirement`.
`routes/runs.py:306` compares exactly: `sorted(set(answer.gap_answers) - known)`.
So a client sending `{" sql ": "..."}` gets a **422 from the route**, where the
gate would have accepted and canonicalised it. The UI cannot produce that today
(it echoes the payload's own keys), so nothing is broken — but the two doors no
longer agree on what "the same question" means. Pick one:
 - normalise in the route the same way before the `known` comparison, and the
   two agree; or
 - keep the 422, deliberately, as "the API takes the key it gave you, verbatim".
Either is fine; the gate's own behaviour stands whichever you choose, because it
is the last door before `state.gap_answers`.

**A2 🟡 `GapText` has no `min_length`, so `{"SQL": ""}` is still accepted.**
`routes/runs.py:67`. An empty answer is a skipped question, and since bug#73 item 5
`profile.enrich` drops blank answers before the prompt and never sends or stores
them — so nothing downstream is harmed any more. This is now a cleanliness
question, not a correctness one: the route stores an answer the pipeline will
discard, and `run["gate_answer"]["gap_answers"]` keeps it. One constraint
(`min_length=1`) or a deliberate "we accept and the agent filters" note in the
model. Your call; no agent-side change depends on it.

**A3 ⚪ `worker._scrub_cv_tree` is now a one-line delegation (2026-10-22, bug#72 item 4).**
Flagged in the work log that day but never written here. Its body is
`return scrub_cv_tree(tree)`, importing `state.state_utils.scrub_cv_tree`; the
function keeps its name because `tests/test_backend_api.py` calls it, and the
behaviour is byte-identical (header section dropped, `raw_text` emptied at every
depth). The reason it moved: `log_state_snapshot` applied none of the scrub, so
every UI run with an uploaded CV wrote the candidate's name, email, phone and the
raw PDF text into `logs/<run_id>/` once per gate. One rule needed one
implementation, and `state/` is the package both writers can import. A dated
"FLAGGED FOR THIS LANE'S REVIEW" block sits above it in your file. Revert it if
you would rather own a copy; nothing else depends on the delegation.

**A4 ⚪ Known, still-open divergence on a gate-2 reject — for the record, not for action.**
`routes/runs.py:317` sends `{}` for `gap_answers` when the decision is `reject`;
`human_gate` keeps whatever arrived and lets it ride into the redo. That is the
design question logged in bug#78's "also noted" list ("answers are facts about the
candidate, but the questions may have changed") and it is now a D3 row in
`context/decisions.md`. Your side is the stricter one. It is the owner's call, and
neither lane should change it unilaterally.

## From KB + Semantic Search + RAG — 2026-10-23: six items from this session's retrieval and index work

> Written by the KB lane under its own grant. **No `backend/` code edited, nothing
> run.** Full write-ups: `context/bugs_audit_fixed.md` #65, #44, audit #4.
> Ids are `KB-n` so they cannot collide with the A/B/E/F numbering above.

- **KB-1 🟡 `routes/kb.py:kb_overview` lists every Chroma collection.** It builds
  `vectors` from `client.list_collections()`. A rebuild (`ingest.build`, #65.2) now
  embeds into `profile__staging`, `documents__staging`, `learning__staging` and, for a
  moment, renames each live collection to `<name>__old`. A hard crash leaves any of
  them behind until the next build. They would show in the KB overview and so in
  the UI's vector counts. Fix: report only `vectordb.ingest.COLLECTIONS`, or skip
  names ending `__staging` / `__old`.
- **KB-2 🟡 `vectorstore.profile_index_problem` can mislead after a killed rebuild.**
  If the process died between two renames inside `VectorStore.swap`, `profile` is
  missing and `profile__old` exists; the boot warning says only "missing". One
  clause pointing at `profile__old` (rename it back, or rebuild) would save a
  search. Optional.
- **KB-3 🟡 `routes/profile.py` is mirrored in `vectordb/ingest.py`.** A rebuild now
  re-embeds `manual_entries.json`, so `ingest` carries copies of `SECTION_TYPES` and
  `_entry_text` (`BUILD_PROFILE_TYPES`, `_build_profile_text`). Change one side and a
  rebuild embeds different text from what your save embedded, with no error. Best
  fix: have the route call the `ingest` builder (design §13.4's one record→text
  definition); otherwise keep both in step. Also: an entry with no `id`, or two
  sharing one, now makes the build raise before it resets (old index kept); the route
  always mints an id, so only a hand edit hits it.
- **KB-4 ⚪ UNKNOWN, not checked: a rebuild while the API is running.**
  `scripts/build_vectordb.py` swaps collections in another process while
  `get_vector_store()` holds the API's client. `VectorStore` re-opens a collection by
  name per call, which should see the new one, but nothing here was run and Chroma's
  behaviour across processes was not read. Until it is checked, restart the backend
  after a rebuild.
- **KB-5 ⚪ B5 above (`/api/search` `k`) is closed in your code.**
  `SearchRequest` has `k: int = Field(5, ge=1, le=50)` and `collection: Searchable`
  (an allowlist), read today in `routes/kb.py`. Mark B5 resolved. `/api/search` calls
  `query` (semantic), not `hybrid`, so audit #4's change to hybrid scores never
  reaches the UI.
- **KB-6 ⚪ `cv_link` now re-reads the profile and bullet tables on every run (#44).**
  `agents/CV_Link._get_parts` does it under `_parts_lock`, so two runs reaching
  `cv_link` together queue on a few hundred vectors and, if the bullet count
  changed, a bullet re-embed. Fine at today's scale; worth knowing if
  `worker.py`'s per-owner slots ever run many at once.
- Frontend: no change required (see `frontend/bugs.md`).

---

## 2026-10-24 (backend test pass) — suites, smoke and a new live probe; one fix in `auth/store.py`

**Who:** Backend test pass (Claude), user-granted run-and-fix scope. **How:** pytest offline; `dev.py up --no-frontend --offline`; `dev.py smoke`; new `scripts/probe_backend.py` (main phase, a manual restart, `--resume`), run twice. Results: `context/testing/backend/results.md`.

**Fixed in `backend/`:**
- `auth/store.py:resolve_token` compares UTF-8 bytes. A non-ASCII token was a `TypeError` → 500 at login, the `Authorization` header and the SSE `?token=`; now a 401 like any unknown token (bug#63 item 1, DEC-164).

**Fixed beside it:** the #68 item 1 test now pins the refusal that was built on 10-15 (DEC-165); `dev.py monitor --file <relative>` no longer crashes (DEC-166).

**Confirmed on a real server for the first time (probe):**
- B answering, resuming, streaming, downloading or deleting A's run: 403 (or 404 where the file is gone); A's gate untouched.
- Encoded `..%2F` run ids: refused on every route tried.
- Gate bounds: 2,001-char feedback, gap answers at gate 1, an unknown decision, `edited_content` before gate 4 → 422; an answer naming another gate → 409.
- Uploads: non-PDF 415, over 5 MB 413, blank PDF 422 `no_text`.
- A retried start with the same `client_request_id` returns the same run and spends nothing.
- Two accounts at once: each stream equals its own run log.
- `/logs/mine` holds the caller's own refusals; `/me/export` names nothing of the other account; no raw token in 104 log/data files.
- Restart while parked at gate 2: `interrupted: true` → resume → gate 2 → `run_done`; resuming a finished run refused.

**Still open from this file's list:** unchanged; nothing found that `backend/` can close alone. bug#110 item 5 (every gate snapshotted twice) is `utils/human_gate.py`'s, cause now confirmed (bug#110 note of 10-24).

