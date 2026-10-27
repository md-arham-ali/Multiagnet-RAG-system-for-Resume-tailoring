"""
Layer-3 context builder (Instructions.md #20-21) — the OVERFITTING GUARD.

Given an agent + the current role type + a token budget, it selects the most
relevant, recent exemplars and corrections from that agent's learning store and
formats them into a string to inject into the agent's prompt.

The whole point is that it must return a *small, relevant subset* — never the
full history — and never exceed the token budget. That selection logic is the
important block (yours to write); the loading and formatting around it is done.
"""

from __future__ import annotations

from learning.store import load_learning

# Rough heuristic: ~4 characters per token. Good enough to enforce a cap without
# pulling in a real tokenizer. Swap for tiktoken later if you want precision.
def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _format(exemplars: list[dict], corrections: list[dict]) -> str:
    """Render selected records into the injectable Layer-3 string."""
    lines: list[str] = []
    if exemplars:
        lines.append("Relevant past examples:")
        for e in exemplars:
            out = e.get("generated_output") or e.get("task") or ""
            lines.append(f"  - {str(out)[:200]}")
    if corrections:
        lines.append("Corrections to keep in mind:")
        for c in corrections:
            lines.append(f"  - was: {str(c.get('before',''))[:120]}")
            lines.append(f"    now: {str(c.get('after',''))[:120]} ({c.get('reason','')})")
    return "\n".join(lines)


def build_context(agent_name: str, role_type: str, token_budget: int = 800) -> str:
    """Return a token-capped, role-relevant slice of this agent's learning.

    Returns "" when there is nothing relevant — the agent then runs on its base
    prompt alone.
    """
    learning = load_learning(agent_name)
    exemplars = learning["exemplars"]
    corrections = learning["corrections"]

    # ▼▼▼ YOUR CODE — the overfitting guard ▼▼▼
    # 1. Score/rank exemplars + corrections by relevance to `role_type`
    #    (e.g. match on role/industry/task_type fields) and by recency.
    # 2. Greedily pick the top records until adding the next one would push
    #    estimate_tokens(_format(...)) over `token_budget`.
    # 3. Return _format(selected_exemplars, selected_corrections).
    # Must return a SUBSET — assert in your test that it's smaller than the full
    # history and under the budget.
    raise NotImplementedError(
        "build_context selection logic is yours to implement (Instructions #20)."
    )
    # ▲▲▲ END YOUR CODE ▲▲▲
