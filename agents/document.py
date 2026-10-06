"""
Document Agent - Gemini in eval mode, Groq in dev mode.

Writes the CV / cover letter from a template + matched evidence + the full
do-not-claim list. Output quality is the product. Prompt: prompts/document/system.yaml.
"""
from __future__ import annotations

import hashlib
from typing import Optional

import re
from dataclasses import dataclass

import config
       
from utils.bullet_rules import check_line, describe_line_rules  
from utils.cv_handling.cv_edit import apply_edits, index_nodes, render_markdown
from utils.cv_handling.cv_extract import walk
from utils.cv_handling.cv_ingest import SECTION_TO_KB_TYPE
from utils.plan_cache import load_plan, save_plan
from vectordb.lookup import profile_blocks

from state.state import (
    CVNode, CVTree, Document, EditVerdict, FitReport, GraphState, LineLink,
    NodeVerdict, Requirements, SectionType, Stage, VerdictSet, DocumentPatchSet, Edit, EditAction, NodeKind, ProfileBlock 
)
from agents.base import structured_call, spec_for
from utils.trace import log

PLANNER = "document_plan"          # LLM call 1: grades CV nodes keep / refine / rewrite
# Add SectionType.EXPERIENCE to grade work-history bullets as well.
GRADED_SECTIONS = {SectionType.PROJECTS, SectionType.SKILLS, SectionType.COURSEWORK, SectionType.ACHIEVEMENTS}
LINKS_SHOWN = 2                    # a line's best linked records shown to the planner
MAX_REASON_CHARS = 200             # backstop for "1-2 short lines"; the prompt is the real limit

def _graded(tree: CVTree) -> list[CVNode]:
    return [s for s in tree.root.children if s.section_type in GRADED_SECTIONS]


def _render_for_planner(tree: CVTree, links: list[LineLink], report: FitReport,
                        requirements: Optional[Requirements]) -> str:
    link_of = {l.node_id: l for l in links}
    out: list[str] = []
    if requirements is not None:
        out += [f"ROLE: {requirements.role_title or '(not stated)'}",
                f"JD KEYWORDS: {', '.join(requirements.keywords) or '(none)'}", ""]
    out.append("REQUIREMENTS (support = how well the profile backs each one):")
    out += [f"- {m.requirement} [{m.kind}] support={m.support.value} evidence={m.evidence_ids}"
            for m in report.matches] or ["(none)"]
    out += ["", "UNMET MUST-HAVES (no evidence in the profile; never to be claimed):"]
    out += [f"- {r}" for r in report.unmet_must_haves] or ["(none)"]
    out += ["", "CV SECTIONS (node id, kind, link status to the profile, best linked records, text):"]

    def walk(node: CVNode, depth: int) -> None:
        link = link_of.get(node.node_id)
        status = link.status.value if link else "-"
        ids = link.source_ids[:LINKS_SHOWN] if link else []
        out.append(f"{'  ' * depth}[{node.node_id}] {node.kind.value} link={status} {ids} :: {node.text}")
        for child in node.children:
            walk(child, depth + 1)

    for section in _graded(tree):
        walk(section, 0)
    return "\n".join(out)


def _resolve_verdicts(tree: CVTree, raw: VerdictSet) -> tuple[VerdictSet, list[str]]:
    given = {v.node_id: v for v in raw.verdicts}
    resolved: list[NodeVerdict] = []
    graded_ids: set[str] = set()

    def visit(node: CVNode, inherited: Optional[NodeVerdict]) -> None:
        if inherited is None:                      # the model's to grade; a node it skipped is a keep
            graded_ids.add(node.node_id)
            v = given.get(node.node_id)
            verdict = v.verdict if v else EditVerdict.KEEP
            reason = " ".join(v.reason.split())[:MAX_REASON_CHARS] if v and verdict != EditVerdict.KEEP else ""
        else:                                      # an ancestor ended the descent: same verdict, same reason
            verdict, reason = inherited.verdict, inherited.reason
        here = NodeVerdict(node_id=node.node_id, verdict=verdict, reason=reason)
        resolved.append(here)
        below = None if verdict == EditVerdict.REFINE else here
        for child in node.children:
            visit(child, below)

    for section in _graded(tree):
        visit(section, None)
    ignored = [nid for nid in given if nid not in graded_ids]    # invented, not graded, or under a stopped node
    return VerdictSet(verdicts=resolved), ignored

_PLAN_FAKE_JSON = (
    '{"verdicts": ['
    ' {"node_id": "projects", "verdict": "refine", "reason": "Backs the ETL requirement but uses few JD keywords."},'
    ' {"node_id": "projects.0", "verdict": "rewrite", "reason": "Aimed at churn, not the pipeline work the job asks for."},'
    ' {"node_id": "projects.0.b1", "verdict": "refine", "reason": "Under a rewritten entry, so ignored."},'
    ' {"node_id": "projects.1", "verdict": "refine", "reason": "Backed by evidence but under-states the pipeline."},'
    ' {"node_id": "projects.1.b2", "verdict": "refine", "reason": "No number and a weak opening verb."},'
    ' {"node_id": "coursework", "verdict": "refine", "reason": "Lists courses the job does not mention."},'
    ' {"node_id": "coursework.i1", "verdict": "refine", "reason": "Closest course to the data-engineering role."},'
    ' {"node_id": "skills", "verdict": "keep", "reason": "A reason on a keep is cleared."},'
    ' {"node_id": "experience.0.b0", "verdict": "rewrite", "reason": "Experience is not a graded section."},'
    ' {"node_id": "nope.9", "verdict": "refine", "reason": "Invented id."}'
    ']}'
)


def _plan(state: GraphState) -> tuple[VerdictSet, str]:
    tree = state.cv_tree
    report = state.fit_report or FitReport()
    user_input = _render_for_planner(tree, state.line_links, report, state.requirements)
    system = spec_for(PLANNER).system_prompt
    # Everything the call depends on: who answers (the model, or the fixture offline, so editing
    # the fixture changes the key), the instruction, and the input.
    answerer = _PLAN_FAKE_JSON if config.fake_llm_active() else config.model_for(PLANNER)
    key = hashlib.sha256(f"{answerer}\n\n{system}\n\n{user_input}".encode("utf-8")).hexdigest()[:16]

    # Guard 1: a redo round never re-plans. A loop-back fixes the draft; it must not move the targets.
    if state.document_plan is not None and state.revision_count > 0:
        log(f"document_plan: redo round {state.revision_count}, kept the saved verdicts")
        return state.document_plan, state.document_plan_key or key

    # Guard 2: the plan in state came from this exact call.
    if state.document_plan is not None and state.document_plan_key == key:
        log(f"document_plan: reused the saved verdicts (key {key})")
        return state.document_plan, key

    if not _graded(tree) or not report.matches:
        log("document_plan: nothing to grade, or nothing to grade against - no LLM call")
        raw = VerdictSet()
    else:
        # Guard 3: another run, or a run that failed after call 1, already got this answer.
        raw = load_plan(key)
        if raw is not None:
            log(f"document_plan: reused the cached answer (key {key}), no LLM call")
        else:
            raw = structured_call(PLANNER, user_input, VerdictSet, fake_json=_PLAN_FAKE_JSON)
            save_plan(key, raw)        # straight away: nothing later in the node can lose it
            log(f"document_plan: LLM call 1 made (key {key})")
    plan, ignored = _resolve_verdicts(tree, raw)
    if ignored:
        log(f"document_plan: ignored {len(ignored)} verdict(s) for nodes it may not grade: {ignored}")
    return plan, key

MATERIAL_CAP = 4                  # evidence not on the CV that a section's writer is offered
MAX_EDITS_PER_SECTION = 8
PROSE_SECTIONS = {SectionType.EXPERIENCE, SectionType.PROJECTS, SectionType.RESPONSIBILITIES}  # bullets here are sentences: the bullet rules apply
_NUMERAL = re.compile(r"\d+(?:[.,]\d+)*")


@dataclass
class _Packet:
    section_id: str
    section_type: SectionType
    text: str                      # the writer's user input for this section
    original: dict[str, str]       # lines it may rewrite: node_id -> current text
    evidence: dict[str, str]       # evidence it may cite: record id -> block text


def _linked_ids(state: GraphState, plan: VerdictSet) -> list[str]:
    todo = {v.node_id for v in plan.verdicts if v.verdict != EditVerdict.KEEP}
    ids: list[str] = []
    for l in state.line_links:
        if l.node_id in todo and l.kind in (NodeKind.BULLET, NodeKind.ITEM):
            ids += l.source_ids[:LINKS_SHOWN]
    return list(dict.fromkeys(ids))


def _build_packets(state: GraphState, plan: VerdictSet, blocks: dict[str, ProfileBlock]) -> list[_Packet]:
    tree, report, req = state.cv_tree, state.fit_report or FitReport(), state.requirements
    nodes = index_nodes(tree)
    verdict_of = {v.node_id: v for v in plan.verdicts}
    link_of = {l.node_id: l for l in state.line_links}
    on_cv = {rid for l in state.line_links for rid in l.source_ids[:LINKS_SHOWN]}
    rank = {rid: i for i, rid in enumerate(report.ranked_evidence_ids)}
    packets: list[_Packet] = []

    for section in _graded(tree):
        targets = [n for n in walk(section)
                   if n.kind in (NodeKind.BULLET, NodeKind.ITEM)
                   and verdict_of.get(n.node_id) is not None
                   and verdict_of[n.node_id].verdict != EditVerdict.KEEP]
        if not targets:
            continue
        lines, cited, original = [], [], {}
        for n in targets:
            v = verdict_of[n.node_id]
            link = link_of.get(n.node_id)
            ids = [rid for rid in (link.source_ids[:LINKS_SHOWN] if link else []) if rid in blocks]
            serves = [f"{m.requirement} [{m.kind}, support={m.support.value}]"
                      for m in report.matches if set(m.evidence_ids) & set(ids)]
            parent = nodes.get(n.parent_id)
            under = parent.text if parent is not None and parent.kind == NodeKind.ENTRY else section.title
            lines.append(f"[{n.node_id}] verdict={v.verdict.value}\n  under: {under}\n  current: {n.text}\n"
                         f"  why: {v.reason or '-'}\n  serves: {'; '.join(serves) or '-'}\n"
                         f"  evidence: {', '.join(ids) or '-'}")
            original[n.node_id] = n.text
            cited += ids
        shown = list(dict.fromkeys(cited))
        kb_type = SECTION_TO_KB_TYPE.get(section.section_type)
        material = sorted((b for b in blocks.values() if b.category == kb_type and b.source_id not in on_cv),
                          key=lambda b: rank.get(b.source_id, len(rank)))[:MATERIAL_CAP]
        evidence = {rid: blocks[rid].content for rid in shown}
        evidence.update({b.source_id: b.content for b in material})

        text = "\n".join([
            f"ROLE: {(req.role_title if req else None) or '(not stated)'}",
            f"JD KEYWORDS: {', '.join(req.keywords) if req and req.keywords else '(none)'}",
            f"SECTION: {section.title} [{section.node_id}]", "",
            "LINES TO WRITE (give a better line for each; every other line stays as it is):",
            *lines, "",
            "EVIDENCE (cite by id; the only facts you may use):",
            *[f"[{rid}] {evidence[rid]}" for rid in shown], "",
            "AVAILABLE EVIDENCE NOT ON THE CV (may be used when a line is rewritten):",
            *([f"[{b.source_id}] {b.content}" for b in material] or ["(none)"]), "",
            "UNMET MUST-HAVES (never claim):",
            *([f"- {r}" for r in report.unmet_must_haves] or ["(none)"]),
        ])
        packets.append(_Packet(section.node_id, section.section_type, text, original, evidence))
    return packets

def _guard_edits(raw: DocumentPatchSet, packet: _Packet) -> tuple[list[Edit], list[str]]:
    accepted: list[Edit] = []
    rejected: list[str] = []
    seen: set[str] = set()
    for e in raw.edits:
        text = " ".join((e.new_text or "").split())
        cited = [i for i in e.evidence_ids if i in packet.evidence]
        why = None
        if e.action != EditAction.REPLACE:
            why = f"action {e.action.value!r} is not supported"
        elif e.target_id not in packet.original:
            why = "not a line it was asked to write"
        elif e.target_id in seen:
            why = "second edit for the same line"
        elif not text:
            why = "no new text"
        elif text == packet.original[e.target_id]:
            why = "same text as before"
        elif not cited:
            why = "cites no evidence from this section's packet"
        else:
            allowed = set(_NUMERAL.findall(packet.original[e.target_id]))
            for i in cited:
                allowed |= set(_NUMERAL.findall(packet.evidence[i]))
            extra = [n for n in _NUMERAL.findall(text) if n not in allowed]
            if extra:
                why = f"numbers not in the line or the cited evidence: {extra}"
            elif packet.section_type in PROSE_SECTIONS:
                broken = check_line(text)
                if broken:
                    why = "breaks the bullet rules: " + "; ".join(v.rule for v in broken)
        if why:
            rejected.append(f"{e.target_id}: {why}")
            continue
        seen.add(e.target_id)
        accepted.append(e.model_copy(update={"new_text": text, "evidence_ids": cited}))
    if len(accepted) > MAX_EDITS_PER_SECTION:
        rejected += [f"{e.target_id}: over the {MAX_EDITS_PER_SECTION}-edit cap" for e in accepted[MAX_EDITS_PER_SECTION:]]
        accepted = accepted[:MAX_EDITS_PER_SECTION]
    return accepted, rejected

WRITER = "document"               # LLM call 2: writes the better lines, one call per section

# Skills, courses and awards are facts, not sentences. Edit this wording freely.
FACT_SECTION_RULES = (
    "SECTION RULES (skills, courses and awards are facts, not sentences): reword or reorder only. "
    "Do not add a skill, course or award that is not in the evidence, and do not add detail the item "
    "does not already state."
)

# Offline fixture. The same reply comes back for every section call, so each section also receives the
# other's edits and must reject them. projects.1.b2 carries an invented number, nope.9 does not exist.
_WRITE_FAKE_JSON = (
    '{"edits": ['
    ' {"target_id": "projects.0.b0", "action": "replace", "purpose": "covers_requirement",'
    '  "new_text": "Streamlined a machine learning system to predict customer churn, improving F1 from 0.62 to 0.68 on weekly releases.",'
    '  "evidence_ids": ["project:derivatives_trading_bot_001"], "reason": "Adds the pipeline angle."},'
    ' {"target_id": "projects.1.b2", "action": "replace", "purpose": "quantifies",'
    '  "new_text": "Analyzed NLP workloads to refine the pipeline, improving R2 from 0.69 to 0.86 across 912 runs.",'
    '  "evidence_ids": ["project:uniswap_recommendation_system_010"], "reason": "Invented number 912."},'
    ' {"target_id": "coursework.i1", "action": "replace", "purpose": "adds_keyword",'
    '  "new_text": "Computer Networks (distributed systems, big data analytics)",'
    '  "evidence_ids": ["coursework:course_005"], "reason": "Adds the course topics."},'
    ' {"target_id": "nope.9", "action": "replace", "purpose": "adds_keyword",'
    '  "new_text": "Invented line.", "evidence_ids": [], "reason": "Not a listed line."}'
    ']}'
)

SECTION_PROMPTS = {
    SectionType.PROJECTS:     "",
    SectionType.SKILLS:       "…your text…",
    SectionType.COURSEWORK:   "…your text…",
    SectionType.ACHIEVEMENTS: "…your text…",
}

def _writer_prompt(section_type: SectionType) -> str:
    rules = describe_line_rules() if section_type in PROSE_SECTIONS else FACT_SECTION_RULES
    extra = SECTION_PROMPTS.get(section_type, "")
    return "\n\n".join(p for p in (spec_for(WRITER).system_prompt, rules, extra) if p)


def _write_section(packet: _Packet) -> tuple[list[Edit], list[str]]:
    raw = structured_call(WRITER, packet.text, DocumentPatchSet, fake_json=_WRITE_FAKE_JSON,
                          system_prompt=_writer_prompt(packet.section_type))
    return _guard_edits(raw, packet)

def node(state: GraphState) -> dict:
    if state.cv_tree is None:
        raise ValueError("document needs state.cv_tree: cv_link runs before document")
    plan, key = _plan(state)

    # the records the lines point to may not be in state.evidence: fetch what is missing
    have = {b.source_id for b in state.evidence}
    fetched = profile_blocks([i for i in _linked_ids(state, plan) if i not in have])
    blocks = {b.source_id: b for b in [*state.evidence, *fetched]}

    edits: list[Edit] = []
    for packet in _build_packets(state, plan, blocks):
        accepted, rejected = _write_section(packet)
        edits += accepted
        for r in rejected:
            log(f"document: rejected {r}")
        log(f"document: {packet.section_id}: {len(accepted)} edit(s) accepted, {len(rejected)} rejected")

    patches = DocumentPatchSet(edits=edits)
    new_tree = apply_edits(state.cv_tree, patches.edits)          # a copy; state.cv_tree stays the original
    report = state.fit_report or FitReport()
    draft = Document(kind="cv", content=render_markdown(new_tree),
                     unsupported_flags=list(report.unmet_must_haves))   # from code, never read back from the model
    return {
        "document": draft, "document_patches": patches,
        "document_plan": plan, "document_plan_key": key,
        "evidence": fetched,          # the reducer drops duplicates; the Verifier can now ground against these
        "stage": Stage.CRITIC,
    }