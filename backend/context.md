# Backend — Architecture & Decisions

> Companion to root `context/context.md`, scoped to `backend/`. Mirrors `frontend/context.md`'s role: records how this side is put together and *why*. Checklist/status live in `backend/bugs.md`; this file is the rationale. Originally written 2026-08-19 as a plan; the package is now **built and verified**. Compacted 2026-10-14 — content unchanged, prose tightened.

## Where this sits

`frontend/src` sends `Authorization: Bearer <token>` on every request and boots by probing `GET /api/auth/me`. `frontend/bugs.md`'s "Backend build plan" and `backend/bugs.md` (written 2026-08-19 from the frontend side) describe the same contract from two angles; this file reconciles them into the buildable structure actually used.

## Package layout

```
backend/
  __init__.py
  app.py            FastAPI app, CORS, router registration, startup checks
  deps.py           require_auth · require_admin · SSE query-token resolver · Scope/Caller
  jsonstore.py      read_json / write_json — atomic tmp + os.replace, mkdir parents
  logplane.py       append-only JSONL audit/run log, per-kind, per-event allowlist
  auth/
    store.py        requests.json + tokens.json, module RLock, no FastAPI import
    profiles.py     profiles.json, normalise_identifier, create_profile/get_or_create_profile
  cv_store.py       upload/confirm/delete/current CV storage
  runs/
    registry.py     run records, per-owner slots, ownership, run-log persistence, resume
    worker.py       graph.stream driver — relays the graph's own interrupt() gates
  routes/
    system.py  auth.py  kb.py  runs.py  profile.py  cv.py  logs.py  admin.py
scripts/frontend_api.py    from backend.app import app   # noqa: F401 — kept as a shim
```

**Why a package, not one growing file.** `scripts/frontend_api.py` was 409 lines; auth + run ownership alone adds ~350 more. Splitting into routers per domain (each file <~150 lines) separates three concerns that were about to collide: auth plumbing, the run worker/registry, and the pre-existing read-only KB/search/profile routes. The shim keeps `uvicorn scripts.frontend_api:app`, `nginx.conf`, and Vite's proxy working unchanged.

**Why `auth/` nests under `backend/`, not top-level.** Keeps every new module discoverable from one root; nothing else in the project imports `auth/` directly.

## The one deviation from the original plan: `ContextVar`, not `threading.local`

The original plan specified a `threading.local()` fake-LLM switch. **Verified against the installed `langgraph`:** `pregel/_runner.py` runs a node inline, on the calling thread, only when exactly one task is scheduled for that step. The moment more than one task exists, `pregel/_executor.py` submits to a `ContextThreadPoolExecutor` via `copy_context()` — a **different** thread than the one that called `graph.stream()`. A `threading.local` value set on the API worker thread is invisible there: the switch would silently fail open, and an "offline" run could place a real, billed call. Confirmed empirically with a throwaway LangGraph node (`ContextVar` read correctly in both the inline and pooled paths; `threading.local` did not).

`contextvars.ContextVar` propagates correctly through `copy_context()` by design, at identical cost:
```python
_fake_llm: contextvars.ContextVar[bool | None] = contextvars.ContextVar("fake_llm", default=None)
def set_fake_llm(value: bool) -> None: _fake_llm.set(value)
def fake_llm_active() -> bool:
    v = _fake_llm.get()
    return USE_FAKE_LLM if v is None else v
```
`agents/base.py`'s two reads of `config.USE_FAKE_LLM` become `config.fake_llm_active()`. Nothing else in `agents/` changes.

## Who owns pausing — the graph, since 2026-08-31

**The bridge used to implement gating itself; it doesn't any more.** A stand-in gate system (2026-07-05) was built *before* `interrupt()` existed. When a real `gate` node landed 2026-08-20, nothing made the stand-in step aside — both were live at once, and every UI run died right after gate 1 on `'tuple' object has no attribute 'items'` (`interrupt()` yields `{"__interrupt__": (Interrupt(…),)}`, which the old loop misread as a dict of state fields — `context/bugs.md` #9).

`backend/runs/worker.py` now only relays:
```
build_graph(checkpointer=make_checkpointer())      # per run, not per process
cfg = {"configurable": {"thread_id": run["id"]}}   # the run id IS the thread id
stream → __interrupt__ → park on the UI → graph.stream(Command(resume=answer))
```
One checkpointer per run (`SqliteSaver` wraps one `sqlite3` connection; a fresh connection per run is cheaper than sharing one), closed in the worker's `finally`.

**Three non-obvious consequences:**
1. **A paused UI run is durable** — the checkpointer outlives the process even though the daemon thread doesn't (crash-survival the CLI has had since 08-20, the UI didn't until this).
2. **`reject` continues the run** instead of ending it — forwarded to the graph, which sends the work back to the gate's producer and reopens at the next revision. The bridge used to emit `run_stopped` and quit, silently overriding the human veto `context/bugs.md` #10 built. `run_stopped` now means only "superseded".
3. **Superseding needed its own signal** — `registry.abort` used to fake a `"reject"` answer to unblock a parked worker; under (2) that would keep the superseded run alive, so it sets `run["aborted"]` instead.

`node_start` also stopped being a guess: it reads `supervisor_decision.next_node` rather than the previous node's `stage`.

`GATE_AFTER` (keyed by node) is gone; `GATES` replaces it, keyed by **gate name** from the graph's `interrupt()` payload (`gate1_requirements`…), with `after` as an explicit field — same four positions/titles/`artifact_node` values, but the table can no longer disagree with `agents/supervisor.py`'s `STAGE_GATE` about *where* a gate sits:
```python
GATES = {
    "jd_analysis": {"title": "Requirements review",  "artifact_node": "jd_analysis"},
    "profile":     {"title": "Evidence review",      "artifact_node": "profile"},
    "matching":    {"title": "Fit review",            "artifact_node": "matching"},
    "verifier":    {"title": "Final document review", "artifact_node": "document"},
}
```
The bug this originally fixed: the final gate sits *after* `verifier` but must review `document`'s output — `PipelineView.jsx` already reads `ev.artifact_node` with a fallback to `ev.node`, so this was additive on the wire (old logs replay unchanged).

**`frontend/context.md` still says the bridge owns gating — not updated there.**

## Status-code discipline: why 403, never 401

`frontend/context.md` ("Boot and failure handling") documents that `api.js`/`AuthContext` treat **any** 401 as "log this session out", globally, except for `/auth/login` and boot `/auth/me`. That constraint postdates the routes' original scoping, so every ownership/permission check here — wrong role, not your run, no runs left — must return **403**, never 401, or a legitimate user gets silently signed out over one failed request. This also settled an old disagreement (one plan wanted 404 "so run existence doesn't leak"): going with 403 everywhere, for consistency.

## Run ownership

`backend/runs/registry.py`'s `_active: dict[str, dict]` slots one in-flight run per owner under a lock. `start_run` aborts only the caller's *own* in-flight run (previously a new run superseded whichever run was active, regardless of owner — wrong once two people can run the pipeline at once). `run["owner"]` is stamped before the worker thread starts (the thread has no request context). `list_runs` filters by owner unless admin — one `GET /api/runs`, no separate "my runs" route, by design.

> **Superseded 2026-10-10, in key only.** `_active`, `owns()`, `run["owner"]` were keyed on `token_id`. They're keyed on **`profile_id`** now (see "⧉ IDENTITY, SCOPE & THE LOG PLANE" below) — a re-issued token used to be a different owner to every one of these checks, silently orphaning an account's in-flight runs and history on re-issue. `token_id` still rides on the run record for audit only, never compared for ownership.

## Cross-references

- `backend/bugs.md` — the checklist this plan implements; status ticked as pieces land.
- `frontend/bugs.md` — earlier frontend-side planning passes this supersedes for backend structure (package layout, ContextVar) while keeping the route/response-shape contract.
- `frontend/context.md` → "Boot and failure handling" (401 semantics), "Gates, and the artifact_node indirection".
- `context/bugs.md` #2 (gate→artifact mismatch), #3 (global `USE_FAKE_LLM`) — both closed here.
- `context/audit.md` #6 — the join-before-start workaround per-owner run slots + `ContextVar` replace.

---

# Role — Backend API + Auth

> Originally a separate `context_Backend+Auth.md`; merged here 2026-09-24. Written against the real tree — the package is **built and verified** (52 automated tests + 33 live checks passing at the time), not a plan.

**Role:** own the single HTTP bridge between the frontend and everything behind it — the request/response contract, authN/authZ, and the run lifecycle over HTTP (start, stream, answer gates, list, own). Mindset: **API design + authZ correctness + concurrency safety** — distinct from the model/agent thinking next door. Everything the frontend can do, it does through a route this team owns.

**Owns:** all of `backend/`; authN/authZ (token issue/consume, `require_auth`/`require_admin`, 401-vs-403 discipline); run lifecycle over HTTP (per-owner slots, ownership checks, SSE emission, log persistence); item (8) API-boundary security hardening (CORS, `kb_file` path containment, gate-decision validation, request-access flooring).

**Does not own:** agent logic, the graph, prompts, `state/state.py` (drives the graph as a black box, never edits it); KB schema/retrieval (exposes read-only routes, doesn't define the data); `config.py` flag *definitions* (Pipeline Infra's; this team reads them and calls `set_fake_llm()`/`fake_llm_active()`).

**Talks to the system through:** the compiled LangGraph app, the `auth/store`+`jsonstore` file layer, and `config`. Nothing imports `backend/` back — it's a leaf.

**Components:** `app.py` (wiring, CORS, lifespan, the global 403→audit handler); `deps.py` (`require_auth`, `require_admin`, SSE token resolver, `Scope`/`require_scope`/`Caller`, `contained_path()`/`ScopeError`); `auth/store.py` (`requests.json`+`tokens.json`, RLock, atomic writes, `secrets.compare_digest`, `consume_run`/`refund_run`) and `auth/profiles.py` (`profiles.json`, `normalise_identifier`, `create_profile`/`get_or_create_profile`); `runs/registry.py` (per-owner `_active`, `profile_id`-keyed ownership, log persistence, path-contained `load_log`) and `runs/worker.py` (`graph.stream` driver, `GATES`→`artifact_node`, `STUB_NODES`, gate blocking); `logplane.py` (append-only JSONL per kind, `write`/`query`/`for_user`, per-event allowlist); `routes/{system,auth,kb,runs,profile,cv,logs,admin}.py`; `jsonstore.py`; the `scripts/frontend_api.py` shim (**must stay ~2 lines**); `scripts/smoke_backend.py`.

**Locked design decisions — do not silently revisit:**
- `ContextVar`, not `threading.local`, for the fake-LLM switch (proof above).
- Every ownership/permission failure is 403, never 401 (401 triggers a global client logout).
- One `GET /api/runs`, owner-filtered server-side; no separate "my runs" route.
- Package layout: routers per domain, each file <~150 lines.
- `profile_id`, not `token_id`, is the account key (since 10-10) — `token_id` survives only for audit.
- `Scope`, not a raw identity dict, is how a route reaches profile_id-keyed storage (since 10-10) — built only from the verified token, never from path/query/body. `contained_path()` is the one shared path-containment check; a second independent copy is a bug waiting to drift, not a style choice.
- The log plane never holds secrets or content — token, API key, raw CV/profile/answer text: never logged, only the id. This is what lets the admin's `/api/admin/logs` be genuinely complete without being a second unprotected copy of everyone's data.

**Working instructions:**
- Plan-only by default (memory) — propose the change and who writes it; the user grants write scope explicitly. Mostly plumbing, but auth/concurrency correctness has bitten before — surface the reasoning, don't just patch.
- Any new route: guard with `Depends(require_auth)`, pick 401 vs 403 deliberately. `health()` is the only open GET; `request-access`/`login` the only open POSTs, and `request-access` needs a floor (identifier/note length, dup-pending, global cap).
- Every read-modify-write to an auth/run file goes through the lock + atomic write — never a bare `write_text` on the audit trail.
- Consume a run allowance *before* start; refund on failed start.
- A new SSE event: remember the stream **replays full history on every connect** — clients must be idempotent; test with one held-open stream, not reconnect-per-gate.

**Seams:** Frontend owns the `/api/*` contract jointly (Backend initiates shape changes). Agents: gate-pause mechanisms were historically split (API path on `threading.Event`, CLI path on real `interrupt()`+`SqliteSaver`) — unified since 08-31, one mechanism now, but don't change gate behaviour on one side alone. Pipeline Infra defines `config.py` flags this team reads. Data Storage: `jsonstore.py`/`auth/store.py` follow the same atomic-write discipline as `learning/store.py` — keep consistent.

**Open gaps (superseded by Stage 0, see below):** API-path runs durability across restart — closed by the restart-survival work (2026-10-13). `/api/search` never exercised live — still true for the shared `profile` collection's scoping. `live` mode run through the API — covered by later live runs. No test for two concurrent runs by one owner — not pursued; `MAX_CONCURRENT_RUNS` added instead.

---

# Stage 0 Production plan (approved 2026-09-27)

> Full overview table, milestones, decisions and showcase script live in `context/context_Pipeline Infra+Config+Testing.md`. This is the backend slice (§13, §16, §17).

**Goal/decisions (shared across all role files):** synthetic data is fine for Stage 0; the Profile agent collects data from users (new-user interview at a gate, later runs append/improve, only after confirmation); a per-profile data layer (efficient ingestion, separated storage per profile, profile-scoped retrieval, a retrieval log in its own DB).

| Topic | Decision |
|---|---|
| When the profile layer is built | Stage 0, before deploy |
| What one profile is | One per user account |
| Vector separation | One Chroma collection per profile |
| Database | SQLite: `profiles.db` (source of truth) + `retrieval_log.db` (separate log) |
| New-user data collection | An intake gate inside the run, before retrieval |
| Adding data later | Gate-2 gap answers + a free "add or correct anything" box |
| Writing changes | Propose → confirm gate → commit, with version history |
| Append-vs-improve rule | Open — decided while building; the plan provides the seam |

Stage scale: S0 not started · S1 stub/scaffold · S2 works offline (`USE_FAKE_LLM=1`) · S3 works live, verified · S4 production-handled (CI-tested, observable, fails safe, deployed).

**Stage 0 Production is done when:** (1) a brand-new user on the public URL is interviewed at intake, confirms extracted profile changes, walks the remaining gates, downloads a Verifier-checked CV from their own profile; (2) their second run appends/updates records with history kept; (3) two accounts never see each other's records/retrievals/runs, every retrieval logged; (4) restart survival, loop cap, provider fallback, auth/403 discipline, audit trail, health/readiness, persistence across redeploy, index rebuild from `profiles.db`, green CI are all demonstrable; (5) known limits shown honestly (Evaluation keeps its "placeholder" chip).

**This role's components, now → target:** §13 profile identity + route scoping, S0→S3, size S; §16 output export download route, S0→S3, size S; §17 Backend API, S2(unrun)→S4, size M. All "Claude on grant."

**How this changed the open gaps above:** "API-path runs aren't durable" was already out of date by 08-31 (worker relays `interrupt()` over the SQLite checkpointer — the paused *state* survives). What's still missing is **UI reattach** (in-memory registry + worker thread don't survive) — that's D7 below. "Two gate-pause mechanisms" is likewise out of date — one mechanism now. `/api/search` needs one live run and profile-scoping (§13.5). `live` mode needs an actual live run. The same-owner-concurrency test is skipped in favor of the `MAX_CONCURRENT_RUNS` cap.

### §13.1 Profile identity + lifecycle
`profile_id = p-<8hex>`, mapped from the normalised identifier (trimmed, lowercased) — not `token_id` (a re-issue would split the profile), not the raw identifier (Chroma naming rules, PII in logs). Created at admin approval, plus a lazy `get_or_create_profile`. The admin identity gets its own (demo) profile. One resolver, `profile_for(identity)`, used by every route and run start. Delete (admin only) drops the rows and the collection.

### §13.5 Route scoping
Build Profile routes list/add/edit only the caller's records (edits show `version`; history view optional) — at the time of writing, `profile_entries()` returned everyone's file, a cross-user leak. `/api/search`: the caller's collection + the shared `documents`. `/api/kb`: the caller's records + the shared stores.

### §16 Output export: S0→S3
> **✅ Built 2026-10-09** (with gate 4). `utils/export.py` writes `outputs/<owner>/{date}_{run_id}_{role}.md`+`.txt`; `close_run` calls it on approve/edit (worker on `run_done`, and the CLI driver). `<owner>` was the token id until `profile_id` existed. `GET /api/runs/{id}/document?fmt=md|txt` is owner-checked; path comes from `run_done.final.export`. Download button fetches it. PDF/DOCX/cover-letter deferred.

### §17 Backend API: S2→S4
- Verify the 08-31 rewrite with fixed tests + the smoke script.
- **Profile flow relay:** add `GATES` entries for three new gates (intake, two confirms — "Tell us about yourself", "Confirm changes to your profile") with `after`/`artifact_node`; add `profile_intake`/`profile_commit` to `AGENTS`; `gate_wait` passes `intake_questions`/`profile_changes`; `GateAnswer` gains `intake_answers`, `pasted_text`, `free_text`, `accepted_changes`, `edited_changes`, each size-capped, forwarded in `Command(resume=…)`.
- **Profiles:** `profile_for(identity)` at approval and run start; `GraphState(..., profile_id=…)`; owner-scoped profile/search routes; retrieval-log routes.
- **Prod config:** CORS from env; `ADMIN_TOKEN` is a hard startup failure when `APP_ENV=prod`; `config.validate(strict=True)` at startup.
- **Readiness:** `/api/health` stays liveness; add `/api/ready` checking DBs migrated/writable, admin profile exists, `documents` indexed, required keys present.
- **Global concurrency cap:** `MAX_CONCURRENT_RUNS` semaphore, 429 when full.
- Live-mode spend control (D5). `STUB_NODES` shrinks to `{"evaluation"}`.
- **Restart-and-resume in the UI (D7), minimal version:** rehydrate the record/events from the log, check `graph.get_state(cfg)` for a pending interrupt, resume. Fallback: the CLI `--thread … --resume`.
- Always one uvicorn worker.
- New routes, all 403-never-401 for "not yours": `GET /api/runs/{id}/document`, `GET /api/runs/{id}/retrievals` (owner/admin); `GET /api/admin/retrievals` (`require_admin`); `GET /api/ready` (open, secret-free like `/api/health`).

**Milestones (Track B, Claude on grant):** M0 Baseline — tests verified, `StubGraph` fixed, smoke passes. M2 Profile update flow — `GATES`/`GateAnswer`/relay for three gates, `profile_for` at approval+start, route scoping, retrieval-log routes — exit: offline run of new-user→intake→confirm→commit; B gets 403/empty on A's data. M4 Product loop in UI — download route — exit: approved CV downloads from the browser. M5 Hardening — prod config, `/api/ready`, caps, `STUB_NODES` — exit: misconfig fails fast, cap returns 429. M6 Deploy+showcase — optional UI resume (D7) — exit: a paused run resumes after a restart.

**Open decisions:** D5 who may start live runs (recommend: admin only, or a 1-run live allowance). D7 restart-resume in the UI (recommend: minimal rehydrate if time allows, else CLI).

**Showcase steps:** readiness all green; approval creates a `profiles` row + empty collection, non-admin gets 403 on an admin route and stays logged in; B's Build Profile/search never show A's data; `GET /api/runs/{id}/retrievals` lists run 1's queries; pause at a gate, `docker compose restart backend`, resume via UI or CLI, run completes; after `down && up -d`, users/tokens/runs/outputs intact.

---

# M0 Baseline — Backend's part (recorded 2026-10-07)

> M0 itself is owned by Pipeline Infra. This role's part: the `StubGraph` shape its tests need, and the smoke checklist for the 08-31 rewrite. `backend/` code is already written; M0 only proves it. Tests/runs are the user's; Claude reads the output.

**`StubGraph` must now:** accept a `checkpointer` kwarg (`BUILD_GRAPH(checkpointer=…)`); take `config`/`stream_mode` on `graph.stream`; detect a `Command` and continue from the paused gate on resume; yield `{"__interrupt__": (Interrupt(…),)}` at each gate with `value={"gate": "gate1_requirements", …}`; carry `supervisor_decision.next_node` for `node_start`; build a checkpointer per run (`MAKE_CHECKPOINTER` patched beside `BUILD_GRAPH`). The old stub had no gate step and never interrupted — couldn't reach the relay path at all.

**Smoke checklist** (`uvicorn scripts.frontend_api:app --port 8000` then `python scripts/smoke_backend.py`): the final `gate_wait` has `artifact_node: "document"`; a rejected gate produces a second `gate_wait`, not `run_stopped`; `POST /api/runs` 422s `pace_seconds: -1`/`mode: "Live"`/empty JD; `GET /api/runs` is newest-first; snapshots land in `logs/<run_id>/` not `logs/no_run_id/`; `node_start` names a node that really ran; every ownership failure is 403 never 401. Two new things the script now has to meet: `cv_link` raises without a CV (worker passes `config.CV_DEFAULT_PATH` server-side — check the file exists first); the run starts on the SQLite checkpointer (`logs/checkpoints.sqlite`).

**Labels:** `STUB_NODES` was `{"document", "verifier", "evaluation"}`; after the Document finish work, `{"verifier", "evaluation"}` — the Verifier stays labelled a placeholder past Stage 0 (same honest-limits treatment as Evaluation; the §17 plan line "shrinks to `{"evaluation"}`" is superseded).

**Exit:** `StubGraph` fixed + smoke passing against the real graph. **Not in M0:** the new profile-flow gates/`GateAnswer` fields/route scoping (M2); download route/`/api/ready`/concurrency cap (M4, M5); any browser check of the frontend (ask first).

---

# October scoping pass — API integration, data handling, auth/OAuth (2026-10-08)

> A read-only pass over everything changed since 2026-09-24 against the backend, which itself changed only one line (`worker.py:217`, `cv_path=str(config.CV_DEFAULT_PATH)`). Six readers covered graph relay, data handling, the frontend contract, a correctness audit, auth+OAuth, and the Stage 0 plan; one adversarial verify pass ran before a usage cap cut it short. **Only the auth/OAuth section was adversarially re-checked** — everything else is first-pass, cross-checked against file:line but not by a second reader: "very likely true, flagged not fixed," re-read cited lines before building on it. No code changed. The frontend-visible overlap (`cv_link` missing from `AGENTS`, `document` still in `STUB_NODES`, gate 3's position) is in `frontend/bugs.md` "Round 6", cross-referenced not repeated.

## 1. The graph moved three times; `worker.py` didn't track it

Since 09-24, `agents/supervisor.py`, `agents/CV_Link.py` (new), `agents/document.py` changed; `worker.py` didn't (bar the `cv_path` line). A new node `cv_link` runs between `matching` and `document`, no LLM call — parses the PDF into `cv_tree`, links every line against the global `profile` collection. `STAGE_GATE` is keyed "before stage X", so gate 3 now opens after `cv_link`, not `matching` — but backend's `GATES["gate3_fit"]["after"]` was still `"matching"`. `document.node` became a real patcher (planner call, disk-cached, then per-section writer, applied to a `cv_tree` copy; raises without `cv_tree`); its artifact grew to include `document_patches`/`document_plan`/`document_plan_key`/fetched evidence — tens of KB per event, persisted in full.

**Backend consequences:** `AGENTS` needed `"cv_link"` inserted between `"matching"`/`"document"`; `GATES["gate3_fit"]["after"]` needed to become `"cv_link"`; `STUB_NODES` needed to drop to `{"verifier", "evaluation"}` now, not wait (superseding this file's own earlier M0 note); `_emit_routing`'s whitelist (`next_node in AGENTS`) needed inverting — skip only `"gate"`/`"END"`/`None` — so a new node anywhere gets a `node_start` by default instead of silently dropping (this exact drift happened twice already: `profile_enrich`, then `cv_link`). **Land this together with the Stage 0 profile-flow gates (§2), not before** — both touch the same tables.

## 2. Stage 0's profile-flow gates will 500 the run the instant they land, not just go unrendered

- `_wait_for_gate` does `GATES[gate_name]` with no `.get()` fallback → `KeyError` → `run_error` for any unknown gate name. The moment the agents lane wires the first new gate, every run dies there until the worker's tables catch up.
- `GateAnswer` has exactly `decision`/`feedback`/`gap_answers`; `answer_gate` copies them one by one into `run["gate_answer"]`. Adding new Pydantic fields alone does **nothing** — they'd validate then get silently dropped at the explicit-dict line (same "accepted but ignored" shape as bug #29 before its fix). Fix: `run["gate_answer"] = answer.model_dump()` once the fields exist.
- `gate_wait` only ever passes `gap_questions`; intake needs `intake_questions`, confirms need `profile_changes`. Generalize with a `payload_keys` tuple per `GATES` entry.
- **No gate name travels with the answer** — `answer_gate` only checks `run["gate"]` is truthy, never that it matches what the client thinks it's answering. A stale/retried POST from an earlier gate can land on whatever gate is open now (e.g. a stale gate-2 submission applied as "approve" at the enrich-confirm gate would commit every profile change the user never saw). Fix: add `gate: str | None` to `GateAnswer`, 409 on mismatch.
- `gate_done` echoes back whatever it's given — if extended to echo `intake_answers`/`pasted_text` the same way it echoes `gap_answers`, a full pasted CV lands in `run["events"]` (replayed on every SSE connect) and the persisted log, no cap, no PII flag. Echo only non-PII summaries.

Consider moving the node list and the gate→`(after, artifact_node)` table into a shared module both `supervisor.py` and `worker.py` import, so the two can't drift by construction — third time one side's table has lagged the graph.

## 3. Run-lifecycle bugs, independent of Stage 0 — bite today, offline, single-user

- **A double-clicked Start spends two runs.** No in-flight disable frontend-side; backend has no dedup — each call runs `consume_run` before `registry.start` even checks for a run to supersede. A new user's entire 2-run allowance is gone after one double-click. Fix: optional `client_request_id` on `RunRequest`; a short-lived `(owner, client_request_id)→run_id` map, returning the existing run before `consume_run` runs.
- **Superseding is not prompt.** `registry.start`'s abort only takes effect at the superseded worker's *next* gate check (`gate_event.wait()` return), not now — it keeps spending live-mode quota meanwhile, and `thread.join(timeout=15)` on the new request blocks on it. Fix: check `run["aborted"]` inside `_drain`'s per-update loop too.
- **The run log is written once, at the end**, only on the clean path. Three consequences: (a) a run parked at a gate across a restart leaves **no file at all** (daemon thread, `finally` never runs) — this is what makes D7/restart-showcase impossible as designed; (b) a browser refresh loses the run (id lives only in React state, `list_for` reads only finished logs); (c) `gate_event.wait()` has no timeout, so an abandoned gate holds a run slot/thread/sqlite connection forever — under the planned concurrency cap, a handful of abandoned gates exhausts it for everyone. **Fix, land early:** call `registry.save_log` from inside `_wait_for_gate` before the `wait()`, not only in `finally`; add a `status` field + current gate; add a bounded `GATE_IDLE_TIMEOUT_MIN`.

## 4. Data handling: every UI run shares one CV and one profile pool

- **One server-side CV, one shared `profile` collection, no per-user separation.** Every run patches `config.CV_DEFAULT_PATH` and links against the global collection — B's Profile agent retrieves A's gap answers/entries as evidence, and B downloads a CV built from the same base file A would get. Blocks Stage 0 exit-criteria 1 and 3 directly — not a plan-execution gap but a plan-*coverage* gap (`cv_link`/`document`'s evidence lookup didn't exist when §13.3/13.5 were written).
- **`POST /api/profile/cv` doesn't exist.** No way for a browser to supply its own CV. Open decision, not a bug: build upload (owner-scoped, `%PDF-` check, size cap, stored under `profile_id`), or let intake's `pasted_text` become the CV source, or accept a shared sample CV for Stage 0 and say so on screen. (`config.py`'s comment pointed at a section number that isn't in the Stage 0 plan — worth resolving.)
- **`GET /api/profile/entries`, `GET /api/kb`, `GET /api/kb/{store}/{file}`, `POST /api/search`** all return/search every user's data — same underlying gap (no `owner` field, no profile-scoped collection) through different routes. Interim: stamp `owner=identity["token_id"]` on new entries, filter `GET` by it, 403 a foreign `PUT`.
- **Offline runs write fixture data into the real KB, unguarded.** `save_gap_answers` has no `fake_llm_active()` check — every offline run answering gate 2 appends the fixed fake answer to `manual_entries.json` **and** upserts it into the shared `profile` collection under a fresh id. Confirmed: three such records already in the file from CLI runs. A later *live* run can retrieve one as genuine evidence; reachable through the API today, will be browser-reachable the moment the gate-2 form ships. Fix: skip `save_gap_answers` when `config.fake_llm_active()` (one line, outside this package). Cleanup needs `VectorStore.delete`, which doesn't exist (open half of bug #30).

## 5. Auth: current model, Stage 0 identity wiring, OAuth scoped as a new feature

**Current gaps, ranked** (bearer token, plaintext in `tokens.json`, `?token=` on SSE, unchanged since 08-19):
1. **Identifier takeover, once `profile_id` exists.** `request-access` takes free-text with no existence check beyond "no duplicate *pending* request." Once approval maps identifier→`profile_id`, anyone typing an existing user's name (including the real "request more runs" wording) gets approved and inherits that account. **Must close before §13.1 lands.** Needs: `normalise_identifier()` (NFKC+casefold+whitespace collapse, reject `:` and reserved names), a uniqueness check at approval (409 on an existing account), and a separate *authenticated* `POST /auth/request-more` for top-ups (keyed off the caller's own identity, mints no new token).
2. **No expiry, no revocation, logout is client-side only.** A copied token is valid forever. Needs `expires_at`/`revoked_at`/`last_used_at`, `resolve_token` honouring them, a real logout, an admin revoke tool.
3. **The bearer travels in the SSE URL, lands in access logs** (including `ADMIN_TOKEN`). Accepted "for an internal tool" — doesn't survive a public deploy. Fix direction: a short-lived single-use SSE ticket in place of `?token=`, plus turning off query-string logging at the proxy/uvicorn.
4. **Re-issuing a token splits the account.** "Request more runs" mints a second unrelated token under the same identifier — run history/in-flight runs/profile all keyed on `token_id`, so re-issue looks like a different person. Same root cause and fix as item 1: split "account" (`profile_id`, holds allowance) from "credential" (an opaque token, or later an OAuth login).
5. **No rate limiting anywhere**, and the planned `MAX_PENDING=100` global cap is itself a DoS lever (100 junk requests lock out every real signup). Also: nginx forwards no client-IP header, uvicorn's `FORWARDED_ALLOW_IPS` defaults to localhost — per-IP limiting needs proxy + uvicorn wiring to work at all.

**Stage 0 §13.1 identity wiring, concretely:** `approve_request` writes only `requests.json`/`tokens.json`; the profile lives in a third store, so approval becomes a three-store operation — make it idempotent (`get_or_create_profile`, insert-on-conflict-then-select) so a retried approval can't create two profiles. `/auth/me`'s response shape is pinned by a test — adding `profile_id` is a wire-contract change, flag to frontend rather than sliding in. Run ownership needs to move from `token_id` to `profile_id` once an account can hold more than one credential. `auth/store.py` is deliberately pure file I/O (no FastAPI/SQLite/Chroma import, sub-second boot) — `profile_for`/`get_or_create_profile` must live in a *new* module called through `deps.py`, not added to `store.py` itself, or the boot-time fix regresses.

**OAuth does not exist anywhere** (repo, tests, plan) — `Authlib` not installed; the only "oauth" hit records the *opposite* decision (single opaque token, no sessions/cookies). This is new-feature scoping, a proposal not a build plan. Recommended shape (keeping the existing admin-approval + allowance model):
- Identity key `(provider, subject)`, never email — `identifier_norm = f"{provider}:{subject}"` (feeds the same `profiles.owner_identifier UNIQUE`→`p-<8hex>` path once typed identifiers reject `:`). Email changes, can be claimed cross-provider, and auto-linking by email is an account-takeover path.
- First-time OAuth login files a pending access request, same as today — admin-approval gate doesn't get bypassed by login method. `display` (verified email/provider name) stays separate from the identity key.
- Post-callback credential, two options: **(A) reuse the opaque bearer** (callback mints the same token kind, one-time code exchange, SPA unchanged — smallest diff); **(B) HttpOnly cookie session** (more standard, fixes SSE auth for free, but opens CSRF surface and touches every `Authorization: Bearer` read site). **Recommendation: (A) for Stage 0.**
- New config: `OAUTH_<PROVIDER>_CLIENT_ID/_SECRET`, `SESSION_SECRET` for the handshake, `PUBLIC_BASE_URL` for the redirect URI. Coexists with `ADMIN_TOKEN` unchanged. Needs owner decisions first: provider(s), (A) vs (B), auto-approve vs queue like today.

## 6. Test suite: the `StubGraph` fix is one root cause, not five failures

All five `test_backend_api.py` failures (plus one unrelated agents-lane failure) trace to `StubGraph` being patched as `lambda: StubGraph()` while the worker calls `BUILD_GRAPH(checkpointer=…)` — every stubbed run errors with `TypeError` before anything else, failing every assertion downstream. Also: because `BUILD_GRAPH` raises *after* `MAKE_CHECKPOINTER()` succeeds, the `checkpointer` local never gets assigned, so `finally`'s `checkpointer.conn.close()` never runs and each failing test leaks an open connection to the *real* `logs/checkpoints.sqlite`. Fix: wrap `_build_graph()` in try/except, close the checkpointer if `BUILD_GRAPH` raises, re-raise.

**Fixing the stub correctly will flip three more tests, not fix five and stop** (not a regression): `test_sse_streams_events` expects a `reject` to end the run — since 08-31 it reopens the same gate instead, so the stub modeling that correctly makes this test's `.join(timeout=5)` hang reading a non-ending generator. Same root cause hits `test_gate_rejection_stops_the_run` (asserts removed semantics) and `test_one_user_cannot_see_or_touch_anothers_run` (asserts a 403 on a log that, for a rejected/parked run, was never written — §3 above). Not new breakage — 08-31 semantics finally reaching the suite once the stub stops masking it.

**Cross-refs:** `frontend/bugs.md` "Round 6" (frontend-visible half of §1), "Round 5 plan" (gate-2 form, same shape as §2's three gates); `context/bugs_audit_fixed.md` #30 (`VectorStore.delete`, blocks §4's cleanup); `context/context_Agents+Orchestration.md` §3.12 (the CV-source question §4 restates).

---

# CV upload — built 2026-10-10

Closes this file's §4 "`POST /api/profile/cv` doesn't exist" and `backend/bugs.md`'s "2026-10-09 (later)" items 1–3/6. Full detail/verification in `backend/bugs.md`'s "2026-10-10" section.

**What changed:** new `backend/cv_store.py` + `routes/cv.py` — upload/confirm/delete/current, server-chosen filenames (`uploads/{owner}/cv/{sha256[:12]}.pdf`), a `CvPreview` from `cv_extract.parse_cv`. `routes/runs.py` resolves the caller's current CV before `consume_run` (409 for a non-admin with none; sample-CV fallback for admin only). `registry`/`worker` carry it into the run (`run["cv_path"]`, a new `run_started` event). `config.CV_DEFAULT_PATH` is now the admin/demo fallback only, not every run's default.

**Still open:** CV text still reaches SSE events/run logs through the `cv_link` artifact (item 4); the unmatched-line count isn't exposed for gate 4 (item 5). 10 flipped tests in `test_backend_api.py` are the user's to update.

---

# Concurrency + hardening fixes — built 2026-10-10

> Six fixes, scoped to `backend/` only. Full code/verification per-fix in `backend/bugs.md`'s dated entries; this is the mechanism and reasoning. Checked by `py_compile`, import checks, scratch concurrency/unit tests against the real schema — **nothing run via pytest, uvicorn, or a live request.**

**One lock per run, closing the gate double-answer race.** Every run dict carries its own `threading.Lock()`. `answer_gate` holds it across the existence check, a new `answered` flag, gate-name/`edited_content` checks, and the `gate_answer` write — set `answered=True` before release, only then `gate_event.set()`. Without it, two POSTs to one open gate could both see "a gate is open," and whichever the worker read last silently wins — at gate 4 a reject in one tab could override an approve in another, both getting `200`. No cleanup needed (`_wait_for_gate` builds a fresh dict per pause).

**One lock per owner + an idempotency map, closing the double-start race.** `registry.start` used to read `_active[owner]`, release its lock, abort+join the previous run, then re-take the lock — a window where two concurrent starts from one owner could both read "no active run" and proceed, orphaning the first forever (thread + sqlite connection held, live-mode quota spending). Fix: `owner_lock(owner)` (one per owner, lazily created, held across the *whole* sequence including the up-to-15s join — only delays this owner's *other* starts); `seen`/`remember` (a 10-min `(owner, client_request_id)→run_id` map so a retry gets the existing run, not a double charge). `RunRequest` gained the matching optional field. **Needed from frontend:** send `crypto.randomUUID()` as `client_request_id` from `start()`.

**Closing out on failure after gate 4, not just on a clean finish.** `run_worker` initialised `checkpointer=None` before `try`, but `graph`/`cfg` were local to the try body — any failure after they were assigned skipped `_close` entirely and went to `run_error`, losing an already-checkpointed approved/edited CV. Fix: `checkpointer=graph=cfg=None` before `try`; `except` now calls `_close(run, graph, cfg)` and merges the result into `run_error` whenever they were assigned. A failure *before* the graph builds skips it cleanly.

**A privacy scrub for `cv_link`'s artifact, no wire-shape change.** New `_scrub_cv_tree()` in `worker.py`, applied in `_drain` right after `_jsonable`: drops the header section (name/email/phone) outright, blanks `raw_text` everywhere else. Was "harmless only while every run used the shared sample CV" — real uploads landed the day before, making it a live PII leak into the persisted, replayed log. Not a shape change: the frontend's documented reads (`node_id`/`title` off `cv_tree.root.children`, `text` off `line_links`, never `cv_tree`'s own text) are untouched. Per-line text in `line_links`/`document`'s artifact left alone on purpose — a product decision, not either lane's to pick unilaterally.

**`gap_answers`/`feedback`: the same input-boundary discipline as #37.** `GateAnswer.gap_answers` is now `dict[GapKey, GapText]` (key ≤200 chars, value ≤2000, ≤20 keys); `answer_gate` 422s a non-empty `gap_answers` at any gate but `gate2_evidence`, and 422s any key not among *that open gate's own* question keys (`_wait_for_gate` now keeps `gap_questions` on the parked `run["gate"]` itself, checked against what was actually asked, not trusted from the client). A rejected decision always stores `gap_answers: {}` server-side. `feedback` capped at 2,000 chars (reaches the checkpoint, every snapshot, `gate_done`, the learning store, soon the Document prompt).

**What this surfaces, not fixed here:** the new `_owner_locks`/`_seen` structures are keyed on `token_id`, same as `_active`/`owns()` — need the same `profile_id` migration later. The `cv_link` scrub / `gap_answers` hardening fix *content* correctness, not *storage isolation* — every run's log still lands in one shared folder, a validated gap answer still writes into the one shared `manual_entries.json`/collection. The real fix stays the per-user vault work (§13/§15), unaffected by this session.

**`bugs.md` now opens with a ranked criticality index** — every open 🔴/🟠/🟡, worst first, pointing to its own entry. Purely additive; other files still cross-reference by section name/item number, never position.

---

# Identity, scope & the log plane — built 2026-10-10 to 2026-10-12

> Four sessions off `bugs.md`'s criticality index, one item at a time: identity → `Scope` → the Build-Profile leak `Scope`'s migration surfaced → `routes/runs.py`'s own migration → the log plane's `audit` kind. Each has its own dated `bugs.md` section with full build/check detail; this is the architecture shape and why. Checked by `py_compile`, import checks, scratch `TestClient`/unit scripts against tmp dirs — **nothing run via uvicorn, a browser, or the frontend.**

**The problem this closes: an account was a credential.** Every ownership check (`registry.owns()`, CV storage, the allowance counter, the run slot) compared `token_id`. A token and an account were the same thing — breaks the moment a token is re-issued, and was an open takeover path (typing an existing user's exact name at `request-access` inherited their account the moment approval mapped name→data). Named as the top 🔴 in the October scoping pass, carried into Stage 0 §13.1 — this is that plan, built.

**`profile_id` = the account; `token_id` = the audit trail.** New `backend/auth/profiles.py` — a fourth flat JSON store (`profiles.json`, same pattern as `requests.json`/`tokens.json`; not yet the eventual `profiles.db` SQLite store, but this module's contract is what the rest of the backend calls, so the storage can swap under it later with no call-site change). `normalise_identifier()` (NFKC+casefold+collapsed whitespace, rejects `:` and reserved names) decides whether two typed names are the same account. `create_profile()` raises on a colliding identifier (closing the takeover path outright, not merging); `get_or_create_profile()` is the idempotent version, used only where seeing the same identifier twice is expected (legacy-token backfill, the admin's sentinel profile).

Every token record now carries `profile_id`, assigned at approval; `resolve_token` lazily backfills it onto pre-existing tokens (confirmed: three real records backfilled cleanly). `/auth/me`/`/auth/login` now return it (a wire change, flagged to frontend). New authenticated `POST /api/auth/request-more` tops up an account's own allowance without minting a second token; `approve_request` mints (signup) or tops up the caller's existing token (topup) by the request's `kind`.

**Every ownership key in `backend/` moved from `token_id` to `profile_id`**: `registry._active`/`owns()`/`start()`, `routes/cv.py`'s storage, `routes/runs.py`'s `start_run`. `token_id` still rides on the run record/audit entries, compared nowhere for ownership — a re-issued token now resolves to the same account/history/CV. One deliberate exception: `consume_run`/`refund_run` still key on `token_id` — the allowance is a property of the *credential* (a top-up adds to the specific token that asked, not "the account" abstractly) — so `routes/runs.py` carries both `scope.profile_id` and `identity["token_id"]` separately rather than folding one into the other.

**`Scope`: the one way a route reaches profile_id-keyed storage.** New in `deps.py`: `Scope(profile_id, role)` — a frozen dataclass built only from `require_auth`'s verified result, never a path/query/body value — and `Caller`, the `Depends()` alias every profile_id-touching route now takes instead of bare `Identity`. Alongside it, `contained_path(root, *parts)`: resolves a join, raises `ScopeError` if it climbs outside `root`, pulled out of `kb.py`'s pre-existing inline check so every profile_id/run_id/cv_id lookup shares one implementation. That consolidation found a real, confirmed path-traversal gap: `registry.load_log()`'s `_log_path()` joined an uncontained `run_id` straight off the URL — for an *admin* caller (whose `owns()` check passes regardless of content) that was a working arbitrary-`*.json` read. Closed the same session it was found. `routes/cv.py`, `profile.py`, `kb.py`, and `runs.py`'s `start_run` all now depend on `Scope`; routes that only ever forwarded raw identity to `registry.owns()` were left alone.

**The leak `Scope`'s own migration surfaced: Build Profile had none.** `GET /api/profile/entries` returned **every** user's data to **any** authenticated caller; `PUT .../{id}` had **no ownership check at all** — one user's own id, visible in their own `GET`, could silently overwrite someone else's entry. Same leak through `GET /api/kb/profile/manual_entries`. Already named in the October scoping pass §4 (interim fix: stamp owner, filter GET, 403 a foreign PUT) — this closes it: new `visible_entries(scope)` in `profile.py` is the one place deciding who sees what (admin: all; non-admin: own `profile_id` only; no-`owner` entries, written before this existed: admin-only, same convention `registry.owns()` already used for pre-ownership logs — never shown to everyone, never a `KeyError`). `kb.py` calls the *same* function for its route onto the same file rather than re-deriving the rule (three tables have drifted before: `AGENTS`/`GATES`/`STUB_NODES` vs. the graph).

**A real gap this created, outside this package's jurisdiction:** `learning/profile_store.save_gap_answers` writes into this same file with no `owner` field — under the admin-only-for-ownerless rule, a user's own gate-2 answers stop appearing in their *own* Build-Profile list until that module stamps `owner`. A deliberate trade (closing a live leak everywhere else was worth this regression on one narrower path), written up loudly in both `bugs.md` and `profile.py`'s docstring.

**Deliberately not touched:** `POST /api/search` still queries the shared `profile` collection unfiltered — same gap, reached through a third route, but needs vector *metadata* work (stamping `owner` at index time, backfilling, confirming a `where=` filter doesn't also exclude genuinely shared/curated vectors mixed into the collection). Scoped as its own next item.

**The log plane: `audit` built, `run`/`llm`/`retrieval` designed only.** New `backend/logplane.py` — one append-only JSONL file per kind under `logs/logplane/` (append, not read-modify-write — a crash mid-write corrupts at most the last line). The rule that makes "the admin sees everything" safe: **never holds secrets or content** — token, API key, raw CV/profile/answer text never reach a log line, only the id. `for_user()` projects each entry through a per-event-type field allowlist before a non-admin sees it; an event type with no allowlist entry is hidden entirely (fail-closed, so a new event can't leak a field by being forgotten). New `routes/logs.py`: `GET /api/logs/mine` (own entries, projected), `GET /api/admin/logs` (admin only, unprojected; 403 never 401 otherwise). New global `HTTPException` handler in `app.py`: writes an audit entry on every 403, app-wide, automatically — response byte-for-byte unchanged, only the side effect is new.

**Still open, sized why:** the `run` kind (start/end, node timings, gate decisions, allowance spent/refunded) needs instrumenting `worker.py`/`registry.py` directly — bigger, riskier than audit calls in request handlers, touches the run lifecycle itself. Left as its own increment. `llm`/`retrieval` are other lanes' writes into the same already-generic module.

**The admin cross-vault route: §2 closed (built 2026-10-12).** `write()` gained `critical: bool = False` — every existing call keeps "never break the request over a logging failure"; the two new admin routes pass `critical=True`, so a failed audit write re-raises and the route 503s rather than letting access through unaudited. New `routes/admin.py`: `GET /api/admin/users/{profile_id}/profile` and `.../cv`, admin only. The `Scope` each builds is deliberately `role="user"` (describes *whose* vault, not who's opening it — the caller's real role would make `visible_entries()` return everyone's). An unknown `profile_id` is 404 (refusing a real account the same way as a fake one leaks nothing), resolved via `profiles.display_for(profile_id)`, which doubles as input validation (a `profile_id` only reaches disk after matching a server-minted `p-<8hex>` string — a traversal-shaped value just 404s). **Deliberately not built:** `GET /api/admin/users/{profile_id}/runs` — whether to keep `GET /api/runs`'s unaudited full access or replace it is open decision D-T2; building it here would've answered that by default.

**Two real bugs in this session's own new code, found and fixed on the spot:** `write()` was serialising its entry *inside* an already-open file handle's `.write()`, so an unserialisable value still created the log dir + an empty file before the `TypeError` — contradicting its own "a failed write leaves nothing behind." Fixed by serialising to a string first. `admin_data_access` (this session's own new event) had no entry in the user-visible allowlist, so fail-closed hid from a user that their vault had been opened — added, visible with `resource` only (deliberately shown that an admin accessed the account, never *which* admin, and no content).

This closes the design's §2 completely. §3 (threading scope into the graph) — **its backend half is built 2026-10-22**, see "Scope into the graph — 2026-10-22" below; the consumers remain the Agents/KB lanes'. The `run` kind is built (10-14); `llm`/`retrieval` are other lanes' writes.

**What this means for earlier text in this file:** "Run ownership" above (written for `token_id`) is superseded in key only — the shape didn't change, only what "owner" means. The `_owner_locks`/`_seen` migration note above turned out unneeded: both are owner-agnostic by construction, so once `routes/runs.py` started passing `scope.profile_id`, they automatically operate on accounts.

**Cross-refs:** `bugs.md` "Open bugs, ordered by criticality"; `bugs.md`'s "2026-10-10 (identity)"/"(scope)"/"(profile scope)", "2026-10-12 (scope, runs.py)"/"(log plane)"/"(admin vault)" — full build detail; "2026-10-09 (design)" §1–5 — the design this implements; October scoping pass §5/§4 — the two gaps closed.

---

# What the frontend needs from the backend — after frontend Rounds 27–38 (2026-10-13)

> Written by the Frontend lane on a grant to edit this one file. No backend code touched; every item checked against the code on 10-13. Frontend detail in `frontend/bugs.md` (top list + one entry per round, 27–38). `backend/bugs.md` → "2026-10-10 (frontend, Rounds 17–26)" still holds detail for its items; the table below gives current status in one place.

## A. Behaviour the frontend relies on — keep it, or tell the frontend first

| Behaviour | Where | Breaks on frontend if changed |
|---|---|---|
| `POST /runs` dedupe remembers only runs that **started**, per (owner, `client_request_id`), 10 min; a repeat returns that run's id and **ignores the body** | `routes/runs.py`, `registry.seen/remember` | `PipelineView.start()` (Round 29) keeps one id per start, reusing while JD+mode unchanged, clears on success |
| A gate answer's **404** means only "this process doesn't hold the run" — a paused run is never pruned until finished | `answer_gate`, `_prune` | `GateScreen` retires with "server restarted…can't continue" (Round 31). Never 404 for anything else — not-yours is 403, stale/answered/moved-on are 409 |
| Every gate-answer **409** means "this form is stale" | `answer_gate` | `GateScreen` "movedOn" (Round 17) |
| `run_stopped` only while paused at a gate; `run_error` from the graph's `except`, names no step | `worker.run_worker` | `settle()` marks the step left "running" failed, a "waiting" review stopped (Round 33) |
| Caps: `feedback` ≤2,000, `edited_content` ≤50,000 chars | `GateAnswer` | the feedback box / CV editor stop at exactly these, with a counter (Rounds 34, 38) |
| `final.export` = `{md, txt}`, set only on approval; `GET /runs/{id}/document?fmt=md\|txt` serves either | `close_run`, `routes/runs.py` | Download buttons + "saved on the server as…" (Round 36) |
| `gate_wait.changes[]` = `{node_id, where, before, after, reason, evidence_ids}`; `where`="Section › Entry"; `evidence_ids` are `ProfileBlock.source_id`; every `evidence`-carrying `node_done` sends `[{source_id, content,…}]` | `final_changes`, `_drain` | `ChangeList` groups on `where`, looks up cited ids from a stream-built map (Round 37) |
| `/search` score = 1 − cosine distance (−1 to 1) | `vectordb.store.query` | `SearchPanel` caps to 0–100 (Round 35) |
| **Retrieval is one shared `profile` collection, no owner filter** — Build Profile entries and gate-2 answers are embedded into it | `agents/profile.py`, `cv_match`, `vectordb/lookup.py` | `EVIDENCE_SHARED*`, `GAP_HELP`, and half of `BUILD_PROFILE_HELP*` say evidence is shared (Rounds 27,28,40). **Tell frontend the same day retrieval/`/search` goes per-profile (vault P3–P4)** — these strings go false |
| **Build Profile listing is owner-scoped**: own entries / all-for-admin / foreign-PUT-403 / ownerless-admin-only (`visible_entries`); gate-2 answers are ownerless | `routes/profile.py`, `kb.py` | `BUILD_PROFILE_*` (Round 40) follows role. **Tell frontend when `save_gap_answers` stamps an owner** — the "your checkpoint answers aren't listed" note goes false |

## B. New asks, most critical first

1. 🟠 `GET /runs/{id}/document` should find `final` on `run_error` too — today only `run_done` is read, so a CV approved before a later-step failure 404s on download though the page claims it's saved (item 26).
2. 🟡 Name the failed step on `run_error` (e.g. `node`) — frontend infers it from whichever step was left "running"; an error outside a step (Supervisor, `_close`) leaves nothing to mark (Round 33). **✅ Built 2026-10-21** — `run_error.node`, see "Failed step on `run_error` — 2026-10-21" below.
3. 🟡 Let the page learn a run is gone without making the user click first — `EventSource` can't see the 404. Smallest fix: `GET /api/runs/{id}` that 404s for unknown runs, probed once after a stream drop. Real fix: Resume (D7) (items 10, 21).
4. 🟡 Put each cited record's text on `gate_wait.changes` (e.g. `evidence: [{id, content}]`) — today rebuilt from stream history, which won't survive Resume (Round 37).
5. ⚪ Optional: clamp `/search` scores to 0–1, or document the range (Round 35).

## C. Earlier asks — status checked 2026-10-13

A1 (CVs on `profile_id`) ✅ done. Build Profile owner scope ✅ for `/profile/entries` and `/kb`'s `manual_entries`; ⬜ `/search` still unscoped. Gate-2 answers' missing `owner` ⬜ (learning lane's). B1 `revision`/`max_revisions` on `gate_wait` ⬜. B2 plain `message` on `run_error` ⬜. B3 `outcome` on run summaries ⬜ (closed later — see Restart Survival section). D1 say what an upload stored ⬜. D2 keep files a run references ⬜. D3 agent-memory CV lines (not this package). `cv_link` per-line text in logs ⬜ (left open, product decision). Token revocation ⬜ (nothing can revoke a token at all).

## D. What the frontend owes back

✅ Round 39 (compiled 10-14): Account calls `POST /auth/request-more {note}` via a new `requestMore()`, wording says runs land on the same account, re-reads `/auth/me` on open (item 27). ✅ Round 40: Build Profile wording follows `visible_entries` per role, a 403 reads "This entry isn't yours" (item 28). `/auth/me`/`/auth/login` returning `profile_id` needs no frontend change.

---

# Open bugs — Backend API + Auth (as of 2026-10-22)

> **Status 2026-10-22:** every entry in this section is now fixed in code
> except #87's items 2 and 4 — #42, #45, #51, #68, #69 and #70 are closed in
> full, and #87's items 1 and 3 were done on 10-14. **#87 item 2** (`cv_link`
> reloading the embedder and reranker a second time) is KB+RAG's, and **item
> 4** (`nginx.conf`'s `proxy_read_timeout` on the events route) is
> deployment's. Everything else still open for this role is in the "Also
> touches this role" table below and, in full, in `bugs.md`'s ranked index:
> all of it needs another lane, the frontend, or a product decision. The
> per-entry ✅ notes below say which session closed each one.
>
> Master list is `context/bugs_audit_fixed.md` — open entries tagged to this role, copied in substance. Update both when one closes. Placement calls: #29/#41→Frontend (browser-side remainder); #35→Data Storage; #83→KB+RAG; #38/#51 split by item. #70 is a numbering collision in the master file (two different entries) — left as-is, numbers never reused.

### 🟡 42 — A UI run with no usable CV fails late (allowance spent, two gates answered first)
*Found 2026-10-06. Where: `routes/runs.py` `start_run`, `worker.py:212-218`, `config.CV_DEFAULT_PATH`, `agents/CV_Link.py`.*

Nothing checks the default CV exists or the profile index is usable before `start_run` spends an allowance. `cv_link` is the sixth node — `jd_analysis`, gate 1, `profile`, gate 2, `profile_enrich`, `matching` all run first (4 LLM calls live-mode) before `parse_cv` raises `FileNotFoundError`/`_get_parts` raises `RuntimeError` → `run_error`. `refund_run` only covers failure-to-*start*. Typical causes: CV never copied, a path typo, a fresh clone (`knowledge_base/input/` is git-ignored, no default CV). **Blast radius:** every UI run until the file exists; a default-allowance user loses both runs. **Status: ✅ FIXED IN CODE 2026-10-22** — 503 before `consume_run` on the resolved path, plus boot warnings for the sample CV and the profile index. The index-as-503 half is deferred to `/api/ready` (it would 503 every run-start test). See "CV preflight — 2026-10-22" below.

### 🟡 45 — `POST /api/search` creates any collection it's asked about, `k` unbounded
*Found 2026-10-06. Also touches KB+RAG. Where: `routes/kb.py`, `vectordb/store.py` (`_collection` is `get_or_create_collection`).*

Despite calling itself read-only: `SearchRequest.collection` accepts any string → `query` creates an empty named collection on first search; `k≤0` or huge `k` passes straight to Chroma → 500. Any token holder can do either. **Impact:** junk collections pile up in the real index, visible in `GET /api/kb`'s counts, survive restarts; bad `k` gives a 500. **Status: OPEN.** Fix: `collection: Literal["profile","documents","learning"]`; `k: int = Field(5, ge=1, le=50)`; give `VectorStore` a read path using `get_collection` (404 on unknown) instead of `get_or_create_collection` for queries. **✅ Fixed 2026-10-15** — store half by KB+RAG (10-14), route half here: `collection` allowlist, `k` 1–50, `query` 1–2000 chars, `CollectionNotFound`→404; see `bugs.md` "2026-10-15 (search boundary)".

### ⚪ 51 (part) — Hygiene items for Backend
- KB overview counts a dict-shaped file by its *keys* (`len(read_json(f))`) — `do_not_claim.json` is `{_comment, version, forbidden_claims}`, shown as "3 records" / one record in `kb_file`. Fix: count `forbidden_claims`. **✅ Fixed 2026-10-22** — one `_records()` both routes read through.
- Live-mode key check ignores `USE_OPENAI` — `routes/runs.py` demands `GROQ_API_KEY` even when OpenAI routes every agent, and lets a run start with no `OPENAI_API_KEY`. Fix: use `config.required_keys_for_mode()`. **✅ Fixed 2026-10-22**, but *not* with `required_keys_for_mode()` (it demands every primary, and returns `[]` on an offline-default process) — `_live_key_problem()` asks the lane question instead. See "Hygiene: KB counts, live keys — 2026-10-22" below.

**Status: FIXED IN CODE 2026-10-22** (both Backend items; the other #51 bullets belong to other lanes).

### 🟠 68 — Legacy-token identity collision, queue skips the identity rule, five storage edges
*Logged 2026-10-12 by Pipeline Infra while writing backend storage tests. Nothing fixed; each pinned by a strict xfail in `test_backend_auth.py`. Where: `auth/store.py`, `auth/profiles.py`, `logplane.py`, `routes/logs.py`, `routes/runs.py`'s `download_document`, `cv_store.ingest_pending`, `registry.load_log`.*

1. **🟠 A legacy token can be backfilled onto a newer, different person's account.** `resolve_token` backfills `profile_id` lazily by name. Until a legacy token is next used it has no `profiles.json` row; an approval in between for a same-normalised name ("Jane"→"JANE") passes `create_profile`'s check and gets a fresh profile; when the legacy holder next logs in, backfill attaches them to that profile — two people, one account. This is the exact takeover §1 (above) exists to prevent, open for every not-yet-backfilled token. (test: `test_a_legacy_token_never_lands_on_a_newer_account_with_the_same_name`) **✅ Fixed in code 2026-10-15** — approval also refuses a name any `tokens.json` entry holds (`_name_held_by_a_token`); see `bugs.md` "2026-10-15 (legacy token collision)".
2. The request queue never calls `normalise_identifier` — reserved/`:`-containing names queue fine, refused only at approval (409); its dedupe uses `.lower()` not NFKC, so "Jane Doe"/"jane  doe" are two pending requests. **✅ Fixed in code 2026-10-16** — `create_request` normalises (`ProfileError`→`AuthError`→the route's existing 400) and dedupes on the normalised key via new `_queue_key()`, which casefolds as a fallback so a pending row predating the change still de-duplicates. Raw length bound stays in front (open route, cheap check first); also closes #70's "measures length before casefolding" edge. The "this name already has an account" check deliberately stays at approval — on an open route it would leak which names are registered. See `bugs.md` "2026-10-16 (request queue identity rule)".
3. Log plane: an unknown `?kind=` on `/logs/mine` raises `ValueError`→500 (should be 400/empty); the cursor is `ts` alone, so same-timestamp entries across a page boundary get skipped. **✅ Both fixed in code 2026-10-16** — `_checked_kind()` in `routes/logs.py` (400, in the body not as a `Literal`, since both routes are also called directly) and `query()` now pages on `(ts, count-at-that-ts)` over a total `(ts, kind, line-no)` order; see `bugs.md` "2026-10-16 (log paging and kind)".
4. An admin download is logged against the admin, not the document's owner — breaks that user's own audit trail and admin lookup by `profile_id`. **✅ Fixed in code 2026-10-16**, and `document_deleted` had the same defect (an admin could delete a user's CV with no trace in their own audit view) — both now attribute to the run's `owner` with `actor="admin"` via one shared `_audit_document()`; see `bugs.md` "2026-10-16 (document audit attribution)".
5. `cv_store.ingest_pending` moves the file into place *before* `_build_preview`/the index write — a failure in either leaves an orphan PDF with no index entry, contradicting "nothing partial is left on disk". **✅ Fixed in code 2026-10-21** — preview built before the move; move + index write + evictions as one step under the index lock; a failed write removes the file only if this upload created it. See "Orphan CV on upload — 2026-10-21" below.
6. A damaged run log is a 500: an empty/whitespace file reads as `[]`, then `owns([], …)` raises `AttributeError`; a truncated file raises `JSONDecodeError`; `list_for` skips both, `/log` and `/document` don't. **✅ Fixed in code 2026-10-16** — `load_log` returns None for anything that isn't a readable JSON *object*, so a damaged file is "unknown run" (404) at all four readers, with a `log.warning` naming it. **Wider than logged, confirmed by reproduction:** `list_for` did *not* skip both — a non-empty non-dict log reached `owns()`, where an admin passes and `data.get` raises, so `GET /api/runs` was a **500 for the admin** (whole Runs view down on one bad file); and for an admin `/log` on an empty file was a 200 carrying `[]`, a wrong answer rather than an error. `list_for` now reads through `load_log`. See `bugs.md` "2026-10-16 (damaged run log)".

**Also noted, no test:** pre-10-10 run logs carry `owner=token_id`, nothing migrates them so their owners lose sight (admin-only now); superseded confirmed CVs are never evicted (only pending ones); a top-up's allowance lives on the credential so doesn't follow a re-issued token, and its dedupe is per-token; `logplane.LOG_DIR` is fixed at import while every other store resolves per-call (tests must patch the module attribute). **Status: FIXED IN CODE** — all six items (5 on 10-21). Fixes: backfill every token eagerly at startup, or have `create_profile` also refuse a name any `tokens.json` entry holds; call `normalise_identifier` in `create_request`, dedupe on the normalised key; map an unknown kind to 400, page on `(ts, seq)`; log `profile_id=record.get("owner")` with `actor="admin"`; build the preview/write the index before moving the file into place (or delete the orphan on failure); treat anything non-dict (and a decode error) as `None` in `load_log`.

### 🟠 69 — A case variant of `manual_entries` skips the owner scope; an unknown Build-Profile section is silently unindexable; a `?token=` 403 logs as anonymous
*Logged 2026-10-12, Pipeline Infra. Where: `routes/kb.py` `kb_file`, `routes/profile.py` `ProfileEntry`/`add_profile_entry`, `app.py` `_audit_every_403`.*

1. **🟠** `kb_file` scopes ownership only when the resolved path *equals* `MANUAL_ENTRIES.resolve()`. On a case-insensitive filesystem (macOS/APFS), `/api/kb/profile/MANUAL_ENTRIES` is inside the store but not equal, so it falls through to an unscoped read — every account's Build-Profile data. Linux (the deploy target) 404s instead, so the xfail is conditional and passes on Linux. **✅ Fixed in code 2026-10-15** — exact on-disk name match + `os.path.samefile` scope check; see `bugs.md` "2026-10-15 (manual_entries case variant)".
2. `ProfileEntry.section` is a free string; an unknown section is accepted, logged as a warning, saved — and silently never indexed (retrieval can never find it). The docstring promises "indexed and never retrieved"; it's not even indexed. **✅ Fixed in code 2026-10-17** — a `field_validator("section")` on `ProfileEntry` refuses anything outside `SECTION_TYPES` (422, naming the valid sections), covering `PUT` as well as `POST`; validated against the table itself rather than a hand-copied `Literal`, so the allowed set can't drift from the mapping it has to match. `_index_entry`'s warning stays as defence in depth for rows already on disk (pre-validator ones and `save_gap_answers`'). See `bugs.md` "2026-10-17 (unindexable profile section)".
3. The app-wide 403 handler resolves the caller from the `Authorization` header only — `GET /api/runs/{id}/events` authenticates via `?token=`, so a 403 there is logged `actor:"anonymous"`, unattributable. **✅ Fixed in code 2026-10-17** — the handler falls back to `request.query_params.get("token")` (header still wins when both are present), so a cross-account stream open is named and the refused user sees it in their own `/logs/mine`. Not confined to the events route: attribution, not authentication. Nothing new reaches the log plane — only `profile_id`, and `fields["path"]` is `request.url.path`, query-free. See `bugs.md` "2026-10-17 (403 attribution on the events route)".

**Status: FIXED** — all three items in code (1 on 10-15, 2 and 3 on 10-17). **Also noted, no test:** `ProfileEntry.record` is unbounded (unlike `RunRequest`/`GateAnswer`, capped per #37's reasoning) — neither is the stored CV `filename`; `start_run` resolves the token twice (depends on both `Identity` and `Caller`); a retried start returns the *current* request's `cv`/`sample`, not the original's. **Status: OPEN.** Fixes: scope by name not path-equality (`file.casefold()=="manual_entries"`, or `os.path.samefile`, or refuse any non-exact on-disk name); ~~`section: Literal[...]` so unknown is a 422~~ (done 2026-10-17, as a validator over `SECTION_TYPES`); fall back to `request.query_params.get("token")` in the 403 handler when there's no `Authorization` header.

### 🟡 70 — A legacy token under a now-refused name is a 500 everywhere (✅ fixed 10-15); a rejected top-up loses its account; the admin can queue an ungrantable top-up
*Logged 2026-10-13, Pipeline Infra. Where: `auth/store.py` `_with_profile_id`/`_resolve`/`create_topup_request`, `routes/auth.py` `reject`.*

1. `resolve_token`'s backfill applies `normalise_identifier`, which is newer than some tokens — a token issued under a reserved name, a `:`-containing name, or a name that casefolds past 64 chars raises `ProfileError`, uncaught. Every request with it (login, any `Authorization` route, the `?token=` stream) is a **500** where `deps.py` promises 401 for an unknown (but this one is known) token — the holder is locked out silently, runs/CV/entries unreachable. Same family as #68 item 1. **✅ Fixed in code 2026-10-15** — `_with_profile_id` catches `ProfileError` and mints under `legacy:{token_id}` via new `profiles.get_or_create_system_profile`, whose key is taken verbatim and must hold a `:`, the one character typed names can't; the 500 was reproduced at three doors first, and all four pinning xfails now XPASS. See `bugs.md` "2026-10-15 (legacy token lockout)".
2. A top-up's only link to its account is `token_id`, set at creation; rejecting it (`_resolve(..., "rejected")`) overwrites it with `None` — the request can no longer be tied to an account, and its `request_rejected` audit line logs `profile_id=None`, so that account's own `/logs/mine` never shows the rejection (approvals do show). **✅ Fixed in code 2026-10-17** — `_resolve` only ever sets `token_id` (`token_id or record.get("token_id")`), so a rejected top-up keeps its account while a rejected signup still ends with None; `reject` attributes through new `store.profile_id_for_token()`, resolved at audit time so a later re-issue doesn't rewrite which credential asked. See `bugs.md` "2026-10-17 (rejected top-up attribution)".
3. `POST /auth/request-more` with the admin token queues a top-up for `token_id="__admin__"`, which has no `tokens.json` row — approving it 409s ("account no longer exists"), it sits pending, holds a `MAX_PENDING` slot, and can never be granted (the admin is unlimited anyway). **✅ Fixed in code 2026-10-21** — `create_topup_request` refuses the admin sentinel with a 400. See "Admin top-up — 2026-10-21" below.

**Also noted, no test:** ~~the request queue measures name length before casefolding (a 40×"ß" request queues, refused only at approval — same root as #68 item 2)~~ **✅ fixed 2026-10-16 with #68 item 2** (the queue now normalises, so the folded length is what's measured); top-ups share `MAX_PENDING` with anonymous signups and could skip the cap since they're already one-per-token; no rate limit/lockout on `/auth/login` and `ADMIN_TOKEN`'s strength is never checked (only non-empty); tokens never expire, no logout/revoke route (a hand-edit of `tokens.json` does take effect next request); two legacy tokens whose names normalise the same get merged onto one account by the backfill — a migration decision sharing #68 item 1's root. **Status: OPEN.** Fixes: don't apply the typed-name rule to an already-approved name — on `ProfileError`, mint under a system key no typed name can reach (`legacy:{token_id}`), or backfill eagerly at startup; in `_resolve` keep the existing `token_id` when there's no new one, and in `reject` log the top-up's actual account; in `create_topup_request`/the route, refuse the admin token with 400 "the admin account has no run limit."

### 🟠 87 — The SSE stream goes silent >30s during `cv_link` (loses a 30s-timeout client); `cv_link` also reloads both models
*Logged 2026-10-14, Pipeline Infra, from a smoke-test log. Where: `routes/runs.py:203-207` (SSE generator), `scripts/smoke_backend.py` (client), `utils/cv_handling/cv_match.py`/the `cv_link` node (model loads). Also touches Agents, Pipeline Infra.*

1. The SSE generator yields only `data:` events and sleeps 0.15s between polls — no keepalive while a node runs silently.
2. On a cold server, `cv_link` reloads the embedding model (8.0s) and the reranker (8.2s) — already loaded once by `profile` earlier in the same process (8.7s/8.2s) — plus opens a second Chroma store and embeds 74 CV lines, all silent.
3. The smoke client's 30s read timeout (`httpx.Client(timeout=30.0)`) fired mid-stream; the section-4 loop doesn't catch `httpx.HTTPError` (unlike `gate_waits()`), so it died with a traceback and the server shut down with the run unfinished.
4. Beyond the smoke test: any proxy with a read timeout does the same to a real browser (`nginx.conf` not checked; nginx's default `proxy_read_timeout` is 60s). `EventSource` reconnects itself but replays full history each time, and the user sees a stall.
5. (Noted in passing, not new) gate 1's text/snapshot print twice on resume-replay as expected; gate 2's evidence includes a stale fixture gap-answer left by an earlier run — that's the known "offline runs write into the real KB" issue.

**Status: PARTLY FIXED, verified 2026-10-14** — the smoke test now passes every check end to end (all 6 sections, four gates, `cv_link` position, `stub:false` for document, correct snapshot paths, the three 422s, the allowance, the reject loop). Item 1 (SSE keepalive every `SSE_KEEPALIVE_SECONDS`=10s when idle) is **in**. Item 3's timeouts are in `smoke_backend.py` (`read=180`); its `httpx.HTTPError` catch wasn't checked. Items 2 (double model load) and 4 (`nginx.conf`) remain **open**. Fixes: send an SSE comment line every ~10-15s when idle (EventSource and the smoke filter both ignore comments) — done; load each model once per process, have `cv_link`/`cv_match` reuse `profile`'s instances; use `httpx.Timeout(30.0, read=180.0)` and catch `httpx.HTTPError` in the section-4 loop; check `nginx.conf` for `proxy_read_timeout`/`proxy_buffering off` on the events route.

### Also touches this role — owned elsewhere
| Entry | Title | Owned by |
|---|---|---|
| #29 | A UI run can never answer the gap interview | Frontend + Deployment |
| #35 | `manual_entries.json` has a CLI writer and a concurrent HTTP writer, no lock | Data Storage + Handling |
| #41 | `cv_link` is invisible to the bridge and the UI | Frontend + Deployment |
| #43 | The API process holds three embedding models + two rerankers; gap-answer saving loads a fourth every time | KB + Semantic Search + RAG |
| #55 | Gate 4 wired end to end, but a reject still changes little; live reviews write real CV text into an un-ignored folder | Agents + Orchestration |
| #63 | A non-ASCII credential is a 500; an interrupted approval mints two tokens; export's kind fallback is unslugged; a failed export leaves half a pair | Data Storage + Handling |
| #64 | Retrieval: keyword channel case/punctuation-blind, scores saturate, reads create collections, `/api/search` takes any k, two indexed types never retrieved | KB + Semantic Search + RAG |
| #70 (LLM door) | Retry+fallback built and its keyless-primary crash fixed, but five gaps remain before a live run can trust it | Agents + Orchestration |
| #72 | Unknown state fields dropped silently, nodes share stored artifact objects, gate snapshots keep what the run log scrubs | Agents + Orchestration |
| #74 | A "none" grade keeps citations, a double citation counts twice, the gate prints the CV to stdout, checks only the decision | Agents + Orchestration |
| #78 | No caller sets LangGraph's recursion limit (a raised revision cap crashes mid-loop); no gate payload carries its round | Agents + Orchestration |
| #82 | A refused gate answer (typo'd decision) leaves the gate stuck — LangGraph replays the bad answer on every later resume | Agents + Orchestration |
| #84 | Four stale backend tests (FastAPI version drift, an old record shape) — nothing actually wrong in the backend | Pipeline Infra + Config + Testing |

### Fixed in code, waiting on a run (not copied in full)
| Entry | Title |
|---|---|
| #28 | `STUB_NODES` still calls Matching a stub, doesn't know `profile_enrich` exists |
| #30 | Editing a gap answer through the UI leaves the old text in the vector index forever |
| #31 | `registry.list_for` promises newest-first, sorts by random hex |
| #32 | UI runs write every snapshot into one shared `logs/no_run_id/` |
| #37 | `POST /runs` accepts any `pace_seconds`/`job_description` |
| #52 | Side effect of the P2 fix: gate 3's waiting marker has no node in the UI |
| #9 (Agents) | Two competing gate systems — the frontend bridge died at the first gate |

---

# Restart survival, saved CVs, log-plane `run` kind, and three small fixes — built 2026-10-13 to 10-15

> Seven backend-only sessions, each the single most important item off `bugs.md`'s ranked list. Full detail/authorship/verification in `bugs.md`'s dated sections (linked below); this is the narrative summary. Frontend impact logged in `frontend/bugs.md` → "2026-10-15 (backend)".

**Restart survival** (`bugs.md` → "2026-10-13 (restart survival)"). A run parked at any gate now survives a restart: `worker._park` persists the log the moment a gate opens, not only at the end. `registry.resume(run_id, identity)` rebuilds the run from that log, reads the pending interrupt off the checkpointer, and re-parks on the exact same gate — installing `run["gate"]` *before* the worker thread starts, so `POST …/gate` is answerable the instant `resume()` returns rather than after the ~20s cold-start. `list_for` reports `interrupted: true` for these rows. New route: `POST /api/runs/{id}/resume`. Verified against the **real** LangGraph + SqliteSaver: parked, killed the connection, recovered the interrupt cold, resumed through to the next gate.

**Saved CVs: list + delete** (`bugs.md` → "2026-10-13 (saved CVs)"). `list_for`'s summaries gained `review`/`saved`. New `DELETE /api/runs/{id}/document`: owner-checked, removes both saved files, nulls the export in memory and on disk. (A mounted `OUTPUTS_DIR` volume for redeploy survival is deployment config, not built here.)

**The log plane's `run` kind** (`bugs.md` → "2026-10-14 (log plane, run kind)"). `worker.py` now writes `run_started`, `node_done` (duration corrected for the artificial UI pacing sleep), `gate_opened`, `gate_decided` (decision only, never typed text), `run_done`, `run_stopped`, `run_error`; `routes/runs.py` writes `allowance_spent`/`allowance_refunded`. Closes the `run` kind in full — `llm`/`retrieval` remain other lanes' writes into the same module.

**Three small, independent fixes** (all "2026-10-15" in `bugs.md`):
- `gate_done` now carries `gate` too, matching `gate_wait`.
- `match_counts: {matched, partial, unmatched}` on `cv_link`'s `node_done`, summed off `line_links`, so the frontend can warn a new user with an empty profile without walking the list itself.
- **`final` is now read off `run_error` too, everywhere it's read** — the real bug found this session: `worker._drive`'s except already attached an approved CV's `final` to `run_error`, but `download_document`/`delete_document`/`list_for`'s `saved`/`review` each only checked `run_done`, so that CV was undownloadable, undeletable, and invisible the moment anything later failed. Fixed with one shared `registry.current_export()` instead of three independent lookups.
- `outcome: "done"|"stopped"|"error"|null` added to `list_for`'s summary (additive; `completed` untouched), so a crashed run no longer reads identically to a superseded one.

**What's left this role can build alone** *(as of 10-15 morning; see the next section for what changed since)*: every remaining 🔴/🟠 is blocked on another lane (Agents, KB+RAG, Data Storage) or already noted as not a live gap. 🟡 tier still has: naming the failed step on `run_error` (data's already in `run["events"]`, just not surfaced), the `cv_link` re-run loop-back artifact issue, and a self-export/account-delete route.

**Verification posture across all seven sessions:** `py_compile` + a clean `import backend.app` each time; the full `test_backend_*` suite before/after every change (holding at the same small set of pre-existing unrelated failures, plus one newly-surfaced route-prefix mismatch in a test added mid-session); a scratch `TestClient`/direct-call script per change, against a stub graph or — for restart-survival specifically — the real graph and checkpointer. **Not run:** uvicorn, a browser, the frontend.

---

# Log paging and kind — 2026-10-16

> One item, user's grant: "the next most critical one". Code in
> `backend/logplane.py` and `backend/routes/logs.py` only. Full detail in
> `bugs.md`'s "2026-10-16 (log paging and kind)"; master entry
> `context/bugs_audit_fixed.md` #68 item 3 marked in place. **Not run:**
> uvicorn, a browser, the frontend.

**#68 item 3 🟠, both halves.** The cursor was the last entry's `ts` and the
next page took `ts < cursor`, so every remaining entry sharing that timestamp
was **silently dropped** — full pages, no error, a walk that looked complete
and wasn't. Ties are ordinary: the `run` kind writes `node_done` in a tight
loop, and `kind=None` merges five files. Separately, an unknown `?kind=`
reached `_path()`'s `ValueError` and was a 500.

**The fix.** Entries are now carried as `(ts, kind, line-number, entry)` and
sorted on that whole key — a *total, reproducible* order, which is what makes
a positional cursor meaningful: append-only files mean a line never moves, and
`KINDS` is iterated in fixed order. The cursor is `"<ts>|<n>"`, n = how many
entries at that exact `ts` have already been sent. `_checked_kind()` in
`routes/logs.py` turns an unknown kind into a 400 for both routes.

- **Past tie groups are immutable** — an append can only carry a `ts` at or
  after the newest — which is why a count is safe to carry across pages.
- **`(ts, seq)` was rejected:** a schema change to an append-only log whose
  existing lines have no `seq`, and per-file counters still wouldn't order a
  five-file merge.
- **Validated in the body, not as a FastAPI `Literal`**: both route functions
  are also called directly in-process (including by the test pinning this),
  where annotations validate nothing.
- **A malformed cursor degrades rather than raises** — the point of this item
  is that a query param can't 500 these routes.
- **Wire note:** `next_cursor`'s format changed from a bare timestamp to
  `"<ts>|<n>"`. Opaque and fed straight back, and nothing in `frontend/src`
  calls either route yet, so no consumer breaks.

**Verification:** `py_compile` + `import backend.app`; a 34-assertion scratch
script including **60 randomised paging trials** (every entry exactly once,
per-timestamp counts exact, order newest-first), cross-kind ties, filter
composition, `for_user()` over tied projected entries, 8 malformed cursors,
and both routes' 400; full `test_backend_*` before/after.

**Tests owed by the user:** remove the `xfail` markers from
`test_paging_never_skips_entries_that_share_a_timestamp` and
`test_an_unknown_log_kind_is_a_client_error_not_a_500`.

**Found while verifying, not mine:** `utils/human_gate.py` now sends
`revision`/`max_revisions` on every gate payload (edited 14:51 today), which
is the Agents-lane line `"gate 4"` §3 and frontend B1 were blocked on. The
backend relays both already (`_PAYLOAD_NOT_PASSED` excludes neither —
verified), so that 🟠 needs no backend code; it needs `StubGraph` updated
(the user's test) and the frontend told. It is also why
`test_the_stub_pauses_with_exactly_the_payload_the_real_gate_sends` began
failing this session.

---

# Rejected top-up attribution — 2026-10-17

> One item, user's grant: "fix the next most critical bug". Code in
> `backend/auth/store.py` and `backend/routes/auth.py` only. Full detail in
> `bugs.md`'s "2026-10-17 (rejected top-up attribution)"; master entry
> `context/bugs_audit_fixed.md` #70 item 2 marked in place. **Not run:**
> uvicorn, a browser, the frontend.

**Tried first, withdrawn.** Yesterday's finding — a damaged `tokens.json`
being a 500 at every door — looked like the worst thing left, and I built the
#68-item-6 fix for it (a shared `jsonstore.read_json_or_empty()` on the
verification paths, fail-closed to 401, write paths left raising so a damaged
file could never be rewritten from `[]`; 133 assertions passing). The suite
then showed `test_the_admin_still_gets_in_when_tokens_json_is_corrupt` going
pass → fail: that test **pins the raise on purpose**. `ADMIN_TOKEN` is
compared before the file is read, so the admin door survives a corrupt
`tokens.json` and can repair it, while a user token "fails closed, never 'no
tokens, no check'". A decision stated in a test isn't mine to flip quietly, so
I reverted the change in full and corrected the logged entry. Lesson worth
keeping: check whether an "unlogged bug" is something a passing test already
asserts, before treating a known-good file's behaviour as an oversight.

**#70 item 2 🟡, the actual fix.** A top-up carries its account's `token_id`
from creation — the whole difference between a top-up and a signup.
`reject_request` called `_resolve(id, "rejected")`, whose `token_id` defaults
to None, and the record's own value was overwritten with it. So the resolved
request could no longer be tied to an account, and `reject` had nothing to
attribute to: `request_rejected` carried `profile_id: None`, and the account's
own `/logs/mine` never showed a decision made about it — while
`request_approved` carried the account and did show.

**The fix.** `_resolve` only ever *sets* `token_id`
(`token_id or record.get("token_id")`); a rejected signup still ends with
None, having never had one. `reject` attributes through new
`store.profile_id_for_token()`, the same rule `approve` follows.

- **Resolved at audit time, not stored on the request:** the request records
  which credential asked, so a later re-issue doesn't rewrite history.
- **Looked up for any request carrying a `token_id`**, not branching on
  `kind == "topup"` as the entry proposed — a `kind` check would be a second
  place that has to know which kinds carry one.
- `profile_id_for_token` maps `ADMIN_TOKEN_ID` → `ADMIN_PROFILE_ID` (no
  `tokens.json` row to find) and is attribution only, never a permission
  check.

**Checked:** 29 assertions — store level: a rejected top-up keeps `token_id`
in the record and on disk, grants nothing, a rejected signup still None,
approval still sets it, and the lookup handles a real token/None/unknown/the
admin sentinel. Over HTTP: the reject response keeps the link, the entry names
the account with `actor: "admin"` and the `request_id` intact, shows in that
account's `/logs/mine` beside its `request_more`, is absent from the admin's
view, findable by `?profile_id=`, carries no raw token; a rejected signup
stays unattributed and hidden; approval attribution unchanged; a double
rejection still 409, changing and auditing nothing.

**Suite:** `39 failed, 528 passed, 24 xfailed` → `41 failed, 528 passed, 22
xfailed` — the difference is exactly the two XPASSes
(`test_a_rejected_topup_keeps_the_account_it_was_for`,
`test_a_rejected_topup_shows_in_that_accounts_own_log`). A
`test_backend_mode_isolation.py` case appeared and vanished between runs
either side of this change; those 15 never-run LLM-door tests are flaky here
and another lane's.

**Owed (yours):** drop both strict xfails.

---

# 403 attribution on the events route — 2026-10-17

> One item, user's grant: "fix the next most critical bug". Code in
> `backend/app.py` only. Full detail in `bugs.md`'s "2026-10-17 (403
> attribution on the events route)"; master entry
> `context/bugs_audit_fixed.md` #69 item 3 marked in place. **Not run:**
> uvicorn, a browser, the frontend.

**#69 item 3 🟠, the last of #69.** `_audit_every_403` read the caller out of
the `Authorization` header only, and the events route authenticates by
`?token=` because `EventSource` can't set headers. So the one 403 with a
security reading — an account opening someone else's run stream — was filed
as `actor: "anonymous"`, `profile_id: null`: invisible in the refused user's
own `/logs/mine` (projection is by `profile_id`) and unfindable by
`?profile_id=` for the admin. Same class as #68 item 4, fixed 10-16.

**The fix.** Fall back to the query token when there's no header.

- **The header wins when both are present**, so a query param can't aim an
  audit line at another account. Pinned.
- **Not confined to the events route**, unlike `identity_from_query_token`:
  that confinement is about authentication (tokens out of logs and history);
  this is attribution, and a token's presenter is its holder either way. A
  future SSE route needs no second fix.
- **Nothing new reaches the log plane:** only the resolved `profile_id`, and
  `fields["path"]` is `request.url.path`, which excludes the query string —
  asserted by looking for the raw token in the serialised entry.
- **The resolve is wrapped**, so failing to work out *who* to blame can't turn
  an ownership 403 into a 500.

**Checked:** 24 assertions over a real `TestClient` (the only place this
handler runs) — bob's refused stream open audited against bob with
`actor: "account"`, visible in his `/logs/mine`, absent from alice's,
findable by `?profile_id=<bob>`, path query-free, token nowhere in the entry;
header path unchanged; header beating a conflicting query token; an unknown
`?token=` still 401 and audited as neither; owner and admin both still
streaming with nothing audited; a non-admin's `/admin/logs` 403 still
attributed.

**Suite:** `38 failed, 528 passed, 25 xfailed` → `39 failed, 528 passed, 24
xfailed` — the difference is exactly
`test_a_403_on_the_events_route_is_attributed_to_its_caller` XPASSing.

**⚠️ Found while checking, not fixed:** a damaged `tokens.json` is a 500 at
every door — `resolve_token` → `read_json` → `JSONDecodeError` out of
`require_auth`, every role, `/auth/login` included. The #68-item-6 shape with
a far wider blast radius (everyone, not one run). Pinned by section 8 of the
scratch script, logged under #69's "also noted"; the fix is `load_log`'s —
fail closed to 401 and log it. Deliberately left for its own turn.

**Owed (yours):** drop the strict xfail on that test.

---

# Unindexable profile section — 2026-10-17

> One item, user's grant: "fix the next most critical bug". Code in
> `backend/routes/profile.py` only. Full detail in `bugs.md`'s "2026-10-17
> (unindexable profile section)"; master entry
> `context/bugs_audit_fixed.md` #69 item 2 marked in place. **Not run:**
> uvicorn, a browser, the frontend.

**#69 item 2 🟠.** `ProfileEntry.section` was a free string, and
`_index_entry` warns-and-returns for a section outside `SECTION_TYPES`. So
`{"section": "hobbies"}` saved with a 200, sat in `manual_entries.json`, and
was never embedded — the user told their entry is in, retrieval unable to ever
reach it. Of everything left on the open list this was the only item where a
user's own typed data is quietly lost; the rest are audit-attribution gaps
(#69 item 3, #70 item 2), an ungrantable pending row (#70 item 3), or disk
litter (#68 item 5).

**The fix.** A `field_validator("section")` → 422 naming the valid sections.
Both routes share the model, so `PUT` is covered with `POST`.

- **Against `SECTION_TYPES`, not a `Literal[...]`.** The entry proposed the
  `Literal`; same 422, but it hand-copies the six keys, so a seventh section
  added to the table would leave the check behind — the drift that produced
  `AGENTS`/`GATES`/`STUB_NODES`. Verified by adding and removing a table key
  at runtime and watching the validator follow.
- **422, not a coerced `extras`:** filing an unrecognised section under a type
  the user never chose would put it in the index under the wrong `type`, which
  `agents/profile.py`'s `QUOTAS` filters on.
- **`_index_entry`'s warning stays, as defence in depth** — pre-validator rows
  and `learning/profile_store.save_gap_answers`' gate-2 answers (which don't
  come through these routes) can still carry an unknown or missing section and
  must keep skipping the index rather than raising inside a daemon thread.

**Checked:** 33 assertions — six real sections still build and each maps to a
record type; eight refusals (`hobbies`, empty, `Skills`, `skill`,
`" skills "`, the internal `work_experience`, punctuation, a fullwidth
spelling) with every valid section named in the message; nothing written on a
refusal; `POST` still saves, stamps `owner` and indexes under `skill:<id>`
with `type`/`section` metadata intact; `PUT` unbuildable with a bad section
and a valid edit still re-indexing under the same id; `_index_entry` on a
legacy row with a bad or missing section still silent, no `KeyError`.

**Suite:** `37 failed, 528 passed, 26 xfailed` → `38 failed, 528 passed, 25
xfailed` — the difference is exactly `test_an_unknown_profile_section_is_refused`
XPASSing; `passed` didn't move.

**Owed (yours):** drop that test's strict xfail.

---

# Request queue identity rule — 2026-10-16

> One item, user's grant: "fix the next most critical bug". Code in
> `backend/auth/store.py` only. Full detail in `bugs.md`'s "2026-10-16
> (request queue identity rule)"; master entry
> `context/bugs_audit_fixed.md` #68 item 2 marked in place. **Not run:**
> uvicorn, a browser, the frontend.

**#68 item 2 🟠.** `create_request` never called `normalise_identifier`,
despite `profiles.py` stating these names are "rejected at normalisation so
none of these can ever be queued". `admin`, ` ROOT `, `ＡＤＭＩＮ` (NFKC-folds
to `admin`), `a:b`, and a name that fits the length bound raw but not folded
(40×"ß" measures 40, folds to 80) all queued, and were refused with a 409 at
approval — a person told their request was in, waiting for review, then
refused for a reason the server knew the moment they typed it. The
pending-duplicate check compared `.lower()`, so "Jane Doe" and "jane  doe"
were two queued requests for one account.

**The fix.** Normalise at the door, mapping `ProfileError` to `AuthError` so
the route's existing handler returns the same 400 it already returns for an
empty or overlong name, with the message the approval path was surfacing.
Dedupe on a new `_queue_key()`.

- **Raw length bound stays in front of the normalised one** — the route takes
  no auth, so the cheap check on the typed string runs before any NFKC work.
- **`_queue_key()` casefolds as a fallback** for a pending row the rule now
  refuses; only rows written before this change can be in that state, and
  without the fallback they'd stop de-duplicating against anything at all.
- **Also closes #70's "measures length before casefolding" note**, same root.
- **Not moved to the queue, on purpose:** whether the name already has an
  account or an issued token. That stays at approval
  (`_name_held_by_a_token`, item 1) — on an open, unauthenticated route it
  would tell the world which names are registered. The existing test for that
  split passes unchanged.
- **Top-ups untouched:** `create_topup_request` takes its identifier off the
  caller's own bearer token, never typed text.

**Checked:** 47 assertions — eight refused shapes queue nothing (raw-overlong
still reports the raw message); the route returns 400, not 500, and audits
nothing on refusal; five spellings of one name each refused with one row left,
while a different name still queues; a rejected request frees its name; a
seeded legacy `"A:B"` row still de-duplicates and still lets an unrelated name
through; the happy path still stores stripped display text, mints token +
profile, and keys the profile on the normalised name; item 1's approval guard
intact; top-up dedupe and `MAX_PENDING` unchanged.

**Suite:** `31 failed, 528 passed, 32 xfailed` → `37 failed, 528 passed, 26
xfailed` — the set difference is exactly the six XPASSing cases of
`test_a_name_no_account_could_have_is_refused_at_request_time` (five) and
`test_two_spellings_of_one_name_are_one_pending_request`; `passed` didn't
move.

**Owed (yours):** drop both strict xfails. Note the first marker's reason says
4 cases; the parametrize has 5.

---

# Damaged run log — 2026-10-16

> One item, user's grant: "the next most critical one". Code in
> `backend/runs/registry.py` only. Full detail in `bugs.md`'s "2026-10-16
> (damaged run log)"; master entry `context/bugs_audit_fixed.md` #68 item 6
> marked in place. **Not run:** uvicorn, a browser, the frontend.

**#68 item 6 🟡, and it was bigger than its entry.** `load_log` trusted the
file. An empty or whitespace-only run log came back as `[]` — `read_json`'s
`default=None` means "a new list", not "None" — and `owns([], identity)` then
raised `AttributeError` on `[].get`; a truncated one raised `JSONDecodeError`
out of the read. Both escaped `/runs/{id}/log`, `/document`, `DELETE
.../document` and `/resume` as a **500**, for a damaged file rather than a bad
request.

Two things the entry had wrong, both found by reproducing it rather than
reading it:
- It says `list_for` skips both. It doesn't — its `except` wrapped only the
  read, and its own `if not data` let a non-empty non-dict log through to
  `owns()`, where an admin clears the role check and `data.get` raises. **`GET
  /api/runs` was a 500 for the admin**: the whole Runs view down on one bad
  file in the folder.
- For an admin, `/log` on an empty file wasn't a 500 at all — it was a **200
  carrying `[]`** as the run's record, because admin short-circuits `owns()`
  before the `.get`. A wrong answer reads as "this run has no events" instead
  of "this file is broken", which is worse than the error.

**The fix.** `load_log` returns None for anything that isn't a readable JSON
*object*: a `ValueError` (covering `JSONDecodeError` and `UnicodeDecodeError`)
or `OSError` from the read, or a parse yielding a non-dict. `list_for` reads
through `load_log(path.stem)` instead of calling `read_json` itself.

- **404, not a 5xx.** The caller can do nothing about a half-written file, and
  a 404 says what the admin's Runs list already says about it. A dedicated
  "this log is damaged" 5xx would leak the state of the server's disk and give
  the caller nothing to act on.
- **One reader, one verdict.** A list that skipped a file while `/log` 500'd on
  the same file is precisely how this stayed invisible — the same two-readers
  drift that produced the three `final` lookups behind A1.
- **Logged, not silent:** a `log.warning` per skip, naming the file and why,
  so a damaged log stays findable by whoever can repair it. Registry gained
  `logging` and the shared `"backend"` logger.
- **Nothing else loosened.** `contained_path()` still runs before anything is
  opened (a crafted `run_id` is None for its original reason); the guard is
  "is it a dict", not "does it have an `owner`", so a pre-ownership log still
  loads and stays admin-only; and a stranger on a *healthy* run still gets
  403, not 404 — the fix must not blur those.

**Checked:** 130 assertions. Ten damaged shapes (empty, whitespace,
truncated, a JSON list, `[]`, a string, `null`, a number, non-JSON, non-UTF-8
bytes) → None from `load_log` and 404 from all four routes for both an owner
and an admin, nothing audited, files left byte-for-byte alone; a healthy log
unchanged through `/log` for both roles with a stranger still 403; a legacy
`owner`-less dict still loading, admin-only; the five traversal cases still
None; `list_for` unbroken for the admin on every damaged shape, row shape and
120-char truncation intact; and a sweep asserting both readers agree about
every file in the folder.

**Suite:** `28 failed, 528 passed, 35 xfailed` → `31 failed, 528 passed, 32
xfailed` — the set difference is exactly the three XPASSing cases of
`test_a_damaged_run_log_reads_as_unknown`; `passed` didn't move.

**Owed (yours):** drop that test's strict xfail, and add a fourth case for a
log that parses to a non-dict (`[{"id": "r1"}]`) asserting both `load_log is
None` *and* that `list_for` with an admin identity still returns the healthy
runs — the admin-500 half, which no current test covers.

---

# Document audit attribution — 2026-10-16

> One item, user's grant: "the next most critical bug". Code in
> `backend/routes/runs.py` and `backend/runs/registry.py` only. Full detail in
> `bugs.md`'s "2026-10-16 (document audit attribution)"; master entry
> `context/bugs_audit_fixed.md` #68 item 4 marked in place. **Not run:**
> uvicorn, a browser, the frontend.

**#68 item 4 🟠: a cross-account document action was recorded against the
wrong account.** `registry.owns()` passes any admin, so
`GET`/`DELETE /api/runs/{id}/document` can act on someone else's saved CV —
and both logged `profile_id=identity["profile_id"]`, `actor="account"`. The
owner's own `/logs/mine` therefore never showed that their CV had been
downloaded or (the half not in the logged summary) **deleted**, and
`/api/admin/logs?profile_id=<owner>` could not find either. Both routes
contradicted a call this package had already made: `routes/admin.py`'s
`admin_data_access` logs the *target* account with `actor="admin"` and is
deliberately user-visible.

**The fix:** one new `routes/runs._audit_document()` through which both call
sites attribute — `profile_id` = the run's `owner`, `actor="admin"` when the
caller isn't the owner. `registry.delete_document` now returns the owner
rather than None, so the route doesn't re-read the log to find out who it was.

- **One helper, not two call sites with the same rule written twice** — that
  is how `AGENTS`/`GATES`/`STUB_NODES` each drifted from the graph.
- **No allowlist change:** both events were already user-visible in
  `logplane._USER_VISIBLE_FIELDS`; they were simply never landing on the
  account that could see them. `actor` is still never projected, so the owner
  learns *that* it happened, not *which* admin — matching
  `admin_data_access`.
- **An ownerless (pre-ownership) log** gives `profile_id: None` — honest,
  since those logs are admin-visible only and there is no account to name.

**Verification:** `py_compile` + `import backend.app`; a 26-assertion scratch
script (admin vs. owner × download vs. delete, the owner's projected view, the
admin's own view, `?profile_id=` lookup, an ownerless log, a stranger's 403
with nothing audited, a nothing-saved 404 with nothing audited); full
`test_backend_*` before/after — the set diff is **exactly** the one strict
xfail pinning this item flipping to XPASS.

**Tests owed by the user:** remove the `xfail` from
`test_an_admin_download_is_logged_against_the_documents_owner`, and ideally add
the `document_deleted` twin plus an `actor == "admin"` assertion.

---

# Legacy-token lockout — 2026-10-15 (evening)

> One item, user's grant: "fix the most critical bug listed". Code in
> `backend/auth/profiles.py` and `backend/auth/store.py` only. Full detail in
> `bugs.md`'s "2026-10-15 (legacy token lockout)"; master entry
> `context/bugs_audit_fixed.md` #70 item 1 marked in place. **Not run:**
> uvicorn, a browser, the frontend.

**#70 item 1 🟠: a token approved before the typed-name rule existed was a 500
at every door.** The lazy `profile_id` backfill runs the token's own
identifier through `normalise_identifier`, a rule newer than the token. A
reserved name, a `:`, or a name that casefolds past 64 chars raised
`ProfileError` uncaught — so login, every `Authorization` route and the
`?token=` stream all 500'd, where `deps.py` promises 401 only for an *unknown*
token. The holder was locked out of their own runs, CV and entries with
nothing on screen to explain it. Reproduced at three doors before fixing. Live,
not theoretical: 5 of 10 real `tokens.json` records still take this path.

**The fix:** new `profiles.get_or_create_system_profile(key, display)` — an
idempotent create whose key is used **verbatim** and must contain a `:`, the
one character `normalise_identifier` refuses in typed input. So a system-keyed
account cannot be collided with or taken over by anything a human types.
`_with_profile_id` falls back to `legacy:{token_id}` on `ProfileError`.

- **Refusing isn't an option here**, unlike #68 item 1: that judged a typed
  name at approval; this is a credential already in `tokens.json`, so the
  choice is give it an account or lock out a legitimate holder.
- **Keyed on `token_id`** because the name is exactly what can't be used — and
  it never changes, so the account is stable and the fallback runs once.
- **Eager startup backfill was rejected:** the same call would raise at boot,
  turning one lockout into a boot failure for everyone.
- Two unnormalisable legacy tokens get **separate** accounts — the fail-safe
  direction; it never merges two people.
- Lock order (profiles → store) and the 401-for-unknown contract both
  unchanged; verified a genuinely unknown token still 401s.

**Verification:** `py_compile` + `import backend.app`; a 45-assertion scratch
script against a tmp `KB_AUTH_DIR`; the full `test_backend_*` suite run with
the fix reverted and then restored — the set diff is **exactly** the four
strict xfails pinning this item flipping to XPASS, nothing else moved.

**Tests owed by the user:** remove the `xfail` markers from
`test_a_legacy_token_whose_name_the_new_rule_refuses_still_resolves` (3 cases)
and `test_a_legacy_token_under_a_name_the_new_rule_refuses_can_still_sign_in`.

---

# Three fixes off the open-bug list — 2026-10-15 (afternoon)

> One session, user's grant: "fix the next most critical one", one at a time. Code in `backend/auth/store.py` and `backend/routes/kb.py` only. Full detail in `bugs.md`'s "2026-10-15 (legacy token collision)", "(manual_entries case variant)", "(search boundary)"; master entries `context/bugs_audit_fixed.md` #68 / #69 / #45 / #64 are marked in place. Checked by `py_compile` + import (and, for the last one, building `SearchRequest` with good and bad values). **Not run:** pytest, uvicorn, any request.

**Ranking used.** What's left inside this role, worst first: someone else's data reaching the wrong account → a cross-user read → lasting damage to shared state → a 500 or lockout. Anything blocked on another lane was skipped.

1. **#68 item 1 🟠: a legacy token could land on a newer person's account.** Tokens issued before 10-10 get a `profile_id` lazily, by looking up their name. Approving a same-normalised name in that gap minted a fresh profile, and the legacy holder's next login then attached to it. **Fix:** new `store._name_held_by_a_token()`. Under `_LOCK`, the signup branch of `approve_request` now refuses (409) any name an issued token already normalises to.
   - **Why refuse rather than split:** it's the same answer approval already gives once that token has been backfilled, so the outcome no longer depends on who logged in first.
   - **No race:** the check reads `tokens.json`, which holds the legacy record whether or not it has been backfilled.
2. **#69 item 1 🟠: on macOS, a case variant of `manual_entries` was served unscoped.** `kb_file` applied the owner scope by path *equality*, and a case-insensitive filesystem opens `MANUAL_ENTRIES.json` without the paths being equal. **Fix, two layers:**
   - `kb_file` only matches an exact on-disk name from the store's own listing. A variant now 404s everywhere, and traversal can't match at all.
   - The scope check is `os.path.samefile` (`_is_manual_entries`), in both `kb_file` and `kb_overview`'s count, so a link onto the file is scoped too. It reads `_MANUAL_ENTRIES_RESOLVED` at call time, so the test fixture's patch still applies.
3. **#45 (and #64 item 4) 🟡: `POST /api/search` took any collection and any `k`.** **Fix:**
   - `collection: Literal["profile","documents","learning"]`, `k` 1–50, `query` 1–2000 chars.
   - `CollectionNotFound` → 404 instead of a 500. The import is local, so boot stays light.
   - **Why an allowlist**, not just the 404: Stage 0 puts per-profile collections into this same index, and a free name would let any caller search another user's.
   - No wire change: the frontend already sends one of the three with `k: 5`.

**Tests owed by the user** (none written or run here):
- #68: rewrite `test_a_legacy_token_never_lands_on_a_newer_account_with_the_same_name` to expect the approval to raise `AuthError`.
- #69: remove the conditional strict xfail on `test_no_spelling_of_manual_entries_skips_the_owner_scope` (it XPASSes on macOS).
- #64: remove the strict xfail on `test_search_refuses_a_non_positive_k_before_the_store`.
- Point `test_the_search_route_returns_the_store_hits_in_its_wire_shape` at an allowed collection name instead of `"kb_test"`.

**What's left this role can build alone, after this:**
- ~~#70 item 1: a legacy token under a now-refused name is a 500 everywhere.~~ ✅ **Done 2026-10-15** — see the section below.
- ~~#70 item 2: a rejected top-up loses the account it was for.~~ ✅ **Done 2026-10-17.**
- ~~The rest of #68: an orphan PDF on ingest failure (item 5).~~ ✅ **Done 2026-10-21.** (Items 2, 3, 4 and 6 are ✅ done 2026-10-16.)
- ~~#69: an unknown section is never indexed; a `?token=` 403 is audited as anonymous.~~ ✅ **#69 fully closed 2026-10-17.**
- ~~**New, found 2026-10-17:** a damaged `tokens.json` is a 500 at every door.~~ **Not a bug — a pinned decision.** (But its sibling *was* a bug: a present-but-**empty** auth file read as "no records" — ✅ fixed 2026-10-22, see "An empty auth store" below.) `test_the_admin_still_gets_in_when_tokens_json_is_corrupt` asserts the raise deliberately: `ADMIN_TOKEN` is compared before the file is read, so the admin door survives a corrupt `tokens.json` and can repair it, while a user token "fails closed, never 'no tokens, no check'". I built the tolerant-read fix, saw that test flip from pass to fail, and reverted it in full rather than overriding a decision a test states. Revisiting it = one tolerant read in `resolve_token` + that test; `profiles.json` and `requests.json` want the same look (an empty-*looking* admin queue is the dangerous reading there).
- ~~#70 item 3: the admin can queue a top-up nothing can grant, holding a `MAX_PENDING` slot.~~ ✅ **Done 2026-10-21** — #70 and #68 are both fully closed. (Item 2 is ✅ done 2026-10-17.)
- ~~#42: a missing CV is caught late.~~ ✅ **Done 2026-10-22** (the index half is `/api/ready`'s).
- ~~#51 hygiene.~~ ✅ **Done 2026-10-22** (both Backend items).
- ~~Naming the failed step on `run_error`.~~ ✅ **Done 2026-10-21.**
- ~~The `cv_link` loop-back `{stage}` artifact.~~ ✅ **Done 2026-10-22.**
- ~~Self-export~~ ✅ **done 2026-10-22**; account-delete blocked (no per-profile collection, no `VectorStore.delete`).

Still blocked elsewhere: scope into the graph (§3) — **the carrier is now built, the consumers are not** — per-user `/search` within `profile`, `revision`/`max_revisions` on `gate_wait`, gate-2 answers' owner, the offline-fixture KB writes, the `llm`/`retrieval` log kinds.

---

# Orphan CV on upload — 2026-10-21

> One item, user's grant: fix bugs in this role's jurisdiction, code in
> `backend/` only. Code in `backend/cv_store.py` and `backend/jsonstore.py`.
> Full detail in `bugs.md`'s "2026-10-21 (orphan CV on upload)"; master entry
> `context/bugs_audit_fixed.md` #68 item 5 marked in place. **Not run:**
> uvicorn, a browser, the frontend.

**Why this one, not #51.** #51's key check looked like an allowance-loss bug
(it ignores `USE_OPENAI`), but `agents/base.py` skips keyless providers and
every lane in `config.FALLBACK_CHAINS` ends in Groq. So with `GROQ_API_KEY`
set, no charged run can fail for lack of a key; the check only refuses some
runs that would work. #68 item 5 left a user's CV, personal data, on disk where
nothing lists it and the owner's own delete can't reach it.

**#68 item 5 🟡, and a second edge in the same code.** `ingest_pending` moved
the PDF to `{sha}.pdf` before `_build_preview` and the index write, so a
failure in either left an unindexed file. Older pending uploads were also
evicted inside the `update_json` callback, *before* the write, so a failed
write left the unchanged index naming files already deleted.

**Flow now:**
```
tmp write → page count → parse → text/section checks → preview → summary
  └─ _commit_pending, under lock_for(index.json):
       confirmed identical? → return (stored file untouched)
       build new index in memory (evict older pending, add this one)
       created = target doesn't exist yet
       os.replace(tmp → {sha}.pdf)
       write_json(index)  ── fails → unlink target only if `created`, re-raise
       unlink evicted files
finally: unlink tmp (already moved on success)
```

- **Only remove what this upload created.** `{sha}.pdf` can already be an
  indexed CV with identical bytes. An unconditional cleanup would delete a
  real CV on a failed re-upload.
- **One lock, not a new one.** `jsonstore.lock_for` is a public name for the
  per-path lock `update_json` already holds, so `confirm`/`delete` (still on
  `update_json`) serialise against the commit. It's re-entrant.
- **File before index**, so `resolve_path` (which reads without the lock)
  never sees an indexed entry whose file hasn't landed yet.
- **Evictions after the write**, so a failure leaves index and disk agreeing.
  A failed unlink of an evicted file after a successful write would still
  surface as an error, as before. The index is already consistent by then.

**Checked:** 19 assertions in a scratch script against a tmp
`CV_UPLOADS_DIR`: preview failure, failed write on a new upload and on an
identical re-upload of a pending CV, the confirmed no-op, eviction, 24
concurrent uploads from one owner (disk == index, one pending entry), and
that `lock_for` is `update_json`'s lock.

**Suite:** `43 failed, 526 passed, 22 xfailed` → `44 failed, 526 passed, 21
xfailed`. The difference is exactly
`test_a_failure_after_the_file_is_stored_leaves_no_orphan` XPASSing.

**Owed (yours):** drop that test's strict xfail. Optionally add an
index-write twin: monkeypatch `cv_store.write_json` to raise, then assert no
new `.pdf` and the older pending file still on disk.

**What's left this role can build alone:** ~~#70 item 3~~ (✅ done), ~~#42~~
(✅ done), ~~#51 hygiene~~ (✅ done 2026-10-22 — the lane-aware rule landed;
it does change `test_live_mode_without_a_key_is_a_400_that_spends_nothing`,
which blanks only Groq), ~~naming the failed step on `run_error`~~ (✅ done, next section), the
`cv_link` loop-back artifact, self-export / account-delete.

---

# Failed step on `run_error` — 2026-10-21

> One item, user's grant: "fix the most critical bug listed". Code in
> `backend/runs/worker.py` and `backend/logplane.py`. Full detail in
> `bugs.md`'s "2026-10-21 (failed step on run_error)"; the ask is
> `bugs.md` "2026-10-14 (frontend, Rounds 27–42)" A2 (no master-file
> number). **Not run:** uvicorn, a browser, the frontend.

**Why this one.** Top of the ranked 🟡 list, and the top item this role can
build alone (#70 item 3 is rejectable by the admin, #42 now only hits the
admin's uncharged fallback, #51 only over-refuses).

**Logic.** `run_error` carried only `error`, so the frontend guessed the
failed step from whichever step it last saw "working", and had nothing to
mark for an error outside a step. It now carries `node`: the agent in flight,
or `null` when the failure came from the Supervisor, a gate, or graph build.

**Flow:**
```
_drive:          run["in_flight"] = None                      (resume starts at a gate)
_drain_stream:   supervisor update → node_start X → in_flight = X
                 any update from X (empty too)  → in_flight = None
                 graph.stream raises            → in_flight still X
_drive except:   run_error {error, node: in_flight}  +  log plane run_error {error, node}
```

**Decisions:**
- **Tracked live, not rebuilt from events.** The ask proposed "the last
  `node_start` without a `node_done`". A node that returns an empty update
  gets no `node_done`, so that rule would blame it for a later Supervisor
  failure. Clearing on *any* update from the node avoids that.
- **`null`, never `"gate"`/`"supervisor"`.** The frontend's step map holds
  agent names only. A non-agent name would match nothing there, and `null`
  honestly says "outside a step".
- **Not persisted.** `in_flight` is per-process state. `save_log` copies a
  fixed key list, so it never reaches disk.
- **Additive on the wire.** `RunLog`/`PipelineView` read only `error`/`final`
  today. Log plane: `node` added to `run_error`'s user-visible fields, the
  same kind of value `node_done` already shows.

**Checked:** 9 assertions over stub graphs (step raise, Supervisor raise,
empty-update step, build failure, clean run, the log-plane projection, not
persisted). Suite identical before and after (`44 failed, 526 passed, 21
xfailed`).

**Owed:** yours, a `StubGraph`-raises-in-a-node test in
`test_backend_api.py`. The frontend's: `settle()` marks `ev.node` failed when
the key is present, and keeps the "left working" inference only for older
logs.

---

# Admin top-up — 2026-10-21

> One item, user's grant: "fix the most critical bug in yellow range". Code in
> `backend/auth/store.py` only. Full detail in `bugs.md`'s "2026-10-21 (admin
> top-up)"; master entry `context/bugs_audit_fixed.md` #70 item 3 marked in
> place. **Not run:** uvicorn, a browser, the frontend.

**Why this one.** The last 🟡 here with a consequence past cosmetics: #42 now
only touches the admin's uncharged sample fallback, #51 is hygiene, and the
`cv_link` loop-back artifact is already worked around in the frontend.

**Logic.** A top-up is keyed on the caller's `token_id`. The admin's is the
sentinel `__admin__`, which has no `tokens.json` row, so `approve_request`
could only ever answer 409 — the row stayed pending, holding one of the 100
`MAX_PENDING` slots that anonymous signups also have to fit into. The admin's
allowance is `None` (unlimited), so there was nothing to grant anyway.

**Flow:**
```
POST /auth/request-more (admin bearer)
  → create_topup_request: token_id == ADMIN_TOKEN_ID → AuthError
  → routes/auth.py's existing `except store.AuthError` → 400
  (nothing written to requests.json, nothing audited)
```

**Decisions:**
- **In the store, not the route.** The rule is about what a valid request
  *is*, so every caller gets it — the same placement #68 item 2 chose for
  the identity rule in `create_request`.
- **Ahead of the note bound**, so a long note still gets the specific
  message instead of being refused for the wrong reason.
- **400, not 403.** The caller is authenticated and permitted on this route;
  the request is meaningless, not forbidden. 403 stays "not yours", and 401
  would log the admin out.
- **`approve_request`'s 409 stays** — still correct for a token deleted
  after its top-up was queued, and for rows already on disk.
- **No migration of stuck rows.** The admin rejects them (which frees the
  slot and, since 10-17, audits to the right account). A boot-time sweep
  would write to the audit trail on every start for one or two rows a click
  clears.

**Checked:** 14 assertions (admin refused and queues nothing, long note
included; a real account's top-up unchanged end to end; a seeded legacy admin
row still 409s on approve, rejects cleanly and frees the slot;
`profile_id_for_token` still maps the sentinel). `test_backend_api.py` +
`test_backend_auth.py` unchanged bar the pinning xfail flipping to XPASS.

**⚠️ Another lane, found while verifying:** a new `agents/contracts.py`
(15:57 today) added `check_schema`, which refuses a registered agent being
asked for a schema other than its own — `test_backend_mode_isolation.py` asks
`jd_analysis` for a local `Out`, so ~54 of its tests now fail with
`TypeError: Agent 'jd_analysis' answers with Requirements`. Unrelated to this
change; those tests need updating to the new contract.

**Owed (yours):** drop that test's strict xfail.

---

# CV preflight — 2026-10-22

> One item, user's grant: "fix the most critical bug in yellow range". Code in
> `backend/routes/runs.py`, `backend/vectorstore.py`, `backend/app.py`. Full
> detail in `bugs.md`'s "2026-10-22 (CV preflight)"; master entry
> `context/bugs_audit_fixed.md` #42 marked in place. **Not run:** uvicorn, a
> browser, the frontend.

**Why this one.** Of the 🟡s left here it is the only one that costs a user
something: #51 is hygiene, the `cv_link` loop-back artifact is already worked
around in the frontend, self-export is a feature.

**Logic.** `cv_link` is the sixth node. A CV file that isn't there, or a
profile index that isn't built, only surfaced there — after gate 1, gate 2 and
four live LLM calls — as a `run_error`, with the allowance already spent
(`refund_run` covers failure to *start* only).

**Flow:**
```
POST /api/runs
  resolve_path(owner) → the owner's confirmed CV, else admin ? sample : 409
  NEW  Path(cv_path).is_file()  → 503 "No CV is configured on the server."
  owner_lock → dedupe → consume_run → registry.start
lifespan (boot, once):
  ADMIN_TOKEN empty?                  → warn (pre-existing)
  NEW  CV_DEFAULT_PATH missing?       → warn (admin demo runs only)
  NEW  profile_index_problem()        → warn, naming unbuilt/empty/wrong-model
```

**Decisions:**
- **Checked on the resolved path, not `CV_DEFAULT_PATH`.** Since CV upload
  landed, a user's run uses their own file; the sample is the admin's
  fallback. Checking the resolved path covers both doors with one line.
- **503, never 401/403.** Nothing is wrong with the caller or the token — a
  401 would log them out and a 403 would read as "not yours".
- **`profile_index_problem()` bypasses `get_vector_store()` on purpose.** It
  opens Chroma directly and compares the stamped `embedding_model` with
  `config.EMBEDDING_MODEL`, so readiness costs no ~440MB model load. Asserted:
  <3s, `torch` never imported, the shared `_store` still None.
- **Read-only.** `get_collection`, never `get_or_create` — otherwise asking
  whether the index exists would create the empty collection it asks about.
  `VectorStore._collection` is the natural call but needs an embedder.
- **Fails open with a reason.** An unreadable index returns a sentence naming
  the exception rather than asserting a fault.
- **Warnings, not a boot refusal.** Auth, the KB and saved runs work without
  either, and a deploy builds the index after the API is up.
- **The index is NOT a 503 in `start_run`, though it belongs there by the same
  argument.** `tests/test_backend_api.py:175` points `config.VECTORDB_DIR` at
  an empty `tmp_path`, so it would 503 every run-start test. It is the natural
  content of `/api/ready` (§17), where the fixture change is deliberate rather
  than fallout.

**Checked:** 14 assertions over a real `TestClient` (admin 503 with no run
created, the user's 409 unchanged with allowance intact, a vanished confirmed
CV refused before `consume_run`, no refusal with the real sample present, the
probe's verdict/cost/purity on the real index, and an unbuilt directory
reported without being created). `test_backend_api.py` + `test_backend_auth.py`
identical before and after — nothing covered #42.

**Owed (yours):** a 503 test for the admin with no sample, and one asserting
`profile_index_problem()` is not None for a `tmp_path` index while
`backend.vectorstore._store` stays None. **Deployment:** the sample CV and the
built index are now named in the boot log; the runbook should say a deploy
supplies both.

---

# Hygiene: KB counts, live keys — 2026-10-22

> One item, user's grant: "fix the most critical bug in yellow range". Code in
> `backend/routes/kb.py` and `backend/routes/runs.py`. Full detail in
> `bugs.md`'s "2026-10-22 (hygiene: KB counts, live keys)"; master entry
> `context/bugs_audit_fixed.md` #51 marked in place. **Not run:** uvicorn, a
> browser, the frontend.

**Why this one.** What remained here was #51, the `cv_link` loop-back
`{stage}` artifact (already worked around in `applyEvent`; the clean fix is a
wire shape the frontend has to want) and self-export (a feature). Both #51
items are wrong answers a user can see.

**Logic, item 1.** `do_not_claim.json` is a wrapper object, so `len()` on it
counted its three keys: the browser said "3 records" for 22 forbidden claims,
while `kb_file` sent the wrapper itself as a single record. Two readers of one
file, two different wrong answers.

**Logic, item 2.** The live check was `not config.GROQ_API_KEY`. Every lane
ends in Groq today, so it was sufficient — but it refused a live run that any
other keyed provider could serve, and it stops being sufficient the moment a
lane's tail changes.

**Flow:**
```
GET /api/kb        → _record_count → _records ─┐ one reader,
GET /api/kb/{s}/{f} ───────────────→ _records ─┘ one answer
   _records: manual_entries → visible_entries(scope)   (owner scope, unchanged)
             dict           → first list value, else [dict]
             list           → as-is

POST /api/runs (mode=live)
   _live_key_problem(): for each config.PIPELINE_AGENTS
       any entry in fallback_chain_for(agent) whose PROVIDER_KEY is set?
   none for some agent → 400 naming those agents + the env vars that fix them
```

**Decisions:**
- **One `_records()` for both routes.** A count that disagrees with its own
  listing is the `AGENTS`/`GATES`/`STUB_NODES` drift again; this makes them
  the same read by construction.
- **A wrapper's scalars are metadata, not records.** `_comment`/`version`
  describe the list; a dict with no list at all stays one record.
- **The lane question, not `required_keys_for_mode()`** (which the entry
  proposed): its live branch demands every agent's *primary* key — all four
  providers — refusing runs the fallbacks exist to serve; and it returns `[]`
  when `USE_FAKE_LLM` is the process default, dropping the check for exactly
  the offline-default server taking one live run.
- **`config` attributes, not `os.getenv`** — what `base._has_key` reads, and
  where a key can be overridden in-process.
- **An unknown provider counts as keyless**, so a config typo is a 400 before
  the charge instead of a `ValueError` mid-run.
- **Env var names only, never values**, in the message. Asserted.

**Checked:** 30 assertions (wrapper counts 22 and lists the claims, plain
lists unchanged, listless dict, empty file, and count == len(records) for
every real KB file; keys: all / none / Groq-only / Groq-missing-others-present
/ Gemini-only / `USE_OPENAI`), plus a `TestClient` run with all five keys
blanked: 400, allowance still 2, no run created.

**One test moves, deliberately.**
`test_live_mode_without_a_key_is_a_400_that_spends_nothing` blanks only
`config.GROQ_API_KEY` while this machine holds three other provider keys, so
the run it expects refused is now genuinely servable and starts. Checked
against the 10-17 lesson before keeping it: the *decision* that test states —
an unservable live run is a 400 that spends nothing — still holds exactly
(re-verified over HTTP). Only its premise predates the four-provider lanes
(config dates that allocation 2026-10-19). On a Groq-only machine it still
passes.

**Owed (yours):** blank all five provider keys in that test instead of Groq
alone, and ideally assert that with only `CEREBRAS_API_KEY` set a live start
is *not* refused. **Frontend:** `KnowledgeBase.jsx:32`'s
`records[0].forbidden_claims` unwrap is now dead code and its comment stale —
claim boundaries arrive as 22 records.

**What is left in this lane:** ~~the `cv_link` loop-back `{stage}` artifact~~
(✅ done 2026-10-22) and ~~self-export~~ (✅ done) — leaving **account-delete**,
which is blocked on the KB lane, and the A3 cited-records robustness ask.
Everything else is blocked on another lane.

---

# Scope into the graph — 2026-10-22

> The design's §3, backend half. **Written outside `backend/` on an explicit
> grant** (the user approved exactly two carrier edits): `config.py` and
> `state/state.py`, plus `backend/runs/worker.py`. Full detail in `bugs.md`'s
> "2026-10-22 (scope into the graph)". **Not run:** uvicorn, a browser, the
> frontend.

**Why it needed a grant.** This is the last 🔴, and the backend's own part of
it is three lines — but neither carrier could live in `backend/`. A ContextVar
here would have to be imported by `agents/` and `vectordb/`, reversing the
"nothing imports `backend/`" rule this package is built on (and risking an
import cycle: `worker` imports `agents.supervisor`). `GraphState` is
`state/state.py`, which this role explicitly drives as a black box. Pydantic
ignores unknown fields, so passing `profile_id=` without that field would have
been silently dropped — bug #72's shape exactly.

**Logic.** Every run in this process used to be indistinguishable to the graph:
nothing below `worker` could tell whose data it was allowed to touch, so the
retriever, the plan cache, the export folder and `save_gap_answers` all resolve
globally. §3's answer is that the run *carries* its account, and the backend's
job is to set it.

**Flow:**
```
POST /api/runs → registry.start stamps run["owner"] = scope.profile_id
worker._drive (the run's own thread, before the graph is built):
    config.set_fake_llm(...)            # pre-existing
    config.set_profile_id(run["owner"]) # §3, inside the try
run_worker:  GraphState(..., profile_id=run["owner"])
node (inline OR on a copy_context() pool thread):
    config.current_profile_id()  → this run's account, never another's
    config.require_profile_id()  → same, but raises when unscoped
```

**Decisions:**
- **A ContextVar, beside `set_fake_llm`, for the proven reason.** LangGraph
  runs a node inline only while it is the single runnable task; any parallel
  step goes to a `ContextThreadPoolExecutor` via `copy_context()`. A module
  global or `threading.local` would leak one user's scope into another's node
  the moment two runs overlap. Re-proved here, not assumed: two runs held
  inside a real graph node by a `threading.Barrier` each read their own
  account.
- **A bare `profile_id`, not `deps.Scope`.** `Scope` carries a role, and
  nothing in the graph may depend on the caller being an admin — an admin's
  run reads the admin's own vault like everyone else's. Keeping the role out
  means there is no path for a privileged caller to widen what a node sees.
- **Both a ContextVar and a state field, deliberately.** The ContextVar is
  what nodes read (it reaches code that never receives state, like the
  retriever); the field is what the checkpointer persists, so a run resumed in
  a new process can restore its scope from its own state instead of guessing.
- **`require_profile_id()` raises, and that is the point.** The fallback to
  "no scope" is not a harmless default — it is the shared, everyone's-data
  behaviour §3 exists to end. Consumers that reach user data call this one;
  `current_profile_id()` stays for code that may legitimately run unscoped (a
  bare CLI driver).
- **Bound inside `_drive`'s `try`,** so an owner-less run is a visible
  `run_error` rather than a silently global run or a dead thread, and bound in
  `_drive` rather than in `run_worker`/`run_worker_resume` so a resumed run is
  scoped identically to a fresh one.

**A real bug this surfaced, fixed here:** `_log_run`'s docstring promises it
never raises, but it read `run["owner"]` in its own argument list. On the
error path that made the failure handler itself throw, so the `run_error` it
was reporting was lost and the exception escaped the worker. Now `.get()` —
a log line that cannot name its account is still worth writing; a run that
cannot report why it failed is not.

**What is NOT built, and is not this lane's:** every consumer still resolves
globally — the retriever's collection, `save_gap_answers`/`profile_commit`,
the plan-cache folder, the snapshot folder, the export folder. Until they call
`require_profile_id()`, this change isolates nothing by itself; it is the
carrier they were blocked on. §3's vault-storage bullets (one checkpointer per
vault, the run trail under the vault, `list_for` reading only the caller's) are
untouched — a storage migration with its own blast radius.

**Suite:** `test_backend_api.py` + `test_backend_auth.py` identical before and
after (`29 failed, 423 passed, 19 xfailed`). `test_routing.py` — the one file
that enumerates `GraphState` — was still running after 40 minutes here, so
only its `GraphState` guards were run directly (below); its total is not
reported rather than guessed.

**Owed (yours), one required by a guard working as designed:**
`tests/test_routing.py:test_the_artifact_fixture_covers_every_field` pins
"a new `GraphState` field has to be added to `_artifacts()`", so this change
fails it until `_artifacts()` gains `"profile_id": "p-abc12345"` beside its
`"run_id"` — which then carries the field through that file's checkpoint and
snapshot tests (`NOT_ARTIFACTS` would skip them, so not that). **That guard was
already red before this change**, for `prompt_versions` — another lane's field,
added to `GraphState` and never registered. Measured, not assumed: the fixture
is missing `{profile_id, prompt_versions}` now, and `{prompt_versions}` with
mine excluded. The serde round
trip is already verified directly: `make_serde()` keeps `profile_id`, and
`state_types()` still resolves 41 types.

**Also owed outside this lane:** the CLI drivers (`scripts/run_graph.py`,
`run_gated_graph.py`) set no scope, so a CLI run is unscoped and will raise at
the first consumer that requires one — §3 already calls for a `--profile` flag
there.

---

# A node that changed nothing — 2026-10-22

> One item, user's grant: "fix the next most critical bug, irrespective of
> colour". Code in `backend/runs/worker.py` only. Full detail in `bugs.md`'s
> "2026-10-22 (a node that changed nothing)". **Not run:** uvicorn, a browser,
> the frontend.

**Why this one, and what it displaced.** The two 🟠s above it are not this
package's: `revision`/`max_revisions` on `gate_wait` **needs no backend code**
— `utils/human_gate.py:226-227` puts both on the payload and
`_PAYLOAD_NOT_PASSED` excludes neither, so `_park` already relays them
(re-verified in the tree today; the row is waiting on the frontend and
`StubGraph`) — and `/search` scoping plus the `llm`/`retrieval` log kinds need
other lanes' data work.

**Logic.** Every node returns its `stage`. A node that ran but produced nothing
new returns *only* that — `cv_link` skipping a re-read of the same CV after a
gate-3 reject, `profile_enrich` with no answers. `_drain` published that dict
as the node's artifact, so a full CV read was replaced on screen by an empty
one, and the frontend wrote a `cv_link`-shaped workaround.

**Flow:**
```
update from node → strip `messages` → set(artifact) ⊆ {"stage"} ?
   yes → node_done {node, stub, unchanged: true}          (no artifact key)
   no  → cv_link? scrub cv_tree, add match_counts
         node_done {node, stub, artifact, …}
either way → duration logged to the run kind, as before
```

**Decisions:**
- **Still a `node_done`.** `node_start` already fired; without the done the
  step pulses "working" forever.
- **Generic, not another `cv_link` case.** `profile_enrich` has the same shape.
  A per-node rule in a fourth place is how `AGENTS`/`GATES`/`STUB_NODES` drifted
  from the graph three times.
- **Absent key, not `artifact: null`** — null could mean "the node returned
  null"; absence cannot.
- **Checked against the live frontend before moving the wire:** `rereadSkipped`
  still fires with the key absent (cv_link keeps its earlier read),
  `StatePanel` hides a card whose artifact is falsy instead of rendering
  `{stage: "document"}`, and `renderArtifact` guards falsy already. The
  frontend can drop its special case; nothing breaks if it doesn't.

**Checked:** 14 assertions — the skipped re-read and the no-answers enrich both
give `unchanged: true` with no artifact; a real `cv_link` result keeps its
artifact, `match_counts` and scrubbed tree; a stub with only a stage is still
flagged a stub; an artifact that merely contains `stage` is still a result; an
empty update still emits nothing; `messages`-only counts as no change. Backend
suites identical (`29 failed, 423 passed, 19 xfailed`).

**Owed (yours):** a `StubGraph` loop-back case asserting the second `cv_link`
`node_done` has `unchanged: true` and no `artifact`. **Frontend:**
`PipelineView.jsx:75` can become "keep the previous artifact when
`ev.unchanged`".

---

# Account export — 2026-10-22

> One item, user's grant: "fix the next most critical bug, irrespective of
> colour". New `backend/routes/me.py`, helpers in `cv_store.py` and
> `runs/registry.py`, registered in `app.py`, one `logplane.py` allowlist
> entry. Full detail in `bugs.md`'s "2026-10-22 (account export)".
> **Not run:** uvicorn, a browser, the frontend.

**Why this, and why only half of §6.** It is the last thing in this lane a
user simply *cannot do*: get their own data out. The delete half is a
**finding, not a deferral** — §6 step 3 says "drop its collection", but there
are no per-profile collections and `vectordb/store.py` has no `delete`
(`bug#30`'s open half). Deleting tokens, files and the account row while the
account's embedded evidence stayed searchable in the shared `profile`
collection would be a deletion that lies, so it waits for the KB lane.

**Flow:**
```
GET /api/me/export  (Caller + Identity)
  own = Scope(scope.profile_id, "user")        ← an admin exports ITSELF, not everyone
  account.json          identity + counts, never a token
  profile_entries.json  visible_entries(own)
  cv/index.json + cv/*.pdf   cv_store.export_index / export_files (index-driven)
  runs/<id>.json        registry.records_for_owner(profile_id)   (full trails)
  documents/*           each record's current_export(), via contained_path(OUTPUTS_DIR, …)
  logs.json             logplane.for_user(profile_id)            (projected)
  → 413 if the running total passes MAX_EXPORT_BYTES (64 MB)
  → audit "account_exported" {bytes}
```

**Decisions:**
- **Role "user" over the caller's own id.** `visible_entries` and
  `registry.owns()` widen for an admin, which is right for an admin tool and
  wrong for "export my account". Same instrument as `routes/admin.py`, aimed
  the other way.
- **`records_for_owner`, a new registry function, not `list_for`.** One
  answers "what may this caller see" (summaries, widened for admin); the
  export needs "what does this account own" (full trails). Reads through
  `load_log`, so a damaged file is skipped exactly as everywhere else.
- **An ownerless run log is never exported** — it belongs to no resolvable
  account, and exporting it would hand it to whoever asked first.
- **Saved CVs come from each run's `current_export()`**, not from guessing the
  owner's folder name under `OUTPUTS_DIR` (which `utils/export.py` slugs), and
  every path still goes through `contained_path()`.
- **`export_files` walks the index, not the directory**, so a stray file in
  the folder cannot leave in an export.
- **A ceiling, not an unbounded in-memory zip** — 64 MB → 413.
- **The audit line carries `bytes` only.** Naming the contents would copy this
  account's data into the log plane, which its own rule forbids.

**Checked:** 28 assertions over a real `TestClient` with two accounts plus the
admin — the archive's shape and filename, Alice's own data present, **Bob's
entry text, Bob's document and the ownerless entry all absent**, no bearer
token anywhere in the bytes, exactly one CV PDF, the admin's self-export empty
of user data, damaged/ownerless logs skipped, the audit entry visible with
`bytes` only, 401 unauthenticated, and 413 under a lowered ceiling. Backend
suites identical (`29 failed, 423 passed, 19 xfailed`).

**Owed (yours):** add `("GET", "/api/me/export")` to `USER_ROUTES` — though
both route-table tests are already failing for an unrelated reason (this
FastAPI version wraps included routers in `_IncludedRouter`, so the test's own
collector returns an empty set: `bug#84`'s version drift). The route is
registered — `app.openapi()` lists it among 28 API paths. **Frontend:** a
"Download my data" button on the Account page.

---

# An empty auth store — 2026-10-22

> One item, user's grant: "fix the next most critical bug, irrespective of
> colour". Code in `backend/jsonstore.py`, `backend/auth/store.py`,
> `backend/auth/profiles.py`. Full detail in `bugs.md`'s "2026-10-22 (an empty
> auth store)". **Not run:** uvicorn, a browser, the frontend.

**Why this one.** Everything still on the ranked list belongs to another lane,
checked in the tree rather than taken from the rows: A3's producer
(`final_changes`) is `utils/human_gate.py`; `revision`/`max_revisions` is
already relayed; `/search` needs vector metadata; `corrections.json` needs a
move out of this package; §6's delete needs a `VectorStore.delete` that does
not exist. What remained in `backend/` was the sibling of the 10-17 finding —
flagged then as "wants the same look", never logged.

**Logic.** `read_json` answers `[]` for a file that is absent, empty or
whitespace. For a cache that is correct. In the three auth stores "no records"
is a *decision*: no account holds that name, no token is valid, no request is
waiting. Reproduced before writing anything:

```
empty profiles.json → profile_for("Alice") is None        ("no such account")
                    → create_profile("Alice") succeeds     (a SECOND profile for a held name)
                    → next write leaves only that row      (every other mapping gone)
empty requests.json → the admin queue reads empty; a re-queue overwrites the history
empty tokens.json   → a valid credential resolves to None
```
Two harms: the answers are wrong, and since every writer is a
read-modify-write, the empty read *becomes* the next write — one transient
empty file permanently destroys the store. `write_json` is atomic, so an empty
auth file is never normal; it was damage being read as consent.

**Flow:**
```
read_records(path):
  absent            → []            (a genuine first run)
  empty/whitespace  → ValueError    (damage, never "no records")
  not a list        → ValueError
  corrupt           → JSONDecodeError, unchanged  ← DEC-102's pinned behaviour
  otherwise         → the rows
```

**Decisions:**
- **The corrupt path is deliberately untouched.**
  `test_the_admin_still_gets_in_when_tokens_json_is_corrupt` pins both that a
  user token raises and that `ADMIN_TOKEN` is compared *before* the read, so
  the admin can sign in and repair the file. Re-checked for the empty case too.
  This is the same test that made me revert a tolerant-read fix on 10-17 — this
  change runs in the direction that decision asks for, not against it.
- **Absent still means empty**, so a first run (no files) works end to end.
- **A real `[]` on disk stays valid** — a store deliberately emptied.
- **Scoped to the auth stores only.** Run logs have their own rule (a damaged
  log is an unknown run, 404), and `manual_entries.json` may legitimately be
  empty.
- **Raise, never repair.** The caller cannot know what the file held; the one
  guarantee worth making is that nothing writes over it. Asserted: after every
  refusal the file is byte-for-byte unchanged.

**Checked:** 26 assertions — `read_records` across absent/rows/empty/
whitespace/corrupt/non-list/real-`[]`; the reproduced `profiles.json` damage
now refused at all four doors with the file intact and a repaired file working;
`tokens.json` corrupt **and** empty both leaving the admin door open while a
user token raises; an empty `requests.json` refusing the queue and a re-queue;
and a clean first run. Backend suites identical (`29 failed, 423 passed, 19
xfailed`), the pinned test included.

**Owed (yours):** a per-store test that a present-but-empty file raises and
leaves the file unchanged — the twin of the corrupt-tokens test.

---

# Handed to other roles — 2026-10-22 (nothing in their code edited)

> Written into each role's own file the same day, from this session's nine
> changes. Tests and live runs are the owner's and are deliberately not listed
> as asks here.

| role | file | item |
|---|---|---|
| Frontend | `frontend/bugs.md` → "2026-10-22 (backend)" | A: `run_error.node`; `node_done.unchanged` (no `artifact`); `GET /api/me/export`; claim-boundaries now 22 records (its unwrap branch is dead). B: **`gate_wait` already carries `revision`/`max_revisions`** — B1 is not blocked on us. C: new `503 "No CV is configured on the server."` on `POST /runs`, and the live-mode `400` text changed |
| Agents + Orchestration | `context_Agents+Orchestration.md` → "From Backend API + Auth — 2026-10-22" | 🔴 the scope carrier exists (`config.require_profile_id()`); the **consumers** (retriever, `save_gap_answers`, plan cache, snapshots, exports) are yours, and nothing is isolated until they adopt it. 🟡 A3's `evidence` belongs on `final_changes` (`utils/human_gate.py`), not here. 🟡 the CLI drivers need `--profile` |
| KB + Semantic Search + RAG | `context_KB+Semantic+RAG.md` | 🟠 `VectorStore` has **no `delete`** — this is what blocks §6's account-delete half and #30's cleanup. 🟠 per-profile collections are the other half of §3/§13. ⚪ `profile_index_problem()` reads your `embedding_model` stamp at boot |
| Data Storage + Handling | `context_Data Storage+Handling.md` | `save_gap_answers` writes no `owner`, so a user's gate-2 answers are now **also missing from their own export**; one stamped field closes that and the Build-Profile gap together. `corrections.json` still unlocked (#35) |
| Pipeline Infra + Config + Testing | `context_Pipeline Infra+Config+Testing.md` | `config.py` gained `set_profile_id`/`current_profile_id`/`require_profile_id` and `state/state.py` gained `profile_id`, **both on the owner's explicit grant**. `/api/ready` should carry `profile_index_problem()` (kept out of `start_run` on purpose). `required_keys_for_mode()` was considered and not used for the live key check, with the reason |
| Eval / Learning loop | — | no change needed |

---

# Session 2026-10-21 → 10-22 — what changed, in order

> Nine changes, each its own section above and its own dated entry in
> `bugs.md`. Written under the owner's backend-only grant, except where noted.
> **Not run anywhere in this session:** uvicorn, a browser, the frontend.
> Verification was `py_compile` + `import backend.app`, a scratch script per
> change (14-30 assertions each), and `test_backend_api.py` +
> `test_backend_auth.py` before and after every one.

| # | Change | Entry | Suite effect |
|---|---|---|---|
| 1 | bug#68.5 — a failed CV upload left an orphan PDF; preview before the move, commit under the index lock | "Orphan CV on upload" | its strict xfail XPASSes |
| 2 | A2 — `run_error` names the step in flight (`node`), tracked live, `null` outside a step | "Failed step on `run_error`" | unchanged |
| 3 | bug#70.3 — the admin can no longer queue a top-up nothing could grant | "Admin top-up" | its strict xfail XPASSes |
| 4 | bug#42 — a 503 before the allowance when no CV file; boot warnings for sample + index | "CV preflight" | unchanged (nothing covered it) |
| 5 | bug#51 — one reader for KB records; the live key check asks the lane question | "Hygiene: KB counts, live keys" | one test moves, deliberately |
| 6 | design §3 (backend half) — a run carries its account: `config.set_profile_id` + `GraphState.profile_id` | "Scope into the graph" | `_artifacts()` guard needs the field |
| 7 | "Round 8-10" §6 — a no-change node says `unchanged: true` and sends no artifact | "A node that changed nothing" | unchanged |
| 8 | design §6 (export half) — `GET /api/me/export`; delete stays blocked | "Account export" | unchanged |
| 9 | **new, found while ranking** — a present-but-empty auth store read as "no records" | "An empty auth store" | unchanged |

**Two rows in the ranked list were wrong, and were corrected rather than
worked around:** the `gate_wait` round number is already relayed (so the
frontend is not waiting on us), and A3's producer is `utils/human_gate.py`.
Both are recorded in `bugs.md`'s index and in the lanes' own files.

**Scope note.** Items 6 touched `config.py` and `state/state.py` — outside
this package — on an **explicit grant asked for and given** when it became
clear neither carrier could live in `backend/` without reversing the
"nothing imports `backend/`" rule. Everything else stayed inside `backend/`.

**Where this leaves the role:** no item in `bugs.md`'s ranked index can now be
closed by this package alone. The handoffs that unblock the rest are in the
table above this section, written into each lane's own file on 10-22.

