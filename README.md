# Multi-Agent CV / Cover-Letter System

A LangGraph supervisor orchestrating six agents that produce a grounded, tailored
CV and cover letter for a specific job description, with four human gates and a
verify-everything discipline. See [`Build.md`](Build.md) for the full design and
[`Instructions.md`](Instructions.md) for the setup spec.

## Architecture at a glance

```
Supervisor (router + context injection)
  └─ JD Analysis ─ Profile ─ Matching ─ Document ─ Critic ─ Verifier ─ Evaluation
                     │ gate                  └── revise loop ──┘  │ fail loop
                     gates ×4 = interrupt() pauses (durable, Postgres checkpointer)
```

| Agent | Model (eval mode) | Role |
|-------|-------------------|------|
| Supervisor  | Groq Llama 3.3 70B | Routing, Critic dispatch, loop-backs, context injection |
| JD Analysis | Groq Llama 3.3 70B | Raw JD → typed `Requirements` |
| Profile     | Groq Llama 3.3 70B | Evidence retrieval + gap-interview |
| Matching    | Groq Llama 3.3 70B | Score evidence vs requirements → `FitReport` |
| Document    | **Gemini 2.5 Flash** | Generate the CV / cover letter (the product) |
| Critic      | **Gemini 2.5 Flash** | Rubric review → `pass`/`revise` |
| Verifier    | Groq Llama 3.3 70B | Grounding check + exact do-not-claim enforcement |
| Evaluation  | Groq Llama 3.3 70B | Post-approval scoring → Learning Store |

In **dev mode**, *every* agent runs on Groq (cheap graph/behaviour testing). In
**eval mode**, Document and Critic switch to Gemini for output-quality testing.
One flag controls it — `TEST_MODE` in `.env` (see `config.MODEL_CONFIG`).

## Project layout

```
.
├── agents/            # one node per agent (+ supervisor, base factory)
├── knowledge_base/    # 4 stores, 4 strategies — see knowledge_base/README.md
│   ├── documents/        #   vector: CV/CL examples + templates
│   ├── profile/          #   vector: projects/skills/achievements
│   ├── do_not_claim/     #   plain JSON, injected whole (hard constraint)
│   └── learning/         #   structured JSONL records + exemplar index
├── state/             # GraphState — the typed Pydantic audit trail
├── learning/          # Learning Store (JSON-backed)
├── evaluation/        # deterministic ATS check + (TODO) deepeval / LLM-judge
├── prompts/           # one folder per agent; versioned system.yaml prompts
├── utils/             # prompt loader, etc.
├── config.py          # the ONLY place env vars / keys are read
├── main.py            # entry point (config + prompt self-check)
└── requirements.txt
```

## Setup

Requires **Python 3.12** (the ML deps — chromadb, spacy, torch — lack wheels for
3.14). On macOS: `brew install python@3.12`.

```bash
# 1. Create and activate the venv
python3.12 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt
python -m spacy download en_core_web_sm   # JD keyword extraction (ATS check)

# 3. Configure secrets
cp .env.example .env        # then fill in GROQ_API_KEY, GOOGLE_API_KEY, ...

# 4. Verify the scaffold (no API calls)
python main.py
```

`main.py` prints the active model assignment, which keys are set, and every
prompt version — a green light that the wiring is sound before you add keys.

## Configuration

All environment variables are read in exactly one place: `config.py`. Never read
`os.getenv` elsewhere or hardcode a key. Key settings:

- `TEST_MODE` — `dev` (all Groq) or `eval` (Document/Critic → Gemini).
- Provider keys — `GROQ_API_KEY`, `GOOGLE_API_KEY`, plus fallback lanes
  (`CEREBRAS_API_KEY`, `OPENROUTER_API_KEY`).
- `DATABASE_URL` — Postgres, for the durable checkpointer (gates survive restarts).
- Gemini budget guard — soft alert at `GEMINI_ALERT_THRESHOLD` calls/day.

## Status & next milestones

This repository is the **scaffold**: folder structure, config, versioned prompts,
typed state, the storage layout, and a deterministic ATS check. Agent node bodies
and the graph itself are stubs (`raise NotImplementedError`), to be filled in next:

1. Knowledge-base ingestion (embeddings → Chroma collections; do-not-claim loader).
2. Agent node implementations (structured output via `with_structured_output`).
3. `agents/supervisor.py:build_graph` — StateGraph, conditional edges, `interrupt()`
   gates, Postgres checkpointer.
4. LiteLLM fallback chains + backoff (`config.FALLBACK_CHAINS`).
5. Langfuse tracing + the Streamlit gate UI.
