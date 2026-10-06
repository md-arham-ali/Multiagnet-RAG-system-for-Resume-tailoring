"""
Instructions.md steps 6 and 7. Prep work, runs before the loader and embedding.

  Step 6: do_not_claim.txt, one forbidden claim per line, from the structured
          do_not_claim.json (which keeps the fuzzy terms for the Verifier).
  Step 7: learning/<agent>/ for the six agents, each with exemplars.json,
          corrections.json (both seeded) and an empty feedback.jsonl.

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
        (d / "exemplars.json").write_text(
            json.dumps(exemplars[folder], indent=2, ensure_ascii=False), encoding="utf-8")
        (d / "corrections.json").write_text(
            json.dumps(corrects[folder], indent=2, ensure_ascii=False), encoding="utf-8")
        fb = d / "feedback.jsonl"
        if not fb.exists():
            fb.write_text("", encoding="utf-8")  # runtime appends feedback here
        counts[folder] = (len(exemplars[folder]), len(corrects[folder]))
    return counts


def prep() -> tuple[int, dict]:
    """Both steps. Returns (do-not-claim count, {folder: (exemplars, corrections)})."""
    return step6_do_not_claim_txt(), step7_learning_subfolders()
