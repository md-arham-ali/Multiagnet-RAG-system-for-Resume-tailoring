"""
Instructions.md steps 6 and 7. Prep work, runs before the loader and embedding.

  Step 6: do_not_claim.txt, one forbidden claim per line, from the structured
          do_not_claim.json (which keeps the fuzzy terms for the Verifier).
  Step 7: learning/<agent>/ for the six agents, each with exemplars.json,
          corrections.json (both seeded, merged by id so a re-run keeps what
          live runs wrote) and an empty feedback.jsonl.

Idempotent. Library only, runs nothing on import. Entry point: prep().
Runner:  python scripts/setup_kb_prep.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB = ROOT / "knowledge_base"

AGENT_FOLDERS = ["jd_analysis", "profile", "matching", "document", "critic", "evaluation"]

# synthetic data splits the writer into resume_writer / cover_letter_writer, both
# land in the one "document" folder. supervisor / verifier aren't in the step-7
# list so their records stay in the top-level corpus only.
AGENT_MAP = {
    "jd_analysis": "jd_analysis",
    "profile": "profile",
    "matching": "matching",
    "critic": "critic",
    "evaluation": "evaluation",
    "resume_writer": "document",
    "cover_letter_writer": "document",
}


def _read(path: Path) -> list:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _merge(path: Path, seeded: list, id_field: str) -> list:
    """Records already on disk, plus the seeded ones they do not already hold.

    Step 7 used to rewrite both files from the synthetic corpus on every run.
    `feedback.jsonl` was protected; `corrections.json` was not, and since
    2026-10-09 it receives real gate-4 corrections — so re-running this script
    deleted them (#65.4). Merging by id keeps the run repeatable (same seeds in,
    same file out) without throwing away anything a run has learned.

    A record with no id is keyed on its own content, so an unstamped older
    record is not duplicated either.
    """
    def key(rec):
        return rec.get(id_field) or json.dumps(rec, sort_keys=True, ensure_ascii=False)

    existing = _read(path)
    seen = {key(r) for r in existing}
    return existing + [r for r in seeded if key(r) not in seen]


def step6_do_not_claim_txt() -> int:
    data = json.loads((KB / "do_not_claim" / "do_not_claim.json").read_text(encoding="utf-8"))
    claims = [c["claim"] for c in data.get("forbidden_claims", [])]
    (KB / "do_not_claim" / "do_not_claim.txt").write_text(
        "\n".join(claims) + "\n", encoding="utf-8"
    )
    return len(claims)


def step7_learning_subfolders() -> dict:
    learnings = _read(KB / "learning" / "agent_learnings.json")
    corrections = _read(KB / "learning" / "correction_records.json")

    exemplars = {f: [] for f in AGENT_FOLDERS}
    corrects = {f: [] for f in AGENT_FOLDERS}
    for rec in learnings:
        folder = AGENT_MAP.get(rec.get("agent_name"))
        if folder:
            exemplars[folder].append(rec)
    for rec in corrections:
        folder = AGENT_MAP.get(rec.get("agent_name"))
        if folder:
            corrects[folder].append(rec)

    counts = {}
    for folder in AGENT_FOLDERS:
        d = KB / "learning" / folder
        d.mkdir(parents=True, exist_ok=True)
        merged_ex = _merge(d / "exemplars.json", exemplars[folder], "learning_id")
        merged_co = _merge(d / "corrections.json", corrects[folder], "correction_id")
        (d / "exemplars.json").write_text(
            json.dumps(merged_ex, indent=2, ensure_ascii=False), encoding="utf-8")
        (d / "corrections.json").write_text(
            json.dumps(merged_co, indent=2, ensure_ascii=False), encoding="utf-8")
        fb = d / "feedback.jsonl"
        if not fb.exists():
            fb.write_text("", encoding="utf-8")  # runtime appends feedback here
        counts[folder] = (len(merged_ex), len(merged_co))
    return counts


def prep() -> tuple[int, dict]:
    """Both steps. Returns (do-not-claim count, {folder: (exemplars, corrections)})."""
    return step6_do_not_claim_txt(), step7_learning_subfolders()
