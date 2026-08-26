"""
JD Analysis Agent - Groq llama-3.3-70b-versatile.

Raw job description in, typed Requirements object out (Build.md #5).
Prompt: prompts/jd_analysis/system.yaml.
"""

from __future__ import annotations

from agents.base import structured_call
from state.state import GraphState, Requirements, Stage

# Offline mode returns this canned JSON. Live mode ignores it.
_FAKE_JSON = (
    '{"role_title": "Data Engineer",'
    ' "requirements": [{"text": "Python", "kind": "must_have"},'
    ' {"text": "SQL", "kind": "must_have"},'
    ' {"text": "ETL pipelines", "kind": "must_have"}],'
    ' "keywords": ["python", "sql", "etl"]}'
)

# why not adding user input to the function"?

def node(state: GraphState) -> dict:
    """Read the JD, return a validated Requirements object."""
    reqs = structured_call(
        "jd_analysis",
        "Extract the structured requirements from this job description:\n"
        + (state.job_description or ""),
        Requirements,
        fake_json=_FAKE_JSON,
    )
    return {"requirements": reqs, "stage": Stage.PROFILE}
