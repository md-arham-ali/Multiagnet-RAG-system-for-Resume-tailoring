"""
Supervisor - the hub. Hand-rolled routing, no LLM.

Owns dispatch order, the human gates, Critic revise loop-backs and Verifier-fail
loop-backs (both capped by max_revisions). All branching lives in route().
"""

from __future__ import annotations

from state.state import GraphState, Stage , Verdict, VerifyStatus, SupervisorDecision

from langgraph.graph import StateGraph, START, END
from agents import jd_analysis, profile, matching, document, critic, verifier, evaluation, CV_Link
from utils.human_gate import human_gate
NEXT_STAGE = {
    Stage.JD_ANALYSIS : "jd_analysis",
    Stage.PROFILE : "profile",
    Stage.MATCHING: "matching",
    Stage.CV_LINK: "cv_link", # not an agent, but a node that links to the CV handling pipeline.s
    Stage.DOCUMENT: "document",
    Stage.CRITIC: "critic",
    Stage.VERIFIER: "verifier",
    Stage.EVALUATION: "evaluation",
    Stage.PROFILE_ENRICH: "profile_enrich",
    Stage.DONE: "END",
}


# The rubric the Supervisor injects into the Critic at call time (the 2026-08-27
# decision, Build.md addendum row 12). These are the three dimensions that
# survived dropping "ATS alignment" (moved to the checking module, bugs.md #17)
# and "template adherence" (judges something that does not exist, bugs.md #20).
#
# Deliberately NO structure/template dimension: Q8 - reword it honestly or wait
# for real templates - is still open in critic_verifier_design.md 3.1, and
# writing an interim wording in here would answer it in code without the
# decision being made anywhere (bugs.md #39).
STAGE_RUBRIC: dict[Stage, str] = {
    Stage.CRITIC: """
        1. Relevance — does the document target THIS job's requirements, and
           does it lead with the strongest evidence for them rather than with a
           generic summary.
        2. Evidence traceability — every claim traces back to a specific
           evidence block, not merely to something that sounds plausible.
        3. Readability — professional, concise and easy to read; consistent
           structure, no padding or filler.
    """,
}

# Keyed on the stage ABOUT to run, i.e. "pause before entering this stage".
STAGE_GATE = {
    Stage.PROFILE:        "gate1_requirements",  # before profile runs
    Stage.PROFILE_ENRICH: "gate2_evidence",      # before enrich runs
    Stage.DOCUMENT:       "gate3_fit",           # before document runs
    Stage.EVALUATION:     "gate4_document",      # before evaluation runs
}

# gate -> the agent that produced the artifact it reviews. A rejected gate is
# sent back to its producer to redo the work (bugs.md #10).
GATE_PRODUCER = {
    "gate1_requirements": "jd_analysis",
    "gate2_evidence":     "profile",
    "gate3_fit":          "matching",
    "gate4_document":     "document",
}

"""
Doubt : Because in LangGraph, the decision of where to go next doesn't live inside the node — it lives on the edge leaving it
"""

def decide(state: GraphState) -> SupervisorDecision:
    """
    Where does the run go next, and why. The whole routing brain lives here.

    Kept separate from route() so supervisor_node() can act on the decision -
    bump the count, clear the verdicts - before route() reads it. Deriving it
    twice would not work: the bump and the clear both destroy the condition the
    decision was made from.

    Status : COMPLETED
    """
    # Loop-backs first, they beat the linear order. Capped by max_revisions.
    if state.revision_count < state.max_revisions:
        if state.critique and state.critique.verdict == Verdict.REVISE:
            return SupervisorDecision(
                next_node="document", redo=True, reason="critic returned revise",
            )
        if state.verifier_report and state.verifier_report.status == VerifyStatus.FAIL:
            return SupervisorDecision(
                next_node="document", redo=True, reason="verifier returned fail",
            )

    # Gate before advancing. The gate node can't change state.stage, so without
    # this feedback check route() would see the same input forever and loop.
    required_gate = STAGE_GATE.get(state.stage)
    if required_gate is not None:
        # Only the LATEST answer counts. The list is append-only (it is the
        # audit trail), so an early round's answer is history, not an instruction.
        entries = [fb for fb in state.gate_feedback if fb.gate == required_gate]
        latest = entries[-1] if entries else None

        if latest is None:
            return SupervisorDecision(
                next_node="gate", reason=f"{required_gate} not answered yet",
            )
        # Answered on an earlier lap - the artifact has changed since, so the
        # human has to see the new one (bugs.md #11).
        if latest.revision != state.revision_count:
            return SupervisorDecision(
                next_node="gate",
                reason=f"{required_gate} answered in round {latest.revision}, "
                       f"now round {state.revision_count}",
            )
        # The veto. Send it back to whoever produced the artifact (bugs.md #10).
        # At the cap we stop honouring it and advance, the same way the
        # loop-back above simply stops firing - no separate hard-stop branch.
        if latest.decision == "reject" and state.revision_count < state.max_revisions:
            return SupervisorDecision(
                next_node=GATE_PRODUCER[required_gate],
                redo=True,
                reason=f"{required_gate} rejected, redo by {GATE_PRODUCER[required_gate]}",
            )

    # No .get() default here on purpose. A missing stage is a wiring bug, not a
    # reason to end the run - that default is what silently dead-ended
    # PROFILE_ENRICH after profile (bugs.md #4). DONE maps to "END" explicitly.
    next_node = NEXT_STAGE.get(state.stage)
    if next_node is None:
        raise KeyError(
            f"No route for stage {state.stage.value!r}. Every Stage member needs an "
            f"entry in NEXT_STAGE (use \"END\" to finish the run). "
            f"Routed stages: {sorted(s.value for s in NEXT_STAGE)}."
        )
    return SupervisorDecision(
        next_node=next_node, reason=f"stage {state.stage.value} advances",
    )


def route(state: GraphState) -> str:
    """
    Conditional-edge router. Reads the decision supervisor_node() just recorded.

    Status : COMPLETED
    """
    decision = state.supervisor_decision
    if decision is None:
        # Only reachable if something drives route() without going through the
        # supervisor node, i.e. a wiring bug worth failing loudly on.
        raise ValueError(
            "route() ran with no supervisor_decision in state. Every edge into "
            "route() must come from supervisor_node(), which records one."
        )
    return decision.next_node

def supervisor_node(state: GraphState) -> dict:
    """
    The hub. Decides where the run goes, records it, and pays for it.

    "Pays for it" = a redo costs one revision. Doing it here rather than in the
    agents keeps ONE owner for the count (agent_brain_build.md 4.4), which is
    what makes a rejected gate 1 - which never passes through document - cost a
    revision like any other loop-back.
    """
    decision = decide(state)
    update = {"supervisor_decision": decision}
    update["active_rubric"] = STAGE_RUBRIC.get(state.stage)
    

    if decision.redo:
        # Without this the reject/loop-back condition is still true next time
        # round and the run redoes the same work forever.
        update["revision_count"] = state.revision_count + 1
        # These describe the draft being replaced. Left in place, route() would
        # bounce the run back here before Critic or Verifier saw the new one
        # (audit #2).
        update["critique"] = None
        update["verifier_report"] = None

    return update

def gate_node(state: GraphState) -> dict:
    """One node for all 4 gates. Which one it is comes from the stage."""
    gate_name = STAGE_GATE.get(state.stage)
    if gate_name is None:
        # Without this, None goes to human_gate and surfaces as
        # "Unknown gate 'None'" from GATE_FIELDS - the wrong table, wrong file.
        raise KeyError(
            f"gate node reached at stage {state.stage.value!r}, which has no gate. "
            f"Gated stages: {sorted(s.value for s in STAGE_GATE)}."
        )
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
    graph.add_node("cv_link", CV_Link.node)
    graph.add_edge("cv_link", "supervisor")
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
    "cv_link": "cv_link",
    "END": END,
    })

    
    
    return graph.compile(checkpointer=checkpointer)

