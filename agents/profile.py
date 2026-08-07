"""
Profile Agent - Groq llama-3.3-70b-versatile.

Retrieves relevant profile blocks for the requirements and runs the interactive
gap-interview (a human gate via interrupt()) to enrich the profile store.
Prompt: prompts/profile/system.yaml.
"""

from __future__ import annotations

from agents.base import structured_call
from state.state import ProfileAssessment, Support, GapQuestion

from state.state import GraphState, ProfileBlock, Stage
from vectordb.retriever import Retriever
from vectordb.reranker import Reranker

_retriever = Retriever(reranker=Reranker()) 

QUOTAS = [
    (["project", "work_experience"], 3),   
    (["skill"], 2),                        
    (["achievement", "coursework"], 1),    
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

def node(state: GraphState) -> dict:
    """
    LangGraph node. 
      - retrieve profile blocks per requirement (vector store, category filter),
      - identify gaps -> emit gap_questions, interrupt() for human answers,
      - upsert answers to the profile store,
      - return {"evidence": ..., "gap_questions": ..., "stage": Stage.MATCHING}.
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

    # 1. Turn by_req into readable text, e.g. for each requirement:
    # "REQUIREMENT: SQL\nEVIDENCE:\n- <doc1>\n- <doc2>\n..."
    #    joined with blank lines.
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
    # 2. assessment = structured_call("profile", <that text>, ProfileAssessment, fake_json=_FAKE_JSON)
    # 3. gap_questions = [
    #        GapQuestion(requirement=a.requirement, question=a.gap_question)
    #        for a in assessment.assessments
    #        if a.support != Support.STRONG and a.gap_question
    #    ]
    # 4. return {"evidence": evidence, "gap_questions": gap_questions, "stage": Stage.MATCHING}


    return {
        "evidence": evidence,
        "gap_questions": gap_questions,
        "stage": Stage.MATCHING,
                }
    # raise NotImplementedError("profile.node is a scaffold — graph wiring is TODO.")
