"""
Profile Agent - Groq llama-3.3-70b-versatile.

node() retrieves evidence per requirement and asks gap questions where the
evidence is thin. enrich() takes the answers back from gate 2 and stores them.
Prompts: prompts/profile/system.yaml, prompts/profile_enrich/system.yaml.
"""

from __future__ import annotations

from agents.base import structured_call
from state.state import ProfileAssessment, Support, GapQuestion, GapAnswerPolish, ProfileEnrichment
from learning.profile_store import save_gap_answers

from state.state import GraphState, ProfileBlock, Stage
from vectordb.retriever import Retriever
from vectordb.reranker import Reranker

_retriever = Retriever(reranker=Reranker()) 

QUOTAS = [
    (["project", "work_experience"], 3),   
    (["skill"], 2),                        
    (["achievement", "coursework"], 1),    
    (["gap_answer"], 1),
]

_FAKE_JSON = (
    '{"assessments": ['
    ' {"requirement": "Python", "support": "strong"},'
    ' {"requirement": "SQL", "support": "partial",'
    '  "gap_question": "Which projects did you write production SQL for, and at what data scale?"},'
    ' {"requirement": "ETL pipelines", "support": "none",'
    '  "gap_question": "Have you built or maintained an ETL pipeline end to end? Describe one."}'
    ']}'
)

_ENRICH_FAKE_JSON = (
    '{"polished": [{"requirement": "SQL", '
    '"gap_question": "Which projects did you write production SQL for?", '
    '"answer": "yeah i used sql a lot for reports at my last job", '
    '"polished_answer": "Wrote SQL queries for business reporting."}]}'
)

def node(state: GraphState) -> dict:
    """
    LangGraph node. Retrieve evidence per requirement (quota'd, category
    filtered), grade each one, emit a gap question where support is weak.
    Ends at PROFILE_ENRICH, not MATCHING - gate 2 and enrich() sit in between.
    """

    evidence = []
    by_req: dict[str, list[str]] = {}

    for req in state.requirements.requirements:
        # to retrieve profie blocks 
        by_req[req.text]=[]
        for types,n in QUOTAS:
            hits = _retriever.hybrid(
            "profile", req.text, k=n,
            where={"type": {"$in": types}},
            )

            for h in hits:
                evidence.append(ProfileBlock(
                    source_id = h.id,
                    content=h.document,
                    category=h.metadata.get("type"),
                    skills=[]
                ))
                by_req[req.text].append(h.document)

    # by_req -> one readable block per requirement for the LLM
    blocks = []
    for req_text, docs in by_req.items():
        lines = "\n".join(f"- {d}" for d in docs)
        blocks.append(f"REQUIREMENT: {req_text}\nEVIDENCE:\n{lines}")
    prompt_text = "\n\n".join(blocks)
    assessment = structured_call("profile", prompt_text, ProfileAssessment, fake_json=_FAKE_JSON)
    gap_questions = [
        GapQuestion(requirement=a.requirement, question=a.gap_question)
        for a in assessment.assessments
        if a.support != Support.STRONG and a.gap_question
    ]
    return {
        "evidence": evidence,
        "gap_questions": gap_questions,
        "stage": Stage.PROFILE_ENRICH,
                }
    # raise NotImplementedError("profile.node is a scaffold — graph wiring is TODO.")

def enrich(state: GraphState) -> dict:
    """Polish the gap answers from gate 2 and save them to the profile store."""
    if not state.gap_answers:
        return {"stage": Stage.MATCHING} 

    prompt_parts =[]
    for requirement, answer in state.gap_answers.items():
        questions = [q.question for q in state.gap_questions if q.requirement == requirement]
        question_text = questions[0] if questions else "No question found"
        prompt_parts.append(
            f"REQUIREMENT: {requirement}\nQUESTION: {question_text}\nANSWER: {answer}\n"
        )

    prompt = "\n\n".join(prompt_parts)

    result = structured_call(
        "profile_enrich", 
        prompt,
        ProfileEnrichment,
        fake_json = _ENRICH_FAKE_JSON,
        )

    # An empty polished_answer is MEANINGFUL, not missing. It is how the prompt
    # says "declined / too vague / hasn't done this". Skip those so a refusal
    # never turns into CV evidence, this run or any future one.
    new_blocks = []
    entries = []
    for p in result.polished:
        if not (p.polished_answer or "").strip():
            continue
        new_blocks.append(ProfileBlock(
            source_id=f"gap_answer:{p.requirement}",
            content=p.polished_answer,
            category="gap_answer",
            skills=[],
        ))
        entries.append({
            "requirement": p.requirement,
            "question": p.gap_question,
            "raw_answer": p.answer,
            "content": p.polished_answer,
            "category": "gap_answer",
            "skills": [],
        })

    save_gap_answers(entries, run_id=state.run_id)
    return {"evidence": new_blocks, "stage": Stage.MATCHING}