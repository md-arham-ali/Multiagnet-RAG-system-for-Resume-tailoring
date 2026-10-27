# Multi-Agent CV Tailoring System

Give it a job description and your own CV. A team of agents works through it in
order:

1. Read the job's requirements.
2. Pull matching evidence from your profile knowledge base.
3. Score how well you fit.
4. Improve the parts of your CV that should change.
5. Review the result.

Built on LangGraph. A human can approve, edit or reject the work at each step,
and every claim must trace back to a real profile record.

> **Status (2026-10-27):**
> - **Agents:** six of the eight are real, and the graph runs end to end
>   offline. The `verifier` is deliberately out of Stage 0 and stays a
>   placeholder that always passes, as does `evaluation`.
> - **Live runs:** only partly proven. On 2026-10-24 Groq worked for
>   `jd_analysis`, `profile`, `matching` and the Document planner. Gemini
>   returned a 503 on the Critic, and the Cerebras and OpenRouter model names
>   were retired. The Document writer and the Critic's findings have never been
>   seen live.
> - **Tests:** 144 failures were cut to about 40 on 2026-10-24; the rest are
>   tracked as bug #117 (see [Status](#status)). CI runs the offline suite on
>   every push.
> - **Deploy:** Docker files and a compose file are written but no image has
>   been built yet.
> - **Full history:** [`context/context.md`](context/context.md).

---

## How it works

### 1. The pipeline

![Architecture: supervisor, human gates, agents and the knowledge layer](docs/diagrams/architecture.svg)

- **Hub and spokes.** The Supervisor is plain routing code with no LLM. It
  sends work to one agent at a time, and every agent hands its result back to
  it. Agents never call each other.
- **Agents, in order:** `jd_analysis` → `profile` → `profile_enrich` →
  `matching` → `cv_link` → `document` → `critic` → `verifier` → `evaluation`
  (`verifier` and `evaluation` are placeholders for now).
  - `cv_link` isn't drawn in the diagram. It isn't an agent and makes no LLM
    call: it turns your CV PDF into a tree and links every line to the profile
    record behind it.
- **Four human gates.** These are LangGraph `interrupt()` pauses. Each paused
  run is saved to SQLite (`logs/checkpoints.sqlite`), so it survives a restart
  and can be resumed from another process; the web UI has a Resume action for a
  run parked at a gate. A rejected gate sends the work back to the agent that
  produced it.
- **Knowledge layer.** `profile` and `profile_enrich` use it today.
  - **Retrieval:** hybrid search (semantic plus keyword), re-ranked by a
    cross-encoder.
  - **Storage:** a Chroma vector store with `bge-base` embeddings, built from a
    JSON knowledge base that is the source of truth.
  - **Not connected yet:** the learning store and the do-not-claim check.

### 2. What each agent writes

![GraphState: which agent fills which field](docs/diagrams/graph_state.svg)

- **Shared state.** All agents share one typed state object, `GraphState`. It's
  saved at every step, so it doubles as the audit trail.
- **Each agent fills its own field.** `profile` fills two: `evidence` and
  `gap_questions`.
- **Gate 2 is the only gate that adds content.** It adds the gap-interview
  answers, which `profile_enrich` polishes, saves to the knowledge base and
  adds to the evidence.
- **The Document agent patches your CV instead of writing a new one.**
  - **Call 1, the planner:** grades each section, entry and line `keep`,
    `refine` or `rewrite`. The answer is cached on disk, so it isn't paid for
    twice.
  - **Call 2, the writer:** rewrites only the flagged lines, one section at a
    time.
  - **Guards in code:** reject any edit that cites no evidence, invents a
    number, or breaks the bullet rules. The original line is kept.

### 3. The review loop

![Review loop: agents decide, the supervisor routes](docs/diagrams/review_loop.svg)

- **Agents decide.**
  - `critic` judges the draft: pass or revise.
  - `verifier` judges its claims: pass or fail.
  - A human judges the result at Gate 4.
- **The Supervisor routes.** It only reads those verdicts and a
  `revision_count`, then either sends the draft back to `document` or moves on.
- **One counter covers every redo,** whether it comes from a critique or a gate
  reject. It is capped at `max_revisions = 2`, so a run produces at most three
  drafts.

---

## Status

| Part | State |
|------|-------|
| `jd_analysis`, `profile`, `profile_enrich`, `matching`, `critic` | Real, one LLM call each. |
| `document` (CV patcher) + `cv_link` | Built, run offline only. Two LLM calls, plan answer cached. |
| `verifier`, `evaluation` | Placeholders, labelled as such. `verifier` always passes. It is out of scope for Stage 0 (decided 2026-10-07). |
| Supervisor routing, 4 gates, revision cap, SQLite checkpointing | Built and verified. |
| Retrieval (hybrid + re-rank) over Chroma | Built and test-covered. |
| CV parsing + line-to-record linking | Built. All 74 lines on the test CV link correctly. |
| Backend (FastAPI) + frontend (React/Vite) | Built. The UI shows the graph's own gates. Accounts are keyed by `profile_id`, a parked run survives a restart, and an audit and run log are kept per user. |
| Live LLM runs | Partly proven: Groq works for four agents, Gemini and the fallback providers need fixing or re-testing (see above). |
| Docker + CI | Backend and frontend Dockerfiles, `docker-compose.yml` and a GitHub Actions workflow (offline tests, then image builds). Written, never built locally. |
| Learning store, do-not-claim check, Gate 5 (critique review) | Designed, not connected. |

**Known gaps**
- **The loop can't use its own feedback yet.**
  - `document` doesn't read `critique` or `verifier_report`, so a redo can't act
    on them.
  - The Supervisor clears both before `document` runs.
- **The Supervisor doesn't wait for the verifier.** It acts on the critic's
  verdict before the verifier runs. The agreed design is to decide only after
  both have finished.
- **Offline runs never exercise the Document writer.** Matching's offline
  fixture produces an empty fit report, so `document` makes no edits. Use
  `scripts/run_agent.py document` to exercise it.
- **Live runs are unfinished.** The Critic's findings and the Document writer
  have not been seen against a live model, and the planner tends to answer
  `keep` for every node.
- **About 40 tests still fail,** tracked as bug #117. The suite is saved per
  run in `logs/testruns/`.
- **Most "fixed" claims in the bug log are offline-only:** they were checked by
  compiling or reading the code, not by a live run. The open and partly fixed
  bugs are listed in [`context/bugs_audit_fixed.md`](context/bugs_audit_fixed.md).
- **Profiles are still one flat `profiles.json`.** The per-user store described
  under Next is not built.
- **`agents/CV_Link.py` has a capital letter in its name.** Every import spells it
  `CV_Link`, so it works on case-sensitive (Linux) filesystems too; keep that spelling
  in new imports.

**Next**
1. Make `document` read the critique and verifier report.
2. Do a live run on the test CV to check both Document prompts.
3. Stage 0 (approved 2026-09-27), in milestones:
   - M0, a green baseline: fix the outdated `StubGraph` tests, get `pytest`
     green, one gated offline run, a smoke test, then commit;
   - a profile store per user, in SQLite with one Chroma collection each;
   - an intake interview for new users;
   - build and test the Docker images, then a public deploy on synthetic data.
4. Later: the Verifier, the learning store and the do-not-claim check.

---

## Models and configuration

All environment variables are read in one place: [`config.py`](config.py). The
template is [`.env.example`](.env.example).

| Agent | `TEST_MODE=dev` | `TEST_MODE=eval` |
|-------|-----------------|------------------|
| `jd_analysis`, `profile`, `profile_enrich`, `matching`, `verifier`, `evaluation` | Groq Llama 3.3 70B | Groq Llama 3.3 70B |
| `document` (writer), `critic` | Groq Llama 3.3 70B | Gemini 2.5 Flash |
| `document_plan` (planner) | Groq Llama 3.3 70B | Groq Llama 3.3 70B |

| Setting | What it does |
|---------|--------------|
| `TEST_MODE` | `dev` puts every agent on Groq; `eval` moves Document and Critic to Gemini. |
| `USE_FAKE_LLM=1` | Offline: a local fake LLM, no keys and no network. Overrides everything else. Can also be set per run from the UI. |
| `USE_OPENAI=1` | Sends every agent to `OPENAI_MODEL` (default `gpt-4o-mini`). |
| `GROQ_API_KEY`, `GOOGLE_API_KEY`, `OPENAI_API_KEY` | Provider keys. |
| `EMBEDDING_MODEL`, `RERANKER_MODEL` | Local models: `bge-base-en-v1.5` and `bge-reranker-base`. |
| `CV_DEFAULT_PATH` | The CV every UI run starts from. Defaults to `knowledge_base/input/CV_test.pdf`. |
| `PLAN_CACHE` | `1` caches the Document planner's answer in `logs/plan_cache/`; `0` calls the model every time. |
| `ADMIN_TOKEN`, `DEFAULT_RUN_ALLOWANCE` | Access control for the web UI: the admin credential, and how many runs each issued token gets. |

**Defined in `config.py` but not used yet:**
- fallback chains (`CEREBRAS_API_KEY`, `OPENROUTER_API_KEY`);
- Langfuse tracing;
- the Gemini daily budget guard;
- `DATABASE_URL`, kept for a future Postgres checkpointer (SQLite is what's in
  use).

---

## Project layout

```
.
├── agents/            # one node per agent + supervisor (routing, gates) + base (LLM calls)
├── state/             # GraphState and every typed artifact (Pydantic)
├── prompts/           # one folder per agent, versioned system.yaml
├── vectordb/          # embeddings, Chroma store, retriever, re-ranker, ingest
├── utils/             # human gates, checkpointer, CV parsing/editing (cv_handling/), plan cache
├── knowledge_base/    # profile, documents, do_not_claim, instructions, learning (+ chroma index)
├── learning/          # learning store (exemplars, corrections) — not wired in yet
├── evaluation/        # deterministic ATS check — not wired in yet
├── backend/           # FastAPI bridge: auth, runs, gate relay to the UI
├── frontend/          # React + Vite single-page app (Docker/nginx image included)
├── scripts/           # runners: graph, single agent, dev launcher, KB build, demos
├── tests/             # pytest suite
├── context/           # project docs: work log, per-role design notes, bug lists
├── docs/diagrams/     # the diagrams in this README
├── config.py          # the only place env vars are read
├── Dockerfile         # backend image (frontend has its own in frontend/)
├── docker-compose.yml # backend + frontend together
├── .github/workflows/ # CI: offline tests, then Docker image builds
└── main.py            # config + prompt self-check, no API calls
```

---

## Setup

Requires **Python 3.12** (chromadb, spacy and torch have no wheels for 3.14 yet).
On macOS: `brew install python@3.12`.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
cp .env.example .env        # then fill in the keys you need
python main.py              # prints the model assignment, which keys are set, and every prompt version
```

Build the knowledge base and vector index (synthetic data, seeded):

```bash
python scripts/generate_kb_data.py
python scripts/setup_kb_prep.py
python scripts/build_vectordb.py
```

## Run it

```bash
# whole graph offline: fake LLM, no API keys, approve every gate
USE_FAKE_LLM=1 python scripts/run_graph.py --auto-approve

# one agent on seeded inputs (the real offline check for the Document writer)
USE_FAKE_LLM=1 python scripts/run_agent.py document

# backend :8000 + frontend :5173 (add --offline for the fake LLM)
python scripts/dev.py up

# tests
python scripts/dev.py test
```

- **Docker (not built yet):** `docker compose up --build` starts the backend
  and the nginx frontend. It defaults to the fake LLM; set
  `COMPOSE_USE_FAKE_LLM=0` to go live. `python scripts/dev.py up --docker` does
  the same for local development. The choices behind it are in
  [`context/final_docker_descision.md`](context/final_docker_descision.md).
- **Smoke test a running backend:** `python scripts/dev.py smoke`.
- **Interactive run:** `run_graph.py` without `--auto-approve` stops at each gate
  and asks you in the terminal.
- **Resume a paused run:** pass `--thread <id> --resume`.
- **Exercise the review loop offline:** set `FAKE_CRITIC_VERDICT=revise`.

---

## Live deployment

The project is hosted at **`http://<SERVER_IP>`** (placeholder; replace with the
real address). The page you reach is the web UI, served by nginx. Port 80 is
the only published port, and the API sits behind it.

> **For now, only the admin can start a run.** Everyone else can request an
> account, but no run is open to them yet.

### 1. Get the admin token

The admin token is the `ADMIN_TOKEN` value in the server's `.env`. It is not
issued through the UI.

- **Owner:** read it from the `.env` on the server. If it is empty, generate
  one, set it and restart the backend:
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(32))"
  ```
- **Everyone else:** ask the owner for it. With an empty `ADMIN_TOKEN`, nobody
  can administer the system and no user token can be issued.
- Treat it like a password. Never commit it or paste it into a shared chat.

### 2. Access it

1. Open `http://<SERVER_IP>` in a browser.
2. Sign in with the admin token.
3. The Account page then shows your role and your runs.

### 3. Execute a run

1. Open the run screen and paste a job description.
2. Choose the mode:
   - **Demo (offline):** a fake LLM, no provider keys used. This is the
     default for the Docker deployment.
   - **Live:** real models. The server needs its provider keys set, and it
     refuses a live run when they are missing.
3. Start the run, then work through the four human gates, approving, editing
   or rejecting at each.
4. Download the patched CV at the end.

**Which CV is used.** A run uses the CV the account uploaded. An admin with no
upload falls back to the shared sample CV, which is labelled as a sample. If
that file is missing on the server, the run is refused with "No CV is
configured on the server."

**Run limits.** The admin is never counted against an allowance.
`DEFAULT_RUN_ALLOWANCE` (default 2) applies only to issued user tokens, which
are not in use yet.

### 4. Other accounts (later)

A visitor can submit an access request. The admin approves it, which issues a
user token exactly once. Approval does not open runs to them yet; see the note
at the top of this section.

---

## Further reading

- [`context/context.md`](context/context.md): full chronological work log.
- [`context/context_Agents+Orchestration.md`](context/context_Agents+Orchestration.md):
  agent design and build record.
- [`context/context_KB+Semantic+RAG.md`](context/context_KB+Semantic+RAG.md):
  retrieval stack.
- [`context/context_Eval_Learning loop.md`](context/context_Eval_Learning%20loop.md):
  Critic, Verifier and the planned loop.
- [`context/context_Pipeline Infra+Config+Testing.md`](context/context_Pipeline%20Infra+Config+Testing.md):
  config, tests, CI and deployment.
- [`context/bugs_audit_fixed.md`](context/bugs_audit_fixed.md): the master bug
  log, open and fixed.
- [`context/test_status.md`](context/test_status.md): the latest test results.
- [`explanations.md`](explanations.md): the vector layer, explained step by
  step.
