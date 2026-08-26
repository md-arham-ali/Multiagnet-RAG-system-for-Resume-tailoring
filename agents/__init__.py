"""
One module per agent. Each is a thin LangGraph node: loads its prompt, gets its
model from config, reads and writes GraphState. base.py holds the shared bits.
"""

from agents.base import AgentSpec, make_chat_model, spec_for

__all__ = ["AgentSpec", "spec_for", "make_chat_model"]
