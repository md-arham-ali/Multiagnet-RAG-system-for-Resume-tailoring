# Frontend — What There Is To Show

> Last checked against the running system 2026-09-24. Facts below were updated
> from the code on 2026-10-12, not re-checked in a browser.
> **Stage 0 Production plan (approved 2026-09-27):** the frontend and deployment
> slice is the last section of this file ("⧉ STAGE 0 PRODUCTION PLAN — Frontend +
> Deployment"). It includes the showcase script, which is what the deployed
> prototype has to demonstrate.

## Open work for this role, by criticality (reconciled 2026-10-12)

The full ranked list is at the top of `bugs.md`; the numbers in brackets are
that list's. This is what stands between the screens below and a showcase.

1. 🔴 **Build and look (M0)** [1].
   - Rounds 4, 5, 8–15 and 17–26 compiled on 2026-10-10.
   - Rounds 27–40 (2026-10-10 to 10-13) compiled on 2026-10-14: first try, no
     code change. Round 41 (2026-10-14, the gate-2 answer count) compiled in a
     later build the same day, and Round 42 (a dead token is noticed) in one
     after that.
   - None has run in a browser, so every "written" claim below is unverified
     until then. Ask first.
2. ✅ **The two honesty gaps a demo viewer would hit are closed** (written, not
   yet compiled):
   - the screen now says the evidence comes from the shared demo profile [2,
     Rounds 27–28];
   - Start sends `client_request_id`, so a repeated request no longer spends a
     second run [3, Round 29].
3. 🟠 **Blocked, and blocking the showcase script:**
   - exact last-redo warnings [4]; showcase step 8, "the cap";
   - CV files deleted from under the user [5];
   - other users' records visible [6]; showcase step 6, "isolation";
   - ~~a re-issued token loses its CV [7]~~: closed by the backend, which
     keys CVs on `profile_id` (checked 2026-10-13).
4. ✅ **Smaller fixes, all in this folder:** all closed by Rounds 30–38 [9, 10,
   12, 13, 14, 15, 16, 17]. Only item 9's central 401 is left, and it waits on
   Resume.
5. ⚪ **M4** (intake form, confirm view, gate-2 free box) waits on the Agents
   lane and the profile data layer. **M6** (production nginx, §22 deployment)
   is not started.

A dashboard that shows the CV/cover-letter system working, live, in a browser.
It runs beside the main project and never changes it. The `backend/` package
connects the two; `scripts/frontend_api.py` is a one-line shim kept because the
run command, `nginx.conf` and `vite.config.js` all name it.

## How to start it (2 commands)

```bash
# 1. the connection layer (from the project root)
.venv/bin/python -m uvicorn scripts.frontend_api:app --port 8000

# 2. the dashboard (from the frontend/ folder; needs Docker running)
docker compose up -d --build
```

Open **http://localhost:3000**.

### Or one command, with the API calls shown live

`scripts/dev.py` (written 2026-09-16, **never run** — see `bugs.md` → Round 16)
supervises both of the above and prints every `/api/*` call as it happens,
coloured by status, with a per-route count on exit:

```bash
python scripts/dev.py up --docker --offline
```

`--offline` makes runs default to demo mode (no model calls). In a second
terminal, `python scripts/dev.py monitor` follows the same API calls on their
own, and `python scripts/dev.py check` reports whether the venv, `ADMIN_TOKEN`
and the three ports are ready without starting anything.

**Use `--docker` on this machine.** Plain `dev.py up` starts the frontend with
`npm run dev`, and there is no Node here. Ctrl-C stops everything it started,
container included.

## The screens, and what each one proves

**1. Pipeline** — the main demo.
Paste a job description, press Start. You watch the nine steps light up one
by one — Job Analysis → Profile Search → Profile Update → Matching → CV Reader →
Writer → Reviewer → Fact Check → Scoring — with the Supervisor's routing decision
shown at every step. (Profile Update folds the answers you give at the second
checkpoint back into the shared profile before the fit is scored. CV Reader
reads the CV being tailored and checks each line against the shared profile;
the Writer then edits that CV rather than writing a new one.) An "Evidence"
line above the job description, and on the running run, says the records are
a shared sample profile, not your own.
If a run stops or fails, the graph marks the step it stopped at, and any CV
edit you had open stays on screen to copy.
Each step's result appears below as it is produced (job requirements found,
evidence retrieved, fit scores, how much of the CV the shared profile backs, draft
document, review verdict, fact-check result, final scores). Two modes: *demo mode* (no model calls, free, always
works) and *live model* (real Groq calls).

**2. Human checkpoints** — the run truly pauses four times.
At each pause a full review screen appears: what the agent produced, a
feedback box, and Approve / Approve with a note / Reject. At the final review
the middle button is "Edit the CV". The system does not move until you answer.
**Rejecting does not end the run** — the work goes back to the agent that
produced it, that agent runs again, and the same checkpoint reopens with the new
version, labelled with its round. Each run allows only a few redos in total;
after that a reject moves the run on (and at the final review, ends it unsaved).
The screen says so. Every decision and comment is saved in the run's audit trail.
If the server restarts while a run is paused, the review says the run can't
continue rather than failing button by button.

**3. Knowledge Base** — browse everything the system knows.
Four sections: Profile (projects, skills, achievements…), Documents (example
CVs and cover letters), Claim boundaries (things the system must never say —
always checked in full), Agent memory (what agents learned from past runs).
Plus **Evidence search**: type any question and see what the system finds in
its knowledge, each result with a 0–100 match score. This is a real search
against the same index the agents use; the header counts the searchable entries
live, so the number on screen is always the true one.

**4. Build Profile** — feeding the system by conversation.
The system asks one direct question at a time ("What did you build in your
last project?"). Answers assemble into a structured entry shown live in a
preview panel before saving. A progress strip (Projects → Skills →
Achievements → Education → Internships → Extras) shows where you are. Any
answer can be clicked and changed; saved entries can be re-edited. Entries go
into a separate new file — nothing existing is overwritten. You see and edit
only your own entries (the admin sees every account's), but each one also
feeds the shared profile that every run reads and evidence search finds. The
screen says both (Round 40). Your answers at the second checkpoint aren't
listed here yet, and the screen says that too.

**5. Runs + Settings** — the paper trail.
Every run is stored event-by-event with your gate decisions and feedback.
Settings shows which model serves which agent and which providers are
connected.

**6. Account, and 7. Admin** — access.
Account shows who you are signed in as, how many runs your token has left, and
your own run history; it can file a request for more once you run out. Admin
(admins only) is the queue of access requests — approving one issues a token,
shown once for copying.

## What is real vs. placeholder (honest version)

- **Real:** the pipeline execution (it is the actual backend graph running,
  not an animation), the Job Analysis, Profile Search, Profile Update, Matching,
  CV Reader, Writer and Reviewer agents, the knowledge base contents, the
  evidence search with real match scores, the four pauses, the audit trail.
- **Shared, not yours:** every run's evidence comes from one shared demo profile
  (synthetic records plus everyone's Build Profile entries and gate-2 answers),
  not the signed-in user's own. The screen says so since Rounds 27–28
  (compiled 2026-10-14, not yet viewed).
- **Placeholder:** two agents still return example output — Fact Check and
  Scoring. The backend says so itself on every step it produces
  (`stub: true`), and the dashboard marks those results "placeholder output"
  rather than dressing them up as findings. They will show real output
  automatically once written, with no frontend change.
- **Compiled, never run in a browser:** the second checkpoint asks follow-up
  questions about gaps the shared profile doesn't cover, and as of 2026-10-09
  the screen has a box to answer each one. Profile Update then saves the
  answers to the shared profile. The screen warns that other people's runs can
  use them and anyone signed in can read them. See `bugs.md` → Rounds 8 and 28.
- **Written, and the backend landed 2026-10-10:** a "CV" line above the job
  description, where you upload the PDF your runs tailor. You check "What we
  read" and then choose "Use this CV". Account shows the same line, with Replace
  and Delete. Start is disabled until you add a CV; the admin falls back to the
  shared sample, labelled "sample CV (not yours)". Compiled 2026-10-10, never
  run in a browser. See `bugs.md` → Round 12, and its open items 5 and 7.

## Boundaries kept

This held while the dashboard was being built. It no longer describes the whole
project: the agents and the graph have been worked on since, and the bridge grew
into the `backend/` package. What is still true of **this folder**:

- Nothing under `frontend/` reaches into the main project except over HTTP —
  same-origin `/api`, proxied by nginx in Docker and Vite in dev.
- It owns its own Docker container and writes nothing to disk itself. Run logs
  (`logs/frontend_runs/`), profile entries
  (`knowledge_base/profile/manual_entries.json`) and issued tokens
  (`knowledge_base/auth/`) are all written by the backend.

## One thing found while connecting — RESOLVED 2026-07-08

`config.py` was missing four values its own search modules expect
(`VECTORDB_DIR`, `EMBEDDING_MODEL`, `RERANKER_MODEL`, `LANGFUSE_ENABLED`).
They were restored in `config.py` on 2026-07-08, and the runtime shims the
bridge used as a workaround were removed from `scripts/frontend_api.py` on
2026-07-15. Nothing to do here anymore.



<!-- ============================================================ -->

---

# ⧉ STAGE 0 PRODUCTION PLAN — Frontend + Deployment (approved 2026-09-27)

> **What this is.** The approved plan for putting a *working prototype* on a
> public HTTPS URL that shows the *production-handling* side of the system, then
> building and redeploying from there. The plan is split by component: each role
> file holds the parts it owns, at full depth. **Nothing below is built yet.**
> Section numbers §1–§24 are the plan's own and mean the same in every file.
> Parts two roles share are copied into both, identical, and marked *(shared)*.
> The full overview table, milestone table and decision list live in
> `context/context_Pipeline Infra+Config+Testing.md`.

## Goal and decisions (same in every file)

- **Synthetic data is fine for Stage 0.** Real data comes later, entered through
  the Profile agent itself.
- **The Profile agent collects data from users.** A new user is interviewed
  through a gate. On later runs the user can add more. New input either
  **appends** records or **improves** existing ones, and only after the user
  confirms the proposed changes.
- **A per-profile data layer:** efficient ingestion, separated storage per
  profile, profile-scoped retrieval, and a retrieval log in its own database.

| Topic | Decision (user, 2026-09-27) |
|---|---|
| When the profile data layer is built | **Stage 0, before deploy** |
| What one profile is | **One per user account** |
| Vector separation | **One Chroma collection per profile** |
| Database | **SQLite, two files:** `profiles.db` (source of truth) + `retrieval_log.db` (separate log) |
| New-user data collection | **An intake gate inside the run, before retrieval** |
| Adding data on later runs | **Gate-2 gap answers + a free "add or correct anything" box** |
| Writing changes | **Propose → confirm gate → commit**, with version history |
| Append-vs-improve rule | **Open.** Decided while building the layer. The plan provides the seam and the candidate-finding plumbing (§4.5) |

**Stage scale:** **S0** not started · **S1** stub or scaffold · **S2** works
offline (`USE_FAKE_LLM=1`) · **S3** works live, verified by a real run · **S4**
production-handled (CI-tested, observable, fails safe, deployed).

**Stage 0 Production is done when all of these hold:**
- **A brand-new user on the public URL:** is interviewed at the intake gate,
  confirms the extracted profile changes, walks the remaining gates, and downloads
  a Verifier-checked CV built from their own profile.
- **Their second run** appends or updates records, with history kept.
- **Two accounts** never see each other's records, retrievals or runs, and every
  retrieval is logged.
- **These are all demonstrable:** restart survival, the loop cap, provider
  fallback, auth/403 discipline, the audit trail, health/readiness, persistence
  across a redeploy, rebuilding the index from `profiles.db`, and green CI.
- **Evaluation** keeps its "placeholder" chip.

**Working split:**
- **You (brain):** agent, routing, merge, schema logic.
- **You (run):** all tests and runs. **You also build and view the frontend** (the
  standing rule: the assistant never builds or serves it without asking).
- **Claude on grant:** plumbing, only after scope is granted.

### Where each part of the plan lives

| § | Part | File |
|---|---|---|
| §1 | Repo + baseline verification | `context/context_Pipeline Infra+Config+Testing.md` |
| §2–§12 | LLM door, agents, profile update flow, Supervisor, prompts, schema | `context/context_Agents+Orchestration.md` |
| §7, §8, §9 | Critic, Verifier, Evaluation | also in `context/context_Eval_Learning loop.md` *(shared)* |
| §13 | Profile data layer | `context/context_Data Storage+Handling.md` · `context/context_KB+Semantic+RAG.md` · `backend/context.md` |
| §14 | Shared stores + retrieval | `context/context_KB+Semantic+RAG.md` |
| §15 | Persistence + backups | `context/context_Data Storage+Handling.md` |
| §16 | Output export | **this file** *(shared with `context/context_Data Storage+Handling.md` and `backend/context.md`)* |
| §17 | Backend API | `backend/context.md` |
| §18, §22 | Frontend, Deployment | **this file** |
| §19, §20, §21, §24 | Config, Tests + CI, Observability, Docs + runbook | `context/context_Pipeline Infra+Config+Testing.md` |
| §23 | Evaluation + learning loop (deferred) | `context/context_Eval_Learning loop.md` |

## This role's components: now → target

| § | Component | Now | Target | Size | Suggested owner |
|---|---|---|---|---|---|
| 16 | Output export: the download button | S0 | **S3** | S | Claude on grant |
| 18 | Frontend | S2 (compiled through Round 40, last on 2026-10-14; never viewed) | **S3** | L | Claude on grant, you build and view |
| 22 | **Deployment** | S0 | **S3** | L | Claude on grant + you (server, domain) |

## How this changes what's described above

- **"Not wired yet: the second checkpoint has no boxes to answer the follow-up
  questions."** Closed by §18's gate-2 form. The Round 5 plan in `bugs.md`,
  plus a free "add or correct anything" box.
- **"Four human checkpoints."** A new user now sees up to three more:
  - **"Tell us about yourself"** (intake);
  - **"Confirm changes to your profile"**, after intake and again after gate 2.
- **"Build Profile … Entries go into a separate new file."** Entries now go into
  the user's own profile in `profiles.db`, with version history. Each user sees
  only their own.
- **"Placeholder: Writer, Fact Check and Scoring."** Writer (Document) and Fact
  Check (Verifier) become real in Stage 0. Scoring (Evaluation) stays a labelled
  placeholder. *(2026-10-10: the Writer is real, and no longer labelled a
  placeholder; Fact Check is still a stub.)*
- **"How to start it (2 commands)."** Stays true for local dev. Production runs
  through the compose stack in §22.

---

### §16. Output export: S0 → S3 *(shared with `context/context_Data Storage+Handling.md` and `backend/context.md`)*

> **✅ Built 2026-10-09 (Agents + Orchestration, with gate 4; not run).** `utils/export.py` writes `outputs/<owner>/{date}_{run_id}_{role}.md` + `.txt`; `utils/final_review.close_run` calls it when the latest gate-4 answer is approve or edit (worker on `run_done`, and the CLI driver). Until `profile_id` exists, `<owner>` is the run owner's token id (`cli` for the CLI). `GET /api/runs/{id}/document?fmt=md|txt` is owner-checked; the path comes from the run's own `run_done.final.export`. The final output's Download button fetches it. Open: `context/bugs_audit_fixed.md` #55.
>
> **Frontend, 2026-10-12 (Round 36, compiled 2026-10-14):** two buttons, "Download .md" and "Download .txt", plus a "saved on the server as …" line. A CV saved before a later failure can't be fetched yet, because the route reads only `run_done` (`bugs.md` top, item 26). The page saves its own copy instead and says so.

- **Writer.** `utils/export.py`'s `export_document(...)` writes
  `outputs/{profile_id}/{date}_{run_id}_{role-slug}.md` plus `.txt`, atomically.
- **When it runs:**
  - on `run_done`, from the backend worker, when gate 4 was approved;
  - at the end of the CLI driver.
- **Route.** `GET /api/runs/{id}/document`, owner-checked (403 otherwise).
- **Frontend.** A "Download" button.
- **Deferred:** PDF, DOCX and the cover letter.

### §18. Frontend: S2 → S3
(Claude on grant. You build and view it, and the assistant always asks first.)

> **Status 2026-10-12** (the plan below is unchanged):
> - **Built:**
>   - the gate-2 gap-answer form (Round 8), without the free box;
>   - the Download button (Round 13, see §16);
>   - an approximate round signal for a reopened gate (Round 19).
> - **Compiled** through Round 40: up to Round 26 on 2026-10-10, the rest on
>   2026-10-14. Nothing viewed.
> - **Not built:** the intake form, the confirm view, own records in Build
>   Profile, the retrieval-log drawer, Resume, and prod nginx.
- **Build and verify Round 4.**
- **`GateScreen` gains three variants.** Put the copy in `copy.js`, with no
  jargon, per `context/design.md`.
  - **Intake form:**
    - one labelled textarea per section or requirement question;
    - a "paste your CV" box;
    - a "Skip for now" action.
  - **Gate 2:** the Round 5 gap-answer form from `bugs.md`, plus one free "add or
    correct anything" box. Nothing is sent on reject, and it resets per `ts`.
  - **Confirm view:** each proposed change is a card with:
    - a "New" or "Update" badge;
    - a before/after view, for updates;
    - the answer it came from;
    - an accept checkbox and an optional correction field.
    - The buttons are "Save all", "Save selected" (edit) and "Discard" (reject).
- **Wiring:**
  - `renderArtifact` gets a branch for `profile_changes`.
  - `AGENT_TITLES` and `CARD_TITLES` get the new nodes.
  - `PipelineView.applyEvent` stores `intake_questions` and `profile_changes`
    from `gate_wait`.
  - `answerGate(...)` sends the new fields.
- **Build Profile screen:** shows the caller's own records with their version.
  History and revert are a stretch goal.
- **Download button** (§16).
- **Stretch goals:**
  - a retrieval-log drawer;
  - a signal for a reopened gate's round;
  - a Resume action.
- **Prod nginx:**
  - `proxy_pass http://backend:8000`;
  - keep the SSE settings;
  - gzip;
  - security headers;
  - no `?token=` in the access logs.

### §22. Deployment: S0 → S3
**Overview.** One VPS running Docker Compose. Requests go Caddy (TLS) → frontend
nginx → backend, with one data volume.
- Serverless is a poor fit, for four reasons:
  - ~1.5 GB of models;
  - SQLite and Chroma on disk;
  - SSE;
  - in-process threads.

**In depth:**
- **Backend image.** Build it from the repo root.
  - `python:3.12-slim`, with CPU torch.
  - Install from the lock.
  - Set `HF_HOME=/models`, with the models pre-downloaded at build time.
  - Run as a non-root user.
- **Entrypoint:**
  1. create the `/data` dirs;
  2. migrate both DBs;
  3. ensure the admin profile exists (seeded per `SEED_PROFILES`);
  4. build `documents` if it's empty;
  5. run `profile_admin.py reconcile`;
  6. `exec uvicorn scripts.frontend_api:app --host 0.0.0.0 --port 8000 --workers 1`.
- **`.dockerignore`:**
  - `.env*`, `.venv`, `__pycache__`;
  - `logs/`, `outputs/`, `test_work/`, `frontend/`;
  - `knowledge_base/chroma`, `knowledge_base/auth`;
  - `*.db`.
- **Prod compose file,** `deploy/docker-compose.prod.yml:`
  - **`backend`:**
    - `env_file`;
    - `agentic-data:/data`;
    - a healthcheck on `/api/ready`;
    - `restart: unless-stopped`;
    - no published port.
  - **`frontend`:** nginx; depends on backend being healthy.
  - **`caddy`:** 80/443 with automatic HTTPS; `reverse_proxy frontend:80` with
    `flush_interval -1`.
- **Host:**
  - a VPS with 8 GB RAM, 2+ vCPU and 30 GB disk;
  - firewall open on 22, 80 and 443 only;
  - SSH by key only;
  - a domain.
- **Secrets:** `.env.prod` exists only on the server.
- **Deploy steps:**
  1. `git pull`;
  2. `docker compose … up -d --build`;
  3. check `/api/ready`.
  - Optionally wrap these in `scripts/deploy.sh`.

---

## Milestones: this role's part (Track B, Claude on grant)

| Milestone | Work in this role | Exit check |
|---|---|---|
| **M0 Baseline** | view everything unviewed: Rounds 4, 5, 8–15 and 17–42, all compiling since 2026-10-14 (you; ask first) | 9-node graph with CV Reader, a "Profile Update" card, no placeholder chip on Fit or Writer, and each round's "how to verify" passes |
| **M4 Product loop in UI** | intake form, gap form + free box, confirm view, download (§18, §16) | in the browser: a new user end to end, then a second run with updates; B can't see A |
| **M6 Deploy + showcase** | backend Dockerfile, prod compose, Caddy, prod nginx, optional Resume action (§22, §18) | HTTPS URL, `/api/ready` green, the script below passes on the host |

## Open decisions this role carries (recommendation first)

| # | Decision | Recommendation |
|---|---|---|
| D1 | Host | VPS with 8 GB, Docker Compose, Caddy |
| D6 | Export format | Markdown + txt for now |
| D7 | Restart-resume in the UI | A minimal rehydrate if time allows, else the CLI |

## The showcase script: what the deployed prototype has to show *(shared with the master copy in `context/context_Pipeline Infra+Config+Testing.md`)*

1. **Readiness.** `/api/health` returns ok. `/api/ready` is all green.
2. **New user A.**
   - Request access and get approved. A gets a `profiles` row and an empty
     `profile__p-…` collection.
   - Start a live run with a JD. After gate 1, the **intake form** appears.
   - Answer two sections and paste a short CV.
3. **Confirm (intake).**
   - The confirm screen lists the extracted records as "New". Deselect one, then
     choose "Save selected".
   - Only the accepted rows appear in `profiles.db`, and the collection gains the
     same number of vectors.
   - Retrieval then runs over them. Gate 2 shows evidence that came from A's
     answers.
4. **Finish run 1.**
   - At gate 2, answer a gap question and use the free box to correct a job
     title.
   - The confirm screen shows one "New" and one "Update" with before/after. Save
     all.
   - `profile_record_history` has the old version of the updated record.
   - Go through gates 3 and 4, then **download** the CV. It is also under
     `/data/outputs/<A's profile_id>/`.
5. **Run 2 as A.**
   - No intake this time, since the profile isn't empty.
   - New gap answers append or update.
   - Re-answering a requirement updates the same record, with no duplicate.
6. **Isolation.**
   - User B, who is new, gets their own intake.
   - B's Build Profile and search never show A's data.
   - `profile_admin.py stats` shows each profile separately.
7. **Retrieval log.** `GET /api/runs/{id}/retrievals` lists run 1's queries,
   only against A's collection, with hits and scores.
8. **Grounding + cap.**
   - The fact-check shows every claim `supported`, with no do-not-claim hits.
   - With `max_revisions=1`, a rejected draft stops and still reaches gate 4.
9. **Durability.**
   - Pause at the intake or confirm gate, then run
     `docker compose restart backend`.
   - Resume, via the UI (D7) or the CLI.
   - The commit still happens exactly once.
10. **Rebuildable index + revert.**
    - Drop A's collection, then run `profile_admin.py reindex --profile <A>`. The
      same evidence is retrieved.
    - `revert` restores the pre-correction job title.
11. **Provider failure.** With the primary key invalidated in a scratch deploy,
    the run completes on the fallback.
12. **Persistence.** After `docker compose down && up -d`, all of these are
    intact:
    - users;
    - profiles;
    - history;
    - runs;
    - the retrieval log;
    - outputs.
13. **CI.** The latest push to main is green.
