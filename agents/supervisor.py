"""
Supervisor - the hub. Hand-rolled routing, no LLM.

Owns dispatch order, the human gates, Critic revise loop-backs and Verifier-fail
loop-backs (both capped by max_revisions). All branching lives in route().
"""

from __future__ import annotations

from state.state import GraphState, Stage , Verdict, VerifyStatus

from langgraph.graph import StateGraph, START, END
from agents import jd_analysis, profile, matching, document, critic, verifier, evaluation
from utils.human_gate import human_gate
NEXT_STAGE = {
    Stage.JD_ANALYSIS : "jd_analysis",
    Stage.PROFILE : "profile",
    Stage.MATCHING: "matching",
    Stage.DOCUMENT: "document",
    Stage.CRITIC: "critic",
    Stage.VERIFIER: "verifier",
    Stage.EVALUATION: "evaluation",
    Stage.PROFILE_ENRICH: "profile_enrich",
}

# Keyed on the stage ABOUT to run, i.e. "pause before entering this stage".
STAGE_GATE = {
    Stage.PROFILE:        "gate1_requirements",  # before profile runs
    Stage.PROFILE_ENRICH: "gate2_evidence",      # before enrich runs
    Stage.DOCUMENT:       "gate3_fit",           # before document runs
    Stage.EVALUATION:     "gate4_document",      # before evaluation runs
}

"""
Doubt : Because in LangGraph, the decision of where to go next doesn't live inside the node — it lives on the edge leaving it
"""

def route(state: GraphState) -> str:
    """
    Conditional-edge router. IT returns the name of the next node, based on
    state.stage, the Critic verdict and the Verifier status.

    Status : COMPLETED
    """
    # loop-backs first, they beat the linear order
    if state.critique and state.critique.verdict == Verdict.REVISE and state.revision_count < state.max_revisions:
        return "document"          # critic said revise
    if state.verifier_report and state.verifier_report.status == VerifyStatus.FAIL and state.revision_count < state.max_revisions:
        return "document"          # verifier failed

    # Gate before advancing. The gate node can't change state.stage, so without
    # this feedback check route() would see the same input forever and loop.
    required_gate = STAGE_GATE.get(state.stage)
    if required_gate is not None:
        already_answered = any(
            fb.gate == required_gate for fb in state.gate_feedback
        )
        if not already_answered:
            return "gate"
        
    return NEXT_STAGE.get(state.stage, "END")
    # raise NotImplementedError("supervisor.route is a scaffold - routing logic is TODO.")

def supervisor_node(state: GraphState) -> dict:
    """The hub. Does no work, routing happens on the edge (add_conditional_edges).
    Later: log the decision, bump revision_count on loop-backs, decide inject_critic functions to be added."""
    return {}

def gate_node(state: GraphState) -> dict:
    """One node for all 4 gates. Which one it is comes from the stage."""
    gate_name = STAGE_GATE.get(state.stage)
    return human_gate(state, gate_name)

def build_graph(checkpointer=None):
    """
    Wire the StateGraph: a node per agent, one gate node, all branching through
    route(). Checkpointer is SqliteSaver so a paused gate survives a restart.

    Build graph according to requirement and condition.
    """

    graph = StateGraph(GraphState)
    graph.add_node("supervisor",supervisor_node)
    graph.add_edge(START, "supervisor")
    graph.add_node("jd_analysis", jd_analysis.node)
    graph.add_edge("jd_analysis", "supervisor")
    graph.add_node("profile", profile.node)
    graph.add_edge("profile", "supervisor")
    graph.add_node("profile_enrich", profile.enrich)
    graph.add_edge("profile_enrich", "supervisor")
    graph.add_node("matching", matching.node)
    graph.add_edge("matching", "supervisor")
    graph.add_node("document", document.node)
    graph.add_edge("document", "supervisor")
    graph.add_node("gate", gate_node)
    graph.add_edge("gate", "supervisor")
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
    "gate": "gate",
    "profile_enrich": "profile_enrich",
    "END": END,
    })

    
    
    return graph.compile(checkpointer=checkpointer)

