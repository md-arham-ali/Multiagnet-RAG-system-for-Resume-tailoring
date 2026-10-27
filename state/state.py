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
    """How well the evidence backs a requirement."""

    STRONG = "strong"
    PARTIAL = "partial"
    NONE = "none"


class Verdict(str, Enum):
    """A reviewer's overall call: accept the draft, or send it back."""

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
    """One atomic thing the job asks of the candidate."""

    text: str = Field(description="The requirement itself, one atomic item, in the JD's own words.")
    # must_have | nice_to_have. Free string, not an enum: a spelling variant reads as
    # must_have and hides an unmet requirement (bugs_audit_fixed.md #58).
    kind: str = Field("must_have", description=(
        "Exactly 'must_have' or 'nice_to_have' - no other word and no other spelling. "
        "The JD's own language decides: required/must/essential is must_have, "
        "preferred/plus/bonus is nice_to_have. When it is ambiguous, use must_have."))
    category: Optional[str] = Field(None, description=(
        "Exactly one of 'hard_skill', 'soft_skill', 'qualification' (education, "
        "certification, years of experience) or 'responsibility'. Null if none fits."))


class Requirements(BaseModel):
    """Everything a job description asks for, extracted and typed.

    Return ONE object with these four fields and no others. Everything the JD asks of
    the candidate goes in `requirements`: there is no separate field for skills,
    responsibilities or qualifications.
    """

    role_title: Optional[str] = Field(None, description="The job title as the JD gives it, or null.")
    seniority: Optional[str] = Field(None, description=(
        "The level as the JD gives it ('Senior', 'Mid-level', ...), or null."))
    requirements: list[Requirement] = Field(default_factory=list, description=(
        "Every requirement in the JD, one entry each, split into atomic items. "
        "Be exhaustive but do not duplicate."))
    keywords: list[str] = Field(default_factory=list, description=(
        "The ATS terms exactly as the JD phrases them - keep casing and multi-word "
        "terms. A normalised form may be added alongside, never instead."))


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
    """One requirement, graded against the evidence retrieved for it."""

    requirement: str = Field(description="Copied from the input, unchanged.")
    support: Support = Field(description=(
        "How well the evidence shown backs this requirement. Judge only from that "
        "evidence; never assume experience that is not there."))
    gap_question: Optional[str] = Field(None, description=(
        "ONE short, answerable question that would close the gap, when support is "
        "partial or none. Null otherwise. Never ask about something the evidence covers."))


class ProfileAssessment(BaseModel):
    """The Profile agent's grading pass over every requirement.

    Return ONE object with a single field `assessments`, holding one entry per
    requirement. Never return a separate object per requirement, and never a bare list.
    """

    assessments: list[RequirementAssessment] = Field(default_factory=list, description=(
        "One entry per requirement given, graded once each. Do not add requirements."))

# -----------------------------------------------------------------------------
# Matching artifacts
# -----------------------------------------------------------------------------
# Deliberately narrower than MatchResult: the model is never asked for the
# requirement's kind, because the caller already holds it on state.requirements.
# Structured output validates shape, never correspondence to the input, so
# anything already known is filled from state and only the judgement is read
# back (bugs.md #14). The docstring below is the tool description the provider
# sees, so it speaks to the model, not to us (bugs_audit_fixed.md #111).
class MatchGrade(BaseModel):
    """One requirement, graded against the profile evidence supplied with it."""

    requirement_id: str = Field("", description=(
        "The label this requirement carries in the list given, copied exactly: 'R1', "
        "'R2', ... It is how the grade is paired back to its requirement, so copy it "
        "character for character and never invent a label that was not in the list."))
    requirement: str = Field(description="Copied from the list given, unchanged.")
    support: Support = Field(description=(
        "How well the supplied evidence backs this requirement. Never upgrade a "
        "partial match to strong to make the candidate look better."))
    evidence_ids: list[str] = Field(default_factory=list, description=(
        "Ids of the evidence blocks that actually support it, best first. Cite only "
        "ids present in the evidence given: an invented id is dropped, and a grade "
        "resting only on invented ids is downgraded to 'none'. Empty for 'none'."))
    justification: str = Field("", description=(
        "One short line, anchored to the blocks cited above."))


class MatchAssessment(BaseModel):
    """The Matching agent's grading pass over every requirement.

    Return ONE object with a single field `matches`, holding one entry per
    requirement. Never return a separate object per requirement, and never a bare list.
    You are not asked for an overall fit score or a coverage percentage: those are
    computed from these grades so they stay reproducible.
    """

    matches: list[MatchGrade] = Field(default_factory=list, description=(
        "One entry per requirement given, graded once each. Do not add requirements "
        "that are not in the list."))


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
    """What an edit does to the line it names. Only 'replace' is built today."""

    REPLACE = "replace"   # rewrite the text of an existing bullet/item
    INSERT = "insert"     # add a new bullet/item after target_id
    DROP = "drop"         # remove a bullet/item


class EditPurpose(str, Enum):
    """Why an edit was made. The last two belong to later review rounds only."""

    COVERS_REQUIREMENT = "covers_requirement"   # makes a requirement the line serves visible
    ADDS_KEYWORD = "adds_keyword"               # works in a JD keyword the evidence supports
    QUANTIFIES = "quantifies"                   # states a result with a figure the evidence has
    FIXES_CRITIQUE = "fixes_critique"
    FIXES_VERIFIER = "fixes_verifier"


class Edit(BaseModel):
    """One better line for one CV line you were asked to write."""

    # replace/drop: the node being changed. insert: the node the new one goes AFTER.
    target_id: str = Field(description=(
        "The line's id exactly as shown in square brackets, without the brackets. It "
        "must be one of the lines you were asked to write; any other id is dropped."))
    action: EditAction = Field(description="Always 'replace'.")
    # The schema cannot say 'required for replace/insert' on its own - a missing
    # new_text validates here and fails downstream (bugs_audit_fixed.md #111 N6).
    new_text: Optional[str] = Field(None, description=(
        "The new line, following the section rules. Required for 'replace'. Use only "
        "facts from the current line and the evidence you cite, and never a figure "
        "that is not in one of them."))
    evidence_ids: list[str] = Field(default_factory=list, description=(
        "Ids of the records this new line rests on: at least one, taken only from the "
        "EVIDENCE or AVAILABLE EVIDENCE blocks. An edit citing nothing is dropped."))
    purpose: EditPurpose = Field(description=(
        "Why this edit was made. Use covers_requirement, adds_keyword or quantifies; "
        "the other two are for later review rounds."))
    reason: str = Field("", description="One short line: what you changed and why.")


class DocumentPatchSet(BaseModel):
    """The lines you improved in ONE CV section.

    Return ONE object with a single field `edits`. Never return a bare list.
    """

    # An empty list is valid: "this CV already fits".
    edits: list[Edit] = Field(default_factory=list, description=(
        "One edit per line you can improve truthfully, at most one per line. Leave a "
        "line out rather than force an edit: the original is kept, which is better. An "
        "empty list is a valid answer."))

class EditVerdict(str, Enum):
    """How much work one CV section, entry or line needs."""

    KEEP = "keep"        # unrelated to the job, or already strong
    REFINE = "refine"    # backed, but under-states it; its children get graded next
    REWRITE = "rewrite"  # backed, but aimed at the wrong thing; replaced whole, children not graded

class NodeVerdict(BaseModel):
    """One graded node of the CV tree."""

    node_id:str = Field(description=(
        "Copied exactly as it appears between the square brackets, without the brackets."))
    verdict: EditVerdict = Field(description=(
        "How much work this node needs. A node you leave out counts as 'keep'."))
    reason: str = Field("", description=(
        "A compact line, only on 'refine' or 'rewrite'. It is cleared on a 'keep'."))

class VerdictSet(BaseModel):
    """The plan: every CV node you graded.

    Return ONE object with a single field `verdicts`. Never return a separate object
    per node, and never a bare list.
    """

    verdicts: list[NodeVerdict] = Field(default_factory=list, description=(
        "One entry per node you graded, from the nodes you were shown."))


# -----------------------------------------------------------------------------
# Critic artifacts
# -----------------------------------------------------------------------------
class CritiqueItem(BaseModel):
    """One finding, on one dimension of the rubric you were given."""

    rubric_item: str = Field(description=(
        "The name of the dimension, copied from the rubric given for THIS call. A "
        "finding on anything else is dropped by code."))
    # info | minor | major. Free string, not an enum: any other word reads as "info",
    # so a real problem labelled "critical" lands as the mildest kind of note
    # (bugs_audit_fixed.md #111 N5).
    severity: str = Field("info", description=(
        "Exactly one of 'info', 'minor', 'major'. These three words are the whole "
        "vocabulary; any other word is read as 'info'. Reserve 'major' for a claim "
        "the evidence shown does not back."))
    location: Optional[str] = Field(None, description=(
        "Where in the document the finding is - quote the line or the evidence id."))
    instruction: Optional[str] = Field(None, description=(
        "For a 'revise', what the Document agent should change and why, concrete "
        "enough to act on directly. No vague advice."))


class Critique(BaseModel):
    """Your review of the document against the rubric given for this call.

    Return ONE object with `verdict` and `items`.
    """

    verdict: Verdict = Field(description=(
        "'revise' or 'pass'. This drives the Supervisor's loop-back. A 'revise' needs "
        "at least one item, and a 'pass' must carry no 'major' item: code corrects "
        "both, and logs the correction."))
    items: list[CritiqueItem] = Field(default_factory=list, description=(
        "One entry per rubric dimension you have a finding on. Empty is valid."))


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
    # int | None: an unreadable prompt records None rather than failing the whole
    # record (#77 item 3). A key that is missing entirely means "never asked".
    prompt_versions: dict[str, Optional[int]] = Field(default_factory=dict)
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
    """One gap-interview answer, rewritten as a storable profile block."""

    requirement: str = Field(description=(
        "Copied exactly from the input - this is how the caller matches your output "
        "back to the right gap."))
    gap_question: str = Field(description="Copied exactly from the input.")
    answer: str = Field(description="Copied exactly from the input (the candidate's raw words).")
    polished_answer: Optional[str] = Field(None, description=(
        "The rewritten evidence text: third person, past tense, 1-3 sentences, keeping "
        "every technology, number and outcome the candidate stated and adding none. "
        "Null when they declined, were too vague, or said they have not done this - "
        "null means 'store nothing', never a restatement of the question."))

class ProfileEnrichment(BaseModel):
    """The Profile Enrichment agent's rewrite of every gap answer given.

    Return ONE object with a single field `polished`, holding one entry per gap in the
    input. Never return a separate object per gap, and never a bare list.
    """

    polished: list[GapAnswerPolish] = Field(default_factory=list, description=(
        "One entry per gap in the input."))
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
    # Whose account this run belongs to (p-<8hex>). Set once at run start and
    # never rewritten by a node. The live carrier for scoped reads is
    # config.current_profile_id() (a ContextVar, visible on LangGraph's pool
    # threads); this field is the checkpointed copy, so a run resumed in a new
    # process can restore that scope from its own state instead of guessing.
    profile_id: Optional[str] = None
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

    # {agent: prompt version}, contributed by each node AS IT CALLS its model and
    # merged with operator.or_ (later writes win for the same agent, which is what
    # a redo should do). Evaluation reports this map instead of re-reading prompts
    # off disk once the run ends, which credited whatever was on disk THEN - a
    # different version if the process restarted while the run waited at gate 4
    # (#77 item 3). Riding in the state means it survives that restart.
    prompt_versions: Annotated[dict[str, Optional[int]], operator.or_] = Field(default_factory=dict)
    

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


