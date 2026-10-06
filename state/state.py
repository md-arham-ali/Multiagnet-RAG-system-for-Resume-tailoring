"""
The graph's State schema (Build.md #2). Every agent reads and writes this one
typed object, so it doubles as the audit trail: one artifact per agent below.

Annotated reducers (add_messages, operator.add) are honoured by LangGraph.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Optional, Literal

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
import operator


# -----------------------------------------------------------------------------
# Enums - these drive Supervisor routing
# -----------------------------------------------------------------------------
class Stage(str, Enum):
    JD_ANALYSIS = "jd_analysis"
    PROFILE = "profile"
    MATCHING = "matching"
    DOCUMENT = "document"
    CRITIC = "critic"
    VERIFIER = "verifier"
    EVALUATION = "evaluation"
    DONE = "done"
    PROFILE_ENRICH = "profile_enrich"
    CV_LINK = "cv_link" # not an agente, but a node that links to the CV handling pipeline.


class Support(str, Enum):
    STRONG = "strong"
    PARTIAL = "partial"
    NONE = "none"


class Verdict(str, Enum):
    PASS = "pass"
    REVISE = "revise"


class VerifyStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"


class ClaimLabel(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"


# -----------------------------------------------------------------------------
# JD Analysis artifacts
# -----------------------------------------------------------------------------
class Requirement(BaseModel):
    text: str
    kind: str = "must_have"  # must_have | nice_to_have
    category: Optional[str] = None  # hard_skill | soft_skill | qualification | responsibility


class Requirements(BaseModel):
    role_title: Optional[str] = None
    seniority: Optional[str] = None
    requirements: list[Requirement] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)  # exact JD phrasing for ATS


# -----------------------------------------------------------------------------
# Profile / evidence artifacts
# -----------------------------------------------------------------------------
class ProfileBlock(BaseModel):
    source_id: str
    content: str
    category: Optional[str] = None
    skills: list[str] = Field(default_factory=list)


def merge_evidence(left: list["ProfileBlock"], right: list["ProfileBlock"]) -> list["ProfileBlock"]:
    """
    Reducer for `evidence`: append, but never the same block twice.

    Plain operator.add was correct only while nothing re-entered profile.node(),
    which returns the WHOLE list every time - so one rejected gate 2 (bugs.md
    #10 made that reachable) concatenated a full duplicate set, and repetition
    reads as stronger support to whatever grades it next (bugs.md #8, same
    failure as #13 one scope up).

    Keyed on source_id, the same key #13's in-node guard uses.
    """
    seen = {block.source_id for block in left}
    merged = list(left)
    for block in right:
        if block.source_id in seen:
            continue
        seen.add(block.source_id)
        merged.append(block)
    return merged


class GapQuestion(BaseModel):
    requirement: str
    question: str

class RequirementAssessment(BaseModel):
    requirement: str
    support: Support
    gap_question: Optional[str] = None


class ProfileAssessment(BaseModel):
    assessments: list[RequirementAssessment] = Field(default_factory=list)

# -----------------------------------------------------------------------------
# Matching artifacts
# -----------------------------------------------------------------------------
class MatchGrade(BaseModel):
    """One requirement as the model graded it - the judgement half only.

    Deliberately narrower than MatchResult: the model is never asked for the
    requirement's kind, because the caller already holds it on state.requirements.
    Structured output validates shape, never correspondence to the input, so
    anything already known is filled from state and only the judgement is read
    back (bugs.md #14).
    """

    requirement: str
    support: Support
    evidence_ids: list[str] = Field(default_factory=list)
    justification: str = ""


class MatchAssessment(BaseModel):
    """The Matching agent's one LLM call. Same shape as ProfileAssessment."""

    matches: list[MatchGrade] = Field(default_factory=list)


class MatchResult(BaseModel):
    requirement: str
    kind: str
    support: Support
    evidence_ids: list[str] = Field(default_factory=list)
    justification: str = ""


class FitReport(BaseModel):
    matches: list[MatchResult] = Field(default_factory=list)
    overall_fit: float = 0.0
    must_have_coverage: float = 0.0
    unmet_must_haves: list[str] = Field(default_factory=list)
    ranked_evidence_ids: list[str] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# Document artifacts
# -----------------------------------------------------------------------------
class Document(BaseModel):
    kind: str  # cv | cover_letter
    content: str
    template_id: Optional[str] = None
    unsupported_flags: list[str] = Field(default_factory=list)


class EditAction(str, Enum):
    REPLACE = "replace"   # rewrite the text of an existing bullet/item
    INSERT = "insert"     # add a new bullet/item after target_id
    DROP = "drop"         # remove a bullet/item


class EditPurpose(str, Enum):
    COVERS_REQUIREMENT = "covers_requirement"
    ADDS_KEYWORD = "adds_keyword"
    QUANTIFIES = "quantifies"
    FIXES_CRITIQUE = "fixes_critique"
    FIXES_VERIFIER = "fixes_verifier"


class Edit(BaseModel):
    # replace/drop: the node being changed. insert: the node the new one goes AFTER.
    target_id: str
    action: EditAction
    new_text: Optional[str] = None        # required for replace/insert, None for drop
    evidence_ids: list[str] = Field(default_factory=list)  # profile ids this edit rests on
    purpose: EditPurpose
    reason: str = ""


class DocumentPatchSet(BaseModel):
    # An empty list is valid: "this CV already fits".
    edits: list[Edit] = Field(default_factory=list)

class EditVerdict(str, Enum):
    KEEP = "keep"        # unrelated to the job, or already strong
    REFINE = "refine"    # backed, but under-states it; its children get graded next
    REWRITE = "rewrite"  # backed, but aimed at the wrong thing; replaced whole, children not graded

class NodeVerdict(BaseModel):
    node_id:str
    verdict: EditVerdict
    reason: str = ""

class VerdictSet(BaseModel):
    verdicts: list[NodeVerdict] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# Critic artifacts
# -----------------------------------------------------------------------------
class CritiqueItem(BaseModel):
    rubric_item: str
    severity: str = "info"  # info | minor | major
    location: Optional[str] = None
    instruction: Optional[str] = None


class Critique(BaseModel):
    verdict: Verdict
    items: list[CritiqueItem] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# Verifier artifacts
# -----------------------------------------------------------------------------
class ClaimCheck(BaseModel):
    claim: str
    label: ClaimLabel
    evidence_id: Optional[str] = None


class DoNotClaimHit(BaseModel):
    text: str
    matched_entry: str
    location: Optional[str] = None


class VerifierReport(BaseModel):
    status: VerifyStatus
    claims: list[ClaimCheck] = Field(default_factory=list)
    do_not_claim_hits: list[DoNotClaimHit] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# Evaluation artifacts - go to the Learning Store after approval
# -----------------------------------------------------------------------------
class EvalRecord(BaseModel):
    role_type: Optional[str] = None
    retrieval_precision: Optional[float] = None
    ats_score: Optional[float] = None
    fit_score: Optional[float] = None
    generation_score: Optional[float] = None
    # Attribution: which prompt version + exemplars produced this run. Without
    # it a score that moves can't be traced to prompt vs exemplars vs model.
    prompt_versions: dict[str, int] = Field(default_factory=dict)
    learning_slice: list[str] = Field(default_factory=list)
    exemplar_worthy: bool = False


# -----------------------------------------------------------------------------
# Human gate feedback - 4 interrupt() pauses
# -----------------------------------------------------------------------------
class GateFeedback(BaseModel):
    gate: str
    decision: str  # approve | edit | reject
    feedback: Optional[str] = None
    edited_payload: Optional[dict[str, Any]] = None
    # Which revision round this answer belongs to (stamped by human_gate from
    # state.revision_count). The list is append-only, so the gate NAME alone
    # only answers "was this ever reviewed" - routing needs "was THIS draft
    # reviewed", and that is what the stamp gives it (bugs.md #11).
    revision: int = 0

class Compactfeedback(BaseModel):
    summary: str
    action_items: list[str] = Field(default_factory=list)
    severity: Literal["minor", "moderate", "blocking"] = "moderate"

# -----------------------------------------------------------------------------
# Profile Enrich 
# -----------------------------------------------------------------------------

class GapAnswerPolish(BaseModel):
    requirement: str
    gap_question: str
    answer: str
    polished_answer: Optional[str] = None

class ProfileEnrichment(BaseModel):
    polished: list[GapAnswerPolish] = Field(default_factory= list)
# -----------------------------------------------------------------------------
# Supervisor decision (Instructions.md #23)
# -----------------------------------------------------------------------------
class SupervisorDecision(BaseModel):
    next_node: str               # name of the next node to run (or "END")
    inject_critic: bool = False  # should the Critic review before proceeding?
    reason: str = ""             # why the Supervisor chose this (logged)
    # True when this dispatch redoes work already done - a Critic/Verifier
    # loop-back or a rejected gate. It is what costs a revision: the Supervisor
    # bumps revision_count and clears the verdicts that described the old draft.
    redo: bool = False

# -----------------------------------------------------------------------------
# CV_LINK node artifacts
# -----------------------------------------------------------------------------


class NodeKind(str, Enum):
    CV = "cv"
    SECTION = "section"
    ENTRY = "entry"      # one job / project / degree / position
    BULLET = "bullet"    # a "•" line under an entry
    ITEM = "item"        # one element of a flat section (a skill, a course, an award)


class SectionType(str, Enum):
    """What a section MEANS, whatever the CV calls it."""
    HEADER = "header"                    # name / location / contact lines
    EDUCATION = "education"
    EXPERIENCE = "experience"
    PROJECTS = "projects"
    COURSEWORK = "coursework"
    SKILLS = "skills"
    ACHIEVEMENTS = "achievements"
    RESPONSIBILITIES = "responsibilities"  # "Positions Of Responsibilities"
    OTHER = "other"                        # unrecognised title: kept, never dropped

class MatchStatus(str, Enum):
    """Score-only grading for now. `contradicted` needs the LLM pass, so it is not
    a status yet."""
    MATCHED = "matched"
    PARTIAL = "partial"
    UNMATCHED = "unmatched"


class CVNode(BaseModel):
    node_id: str                          # stable address from position, e.g. "experience.0.b2"
    kind: NodeKind
    section_type: SectionType             # inherited down the tree from the section
    depth: int                            # 0 cv, 1 section, 2 entry, 3 bullet/item
    parent_id: Optional[str] = None       # None only for the cv root
    title: str = ""                       # section heading, or an entry's name (first "|" field)
    text: str = ""                        # what is matched: repaired text of this line
    raw_text: str = ""                    # exactly what pypdf returned, kept for audit
    page: Optional[int] = None            # 0-based PDF page the line came from
    # An entry header like "Research Engineer|MLflow + dbt|Internship|Cobalt Analytics
    # Mar 2023 – Apr 2024" splits into named parts. Keys used so far: role, tech,
    # kind, org, date_range. Strings only, so a node flattens to Chroma metadata.
    attrs: dict[str, str] = Field(default_factory=dict)
    children: list["CVNode"] = Field(default_factory=list)

class CVTree(BaseModel):
    source_file: str                      # CV_test.pdf
    root: CVNode                          # kind == CV


class LineLink(BaseModel):
    """One CV node -> the profile record(s) it points to. The matcher's output."""
    node_id: str
    kind: NodeKind
    section_type: SectionType
    text: str
    status: MatchStatus
    # Chroma ids of the profile records, best first. Empty when unmatched.
    source_ids: list[str] = Field(default_factory=list)
    score: float = 0.0                    # best rerank score behind `status`

# -----------------------------------------------------------------------------
# Top-level graph state - the audit trail
# -----------------------------------------------------------------------------
class GraphState(BaseModel):
    # Conversation log (LangGraph append reducer).
    messages: Annotated[list, add_messages] = Field(default_factory=list)

    # Run metadata.
    run_id: Optional[str] = None
    stage: Stage = Stage.JD_ANALYSIS

    # Input.
    job_description: Optional[str] = None
    cv_path: Optional[str] = None

    # Per-agent artifacts (each is one node's output).
    requirements: Optional[Requirements] = None
    evidence: Annotated[list[ProfileBlock], merge_evidence] = Field(default_factory=list)
    gap_questions: list[GapQuestion] = Field(default_factory=list)
    gap_answers: dict[str, str] = Field(default_factory=dict)
    fit_report: Optional[FitReport] = None

    cv_tree: Optional[CVTree] =None
    line_links: list[LineLink] = Field(default_factory=list)
    
    document: Optional[Document] = None
    document_patches: Optional[DocumentPatchSet] = None

    document_plan: Optional[VerdictSet] = None    # call 1's resolved verdicts, reused on revision rounds
    document_plan_key: Optional[str] = None       # hash of the exact call that produced it

    critique: Optional[Critique] = None
    verifier_report: Optional[VerifierReport] = None
    eval_record: Optional[EvalRecord] = None
    active_rubric: Optional[str] = None # this is the rubric suprvisor is using. 
    

    # Control flow.
    # The Supervisor's last decision. route() reads next_node off this rather
    # than re-deriving it, which is what lets supervisor_node() change the state
    # the decision was made from (bump the count, clear the verdicts) without
    # deleting the very condition the dispatch was based on (bugs.md #18).
    supervisor_decision: Optional[SupervisorDecision] = None
    revision_count: int = 0
    max_revisions: int = 2
    gate_feedback: Annotated[list[GateFeedback], operator.add] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}


