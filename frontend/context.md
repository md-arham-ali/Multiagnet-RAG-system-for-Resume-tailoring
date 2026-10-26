# Frontend — Architecture & Decisions

> Companion to root `context/context.md`, scoped to `frontend/`. Bugs/open work live in `frontend/bugs.md` ("Open work, by criticality" at top — the single source; this file doesn't copy that list). Backend owes-us notes: `backend/bugs.md` (through Round 26) and `backend/context.md` → "What the frontend needs from the backend" (Rounds 27–38, 2026-10-13) plus "2026-10-14 (frontend, Rounds 27–42)". Last updated 2026-10-15 (Round 43). (Compacted 2026-10-14 — content unchanged, prose tightened.)

## Change log (condensed)

Everything in `frontend/src` since 2026-09-24, one line per round. All of Rounds 4,5,8–15,17–42 **compile** (last full build 2026-10-14, 63 modules, first try); **Round 43 (2026-10-15) is not compiled yet**; **none has run in a browser** — the single biggest open risk (see "Local environment note"). Checked each round by diff-against-backup + bracket/import checks; Rounds 19,24,29–38 also had a Python logic mock-up.

- 4,5 (2026-09-24): last code before the 09-24 baseline. 6,7,11: audits/scoping only, no code.
- 8 (2026-10-09): gate-2 answer form. 9: `cv_link`→"CV Reader" label. 10: single in-flight guard on Start. 12: CV upload, frontend half. 13: gate-4 final review (Agents session). 14: fit-review's stray "Fact check" block removed. 15: final-review edit guarded (leave-page prompt, Cancel confirm).
- 16 (2026-10-10): `scripts/dev.py` launcher — Pipeline+Infra lane, not this one.
- 17–26 (2026-10-10, one fix/request): 17 gate form retires after any answer (409); 18 honest reject note at final review; 19 reopened gate shows its round, browser-counted; 20 `CvStrip` never deletes current CV; 21 finished/stopped/failed told apart; 22 "Request edit"→"Approve with a note" at gates 1–3; 23 reject note names the redo limit; 24 nginx 502 reads as "cannot reach backend"; 25 feedback label says where it goes; 26 CV-editor text says what's kept.
- 27–42 (2026-10-10 to 10-14 — table below has files/backend-deps): 27 evidence labelled "shared sample, not yours"; 28 no screen calls shared pool "yours", gate2/BuildProfile say who can read; 29 `client_request_id` per start not per click; 30 logout/new-run confirm before dropping unsaved CV edit; 31 gate-answer 404 retires form, run marked unfinishable; 32 run ending mid-edit keeps the edit on screen w/ Copy; 33 agent graph shows stopped/failed instead of pulsing; 34 feedback box caps at 2,000 chars w/ counter; 35 evidence score clamped 0–100; 36 final output gets Download .md/.txt + "saved on server" + unapproved-draft label; 37 final-review diff grouped by section, was/now, word-highlighted, cites records; 38 CV editor gets Preview/Reset-to-draft/char count; 39 Account's "request more runs" calls `/auth/request-more`; 40 Build Profile wording follows owner scope (user vs admin); 41 (10-14) gate-2 answer boxes get a char counter; 42 (10-14) dead token noticed — `refresh()` ends session on 401, dropped SSE probes once.
- 43 (2026-10-15): Resume — a run the server restarted under (gate 404 or dropped stream) picks back up at its review from Pipeline or Runs (`interrupted` row); same-run unsaved final edit survives. Not compiled. Detail `bugs.md` Round 43.
- 44 (2026-10-24): first full browser pass (Docker build 63 modules — Round 43 now compiles; offline run `d0ce5fc6` through every gate, Resume after a restart, download). Fixed `GAP_DEMO_NOTE` (N2) and `FINAL_REJECT_NOTE`; backend `/api/config` lists all providers. New: phone layout, empty gate-4 reject, no entry delete, raw names in Settings. Detail `bugs.md` Round 44, `context/testing/frontend/`.

**Backend asks for Rounds 27–42** are in `backend/bugs.md` → "2026-10-14 (frontend, Rounds 27–42)" (+3 criticality-index rows): A = asks (`final` read from `run_error` too for download/delete/`list_for`; failed-step name on `run_error`; optionally record text on `changes`; clamped scores); B = behaviour relied on; D = checked status of earlier asks.

**Restart survival landed backend-side (found 2026-10-14):** a parked run's log now saves at gate-open, `POST /runs/{id}/resume` exists, `list_for` marks such a run `interrupted`. So Round 31's "can't be finished" wording is now **false** for `GATE_GONE`/`RUN_GONE`/`STREAM_LOST` — they should say "reopen it from Runs" once a frontend Resume action exists: find the run via `GET /runs`→`interrupted`, `POST …/resume` (409s if another run is active), reopen the stream. No backend change needed. Would close items 10, 21, part of 9. **✅ Built 2026-10-15 (Round 43)** exactly this way — see "Resume (Round 43)" under Gates; item 9's central-401 case still needs the localStorage draft. Saved-CV routes (`list_for` review/saved, `DELETE …/document`) also unblock item 22.

**The backend moved under this folder twice, in parallel sessions:**
- 2026-10-10: CV routes; `run_error` carries `final`; a second gate answer gets 409; per-owner start lock + `client_request_id` dedupe; caps on `feedback`/`gap_answers`; `cv_link` event scrubbed. (What we owed back: `backend/bugs.md` → "2026-10-10 (frontend, Rounds 17–26)", `backend/context.md` for 27–38.)
- 2026-10-10 to 10-13 (identity/scope, full rationale `backend/context.md` → "⧉ IDENTITY, SCOPE & THE LOG PLANE"): account identity is now `profile_id` not `token_id` — a re-issued token resolves to the same account/runs/CV. `GET /api/auth/me` and `POST /api/auth/login` now also return `profile_id` (additive, unused). `GET`/`PUT /api/profile/entries` (+ KB mirror) are now owner-scoped — **retrieval is untouched**, `/search` and run evidence still read the one shared `profile` collection unfiltered. New read-only, unused today: `GET /api/logs/mine`, admin `GET /api/admin/logs` / `.../users/{id}/{profile,cv}`.
  - Two asks landed: (1) `Account.jsx`'s "request more runs" must call authenticated `POST /api/auth/request-more {note?}` (resolves account from bearer token) instead of free-text `requestAccess()`, which used to mint a second unrelated token — fixed Round 39. Correction: `approve_request`→`create_profile` now 409s a duplicate-name signup, so no second token is minted either way, but the old button still told the user it was sent. (2) Build Profile wording narrowed: lists/edits are per-account now, but retrieval/`/search` are still shared — fixed Round 40 (`BUILD_PROFILE_*`, `GAP_HELP`).

## Fixes table, Rounds 27–42

| Round | Fix | Files | Backend dependency |
|---|---|---|---|
| 27 | Evidence labelled "shared sample profile, not your own" (start screen, run line, final review) | `PipelineView`, `GateScreen`, `copy.js` | Retrieval is one shared collection; drop `EVIDENCE_SHARED*` when P3–P4 (vault) lands |
| 28 | No screen calls shared pool "your profile"; gate2/BuildProfile say who can read/edit | `copy.js`, `StatePanel`, `BuildProfile`, `PreviewPanel` | Build Profile half corrected in Round 40 once owner scope landed |
| 29 | `client_request_id` per start, not per click | `PipelineView` | Backend dedupe ignores body, remembers only started runs |
| 30 | Logout / new-run confirm before dropping unsaved CV edit | `unsavedEdit.js` (new), `GateScreen`, `Header`, `PipelineView`, `copy.js` | none |
| 31 | Gate-answer 404 retires form: run lost on server | `GateScreen`, `PipelineView`, `copy.js` | 404 means only "not held"; needs a probe route or Resume |
| 32 | Run ending mid-edit keeps edit + Copy, still guarded | `unsavedEdit.js` (`useUnsavedEdit`), `GateScreen`, `PipelineView`, `copy.js` | none |
| 33 | Agent graph shows stopped/failed on ended run | `AgentNode`, `PipelineView` | Name the failed step on `run_error` |
| 34 | Feedback box caps at 2,000 chars, with counter | `GateScreen`, `copy.js` | `feedback` cap |
| 35 | Evidence score clamped 0–100 | `SearchPanel` | Optional: clamp server-side too |
| 36 | Download .md/.txt, "saved on server as…", unapproved-draft label | `FinalOutput`, `copy.js` | `final.export`; doc route must also read `run_error`'s `final` (item 26) |
| 37 | Readable final-review diff: grouped, was/now, highlighted, cited records | `ChangeList` (new), `GateScreen`, `PipelineView`, `copy.js` | `changes[]`/`evidence` shapes; record text on `changes` |
| 38 | CV editor: Preview, Reset-to-draft, char count | `MarkdownPreview` (new), `GateScreen`, `copy.js` | 50,000 cap and `render_markdown` forms |
| 39 | Account top-up calls `/auth/request-more`; honest wording; identity re-read on open; Pipeline 403→Account | `AuthContext`, `Account`, `PipelineView`, `copy.js` | Uses existing `request_more` route |
| 40 | Build Profile wording follows owner scope; gate-2 answers note; plain 403 sentence | `copy.js`, `BuildProfile`, `PreviewPanel` | `visible_entries` (own / all-for-admin / ownerless-admin-only) + unscoped index |
| 41 | Gate-2 answer boxes get a char counter | `GateScreen` | `GapText` ≤ 2,000; keep in sync with `GAP_ANSWER_MAX` |
| 42 | Dead token noticed: `refresh()` ends session on 401; dropped SSE probes once | `AuthContext`, `PipelineView` | Relies on 401 meaning only "missing/unknown token" |
| 43 | Resume after a restart/dropped stream, from Pipeline or Runs; Round 31 wording corrected | `PipelineView`, `GateScreen`, `RunsView`, `App`, `copy.js` | `POST /runs/{id}/resume`, `GET /runs` `interrupted`, full-trail replay on the events route |

Closed since by backend's identity/scope work: items 27, 28 (above). Same work also closed item 7 (re-issued token keeps CV) and half of item 6.

## Session record, 2026-10-10 to 10-14 (Frontend lane)

One session, grant to edit `frontend/` only, later extended to `backend/context.md`/`backend/bugs.md` for the asks.

- **Builds:** 2026-10-10 Rounds 4–26 compiled first try (60 modules). 2026-10-14 Rounds 27–40 (63 modules, 3 new files), then 41, 42 each in their own later build same day — all first try, no code change. Docker Desktop needs `open -a Docker` each day.
- **New files:** `unsavedEdit.js`, `ChangeList.jsx`, `MarkdownPreview.jsx`.
- **Docs:** 10-12 reconciled context.md/bugs.md/design.md/DELIVERABLES.md against code. 10-13: wrote the backend "What the frontend needs" section, found items 27/28 opened + item 7 closed, fixed 9 stale spots in this file. 10-14: wrote backend's Round-27–42 ask section + found restart survival.
- **Re-ranks on evidence:** item 11 (revoked token) demoted 10-12 — nothing can revoke a token; item 10 promoted above item-9's sub-case — restarts are frequent; items 27/28 promoted to top 10-13 — backend's identity work.
- **Corrections caught in-session:** an over-claiming `charCount` sentence (Round 34); a wrong "stream reconnects" verify-step (Round 42); a backend note claiming a second token is minted — code actually 409s.
- **Open at session end:** item 1 (browser pass — left to live testing); the Resume action (Round 31 wording now false — built next session, Round 43); item 22 (saved CVs on Runs/Account, now buildable); backend asks A1–A4 in `backend/bugs.md`.

## Session record, 2026-10-15 (Frontend lane)

Grant: "fix the bug, one at a time" in `frontend/` (+ this file and `bugs.md`).
- **Read-in:** root `context/context.md`, `learnings.md`, this file, `bugs.md` (incl. the backend's 10-15 handoff note).
- **Round 43 — Resume** (items 10, 21 frontend half; full detail + 5 verify steps at the end of `bugs.md`). Chosen first because Round 31's on-screen sentence had become false and restarts are frequent. Files: `PipelineView`, `GateScreen`, `RunsView`, `App`, `copy.js`. Checked by diff vs scratchpad backup (`round43/`, not kept), bracket balance, import/caller greps. **Not compiled, not run** — awaiting a yes to `docker compose build frontend`.
- **Drift found, not fixed (docs only):** (a) `bugs.md` top list marks items 18, 20, 22, 26 ✅ though only the backend half is built — the frontend wiring is still open (21 and 10 now genuinely wired); (b) this file's "Open bugs" copy of the master list still shows #29 (gap form) and #41 (`cv_link` invisible) open, though Rounds 8/9 closed their frontend halves — reconcile with `context/bugs_audit_fixed.md`.
- **Handed to other lanes (written 2026-10-15):** `backend/bugs.md` → "2026-10-15 (frontend, Round 43)" (B1–B5 relied-on behaviour, A1: log at `run_started` so a pre-gate run lost to a restart is listed/refundable); `context/bugs_audit_fixed.md` status note on #29/#41 + the A1 pointer.
- **Next by rank:** compile 43, then the browser pass (item 1); next code item is item 18 (Runs/Account outcome column from `outcome`), then 22, 20.

## Shape of the thing

Vite + React 18 SPA, no router, no state library. Six screens (seven with Admin) selected by one `useState` string in `App.jsx`. Talks to `scripts/frontend_api.py` over same-origin `/api`, proxied by Vite (dev) / nginx (Docker).

```
main.jsx → App.jsx → AuthProvider → Shell
                                     ├── boot: ready? → bootError? → identity?
                                     │   (blank screen · BackendError+Retry · LoginScreen)
                                     ├── CvProvider (keyed by user: current CV)
                                     ├── Sidebar (nav + health poll)
                                     ├── Header  (identity menu: runs left, Account, logout)
                                     └── main    (seven view divs, each its own ErrorBoundary, six hidden)
```

**Every view stays mounted**, hidden via Tailwind `hidden` rather than unmounted — load-bearing, because unmounting `PipelineView` during a live run would kill its `EventSource` and lose the run. Views that fetch on demand take `active={view === "..."}` instead; `KnowledgeBase`, `RunsView`, `SettingsView`, `Account`, `AdminPanel` all go through the shared `useFetch` hook rather than hand-rolled `useEffect`.

**Every view has its own `ErrorBoundary`** (`App.jsx`'s `panel()` helper) — a render throw degrades just that panel to an error card with "try again", not the whole app. `ErrorBoundary.jsx` is the one class component in the codebase (no hook equivalent for `componentDidCatch`).

## Boot and failure handling

Used to fail illegibly: a network error threw a bare `TypeError` with no status; three views swallowed fetch errors with `.catch(()=>{})` and hung on "loading…"; before auth routes existed, `GET /api/auth/me` 404s fell through to `LoginScreen` with no explanation, and its login POST 404s surfaced as raw `"404 Not Found"`.

**`api.js`** normalises every failure to `ApiError` with numeric `.status`: real HTTP status kept as-is; a network-level rejection (backend unreachable) becomes `ApiError(0, "cannot reach the backend")`. `0` is deliberately never a real HTTP status.

**Unwraps FastAPI's error envelope** (`readDetail`, 2026-09-24): a string `detail` used as-is; the validation-array shape becomes `field: msg`; unparseable falls back to raw text. `.status` untouched (callers branch on it, not the message). `ApiError.detail` (2026-10-10) keeps the reason without the status prefix, for sentence-embedding callers.

**A proxy's 502 also reads as "unreachable" (2026-10-10, Round 24).** In Docker (the only way this app runs / is planned to run), a stopped backend doesn't fail at network level — nginx/Caddy answers 502 with its own HTML page, so raw HTML used to reach the boot card, every Failed card, and the gate error line. `failure(status, text)` now: a 502 with a non-JSON body → `ApiError(0, "cannot reach the backend")`; any other HTML error page → "the server answered with an error page and no details"; a JSON 502 from FastAPI itself keeps its status (not sent today). 401 checks still read real status. Known imprecision: nginx also answers 502 if the backend crashes *after* receiving a request, so "your decision wasn't sent" may occasionally be wrong there.

**`AuthContext.jsx`**'s boot `check()` calls `GET /api/auth/me` unconditionally (even with no stored token) — this is what surfaces a broken backend to a first-time visitor too:

| status | meaning | outcome |
|---|---|---|
| success | token valid | `identity` set, app renders |
| 401 | no/invalid token, auth is live | clear stored token → `LoginScreen` |
| 404 | backend has no `/api/auth/*` at all | `bootError` → `BackendError` card |
| 0 / 5xx | unreachable/broken (non-JSON 502 arrives as 0) | `bootError` → `BackendError` card |

`bootError` + `retry()` (re-runs `check()`) exposed on the auth context; `Shell` renders `BackendError` ahead of `!identity`. `LoginScreen` gets the same 404/0 messages for the login-time case.

**Central 401 handling.** `api.js` exposes `setUnauthorizedHandler(fn)`; `AuthContext` wires it to log out + set `sessionEnded`, rendered by `LoginScreen` as "your session ended — ask an admin for a new token". Fires on *any* 401 from *any* call — a mid-session revoke now logs out centrally instead of each call site noticing on its own. Suppressed for `/auth/login` and boot `/auth/me` (expected to 401 on a bad token without tearing down a session that never existed).

**Two blind spots for the central handler (Round 42):**
- `refresh()` re-reads `/auth/me` mid-session, which is exempt — so it now calls `endSession()` itself on a 401.
- `EventSource` can't see status at all — a dropped stream calls `refresh()` once as a probe; a dead token then ends the session instead of reading as "lost connection". Runs once, at the drop; if the backend is down then, the next real call's 401 catches it.

This raises the bar on backend status-code discipline: **any 401 anywhere now has a global side effect (logout)**. "Not admin" / "not your run" etc. must be 403, never 401.

**`useFetch.js`** — one hook, `useFetch(path, {active, once})` → `{data, error, loading, reload}`, backs every read-only fetch view. `once: true` fetches on first activation and caches (`KnowledgeBase`/`SettingsView`); `once: false` refetches every activation (`RunsView`). `BuildProfile` joined 2026-09-24 for *saved* entries, previously reseeded empty on every mount — since editing an entry re-embeds the correction into retrieval, that made entries uncorrectable after reload. Fetched list is **merged** into local state, not assigned over it, so a slow response can't drop an entry saved mid-flight. Paired with `Failed.jsx` (error + retry button) so a failed fetch is never a permanent "loading…".

## The pipeline edits a CV, it doesn't write one

Since the 2026-10 agent work, a run is **a tailoring pass over an existing CV PDF**, not generation from scratch. `cv_link` (`agents/CV_Link.py`) parses `state.cv_path` into a `CVTree`, matches every line to profile records; `document` plans edits per section, applies to a *copy* of the tree, renders to markdown. Final output = the user's own CV with edited lines — `Document.content` stays a plain string, `FinalOutput` needs no change for this.

**Choosing the CV** (frontend 2026-10-09 Round 12; backend routes 2026-10-10, `backend/routes/cv.py`, `backend/cv_store.py`):
- `POST /runs` resolves the caller's current CV before spending a run.
- No CV → 409 for a user; admin falls back to the shared sample, flagged `sample: true`.
- Worker passes resolved path as `cv_path`, emits `run_started {cv, sample}`.
- Checked 2026-10-10: every route/shape/status matches what Round 12 assumed.

Frontend side:
- **`CvContext.jsx`** holds the caller's current CV app-wide; Pipeline gates Start on it, Account can replace/delete. Probes `GET /api/profile/cv` once per signed-in user. 404 means "no CV routes deployed" (once deployed it answers `{cv: null}`) — in that state `CvStrip` says every run uses the shared sample and Start stays enabled, so this frontend degrades gracefully against an older backend.
- **`CvStrip.jsx`**: the one-line "CV · file · pages · date" strip, picker + drag-drop + upload→read→preview (`CvPreview.jsx`)→"Use this CV" flow, plus Delete in Account. Current CV changes only on "Use this CV".
- **`api.js` → `upload()`** uses `XMLHttpRequest` (only XHR reports upload progress).
- **An unconfirmed upload is discarded via DELETE — never the current CV (Round 20).** CV ids are content hashes, so re-uploading a stored file comes back as a "new pending upload" under the *stored* CV's id — Cancel/pick-another/Start (unmounts the strip) used to delete the current CV and break the run resolving it. `discard()` now skips the current CV's id (read via ref so unmount cleanup sees the latest value). Can't protect an *older* re-uploaded stored CV — needs the backend to say what it stored (`backend/bugs.md` 2026-10-10, D1).

**The evidence is not the user's own profile yet.** Users tailor their own CV, but Profile Search / CV Reader / Writer still read the shared synthetic `profile` collection plus every user's Build Profile entries and gate-2 answers — none owner-scoped at retrieval. Since Round 27 the screen says so in three places (start screen's `Evidence ·` row, run's `tailoring: … · evidence:` line, a note under final-review change cards) — strings are `EVIDENCE_SHARED*` in `copy.js`. Since Round 28, no screen calls the pool "your profile"; drop these strings once the per-user vault (P3–P4) lands.

**Since the backend's owner scope (10-10 to 10-12):** Build Profile *lists/edits* are per-account, but retrieval/`/search` stay shared. `BUILD_PROFILE_*` used to overstate visibility — Round 40 made it follow role ("only you and an admin" for a user, "every account's" for admin); both versions still say every run reads the entries and search can find them (item 28). A user's own gate-2 answers (no `owner`) are admin-only in Build Profile. `GAP_HELP` and `EVIDENCE_SHARED*` remain true.

## Data flow: how a run reaches the screen

Backend is the source of truth; frontend holds no run state beyond a fold of the event stream.

1. `POST /api/runs` → `{run_id, cv, sample}` (which CV the run tailors, since 10-10); accepts `client_request_id` for dedupe.
   - `start()` sends one per *start* not per click (Round 29); id kept until a run starts, reused while job description/mode unchanged (so a retry after a lost answer gets back the started run); cleared on success (else the next run within 10 min gets the old id back); a changed description/mode gets a new id (repeated id → backend ignores the body).
2. `openEvents(runId, …)` opens `EventSource` on `GET /api/runs/{id}/events`.
3. Each event folds through `applyEvent(run, ev)` (pure reducer, `PipelineView.jsx`) into `{statuses, artifacts, stubs, events, gate, lastRoute, final, done, outcome, endReason}` + `mode`/`cv`/`sampleCv` (set at start). Three flags set outside the reducer: `streamLost` (stream drops), `gone` (gate answer 404s, Round 31), `lostEdit` (unsaved CV edit read by the stream callback when a stop/failure closes review, Round 32).
4. `artifacts`/`stubs` keyed by graph node id — raw `ev.artifact` / `ev.stub` (backend's own placeholder flag).
5. `run.gate` = open checkpoint: `{node, title, artifactNode, ts, gapQuestions, name, changes, round}`. `name` is the gate's own id (`gate1_requirements`…`gate4_document`, on the wire since 10-09). `changes` is the final review's line diff. `round` counts reopenings (see "Gates" below).

Graph runs **nine** nodes (since 2026-10-07): `jd_analysis → profile → profile_enrich → matching → cv_link → document → critic → verifier → evaluation`. `AGENT_TITLES` in `AgentGraph.jsx` lists all nine (`cv_link`→"CV Reader", Round 9); backend half landed 10-08 (`cv_link` in `AGENTS`, `backend/runs/worker.py`, so it gets `routing`/`node_start` like every other node).

`applyEvent` has one node-specific rule: after a rejected fit review, `cv_link` re-runs but skips re-reading the CV, returning only `{stage}` — the fold keeps the earlier artifact since that read is still the run's.

`gate_wait` also carries `gap_questions` (gate 2's follow-ups, `[{requirement, question}]`, `[]` elsewhere, absent before 2026-08-31). Since Round 8, `GateScreen` renders one answer box per question. Three load-bearing rules: answers keyed by `requirement` exactly as received (`enrich()` matches on that string); `answerGate` sends `gap_answers: {}` on reject (graph keeps whatever's sent); `GateScreen` keyed on `gate.ts` so a reopened gate starts empty. In demo mode the saved answer is a fixed stand-in, not what was typed, and still lands in the shared profile every run reads (`GAP_DEMO_NOTE`).

Event types consumed: `node_start`, `node_done`, `gate_wait`, `gate_done`, `routing`, `document_edited`, `run_started`, `run_done` (with `final`), `run_stopped`, `run_error` (with `final`, since 10-10). Anything else just appends to `events` (shown in `RunLog`) — new backend event types are safe to add. `RunLog.line()` treats every event field as optional (used to call `.toLowerCase()` on `ev.title` unguarded, which threw on malformed `gate_wait` and, pre-`ErrorBoundary`, blanked the app).

**How a run ended (Round 21).** `run.done` only means "no more events" — read `run.outcome` (`"done"|"stopped"|"error"`) and `run.endReason` instead:
- Line under an ended run: green "run finished" / amber "run stopped — …" / red "run failed — …". Stopped/failed also say "everything up to that point is saved in Runs" (true — worker saves the log in its `finally`).
- `run_stopped`/`run_error` **clear `run.gate`** (a stop sends no `gate_done` — previously a run replaced while paused kept its live review screen up, hiding the reason) and **settle the agent graph** (Round 33): a "working" step becomes "failed"/"stopped"; a "waiting" review becomes "stopped". `run_error` names no step, so the step still "working" is the only clue where it failed.
- `run_error` reads `final` too, so a CV saved before a later failure shows as saved. `extractFinalArtifacts` derives the same `outcome` from a saved trail for past runs in Runs.
- Since 2026-08-31, `run_stopped` means only "superseded by a new run from the same user" (a reject no longer ends the run). The run *list* still can't distinguish failed from stopped — summaries carry only `completed` (item 18).

## Rendering artifacts: one renderer, three callers

`renderArtifact(node, artifact)` in `StatePanel.jsx` is the single per-agent-shape renderer, used by `StatePanel` (live cards), `GateScreen` (review), `Drawer` (detail pane); falls back to a key/value dump for unknown shapes so a new agent renders *something* with no code change.

Two shapes drifted in the 2026-10 agent work:
- **`cv_link`** (own branch since 10-09): artifact is `{cv_tree, line_links}` — a nested `CVNode` tree + one link record per CV line (the key/value fallback would've `JSON.stringify`'d it onto one line). The card shows counts only (file, lines checked, backed-by-profile yes/partly/no); the drawer adds the full per-line list grouped by CV section, via `renderArtifact`'s third arg `{detail}` (only the drawer passes it).
- **`document`**'s artifact grew to `{document, document_patches, document_plan, document_plan_key, evidence}` — rendering unaffected (branch matches on `a.document`), but the event is now an order of magnitude bigger and `RunLog` holds every event.

The `document` branch caps body at `max-h-64` (summary card) — `FinalOutput.jsx` does **not** reuse it for the document itself (needs the full, uncapped, copyable text), but does reuse it for the fact-check block.

`FinalOutput` takes `outcome`: a stopped/failed run's draft shows amber **"last draft"** ("wasn't saved") unless `final.export` says the server kept a copy. Since Round 36, a finished run whose review didn't approve is also amber, **"last draft (not approved)"**.

### Stub detection

Some agents are still placeholder skeletons returning fixed example output — labelled with an amber "placeholder output" chip in `StatePanel`/`FinalOutput`. **The backend decides, not the frontend**: `node_done` carries `stub: true` for exactly the nodes in `STUB_NODES` (`backend/runs/worker.py`; `verifier`, `evaluation` as of 10-08). `applyEvent` records it as `run.stubs[ev.node]`; `extractFinalArtifacts` pulls the same flag from a saved trail for past runs.

The fact check has its own wording: while `verifier` is a stub, the review and `FinalOutput` show `FACT_CHECK_PENDING` ("not checked yet…") instead of the stub's fixed "all claims check out" — a placeholder saying "pass" is worse than one saying nothing.

This replaced `stubs.js` (shape-based heuristics, deleted 2026-09-24) — it started mislabelling **real** Matching output as placeholder once `agents/matching.py` became a real brain, and could never detect `verifier` at all. Lesson: the frontend has no way to know what's real and must not try to infer it. Logs written before the flag existed go unlabelled, not mislabelled — the safe direction.

**The exact risk this section warns about fired once, fixed backend-side 2026-10-08:** `agents/document.py` became a real writer while `STUB_NODES` still listed it, so a genuine tailored CV was stamped "placeholder output". `STUB_NODES` is now `{"verifier","evaluation"}`; frontend needed no change and must never add a compensating heuristic.

Wording lives in `copy.js` — the one place plain-language strings belong, auditable against `context/design.md`'s jargon-free requirement.

## Gates, and the artifact_node indirection

Four human gates pause the run. Subtlety: a gate sits *after* one node but reviews *another*'s output — the final gate fires after `verifier` but the thing to approve is `document`. So `gate_wait` carries:
- `ev.node` — node the gate sits after (drives the status dot).
- `ev.artifact_node` — whose output is under review.
- `ev.gate` — the gate's own name, what identifies it; `answerGate` sends it back, backend 409s if it's no longer the open gate (blocks a late click on a stale form).

`PipelineView` stores `artifactNode: ev.artifact_node || ev.node` — the fallback is what lets saved logs from before this change still replay (no `artifact_node` field; identical for the first three gates anyway).

`GateScreen` renders the fact-check block only at the final review, **keyed on gate name** (`isFinal`: `gate.name === "gate4_document"`, falling back to `artifactNode === "document"` for nameless logs) — it used to be `gate.node !== gate.artifactNode`, which broke when gate 3 moved after `cv_link` (10-08: gate 3 then also had two different nodes, showing an empty block). Fixed Round 14; the block also names "Fact Check" and renders `"verifier"` explicitly now instead of whatever node the gate sits after.

### Answering a gate: form retires after one answer (since 10-10)

`GateScreen` keeps `closed: null | "sent" | "movedOn" | "gone"` (Round 17; `"gone"` since Round 31):
- **Accepted (200) → `"sent"`.** Buttons become "Decision sent — waiting…" until `gate_done` closes the screen. (Previously buttons re-enabled on POST return, and a second click 409'd the user's own first answer — the form must retire for the 409 wording below to hold.)
- **Any 409 → `"movedOn"`.** "This review is no longer open — the run has moved on, so this answer wasn't applied." Nothing refetched — the stream brings the next `gate_wait` or the end. Backend has three 409 cases (no gate waiting / already answered / moved on), all meaning "stale form" — **keep them 409**.
- **404 (Round 31) → `"gone"`.** Server restarted. `PipelineView.answerGate` also marks the run `gone`. Since Round 43 the wording (`GATE_GONE`/`RUN_GONE`) points to the **Resume** button on the line under the run, not "can't be finished".

### Resume (Round 43, 2026-10-15)

`PipelineView.resumeRun(id)` — one path for all three entries (dropped stream, gate 404, Runs' Resume):
1. `GET /runs` → find the row. `interrupted` (parked at a gate, no live worker = a restart) → `POST /runs/{id}/resume` (never charges; 409 if another of your runs is active / not parked / a worker holds it; shown as `RESUME_FAILED` + server reason). Not interrupted → the server still holds it, so no POST.
2. Fresh fold (`{...IDLE, mode, restoredEdit}`) + `openStream(id)` (factored out of `start`). The events route replays the whole saved trail, ending in the open `gate_wait` with its original `ts`, so the same review reopens. `cv`/`sampleCv` come back on the replayed `run_started`.
- **Unsaved final edit:** same run → kept as `restoredEdit {ts, text}` and passed to `GateScreen` only while `run.gate.ts` matches, which opens straight into the editor with it (the review unmounts between reset and replay, so the module-scope hold drops briefly). Different run → refused (`RESUME_UNSAVED_EDIT`) rather than replacing the screen.
- **Runs → Pipeline handoff:** `App` holds `resumeRequest` (a new `{id, mode}` object per click) and switches view; `PipelineView` runs `resumeRun` in an effect on it. The Resume button sits in the opened run's detail, not in the row (the row is already a `<button>`); the row's outcome reads amber "interrupted".
- **Limits:** a run lost before its first review has no saved log — Resume only reconnects and the stream fails again (`STREAM_LOST` says "may"); clicking during backend boot gets "cannot reach the backend".
- **422 while editing:** "Your edit couldn't be saved: <detail>", editor + text kept. **0 (unreachable):** "your decision wasn't sent. Try again", everything kept.
- Leave-page prompt doesn't fire once an edit has been *sent*.

### Rounds: a reopened gate says so (since 10-10)

`gate_wait` carries no round number (backend ask, item B1), so the browser counts (Round 19): `gateKey(ev)` (`RunLog.jsx`) = gate name, or `node|title` for pre-10-09 logs; `applyEvent` sets `gate.round` = count of `gate_wait`s with that key in the trail. From round 2, `GateScreen` shows amber "round N · reopened with a redone version"; `RunLog` numbers the repeated "paused — …" line the same way, including for past runs. Label says "redone version" not "after your reject" — today a gate only reopens after its own reject, but the browser can't see the reason, so it states only what it knows.

### What each button/note claims, and why it's true

Each string is a contract; `copy.js` comments name the dependent code.

| Where | Claim | True because |
|---|---|---|
| Gates 1–3, middle button | "Approve with a note" (was "Request edit"), disabled until there's a note; still sends `edit` (Round 22) | `human_gate` records the `edit` but never applies it; `decide()` treats it as approve |
| Gates 1–3, under buttons | reason isn't used; past the redo limit a reject lets the run carry on (Round 23) | no agent reads `gate_feedback`; `decide()` honours a reject only while `revision_count < max_revisions` (default 2, shared run-wide) |
| Final review, under buttons | writer doesn't use the reason yet; past the limit a reject ends the run unsaved (Round 18) | same rule + `close_run` saves only approve/edit |
| Feedback label | gates 1–3: "saved with this run's history"; final review: "kept in agent memory" (live) / "demo runs aren't kept" (demo) (Round 25) | `close_run`→`record_learning` writes gate-4 answers only, live runs only |
| CV editor | "saved as a file" always; "lines you change are also kept in agent memory" live only (Round 26) | export has no live check; `record_learning` stores each changed line before/after. Nothing reads memory back, so the old "later runs can learn" claim was dropped |
| Start screen / run line / final review | evidence is "shared sample profile, not your own" + whatever any user added (Round 27) | Profile Search/CV Reader/Writer read the one unowned `profile` collection. Drop when P3–P4 land |
| Gate2 help; Build Profile header/list/preview | answers+entries go into the shared pool, other people's runs can use them **(narrowed 10-10)** | `save_gap_answers` embeds unfiltered; `GET/PUT /profile/entries` now DO check ownership (`visible_entries()`) |
| Gate 404 / line under run | "server restarted and dropped this run — Resume picks it back up at its review, without using another run" (Round 43, was Round 31's "can't finish") | `answer_gate` 404s only when the in-memory registry lacks the run; log saved at gate-open; `registry.resume` rebuilds it at that gate, never charges |
| Final output | "saved on the server as … (.md/.txt)"; "last draft (not approved)" (Round 36) | `utils/export.py` writes both files, `close_run` names them in `final.export`, approval-only |
| Final review, a change's records | "records it cites" w/ each record's text, or "not among this run's records" (Round 37) | `evidence_ids` = `ProfileBlock.source_id` values; text from this run's own `node_done` evidence. "Records" not "your evidence" — the pool is shared |
| Build Profile (Round 40) | user: "only you and an admin… every run reads them, search can find them"; admin: "every account's"; + "your checkpoint answers don't appear here yet" | `visible_entries` returns own/all-for-admin, ownerless = admin-only; foreign `PUT` is 403; `_index_entry` embeds into the shared collection; `/search` unscoped; gate-2 answers ownerless |

**Resolved 2026-10-13, checked in `copy.js`:** `BUILD_PROFILE_HELP/SAVED/COUNT` did state the now-false "anyone can see and edit / everyone's / all users" — fixed per-role in Round 40. `GAP_HELP` only ever said the still-true half (read access via unscoped `/search`).

General notes become exact "last redo" warnings once `revision`/`max_revisions` land on `gate_wait` (item 4).

### The final review (gate 4), since 10-09

Built by the Agents session (Round 13). The one gate where "edit" means editing the artifact itself:
- **"What changed from your CV":** one card per edited line, from `gate_wait.changes` ("No lines were changed" if empty). Since Round 37, `ChangeList.jsx`: grouped by section/entry from `where`, labelled "was"/"now" with changed words marked, plus a "records it cites" toggle looking each `evidence_ids` entry up in a `source_id → text` map (`PipelineView` builds it from every `node_done` artifact's `evidence`).
- **"Edit the CV"** swaps in a textarea (max 50,000 chars) pre-filled with the draft; "Save my edits and finish" sends `decision: "edit"` + `edited_content`, backend emits `document_edited` (replaces `artifacts.document` so the edit wins). Since Round 38, a toolbar adds Preview/Edit (`MarkdownPreview.jsx`, built as elements never raw HTML), "Reset to the draft" (inline confirm), and a char counter (amber from 45,000; `charCount` shared with the feedback box).
- **Reject** sends the draft back to the Writer while the revision budget lasts; once spent, the run ends unsaved.
- **`run_done.final`** says how review ended (approved/edited) and where saved (`export.md`/`.txt`). `FinalOutput` shows "approved — saved" / "approved with your edits — saved" / "not approved — not saved". **Download** uses `api.download()` (authenticated fetch + blob save — a plain `<a href>` can't carry the bearer token); falls back to the page's own text if nothing was saved.
- **Since Round 36:** two buttons, Download .md/.txt (`?fmt=md|txt`), under the saved file's own name, + "saved on the server as …" line; a finished-but-unapproved run is amber "last draft (not approved)"; a server copy that won't download falls back to the page copy (happens today for a CV saved before a later failure — the route reads `final` only from `run_done`, item 26).

Round 13's list as of 10-10 — **done:** retire-on-409 (17), honest reject copy (18), `final` on `run_error` (21), honest feedback labels (25), "Approve with a note" (22), demo note (26), both download formats + not-approved label (36), readable diff (37), editor comfort (38). **Approximated:** last-round warning (18,19,23) — exact once `gate_wait` carries round info. **Deferred:** a localStorage draft of an in-progress edit, until Resume exists (nothing can reopen the screen to restore it); leave-page prompt + Cancel confirm already done (15).

**Leaving with an unsaved edit (Rounds 30, 32).** Leave-page prompt only covers reload/closed-tab, so `unsavedEdit.js` covers the rest: `useUnsavedEdit(text)` holds the edit in module scope and registers the prompt while text isn't null; logout/new-run read `hasUnsavedEdit()` at click time and confirm inline; `GateScreen` holds the text while editing; when a stop/failure clears `run.gate` (Round 21), the stream callback reads the text first and keeps it as `run.lostEdit`, shown with Copy via the same hook. Only a central 401 still loses an edit (item 9).

### Who pauses the run: the graph, not the backend (since 2026-08-31)

The graph pauses at a real `interrupt()`; `backend/runs/worker.py` only relays it — the pause becomes `gate_wait`, the `POST /runs/{id}/gate` answer becomes `Command(resume=…)`. Backend's `GATES` table is keyed by the graph's gate names; still emits the same `node`/`title`/`artifact_node`, so old logs replay unchanged.

What changed for the UI:
- **`reject` loops back instead of ending the run** — work returns to the producing agent, reruns, **the same gate reopens** with revised output (capped by `max_revisions`); UI/`RunLog` label it with its round (browser-counted; `gate_wait` itself still carries none).
- **A paused run's checkpoint survives a backend restart; the run itself doesn't** — each run has its own SQLite checkpoint (run id = checkpoint thread id), but the run registry lives in memory, so post-restart it 404s until resumed. Since 10-13 the log saves at gate-open and `POST /runs/{id}/resume` reattaches; the UI offers Resume (Round 43, was "gone" in Round 31).
- **Gate 2 carries `gap_questions`**; answer route accepts `gap_answers` (see "Data flow").

## Auth

Two roles, `user`/`admin`; single opaque bearer token, no username/password. Users self-request access; an admin approves and issues a token good for a fixed run count (default 2). Admin token comes from `ADMIN_TOKEN` in `.env`, unlimited, never decremented.

- `api.js` holds the token in module scope, attaches `Authorization: Bearer <token>` to every call (`get`/`post`/`put`/`del`, `upload()` via XHR, `download()` via fetch+blob) — all raise `ApiError`; all except the two auth probes trigger central 401 logout.
- `AuthContext.jsx` persists the token in `localStorage`, validates against `GET /api/auth/me` on every boot (see "Boot and failure handling" for the full status breakdown — replaced a simpler "only check if stored" version that couldn't detect a backend with no auth at all).
- `ApiError.status` lets callers distinguish 401 (log in again) / 403 (no runs left, not your run) / 404 (route not deployed) / 0 (unreachable) without parsing messages.

**SSE is the exception** — `EventSource` can't set headers, so `openEvents` appends `?token=`, and the backend accepts a query-param token on that one route. A real if minor leak (tokens in server logs/browser history); accepted for an internal tool, the alternative (cookie session) is a bigger change.

Admin UI is hidden, not enforced, client-side: `Sidebar` shows the Admin nav item only for `role === "admin"`; `Shell` falls back to Pipeline if a non-admin lands there anyway. **Cosmetic only** — the real check is backend `require_admin`.

**Account page** (`Account.jsx`, 6th nav item, visible to both roles) shows identity/role/runs-remaining from `useAuth()` and the caller's own runs via `GET /api/runs`. Below zero runs, a "request more runs" button — previously called the same `requestAccess()` as `LoginScreen`, pre-filled with the caller's identifier (an exhausted token could otherwise reach this page since login only checks the token *exists*, not runs-left, so the button was reachable without logging out).

**That button no longer worked (found 10-13):** since the identity work, approving a signup for an existing name 409s (`approve_request`→`create_profile`), yet the page still claimed the request was sent. **Fixed Round 39:** `AuthContext.requestMore(note)` (requestAccess now sign-in-page only); Account calls it, shows the server's 400 reason (e.g. "already awaiting review"); wording says runs land on this same account, no new token/sign-in (`TOPUP_HELP`, `TOPUP_SENT`); calls `refresh()` on every open so approved runs show up here and in the header; Pipeline's 403 on Start now says "request more from Account" (`NO_RUNS_LEFT`).

**Header** (`Header.jsx`) is a `Menu.jsx`-based dropdown (`identifier · role ▾`) rather than a static badge + logout link — `Menu.jsx` is a generic click-outside/Escape popover, reusable for any future per-row action menu.

## Styling

Tailwind v4 via `@tailwindcss/vite` (`@import "tailwindcss";` in `index.css`). **No `tailwind.config.js`, no theme layer** — every colour is an arbitrary-value hex literal inline; new components must hand-match:

| role | hex |
|---|---|
| page background | `#0b0c0e` |
| panel | `#131518` |
| row hover | `#17191d` |
| border / focus border | `#26282e` / `#3a3d44` |
| text primary / secondary / muted | `#d7d9de` / `#85888f` / `#5c5f66` |
| green (ok, final output) | `#4ade80` |
| amber (warning, edit) | `#e8b44c` |
| red (error, reject) | `#f87171` |
| blue (human gate) | `#6ca0f5` |

Font sizes also arbitrary (`text-[11px]` labels … `text-[15px]` headings). Dark-only; `index.css` hardcodes body colours, no `dark:` variants.

## Local environment note

**No Node / `node_modules` on the dev machine** — everything builds/runs via Docker (`docker compose up -d --build` from `frontend/`). **Standing rule: ask before running the frontend in any form**, including throwaway `--rm` bundle checks.

**The unrun backlog is the biggest risk here.** Rounds 4,5,8–15,17–40 compiled but never ran, checked only by re-reading/bracket-counts/import-greps/diffs; Python mock-ups covered 19,24,29–38. Round 41 compiled in its own build, Round 42 in the next — both 63 modules, new hash, no errors. Round 43 (2026-10-15) is **not compiled yet**. Precedent: Round 3 was a syntax error that survived two review sessions and stopped the build entirely.

Builds: 10-10 passed first try, no code change (rules out syntax/import errors, not runtime behaviour — see each round's own "how to verify" in `bugs.md`). 10-14 (after Rounds 27–40) passed first try too, 63 modules including the 3 new files; `npm install` was cached (same deps as 10-10, Vite 6.4.3 both times). Docker Desktop isn't auto-started — run `open -a Docker` first. No `package-lock.json`, so every build resolves deps fresh. **`frontend/` is untracked in git** (`?? frontend/`) — no history to diff/roll back to; copy a file before editing, or commit the folder first.

**Starting it:** `scripts/dev.py` (written 2026-09-16, never run) supervises backend+frontend together and prints every `/api/*` call by parsing uvicorn's access log (no monitoring service/request-logging middleware exists otherwise). On this machine use `--docker`:
```bash
python scripts/dev.py up --docker --offline    # backend :8000 + dashboard :3000
python scripts/dev.py monitor                  # API calls, second terminal
```
Plain `dev.py up` uses `npm run dev`, which can't work here (no Node) — its preflight detects missing `node_modules` but suggests `npm install` first, `--docker` only as an aside (backwards for this machine). The two-command path above still works and is what every past session used. `scripts/dev.py` itself is Pipeline+Infra jurisdiction, not this folder's — the ask-first rule is why this lane never runs it.

## Known sharp edges

- `run.done` conflates success/supersession/error — read `run.outcome` instead. The run *list* still can't tell them apart (summaries lack `outcome`).
- **Re-uploading a stored CV returns the stored CV's id** (content-hash ids) — never `DELETE` a preview's id without checking it isn't the current CV (Round 20); older stored CVs are still exposed until the backend says what it stored.
- **Evidence is the shared demo profile, not the user's** — don't add UI implying otherwise.
- **`copy.js` states backend rules as facts** (feedback label, editor text, reject notes, "Approve with a note", shared-evidence wording, lost-run sentence, "saved on the server as…") — the Gates table lists each claim's dependent code. Already broken once: owner scope made Round 28's Build Profile wording false (fixed Round 40).
- **Build Profile is per-account; the evidence pool isn't.** Lists/edits owner-scoped; every entry still embeds into the one shared collection retrieval/`/search` read. Don't blur the two in wording.
- **A 502 reads as "unreachable" unless its body is JSON** — keep the backend from ever sending a non-JSON 502 itself.
- **After a backend restart, a paused run was gone for good** — registry is in-memory, log written only on worker finish. **Outdated** since restart survival landed (10-13/10-14): the log now saves at gate-open and `POST /runs/{id}/resume` exists, and the UI's Resume (Round 43) uses them; a gate answer still 404s until the user resumes (nothing resumes runs at startup). After a dropped stream, Resume tells a restart from a blip via `GET /runs`'s `interrupted`; without clicking it the page still can't. Never make the backend 404 a gate answer for any other reason, or this wording goes false again.
- `StatePanel`'s fallback `JSON.stringify`s nested objects onto one line — fine for scalars, unusable for deep shapes; `cv_link`'s `cv_tree` was the first case bad enough to need its own branch. The next deep artifact will too.
- **The node label maps drift silently.** `AGENT_TITLES`/`CARD_TITLES` are hand-written; a new graph node appears in neither and just renders nowhere under its raw id. Happened twice (`profile_enrich` 08-31, `cv_link` 10-07, both fixed). No warning exists — check `AGENTS` in `worker.py` + `add_node` calls in `supervisor.py` whenever the graph changes.
- `RunsView` refetches the whole list on every nav-back (`once: false`) — deliberate, list is small/volatile.
- Backend-side, each user has **one run at a time** — a new run supersedes that same user's previous run (`run_stopped`), never someone else's. Demo vs live is a per-run `ContextVar`, not the old mutated `config.USE_FAKE_LLM` global (landed 08-19).
- **401 has a global side effect** — any endpoint returning 401 for something that isn't "invalid token" will wrongly sign the user out; new routes must use 403 for permission failures.
- Stub labelling is only as correct as `STUB_NODES` in `worker.py` — an agent that goes real without being removed keeps its "placeholder" chip and the frontend can't tell (happened to `document` until 10-08). Still far better than the deleted `stubs.js`, which guessed.
- **CV state reads a 404 as "not deployed."** `CvContext` treats 404/405 on `GET /api/profile/cv` as "no CV routes" and unblocks Start. Now the routes exist, "no CV" must stay `200 {cv: null}` — a 404 there would let a CV-less user start a run.
- **`CvStrip` swallows every file drop on itself**, even while uploading is off — an unhandled PDF drop makes the browser navigate away and kills a live run's stream. Drops elsewhere are the browser's default.
- The clipboard fallback (`clipboard.js`) uses deprecated-but-functional `document.execCommand("copy")`, engaging only outside a secure context where `navigator.clipboard` doesn't exist at all.

---

# Role — Frontend + Deployment

> Scope/boundaries/jurisdiction for this team; originally a separate `context_Frontend+Deployment.md`, merged here 2026-09-24.

**Role:** own everything the human sees/clicks and everything that makes this a runnable, shippable artifact — the pipeline UI, four human gates, KB browser, auth screens, run history, plus packaging so it runs anywhere with just Docker. Mindset is **UI/UX + client resilience + containerization**, not business logic — this team never decides *what* an agent produces or *how* evidence is retrieved, only how it's shown and how failure is shown legibly.

**Owns:** all of `frontend/`; the client-side auth *experience* (login, token storage, session-ended handling — not the auth *decisions*, Backend's); Docker image/compose/nginx/Vite packaging; item (17) production deployment beyond local compose (not started).

**Does not own:** backend internals, `config.py`, KB JSON, agent code, the graph; the `/api/*` contract shape (consumes, doesn't define — a shape change is a joint decision Backend initiates).

**Talks to the system only via** same-origin `/api/*` JSON + SSE (Vite-dev / nginx-Docker proxied). Missing data from an endpoint → a Backend request, never a reach into another folder.

**Components:** App shell/boot (`App.jsx`, `AuthContext.jsx`, `CvContext.jsx`, `main.jsx`); API client (`api.js`, `useFetch.js`); 29 files in `components/` (Pipeline, GateScreen, ChangeList, MarkdownPreview, CvStrip/CvPreview, KnowledgeBase, RunsView, AdminPanel, Account, Header/Menu, StatePanel, FinalOutput, BackendError, ErrorBoundary, …); stub wiring (backend `node_done.stub` → `run.stubs`, wording in `copy.js`); `copy.js` itself; utilities (`clipboard.js`, `unsavedEdit.js`); styling (`index.css`, no theme layer); packaging (`Dockerfile`, `docker-compose.yml`, `nginx.conf`, `vite.config.js`, `.dockerignore`); own docs (`context.md`, `bugs.md`).

**Load-bearing facts not to "clean up" blind:** every view stays mounted (unmounting Pipeline kills the live SSE); each view has its own ErrorBoundary; `renderArtifact()` is the single per-agent renderer with a dump fallback; the frontend never guesses placeholder status, only reads the backend's `stub` flag (`stubs.js` guessed, mislabelled real output, deleted).

**Working instructions:**
- Never build/serve/bundle the frontend unprompted (no Node locally) — ask first, every time.
- Match the palette by hand; there's no theme layer.
- 401 has a global logout side effect — integrate every endpoint assuming that; a permission failure returning 401 is a Backend bug, file it, don't paper over client-side.
- Unknown SSE event types are safe to ignore/log (the `PipelineView` reducer already tolerates them).
- Run state is a fold of the event stream — the backend is truth; don't accumulate independent state.
- Check the backend in code before writing down what it still owes (Round 9 found two "open" items had already landed).
- Other lanes edit this folder concurrently (e.g. the Agents session edited several files mid-work on 10-09) — re-read a file right before changing it; keep edits small and anchored so a stale edit fails loudly instead of silently overwriting.
- Plain-language strings go in `copy.js` only, including every error sentence — never a generic "failed".
- One fix per request, most critical first, re-ranked on fresh evidence; back up every file first (untracked in git); check via diff + bracket/import greps; report what wasn't verified. Re-ranking can also demote (item 11 dropped once code showed nothing can revoke a token).
- The backend lane writes into this file too (dated notes) — keep its text, verify in code, and append a dated correction rather than rewriting another lane's words.
- Keep each `copy.js` comment with its constant — a new block has twice landed between a comment and the string it describes; diffs caught both.
- Don't state what the frontend can't observe — "redone version" not "after your reject", a general redo-limit note not a guessed number (the `stubs.js` lesson applied to wording).

**Seams with other teams:**
- **Backend:** the `/api/*` contract, 401/403 discipline, SSE `?token=`, the `artifact_node` indirection — any change is co-owned.
- **Agents via Backend:** which nodes are stubs is `STUB_NODES` in `worker.py` — shrinks when an agent goes real (missed once for `document`, fixed 10-08; only `verifier`/`evaluation` remain). A new graph node must be added to `AGENTS` (worker) *and* `AGENT_TITLES`/`CARD_TITLES` (frontend) or it renders nowhere (missed twice: `profile_enrich`, `cv_link`).
- **Agents, gate 2:** the `{requirement, question}` shape and the "answers keyed by exact `requirement` string" rule come from `agents/profile.py` + `utils/human_gate.py`.
- **Agents + Backend, gate 4:** `changes[]` = `{node_id, where, before, after, reason, evidence_ids}`; `edited_content`; `document_edited`; `run_done.final`; `GET /api/runs/{id}/document?fmt=md|txt`. The Agents session edits this folder directly too — re-read before changing.
- **Backend, CV upload:** the four `/api/profile/cv` routes, `{cv:null}` rule, 422 `detail` codes, 409 on CV-less `POST /runs`, `cv`/`sample` on the run — built and matched 10-10. Still owed: say what an upload stored; keep files runs reference. (Keying CVs on `profile_id` not `token_id` is done, 10-10 — same wire shape, no frontend change needed.)
- **Agents + Backend, redo budget:** `revision`/`max_revisions` on `gate_wait`, `honoured` on `gate_done` — three screens approximate this today.
- **Data Storage, agent memory:** the UI tells live users their CV edits are kept in agent memory; where that memory lives (vault D-T5, `knowledge_base/learning/`, not git-ignored) is that lane's, wording here must follow any change.
- **Backend, everything since Round 27:** `backend/context.md` → "What the frontend needs from the backend — after frontend Rounds 27–38" — §A behaviour relied on, §B new asks (first: the document route must also read `final` from `run_error`), §C checked status of earlier asks. Plus identity work (10-10 to 10-12): items 27 (fixed Round 39), 28 (fixed Round 40).

**Open gaps:** superseded by `bugs.md`'s "Open work, by criticality" (the single ranked list). As of 10-13 its head: (1) 🔴 compile Round 43, then run Rounds 4,5,8–15,17–43 in a browser — nothing else is more important; (2) ✅ items 27/28 fixed (Rounds 39/40) — every 🟠/🟡 this folder can fix alone is done; (3) ✅ evidence labelling (27/28) and `client_request_id` (29); (4) 🟠 blocked on other lanes: round info, CV file safety, `/search` scope — the re-issued-token case closed backend-side (item 7); (5) ✅ items 9,10,12,13,14,15,16,17 closed across Rounds 30–38, the gate-2 paste cut in 41, dead-token in 42. **Update 10-15:** the backend's 10-13→10-15 work made items 18, 20, 21, 22, 26 frontend-buildable; 21 (+10) done in Round 43, the rest open. (Items still genuinely unscoped: (17) production deployment beyond local Docker — no hosting/CI-CD, scope TBD; SSE token-in-logs — accepted tradeoff for an internal tool.)

**Cross-references:** `frontend/bugs.md` (open work + full round history + Round-13's final-review checklist + the 10-09/10 session summary); `backend/context.md` → "What the frontend needs…" and "⧉ MERGED SECTION — Backend+Auth"; `backend/bugs.md` (owed-to-frontend sections, 10-08/10-09/10-10); `frontend/design.md` (visual/UX spec incl. the "Your CV" addendum Round 12 implements); `frontend/DELIVERABLES.md` (showcase mapping).

---

# Open bugs — Frontend + Deployment (as of 2026-10-15)

> Master list is `context/bugs_audit_fixed.md` — these are its open entries tagged to this role, copied verbatim-in-substance. Update both when one closes. Placement judgement calls: #29/#41 here (browser-side remainder); #35→Data Storage; #83→KB+RAG; #38/#51 split by item. Note: #70 is a numbering collision in the master file (two different entries), left as-is — numbers are never reused.

### 🟠 #29 — A UI run can never answer the gap interview
*Also touches: Backend API+Auth, Agents+Orchestration. Found 2026-08-30.*

**Where:** `backend/routes/runs.py` (`GateAnswer`) vs `utils/human_gate.py` (reads `answer["gap_answers"]`).

**Bug:** `human_gate()` surfaces `gap_questions` at gate 2 and reads `gap_answers` back from the resume value, but `GateAnswer` originally had only `{decision, feedback}` — no gap-answer field, so a UI-driven run always resolved gate 2 with `state.gap_answers == {}`, `enrich()` early-returned, and `profile_enrich` no-opped silently (run reports success). Sharper: the string `gap_answers` appeared nowhere in `backend/` at all while `StatePanel.jsx` already rendered `gap_questions` — the UI showed the candidate the questions with no way to answer them, the worst of the three failure states since it looks like a working feature. Independent of #9 (interrupt/stream mismatch) — both must be fixed.

**Lesson:** a payload-contract change must be grepped by field name across *every* consumer, not just "the drivers" — a third consumer (HTTP) was missed.

**Status: 🟠 backend half fixed in code 2026-08-31, still broken end to end.** `GateAnswer.gap_answers` now exists, forwarded by `answer_gate`, read by `human_gate()` via `Command(resume=…)`; `gate_wait` carries `gap_questions` straight from the interrupt payload. **But no form exists in the browser** — a UI run still sends `{}`. Needed (written up as `bugs.md` 08-31 item 1): `GateScreen.jsx` renders an input per question keyed by `requirement`; `PipelineView.jsx` stores `ev.gap_questions` and forwards `gap_answers` on the POST. Leave open until that lands.

### 🟠 #41 — `cv_link` is invisible to the bridge and the UI (#28 again)
*Also touches: Backend API+Auth, Agents+Orchestration. Found 2026-10-06.*

**Where:** `backend/runs/worker.py` (`AGENTS`; `GATES["gate3_fit"]["after"]="matching"`; `_emit_routing` drops non-`AGENTS` nodes); `AgentGraph.jsx` (`AGENT_TITLES`); `StatePanel.jsx` (`CARD_TITLES`, document renderer).

**Bug:** the graph runs `matching → cv_link → gate 3 → document`, but:
- the bridge doesn't know `cv_link` — no `routing`/`node_start` emitted for it, though `_drain` still emits a `node_done` carrying the whole `cv_tree`+`line_links`;
- the frontend doesn't know it either — no `AgentGraph` box, `StatePanel` only renders `CARD_TITLES`-listed nodes — so the ~1.5GB-model, tens-of-seconds step shows nothing and the log goes quiet (looks like a hang);
- gate 3's event still says `node: "matching"` though it now opens after `cv_link`;
- same shape for `document`: its real output is now `document_plan` (keep/refine/rewrite verdicts), but the renderer shows only the placeholder `a.document` and `STUB_NODES` used to label the whole node fabricated — so the planner's verdicts were never shown.

**Impact:** every UI run and every saved log since `cv_link` was wired; user can't see which CV was used, how lines linked to the profile, or the planner's verdicts.

**Status update 10-08 (Agents, half-fixed in code, not run):** `cv_link` is in `AGENTS` (gets `routing`/`node_start`); `GATES["gate3_fit"]["after"]` is `"cv_link"` (`artifact_node` stays `matching`); `document` is out of `STUB_NODES`. **Still open:** frontend `AGENT_TITLES`/`CARD_TITLES`/renderer for `cv_link`; `document_plan` still unrendered; no single exported node list exists (`_emit_routing` still hand-whitelists `AGENTS`), so the next new node can go missing the same way. (That fix also caused #52, below.)

**Proposed fix:** add `cv_link: "CV Linking"` to `AGENT_TITLES`; a `CARD_TITLES` entry/renderer showing source file + matched/partial/unmatched counts + the unmatched lines (not the whole tree); render `document_plan` below the draft in the document card; same #28 lesson — export one `PIPELINE_NODES` list from `agents/supervisor.py` and import it in the worker so this can't recur.

### Also touches this role — owned elsewhere
| Entry | Title | Owned by |
|---|---|---|
| #55 | Gate 4 wired end to end (10-09), but a reject still changes little; live reviews write real CV text into an un-ignored folder | Agents + Orchestration |
| #40 | `scripts/dev.py` starts the backend on :8002 while `vite.config.js` and `nginx.conf` proxy :8000, so `dev.py up` serves a dashboard where every API call fails | Pipeline Infra + Config + Testing |
| #87 (item 4) | The event stream goes silent >30 s during `cv_link`; check `frontend/nginx.conf` for `proxy_read_timeout` and `proxy_buffering off` on the events route (nginx's default read timeout is 60 s; a reconnect replays the full history) | Backend API + Auth |

### Fixed in code, unverified by a run
| Entry | Title | Owned by |
|---|---|---|
| #52 | Side effect of the P2 fix: gate 3's waiting marker has no node in the UI | Backend API + Auth |
