# Knowledge Base — stores & strategies

These are **not** all vector stores. Mixing them up is the main storage trap
(Build.md). Each subfolder is loaded differently:

| Store | Folder | Storage strategy | Why |
|-------|--------|------------------|-----|
| **Documents** | `documents/` | Vector store + metadata | CV/CL examples + templates, retrieved by similarity. |
| **Profile** | `profile/` | Vector store + structured fields | Projects/skills/achievements; semantic retrieval, filtered by category. |
| **Do-not-claim** | `do_not_claim/` | Plain JSON, injected **whole** | A hard constraint must be checked exhaustively. Never embed it — a near-miss retrieval that drops a forbidden claim is a silent failure. |
| **Learning** | `learning/` | Structured JSONL records + vector index on exemplars | Scores/corrections are structured; exemplar retrieval by role-type is vector + metadata filter. |
| **Instructions** | `instructions/` | Plain JSON, used as-is | Static writing-instruction sets (e.g. `cv_bullet_generation_v1`) referenced by the writer. |
| **Agent prompts** | `agent_prompts/` | JSON, one file per agent | 50 versioned prompt examples per agent (objective, prompt template, few-shot, success/failure patterns). |

On-disk vector indexes and SQLite files are git-ignored; the seed/config files here are not.
