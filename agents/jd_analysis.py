"""
JD Analysis Agent - Groq llama-3.3-70b-versatile.

Raw job description in, typed Requirements object out (Build.md #5).
Prompt: prompts/jd_analysis/system.yaml.
"""

from __future__ import annotations

from agents.base import structured_call
from state.state import GraphState, Requirements, Stage
from utils.prompt_loader import all_prompt_versions
from utils.trace import log


class EmptyJobDescription(ValueError):
    """No JD text to analyse. Raised BEFORE any LLM call is paid for."""


class NoRequirementsFound(ValueError):
    """The model read a real JD and returned nothing usable."""

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
    # Input guard (#57 item 1). The backend rejects an empty JD at the API edge;
    # the CLI drivers and run_agent.py do not, and an empty prompt still costs a
    # real call and then poisons every downstream node with zero requirements.
    jd = (state.job_description or "").strip()
    if not jd:
        raise EmptyJobDescription(
            "jd_analysis needs state.job_description and it is empty. Nothing was "
            "sent to the model."
        )

    reqs = structured_call(
        "jd_analysis",
        "Extract the structured requirements from this job description:\n" + jd,
        Requirements,
        fake_json=_FAKE_JSON,
    )

    # Output guard (#79 item 1). Every field of Requirements has a default, so a
    # live model answering "{}" validates into a perfectly shaped empty object -
    # and the door only retries on None, never on empty-but-valid. Without this
    # the run pays for Profile, Matching and the Critic to work on nothing and
    # delivers an unedited CV with no explanation.
    if not reqs.requirements:
        raise NoRequirementsFound(
            f"jd_analysis extracted 0 requirements from a {len(jd)}-character job "
            f"description. The model returned an empty Requirements object; the run "
            f"would otherwise continue with nothing to match against."
        )

    # Output guard (#73 item 2). The prompt says "be exhaustive but do not
    # duplicate"; structured output checks shape, never whether the answer
    # obeys the instruction (#14's lesson). Everything downstream counts this
    # list, so a blank or a repeat is not cosmetic:
    #   - a blank text retrieves on an empty query in profile.node, and keys an
    #     empty REQUIREMENT block the grader then has to invent a grade for;
    #   - a repeat is graded twice, averaged twice into overall_fit and
    #     must_have_coverage, listed twice in unmet_must_haves, and arrives
    #     twice in Document's unsupported_flags. Two spellings of one
    #     requirement also split its evidence across two by_req buckets.
    # Sanitised here, at the door it enters state through, rather than in each
    # of the four readers.
    kept, seen = [], set()
    for req in reqs.requirements:
        text = (req.text or "").strip()
        if not text:
            continue
        # Same normalisation profile._key and matching._key already use to match
        # the model's echo back: whitespace-folded and case-insensitive.
        key = " ".join(text.split()).lower()
        if key in seen:
            continue
        seen.add(key)
        # First spelling wins, with its kind. A later duplicate cannot downgrade
        # a must_have to a nice_to_have, which is the one direction that hides an
        # unmet requirement (#58).
        kept.append(req if text == req.text else req.model_copy(update={"text": text}))

    dropped = len(reqs.requirements) - len(kept)
    if dropped:
        log(f"jd_analysis: dropped {dropped} blank or duplicate requirement(s) of "
            f"{len(reqs.requirements)}")
    if not kept:
        raise NoRequirementsFound(
            f"jd_analysis extracted {len(reqs.requirements)} requirement(s) from a "
            f"{len(jd)}-character job description and every one was blank or a "
            f"duplicate of another. Nothing is left to match against."
        )
    reqs = reqs.model_copy(update={"requirements": kept})

    # Attribution for THIS call, merged into state.prompt_versions (#77 item 3).
    # Every node that calls a model does the same, so the record names the
    # version each agent actually ran on, not whatever is on disk when the run
    # finishes. all_prompt_versions never raises: an unreadable prompt is None.
    return {
        "requirements": reqs,
        "prompt_versions": all_prompt_versions(["jd_analysis"]),
        "stage": Stage.PROFILE,
    }
