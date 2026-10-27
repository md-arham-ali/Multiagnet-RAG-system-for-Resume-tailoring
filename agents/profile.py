"""
Profile Agent - Groq llama-3.3-70b-versatile.

node() retrieves evidence per requirement and asks gap questions where the
evidence is thin. enrich() takes the answers back from gate 2 and stores them.
Prompts: prompts/profile/system.yaml, prompts/profile_enrich/system.yaml.
"""

from __future__ import annotations

import threading

import config

from agents.base import structured_call
from utils.prompt_loader import all_prompt_versions
from utils.trace import log
from state.state import ProfileAssessment, Support, GapQuestion, ProfileEnrichment
from learning.profile_store import save_gap_answers

from state.state import GraphState, ProfileBlock, Stage

# #73 item 8. Built on first use, not at import. Importing this module imports the
# graph, so a module-level `Retriever(reranker=Reranker())` loaded PyTorch and a
# cross-encoder - about 20s cold and several hundred MB - in every test run, every
# CLI driver and every script, including all the ones that never retrieve anything.
# The API worker has worked around it with a lazy import since 2026-08-19; this
# removes the reason for the workaround. The imports move inside too: reaching
# `vectordb.retriever` at module scope is itself what pulls sentence-transformers in.
#
# Tests set `_retriever` directly (nine places) and still win: _get_retriever()
# returns whatever is here whenever it is not None.
_retriever = None
_retriever_lock = threading.Lock()


def _get_retriever():
    """The process's retriever, built once on the first retrieval.

    Double-checked: the lock is paid for once, not on every requirement, and two
    LangGraph nodes entering together still build one model rather than two.
    """
    global _retriever
    if _retriever is None:
        with _retriever_lock:
            if _retriever is None:
                from vectordb.models import get_reranker
                from vectordb.retriever import Retriever

                _retriever = Retriever(reranker=get_reranker())   # the process's one cross-encoder (#43)
    return _retriever

def _key(text: str) -> str:
    """Normalise a requirement string so the model's echo matches ours.

    Twin of agents/matching.py::_key. Duplicated rather than imported: agent
    modules do not depend on each other today. Worth one shared helper if a
    third agent needs it.
    """
    return " ".join((text or "").split()).lower()


# What the grader is shown for a requirement retrieval found nothing for. Same
# wording as agents/matching.py's, and prompts/profile/system.yaml v4 names it.
NOTHING_RETRIEVED = "- (no evidence retrieved)"

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

    # #57 item 3: requirements=None reached the retrieval loop as a bare
    # AttributeError, and an empty list still paid for an LLM call on an empty
    # prompt. jd_analysis now refuses both upstream; this is the guard for
    # run_agent.py's custom chains, which can enter this node directly.
    if state.requirements is None:
        raise ValueError(
            "profile.node needs state.requirements; jd_analysis runs before it. "
            "(Running this node alone? Pass a Requirements object in the state.)"
        )
    if not state.requirements.requirements:
        return {"evidence": [], "gap_questions": [], "stage": Stage.PROFILE_ENRICH}

    evidence = []
    seen: set[str] = set()
    by_req: dict[str, list[str]] = {}

    # Once, here: the first retrieval of the run pays for the models, and the
    # no-requirements return above never does.
    retriever = _get_retriever()

    for req in state.requirements.requirements:
        # to retrieve profie blocks 
        by_req[req.text]=[]
        for types,n in QUOTAS:
            hits = retriever.hybrid(
            "profile", req.text, k=n,
            where={"type": {"$in": types}},
            )

            for h in hits:
                # One block can hit for several requirements. by_req still gets it
                # (the LLM grades per requirement), evidence only once.
                # Small pools like gap_answer would repeat on every requirement.
                if h.id not in seen:
                    seen.add(h.id)
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
        # #73 item 4. A requirement nothing was retrieved for used to arrive as
        # "EVIDENCE:" and then nothing, which reads like a formatting slip rather
        # than a finding - and the model still has to return a grade, so it grades
        # the requirement's wording instead of the evidence. A strong grade there
        # asks no gap question, so the one requirement with no support behind it is
        # the one the human is never asked about. Said explicitly, in the same words
        # agents/matching.py uses, so the two graders read the same sentence.
        lines = "\n".join(f"- {d}" for d in docs) if docs else NOTHING_RETRIEVED
        blocks.append(f"REQUIREMENT: {req_text}\nEVIDENCE:\n{lines}")
    prompt_text = "\n\n".join(blocks)
    assessment = structured_call("profile", prompt_text, ProfileAssessment, fake_json=_FAKE_JSON)

    # Loop OUR requirements and look the model's grade up by normalised key -
    # never loop the model's list (#79 item 2, #57 item 2, bugs.md #14, and the
    # pattern agents/matching.py::_reconcile already follows). Two faces, one
    # fix: a requirement the model SKIPPED kept its gap question (it used to
    # vanish silently), and a requirement the model INVENTED can no longer
    # become a real gate-2 question, because it is not in state to be asked for.
    graded = {_key(a.requirement): a for a in assessment.assessments}
    gap_questions = []
    for req in state.requirements.requirements:
        a = graded.get(_key(req.text))
        if a is None:
            # Not graded at all. Treat as unsupported and say so, rather than
            # dropping the requirement out of the interview without a word.
            gap_questions.append(GapQuestion(
                requirement=req.text,
                question=f"The profile search found nothing clearly covering "
                         f"\"{req.text}\". Do you have experience with it? If so, "
                         f"where, and what did you do?",
            ))
            continue
        if a.support != Support.STRONG and a.gap_question:
            # The requirement text is OURS; only the question is the model's.
            gap_questions.append(GapQuestion(requirement=req.text, question=a.gap_question))
    return {
        "evidence": evidence,
        "gap_questions": gap_questions,
        "prompt_versions": all_prompt_versions(["profile"]),
        "stage": Stage.PROFILE_ENRICH,
                }
    # raise NotImplementedError("profile.node is a scaffold — graph wiring is TODO.")

# Set True by a caller that has pointed save_gap_answers at a disposable store
# and wants the offline round trip exercised anyway (scripts/check_system.py
# does exactly that, and it drives the graph, so it cannot pass an argument to
# this node). Left False, an offline run never writes to the profile store.
SAVE_OFFLINE = False


def enrich(state: GraphState) -> dict:
    """Polish the gap answers from gate 2 and save them to the profile store."""
    if not state.gap_answers:
        return {"stage": Stage.MATCHING} 

    # #73 item 5. A skipped question comes back as "" - gate 2's form has no
    # minimum length - and every one of them used to be sent. That is not only a
    # call paid for to polish nothing: the model is handed "ANSWER:" and nothing,
    # is asked for storable evidence, and what it writes is saved. Since the
    # 2026-10-09 decision trusts the polished text (DEC-051's one exception),
    # nothing downstream would catch an answer the candidate never gave. A blank
    # is not an answer, so it never reaches the model.
    prompt_parts =[]
    skipped = 0
    for requirement, answer in state.gap_answers.items():
        if not (answer or "").strip():
            skipped += 1
            continue
        questions = [q.question for q in state.gap_questions if q.requirement == requirement]
        question_text = questions[0] if questions else "No question found"
        prompt_parts.append(
            f"REQUIREMENT: {requirement}\nQUESTION: {question_text}\nANSWER: {answer}\n"
        )

    if skipped:
        log(f"profile_enrich: {skipped} of {len(state.gap_answers)} gap answer(s) left blank, not sent")
    if not prompt_parts:
        # Every question skipped. The interview happened and produced nothing;
        # that is a valid outcome, not an error - Matching simply grades without
        # the answers. Same shape as the no-answers return above.
        return {"stage": Stage.MATCHING}

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

    # Offline, `content` is the fixture's answer, not the candidate's. Saving it
    # puts invented text in knowledge_base/profile/manual_entries.json and the
    # profile collection, where EVERY later run retrieves it as real evidence -
    # the 2026-08-26 session had to restore the KB by hand (#73 item 6). The
    # blocks still go into this run's state, so the rest of the pipeline is
    # unchanged; only the write to the store is skipped, the same rule
    # final_review.close_run already applies to the learning store.
    if SAVE_OFFLINE or not config.fake_llm_active():
        save_gap_answers(entries, run_id=state.run_id)
    else:
        log(f"profile_enrich: offline run, {len(entries)} answer(s) NOT saved to the profile store")
    return {"evidence": new_blocks, "prompt_versions": all_prompt_versions(["profile_enrich"]),
            "stage": Stage.MATCHING}