"""
Agents package.

One module per agent, each a thin LangGraph node that:
  - reads its versioned system prompt via utils.prompt_loader,
  - is assigned a model by config.MODEL_CONFIG,
  - reads from / writes to the shared GraphState.

base.py holds the shared spec + chat-model factory; the per-agent node functions
are scaffolds to be filled in as the graph is wired.
"""

from agents.base import AgentSpec, make_chat_model, spec_for

__all__ = ["AgentSpec", "spec_for", "make_chat_model"]
