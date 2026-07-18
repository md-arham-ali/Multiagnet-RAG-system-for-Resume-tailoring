"""
Supervisor — Groq llama-3.3-70b-versatile.

LangGraph's supervisor pattern (start from the langgraph-supervisor prebuilt or
hand-roll the routing). Owns: agent dispatch order, Critic loop-backs (capped by
max_revisions), Verifier-fail loop-backs, and context-injection control
(recency / relevance / size-cap). Prompt: prompts/supervisor/system.yaml.
"""

from __future__ import annotations

from state.state import GraphState, Stage , Verdict, VerifyStatus

from langgraph.graph import StateGraph, START, END
from agents import jd_analysis, profile, matching, document, critic, verifier, evaluation

NEXT_STAGE = {
    Stage.JD_ANALYSIS : "jd_analysis",
    Stage.PROFILE : "profile",
    Stage.MATCHING: "matching",
    Stage.DOCUMENT: "document",
    Stage.CRITIC: "critic",
    Stage.VERIFIER: "verifier",
    Stage.EVALUATION: "evaluation",
}

"""
Doubt : Because in LangGraph, the decision of where to go next doesn't live inside the node — it lives on the edge leaving it
"""

def route(state: GraphState) -> str:
    """
    Conditional-edge router. IT returns the name of the next node based on
    state.stage, the Critic verdict (revise -> document, capped), and the Verifier
    status (fail -> document). This is the conditional-edge logic for Critic
    dispatch + loop-backs (Build.md #1).

    Status : COMPLETED
    """
    # default linear order; loop-backs are the interesting part
    if state.critique and state.critique.verdict == Verdict.REVISE and state.revision_count < state.max_revisions:
        return "document"          # Critic said revise -> redo the draft
    if state.verifier_report and state.verifier_report.status == VerifyStatus.FAIL and state.revision_count < state.max_revisions:
        return "document"          # Verifier failed -> redo
    # otherwise advance to the next stage in the pipeline
    return NEXT_STAGE.get(state.stage, "END")
    # raise NotImplementedError("supervisor.route is a scaffold - routing logic is TODO.")

def supervisor_node(state: GraphState) -> dict:
    """The hub. Does no work now - routing happens on the edge (add_conditional_edges).
    Later: log the decision, bump revision_count on loop-backs, decide inject_critic functions to be added."""
    return {}

def build_graph(checkpointer=None):
    """
    Assemble the StateGraph: nodes for each agent, conditional edges via route(),
    interrupt() human gates (4), and a Postgres checkpointer for durable pauses.
    
    Build graph according to requirement and condition.
    """

    graph = StateGraph(GraphState)
    graph.add_node("supervisor",supervisor_node)
    graph.add_edge(START, "supervisor")
    graph.add_node("jd_analysis", jd_analysis.node)
    graph.add_edge("jd_analysis", "supervisor")
    graph.add_node("profile", profile.node)
    graph.add_edge("profile", "supervisor")
    graph.add_node("matching", matching.node)
    graph.add_edge("matching", "supervisor")
    graph.add_node("document", document.node)
    graph.add_edge("document", "supervisor")
    graph.add_node("critic", critic.node)
    graph.add_edge("critic", "supervisor")
    graph.add_node("verifier", verifier.node)
    graph.add_edge("verifier", "supervisor")
    graph.add_node("evaluation", evaluation.node)
    graph.add_edge("evaluation", "supervisor")
    graph.add_conditional_edges("supervisor", route, {
    "jd_analysis": "jd_analysis",
    "profile": "profile",
    "matching": "matching",
    "document": "document",
    "critic": "critic",
    "verifier": "verifier",
    "evaluation": "evaluation",
    "END": END,
    })

    
    
    return graph.compile(checkpointer=checkpointer)

