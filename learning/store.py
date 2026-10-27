"""
Learning Store — JSON-backed structured records per agent (Instructions.md #19).

Layout on disk (already populated with fixtures):
    knowledge_base/learning/<agent>/exemplars.json     # approved good examples
    knowledge_base/learning/<agent>/corrections.json   # human corrections
    knowledge_base/learning/<agent>/feedback.jsonl      # append-only raw feedback

This module is pure file I/O (boilerplate). The *selection* of which records to
inject into an agent's context lives in learning/context_builder.py — that's the
part with real logic (the overfitting guard).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import config
from backend import jsonstore   # one atomic-write helper, as its docstring intends (#62 item 1)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _agent_dir(agent_name: str) -> Path:
    return config.KB_LEARNING_DIR / agent_name


def _read_json_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8").strip() or "[]")   # "\n" is empty, not a crash (#62 item 3)
    return data if isinstance(data, list) else [data]


def _append_json_list(path: Path, record: dict) -> None:
    """Read-modify-write append to a JSON array file (creates it if missing).

    Under the file's `jsonstore` lock, so two threads appending at once both
    land: unlocked, 16 threads x 10 corrections kept 10 of 160 (audit #12,
    scripts/check_storage.py --stress). Written by `jsonstore.write_json`
    (atomic, own temp file). One process only: a CLI run and the server
    appending to the same file at once can still lose one record.
    """
    with jsonstore.lock_for(path):
        records = _read_json_list(path)
        records.append(record)
        jsonstore.write_json(path, records)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# --- public API (Instructions.md #19) ----------------------------------------
def load_learning(agent_name: str) -> dict:
    """Return all learning content for an agent as structured lists.

    {"exemplars": [...], "corrections": [...], "feedback": [...]}
    """
    d = _agent_dir(agent_name)
    return {
        "exemplars": _read_json_list(d / "exemplars.json"),
        "corrections": _read_json_list(d / "corrections.json"),
        "feedback": _read_jsonl(d / "feedback.jsonl"),
    }


def save_exemplar(agent_name: str, input: dict | str, output: dict | str, feedback: str | None = None) -> dict:
    """Append one approved example to the agent's exemplars.json. Returns the record."""
    record = {
        "agent_name": agent_name,
        "timestamp": _now(),
        "input_context": input,
        "generated_output": output,
        "feedback": feedback or "",
    }
    _append_json_list(_agent_dir(agent_name) / "exemplars.json", record)
    return record


def save_correction(agent_name: str, original: str, corrected: str, reason: str,
                    extra: dict | None = None) -> dict:
    """Append one human correction to the agent's corrections.json. Returns the record.

    `extra` adds provenance fields (run_id, gate, ...) without changing the core keys:
    it is spread first, so a clashing key in it loses (#62 item 4).
    """
    record = {
        **(extra or {}),
        # same key the seeded records carry, so a deduper/selector sees live ones too (#66)
        "correction_id": f"corr_{uuid.uuid4().hex[:12]}",
        "agent_name": agent_name,
        "timestamp": _now(),
        "before": original,
        "after": corrected,
        "reason": reason,
    }
    _append_json_list(_agent_dir(agent_name) / "corrections.json", record)
    return record


def append_feedback(agent_name: str, record: dict) -> dict:
    """Append one raw feedback record to the agent's feedback.jsonl. Returns it.

    One line per record, opened in append mode, so concurrent runs add lines
    rather than overwrite each other (unlike the JSON-array files, audit #12).
    """
    record = {**record, "agent_name": agent_name, "timestamp": _now()}   # core keys last (#62 item 4)
    path = _agent_dir(agent_name) / "feedback.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


# --- existing append-only run log + (TODO) exemplar vector retrieval ----------
class LearningStore:
    """Append-only JSONL of full evaluation records (one row per run)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (config.KB_LEARNING_DIR / "records.jsonl")

    def record(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(data, ensure_ascii=False) + "\n")

    def all_records(self) -> list[dict]:
        return _read_jsonl(self.path)
