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
from utils.do_not_claim import check_text as dnc_check, describe_claims, phrase_pattern
from utils.plan_cache import load_plan, save_plan
from utils.prompt_loader import all_prompt_versions
from vectordb.lookup import profile_blocks

from state.state import (
    CVNode, CVTree, ClaimLabel, Document, EditVerdict, FitReport, GraphState, LineLink,
    NodeVerdict, Requirements, SectionType, Stage, Verdict, VerdictSet, VerifyStatus,
    DocumentPatchSet, Edit, EditAction, NodeKind, ProfileBlock
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
# A figure the way a reader of the CV reads it: the number WITH its unit.
# Comparing bare digit runs, which is what this guard did, let any digit in the
# evidence license the same digit in ANY role in the new line - "a team of 5" licensed
# "cut query time by 5%" (#75 item 4), an invented metric in the candidate's
# name, and the number guard is the only code check against those.
# The unit may be written against the number or a space away ("40M", "250 ms").
# The lookahead is what keeps a following WORD from being read as a unit: in
# "5 members" the "m" cannot end the match, so that figure stays the bare 5.
_QUANTITY = re.compile(r"(\d+(?:[.,]\d+)*)\s*(%|ms|rows?|users?|[xkmsh])?(?!\w)",
                       re.IGNORECASE)


def _quantities(text: str) -> set[str]:
    """Every figure in `text`, each as "<number><unit>".

    Thousands commas are dropped and the unit is lower-cased, so "1,000" and
    "1000" are one quantity, and so are "40M" and "40m". Strict the other way
    on purpose: "40K" and "40,000" are NOT the same quantity here, so an edit
    that re-scales a figure out of the evidence is rejected and the candidate's
    original line is kept. Only a conversion table should change that, never a
    comparison of digits.
    """
    return {number.replace(",", "") + (unit or "").lower()
            for number, unit in _QUANTITY.findall(text or "")}

# The line the packet shows the writer above the unmet list, and the line the
# guard below reads that list back out of. One constant, because the guard is
# only trustworthy while it enforces exactly what the writer was told.
UNMET_HEADER = "UNMET MUST-HAVES (never claim):"


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


# The header of the block a redo round carries, and the gate whose reject reaches
# this node. Gates 1-3 send the run back to an earlier agent, so a reject there
# never loops through Document; only gate 4's does.
REVISION_HEADER = "REVISION NOTES (this draft was reviewed and sent back):"
FINAL_GATE = "gate4_document"
MAX_NOTES = 12                    # a packet carries findings, not a transcript


def _revision_notes(state: GraphState) -> str:
    """What the last round said against the draft, for the writer. "" on round 0.

    bugs_audit_fixed.md #76 item 1 / #55 item 1 / #54. Document never read
    `critique`, so on a Critic loop-back it rebuilt the same packets from the same
    state: every writer call and the next Critic call were byte-identical to the
    round before. The redo bought nothing, and the run spent its whole revision
    budget regenerating the draft the Critic had rejected, then shipped it.

    The verdicts are available to read here because `node()` clears them AFTER
    producing, not the Supervisor before (D3, 2026-10-08) - the clearing half of
    this landed then, and this is the reading half it was for.

    Three sources, in the order a writer can act on them:
      - the Critic's items (rubric dimension, severity, where, what to do). Already
        sifted by `critic._sift`, so every one names a dimension someone asked for;
      - the Verifier's findings: claims it would not call supported, and
        do-not-claim hits. Dormant while `verifier.node` is the passing stub;
      - the human's own reason from a gate-4 reject, which is the only one of the
        three a person wrote.

    NOT filtered to this packet's section. A `location` is free text from the model,
    and dropping a finding because that string did not match a section id would
    lose it silently - the one failure mode this whole fix is about. The block says
    to act only on what concerns the section, and costs its tokens in every packet.
    """
    if state.revision_count < 1:
        return ""

    notes: list[str] = []

    critique = state.critique
    if critique is not None and critique.verdict == Verdict.REVISE:
        for item in critique.items[:MAX_NOTES]:
            where = f" at {item.location}" if item.location else ""
            notes.append(f"- Critic [{item.rubric_item}, {item.severity}]{where}: {item.instruction}")

    report = state.verifier_report
    if report is not None and report.status == VerifyStatus.FAIL:
        for claim in report.claims:
            if claim.label != ClaimLabel.SUPPORTED and len(notes) < MAX_NOTES:
                notes.append(f"- Verifier [{claim.label.value}]: {claim.claim}")
        for hit in report.do_not_claim_hits:
            if len(notes) < MAX_NOTES:
                notes.append(f"- Verifier [do-not-claim]: \"{hit.text}\" matches {hit.matched_entry}")

    # Newest first: the last reject is the one this round has to answer.
    for feedback in reversed(state.gate_feedback):
        if feedback.gate == FINAL_GATE and feedback.decision == "reject" and (feedback.feedback or "").strip():
            notes.append(f"- The candidate rejected the draft: {feedback.feedback.strip()}")
            break

    if not notes:
        # A redo with nothing recorded against the draft. Say so rather than send
        # the round-0 packet again, which is what made the two rounds identical.
        notes = ["- (no specific finding was recorded; improve the listed lines further)"]

    log(f"document: round {state.revision_count}, {len(notes)} revision note(s) in every packet")
    return "\n".join([REVISION_HEADER, *notes,
                       "Act only on the notes that concern THIS section; ignore the rest."])


def _build_packets(state: GraphState, plan: VerdictSet, blocks: dict[str, ProfileBlock]) -> list[_Packet]:
    tree, report, req = state.cv_tree, state.fit_report or FitReport(), state.requirements
    nodes = index_nodes(tree)
    verdict_of = {v.node_id: v for v in plan.verdicts}
    link_of = {l.node_id: l for l in state.line_links}
    on_cv = {rid for l in state.line_links for rid in l.source_ids[:LINKS_SHOWN]}
    rank = {rid: i for i, rid in enumerate(report.ranked_evidence_ids)}
    notes = _revision_notes(state)
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
            UNMET_HEADER,
            *([f"- {r}" for r in report.unmet_must_haves] or ["(none)"]),
            "",
            # The do-not-claim file's own contract: injected WHOLE, never
            # retrieved top-k. It was never injected anywhere (#75 item 2), and
            # the Verifier that was meant to catch a hit is out of Stage 0.
            describe_claims(),
            # Last, and empty on round 0, so a first-round packet is byte-identical
            # to what it was before this change (#76 item 1).
            *([notes] if notes else []),
        ])
        packets.append(_Packet(section.node_id, section.section_type, text, original, evidence))
    return packets

def _unmet_from_packet(text: str) -> list[str]:
    """The unmet must-haves as this packet states them.

    Read back out of the packet text rather than passed in beside it: the
    writer and the guard then cannot disagree about which requirements are
    off-limits, and _guard_edits keeps its one-argument shape. "(none)" does
    not start with "- ", so an empty list parses as empty.
    """
    out: list[str] = []
    found = False
    for line in text.splitlines():
        line = line.strip()
        if not found:
            found = line == UNMET_HEADER
        elif line.startswith("- "):
            out.append(line[2:].strip())
        else:
            break                       # the block ends at the first other line
    return [r for r in out if r]


def _other_entries_records(text: str) -> dict[str, set[str]]:
    """line id -> the record ids that belong to a DIFFERENT entry of this section.

    bugs_audit_fixed.md #75 item 1. Every packet's EVIDENCE block is the whole
    section's: the ids cited by every line it lists, plus unseen material. The
    guard accepted any of them for any line, so a rewrite of a bullet under
    "Churn Model" could cite the record behind a bullet under "Recommender",
    take its facts, and leave the entry header still saying "Churn Model". The
    CV then states that the other project's work happened in this one - a false
    claim in the candidate's name, which is the one thing this system promises
    not to make.

    A record "belongs to" an entry when a line under that entry cites it. A
    record no listed line cites belongs to no entry: that is the AVAILABLE
    EVIDENCE NOT ON THE CV material, and it is NOT restricted here - whether
    material may be used under an entry at all is the design half of this item
    and is still the owner's (decisions.md D3).

    Read back out of `packet.text`, the way `_unmet_from_packet` is, so the
    guard enforces exactly the grouping the writer was shown ("under:"). Two
    entries whose text is identical merge into one, which only ever makes this
    more permissive, never less.
    """
    under_of: dict[str, str] = {}
    ids_of: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        if line.startswith("[") and "] verdict=" in line:
            current = line[1:line.index("]")]
        elif current is None:
            continue
        elif line.startswith("  under: "):
            under_of[current] = line[len("  under: "):].strip()
        elif line.startswith("  evidence: "):
            raw = line[len("  evidence: "):].strip()
            ids_of[current] = [] if raw == "-" else [i.strip() for i in raw.split(",") if i.strip()]
            current = None              # "evidence" is the last field of a line block

    owners: dict[str, set[str]] = {}    # record id -> the entries that cite it
    for node_id, ids in ids_of.items():
        for rid in ids:
            owners.setdefault(rid, set()).add(under_of.get(node_id, ""))

    return {node_id: {rid for rid, entries in owners.items()
                      if under_of.get(node_id, "") not in entries}
            for node_id in ids_of}


def _claim_pattern(requirement: str) -> Optional[re.Pattern[str]]:
    """Match a requirement as a phrase, not as a substring.

    The same matcher the do-not-claim guard uses, so the two claim checks in
    this file cannot disagree about what counts as writing something.
    """
    return phrase_pattern(requirement)


def _guard_edits(raw: DocumentPatchSet, packet: _Packet) -> tuple[list[Edit], list[str]]:
    accepted: list[Edit] = []
    rejected: list[str] = []
    seen: set[str] = set()
    unmet = [(r, p) for r, p in ((r, _claim_pattern(r)) for r in _unmet_from_packet(packet.text))
             if p is not None]
    elsewhere = _other_entries_records(packet.text)
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
        elif (stolen := sorted(set(cited) & elsewhere.get(e.target_id, set()))):
            # #75 item 1. Checked before the content guards, because this is not a
            # question about what the new text says: the citation itself is the
            # misattribution, whatever wording it ends up in.
            why = ("cites record(s) belonging to another entry of this section: "
                   + ", ".join(stolen))
        else:
            # What this line is allowed to say: its own current text plus the
            # records it cites. Both the number guard and the unmet-must-have
            # guard below read the same two sources - a figure or a claim that
            # is in neither was invented by the writer.
            sources = [packet.original[e.target_id], *(packet.evidence[i] for i in cited)]
            allowed: set[str] = set()
            for s in sources:
                allowed |= _quantities(s)
            extra = sorted(_quantities(text) - allowed)
            # The packet says "never claim" and nothing enforced it (#59): an
            # edit citing any real record could write the unmet requirement
            # into the line, and the Verifier that was meant to catch it is out
            # of Stage 0. Claiming it is the one thing this system promises not
            # to do, so it is rejected here. A term already in the line, or in
            # a cited record, is the candidate's own words and stays allowed.
            claimed = [r for r, pat in unmet
                       if pat.search(text) and not any(pat.search(s) for s in sources)]
            # The do-not-claim list is a hard constraint, not an evidence
            # question: no cited record can license it and the candidate's own
            # line cannot either, so this check ignores `sources`. Rejecting
            # keeps the original line, which is the safe outcome.
            forbidden = dnc_check(text, location=e.target_id)
            if extra:
                why = f"numbers not in the line or the cited evidence: {extra}"
            elif forbidden:
                why = "writes a do-not-claim entry: " + ", ".join(h.matched_entry for h in forbidden)
            elif claimed:
                why = "claims unmet must-have(s) nothing in the profile backs: " + ", ".join(claimed)
            elif packet.section_type in PROSE_SECTIONS:
                broken = check_line(text)
                if broken:
                    why = "breaks the bullet rules: " + "; ".join(v.rule for v in broken)
        if why:
            rejected.append(f"{e.target_id}: {why}")
            continue
        seen.add(e.target_id)
        # The reason travels with the edit: the gate-4 diff, every gate
        # snapshot, document_patches in the checkpoint and, live,
        # corrections.json. The planner's reasons are cut to the same length
        # (_resolve_verdicts); the writer's were kept at whatever the model
        # sent (#75 item 3).
        accepted.append(e.model_copy(update={
            "new_text": text, "evidence_ids": cited,
            "reason": " ".join((e.reason or "").split())[:MAX_REASON_CHARS]}))
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

# Extra per-section guidance, appended after the section rules. "" sends nothing, so a
# section falls back to FACT_SECTION_RULES / describe_line_rules() alone.
# The three below read "…your text…" until 2026-10-19 and were going to the model
# verbatim on every live call (bugs_audit_fixed.md #111 N2) - offline could not show it,
# because the fixture answers whatever the prompt says. Emptied, not deleted: the keys
# stay as the TODO they were.
SECTION_PROMPTS = {
    SectionType.PROJECTS:     "",
    SectionType.SKILLS:       "",       # TODO (user): per-section writer guidance, if any
    SectionType.COURSEWORK:   "",       # TODO (user)
    SectionType.ACHIEVEMENTS: "",       # TODO (user)
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
        # The verdicts judged the draft this one replaces. Document clears them, not the Supervisor,
        # so a redo can read them first (D3). Left in place, decide() would send the new draft
        # straight back here before Critic or Verifier saw it (audit #2).
        "critique": None, "verifier_report": None,
        "prompt_versions": all_prompt_versions([PLANNER, WRITER]),
        "stage": Stage.CRITIC,
    }