#!/usr/bin/env python3
"""
Run one agent node, or a chain of them, without the graph. Each node's output is
threaded into the state the next one sees.

Anything a node needs that no earlier node produced gets seeded from PREREQS, and
only when still missing - real upstream output always wins.

profile_enrich no-ops in this runner: its gap answers come from gate 2 and there
are no gates here, so it early-returns with just a stage.

Usage:  python scripts/run_agent.py                      # the COMPLETED chain
        python scripts/run_agent.py profile              # one agent, seeded
        python scripts/run_agent.py jd_analysis profile  # an explicit chain
        python scripts/run_agent.py document             # seeded with a parsed CV, its links, evidence
                                                         # and a fit report (needs scripts/match_cv_test.py
                                                         # to have been run once; see _document_inputs)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from importlib import import_module

from pydantic import BaseModel

import config
from state.state import (
    CVTree, Document, FitReport, GraphState, LineLink, MatchResult, ProfileBlock, Requirement,
    Requirements, Stage, Support,
)
from state.state_utils import update_state
from vectordb.lookup import profile_blocks

SAMPLE_JD = "We need a Python data engineer with strong SQL and ETL experience."

# Real agents, pipeline order. No-args runs exactly this chain.
# Append as each one stops being a stub. Still stubs: verifier, evaluation.
COMPLETED = ["jd_analysis", "profile", "profile_enrich", "matching", "cv_link", "document", "critic"]

# agent name -> the callable build_graph() wires as that node. Not always
# agents.<name>.node - profile_enrich is a second function inside
# agents/profile.py, so importing one module per name cannot reach it.
NODES: dict[str, str] = {
    "jd_analysis":    "agents.jd_analysis:node",
    "profile":        "agents.profile:node",
    "profile_enrich": "agents.profile:enrich",
    "matching":       "agents.matching:node",
    "cv_link":        "agents.CV_Link:node",   # becomes agents.cv_link once the file is renamed
    "document":       "agents.document:node",
    "critic":         "agents.critic:node",
    "verifier":       "agents.verifier:node",
    "evaluation":     "agents.evaluation:node",
}

# Stand-in for what jd_analysis would have produced, so downstream nodes can run
# on their own.
SAMPLE_REQUIREMENTS = Requirements(
    role_title="Data Engineer",
    seniority="fresher",
    keywords=["Python", "SQL", "ETL", "data pipeline"],
    requirements=[
        Requirement(text="Strong Python for data processing", kind="must_have",
                    category="hard_skill"),
        Requirement(text="SQL and relational data modelling", kind="must_have",
                    category="hard_skill"),
        Requirement(text="Build and maintain ETL pipelines", kind="must_have",
                    category="responsibility"),
        Requirement(text="Machine learning exposure", kind="nice_to_have",
                    category="hard_skill"),
    ],
)

# --- Document agent seeds ---------------------------------------------------------
# The Document node needs a parsed CV, its links to the profile, the retrieved
# evidence and a fit report. An offline run of the whole graph cannot supply
# realistic ones (the Matching fixture cites ids that do not exist, so its fit
# report comes out empty). So this builds one consistent set from the sandbox
# outputs of scripts/match_cv_test.py plus the profile index. It is a dev seed,
# not Matching's output.
DOC_CV_STEM = "CV_test"
DOC_EVIDENCE_CAP = 24
# Chosen so the seeded fit report has a spread against the synthetic profile: two
# strong, one partial (a single block), one with no evidence at all (an unmet
# must-have). The other agents keep SAMPLE_REQUIREMENTS.
DOC_REQUIREMENTS = Requirements(
    role_title="Data Engineer",
    seniority="fresher",
    keywords=["Python", "PostgreSQL", "Airflow", "XGBoost"],
    requirements=[
        Requirement(text="Strong Python for data processing", kind="must_have", category="hard_skill"),
        Requirement(text="Relational database design (PostgreSQL)", kind="must_have", category="hard_skill"),
        Requirement(text="Build and maintain ETL pipelines with Airflow", kind="must_have",
                    category="responsibility"),
        Requirement(text="Experience with XGBoost models", kind="nice_to_have", category="hard_skill"),
    ],
)
# a block backs a requirement when its text contains one of these (by requirement text)
DOC_REQUIREMENT_TERMS: dict[str, list[str]] = {
    "Strong Python for data processing": ["python"],
    "Relational database design (PostgreSQL)": ["postgres"],
    "Build and maintain ETL pipelines with Airflow": ["airflow", "pipeline"],
    "Experience with XGBoost models": ["xgboost"],
}
_DOC_INPUTS: dict = {}


def _sample_fit(requirements: Requirements, evidence: list[ProfileBlock]) -> FitReport:
    scores = {Support.STRONG: 1.0, Support.PARTIAL: 0.5, Support.NONE: 0.0}
    matches: list[MatchResult] = []
    cited: dict[str, int] = {}
    for req in requirements.requirements:
        terms = DOC_REQUIREMENT_TERMS.get(req.text, [])
        hits = [b for b in evidence if any(t in b.content.lower() for t in terms)]
        support = Support.STRONG if len(hits) >= 2 else Support.PARTIAL if hits else Support.NONE
        by_type: dict = {}                   # spread across record types, so every kind of CV line has support
        for b in hits:
            by_type.setdefault(b.category, []).append(b.source_id)
        picked = [rid for ids in by_type.values() for rid in ids[:3]]
        matches.append(MatchResult(requirement=req.text, kind=req.kind, support=support,
                                   evidence_ids=picked, justification="dev seed"))
        for rid in picked:
            cited[rid] = cited.get(rid, 0) + 1
    must = [m for m in matches if m.kind == "must_have"]
    return FitReport(
        matches=matches,
        overall_fit=round(sum(scores[m.support] for m in matches) / len(matches), 3) if matches else 0.0,
        must_have_coverage=round(sum(scores[m.support] for m in must) / len(must), 3) if must else 0.0,
        unmet_must_haves=[m.requirement for m in must if m.support == Support.NONE],
        ranked_evidence_ids=sorted(cited, key=lambda rid: -cited[rid]),
    )


def _document_inputs() -> dict:
    """cv_tree, line_links, evidence and fit_report for one CV, built once per script run."""
    if _DOC_INPUTS:
        return _DOC_INPUTS
    tree_path = config.CV_MATCH_DIR / f"{DOC_CV_STEM}.tree.json"
    links_path = config.CV_MATCH_DIR / f"{DOC_CV_STEM}.links.json"
    if not (tree_path.exists() and links_path.exists()):
        raise SystemExit(
            f"No parsed CV in {config.CV_MATCH_DIR}. Run "
            f"`python scripts/match_cv_test.py --pdf {DOC_CV_STEM}.pdf` once, then run this again."
        )
    tree = CVTree.model_validate_json(tree_path.read_text(encoding="utf-8"))
    raw_links = json.loads(links_path.read_text(encoding="utf-8"))["links"]
    links = [LineLink.model_validate(v) for v in raw_links.values()]

    ids: list[str] = []                  # the records the CV points to, best two per line
    for link in links:
        for rid in link.source_ids[:2]:
            if rid not in ids:
                ids.append(rid)
    evidence = profile_blocks(ids[:DOC_EVIDENCE_CAP])
    _DOC_INPUTS.update(
        cv_tree=tree, line_links=links, evidence=evidence,
        fit_report=_sample_fit(DOC_REQUIREMENTS, evidence),
    )
    return _DOC_INPUTS


def _critic_rubric() -> str:
    # In the graph the Supervisor injects it; imported lazily, because importing
    # agents.supervisor imports every agent (and the models agents.profile loads).
    from agents.supervisor import STAGE_RUBRIC

    return STAGE_RUBRIC[Stage.CRITIC]


# agent -> the state fields its node expects to be filled already. A value may be a
# zero-argument callable, evaluated only when the field is actually missing.
PREREQS: dict[str, dict] = {
    "profile": {"requirements": SAMPLE_REQUIREMENTS},
    "matching": {"requirements": SAMPLE_REQUIREMENTS},
    # cv_link raises without a CV; same server-side default the backend uses.
    "cv_link": {"cv_path": str(config.CV_DEFAULT_PATH)},
    "critic": {
        "requirements": SAMPLE_REQUIREMENTS,  # the node lists them in its prompt
        "active_rubric": _critic_rubric,
        "document": Document(kind="cv", content="Data Engineer. Built Python ETL pipelines on PostgreSQL."),
        # critic.node() refuses to run without a fit report (#76 item 2); same sample the document seed uses.
        "fit_report": lambda: _document_inputs()["fit_report"],
    },
    "document": {
        "requirements": DOC_REQUIREMENTS,
        "cv_tree": lambda: _document_inputs()["cv_tree"],
        "line_links": lambda: _document_inputs()["line_links"],
        "evidence": lambda: _document_inputs()["evidence"],
        "fit_report": lambda: _document_inputs()["fit_report"],
    },
}


def resolve(agent: str):
    """agent name -> its node callable. Mirrors build_graph's add_node calls.

    Unknown name used to surface as a ModuleNotFoundError from deep in importlib.
    """
    if agent not in NODES:
        raise SystemExit(f"Unknown agent {agent!r}. Known: {', '.join(NODES)}")
    module_path, func = NODES[agent].split(":")
    return getattr(import_module(module_path), func)


def render(value) -> str:
    """Pretty-print: models as indented JSON, lists element by element."""
    if isinstance(value, BaseModel):
        return value.model_dump_json(indent=2)
    if isinstance(value, list):
        return "[\n" + "\n".join(f"  - {render(v)}" for v in value) + "\n]" if value else "[]"
    return str(value)


def _is_missing(value) -> bool:
    """None, or an empty list/dict: a list field defaults to [] rather than None."""
    return value is None or (isinstance(value, (list, dict)) and not value)


def seed_missing(state: GraphState, agent: str) -> GraphState:
    """Fill only the prereq fields still empty.

    In a chain an upstream agent already produced them for real, leave those
    alone. Running a node by itself, nothing did, so the sample stands in.
    """
    missing = {
        field: value() if callable(value) else value
        for field, value in PREREQS.get(agent, {}).items()
        if _is_missing(getattr(state, field, None))
    }
    return update_state(state, **missing) if missing else state


def main() -> int:
    agents = sys.argv[1:] or COMPLETED

    state = GraphState(job_description=SAMPLE_JD)

    for agent in agents:
        node = resolve(agent)
        state = seed_missing(state, agent)

        print(f"\n=== Running agent: {agent} ===")
        output = node(state)

        for key, value in output.items():
            print(f"\n{key}:\n{render(value)}")

        # thread this output into what the next node sees
        state = update_state(state, **output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())