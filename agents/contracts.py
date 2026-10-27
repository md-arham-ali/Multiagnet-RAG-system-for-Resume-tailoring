"""
One contract per LLM agent: the answer schema it must return and its output cap
(bugs_audit_fixed.md #112). The door (agents/base.py) reads this, so the pieces of
a call stop living in four files with nothing checking they agree.

What a contract holds today:
  schema      - the model the door binds. structured_call refuses any other.
  max_tokens  - the output cap. Without one, a cut-off answer looks exactly like a
                schema mismatch (#111 N3, #76 item 4).

Not here yet (#112 4d step 3): the offline fixtures still live in each agent file.

An agent without a contract (the sandbox scripts) still works: default cap, no
schema check. The pipeline agents are all registered.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from state.state import (
    Critique,
    DocumentPatchSet,
    MatchAssessment,
    ProfileAssessment,
    ProfileEnrichment,
    Requirements,
    VerdictSet,
)

DEFAULT_MAX_TOKENS = 4096


@dataclass(frozen=True)
class Contract:
    agent: str
    schema: type
    max_tokens: int = DEFAULT_MAX_TOKENS


# Caps are generous on purpose: a cap exists to make truncation visible, not to
# squeeze the answer. document_plan grades every CV node (64 on CV_test, a reason on
# each refine/rewrite), so it gets the most room.
CONTRACTS: dict[str, Contract] = {
    c.agent: c
    for c in (
        Contract("jd_analysis", Requirements, 2048),
        Contract("profile", ProfileAssessment, 4096),
        Contract("profile_enrich", ProfileEnrichment, 2048),
        Contract("matching", MatchAssessment, 4096),
        Contract("document_plan", VerdictSet, 8192),
        Contract("document", DocumentPatchSet, 4096),
        Contract("critic", Critique, 4096),
    )
}


def max_tokens_for(agent: str) -> int:
    contract = CONTRACTS.get(agent)
    return contract.max_tokens if contract else DEFAULT_MAX_TOKENS


def check_schema(agent: str, schema) -> None:
    """A registered agent may only be asked for its own answer schema."""
    contract = CONTRACTS.get(agent)
    if contract is not None and schema is not contract.schema:
        raise TypeError(
            f"Agent '{agent}' answers with {contract.schema.__name__} (agents/contracts.py), "
            f"but the call asked for {getattr(schema, '__name__', schema)}."
        )


def _strip_titles(node):
    """Pydantic puts an auto 'title' on every node; to the model it is noise. Only
    string titles go - a FIELD named 'title' is a dict under 'properties' and stays."""
    if isinstance(node, dict):
        return {k: _strip_titles(v) for k, v in node.items() if not (k == "title" and isinstance(v, str))}
    if isinstance(node, list):
        return [_strip_titles(v) for v in node]
    return node


def shape_block(schema) -> str:
    """The answer shape, rendered from the schema itself and appended to every prompt.

    #91 happened because a prompt's hand-written shape left out the wrapper field. This
    block cannot: it is the schema. The YAML keeps the judgement rules; the shape comes
    from here. It is also what makes json_mode (the door's second binding) usable at all -
    that mode sends no schema to the provider, only this text.
    """
    body = json.dumps(_strip_titles(schema.model_json_schema()), separators=(",", ":"))
    return (
        "ANSWER SHAPE: reply with exactly ONE JSON object that validates against this JSON "
        "schema. Every required field must be present, at the top level. No prose, no "
        f"markdown, never several objects or a bare list.\n{body}"
    )
