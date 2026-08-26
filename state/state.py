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

    # Per-agent artifacts (each is one node's output).
    requirements: Optional[Requirements] = None
    evidence: Annotated[list[ProfileBlock], operator.add] = Field(default_factory=list)
    gap_questions: list[GapQuestion] = Field(default_factory=list)
    gap_answers: dict[str, str] = Field(default_factory=dict)
    fit_report: Optional[FitReport] = None
    document: Optional[Document] = None
    critique: Optional[Critique] = None
    verifier_report: Optional[VerifierReport] = None
    eval_record: Optional[EvalRecord] = None

    # Control flow.
    revision_count: int = 0
    max_revisions: int = 2
    gate_feedback: Annotated[list[GateFeedback], operator.add] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}
