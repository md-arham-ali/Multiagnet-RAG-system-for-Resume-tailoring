"""
Versioned prompt loader.

Prompts live as YAML under prompts/<agent>/system.yaml, never hardcoded in agent
code (Instructions #4). One way in, so prompt text stays out of the code and the
version travels with it - log that next to eval scores (Build.md #19).

Note: load_prompt is lru_cached, so a long-lived process needs a restart to see
prompt edits.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

import config

# in priority order, .txt is the plain-text fallback
_FILENAMES = ("system.yaml", "system.yml", "system.txt")


@dataclass(frozen=True)
class Prompt:
    """A loaded prompt + its metadata."""

    name: str
    version: int
    model: str
    provider: str
    description: str
    system_prompt: str
    path: Path


def _resolve(agent: str) -> Path:
    folder = config.PROMPTS_DIR / agent
    for filename in _FILENAMES:
        candidate = folder / filename
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"No prompt file for agent '{agent}' in {folder} "
        f"(expected one of {_FILENAMES})."
    )


def _version(raw, path: Path) -> int:
    """An int or a digit string. int() would turn 2.1 into 2 and true into 1, so
    two prompts would log the same version next to their scores (#66)."""
    if isinstance(raw, int) and not isinstance(raw, bool):
        return raw
    if isinstance(raw, str) and raw.strip().isdecimal():
        return int(raw)
    raise ValueError(f"Prompt {path} has version {raw!r}; it must be a whole number.")


@lru_cache(maxsize=None)
def load_prompt(agent: str) -> Prompt:
    """Load (and cache) the prompt for an agent by folder name."""
    path = _resolve(agent)

    if path.suffix in (".yaml", ".yml"):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        text = (data.get("system_prompt") or "").strip()
        if not text:
            raise ValueError(f"Prompt {path} has no non-empty 'system_prompt'.")
        return Prompt(
            name=str(data.get("name", agent)),
            version=_version(data.get("version", 1), path),
            model=str(data.get("model", "")),
            provider=str(data.get("provider", "")),
            description=(data.get("description") or "").strip(),
            system_prompt=text,
            path=path,
        )

    # .txt fallback: whole file is the prompt, version 1
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Prompt file {path} is empty.")
    return Prompt(
        name=agent, version=1, model="", provider="",
        description="", system_prompt=text, path=path,
    )


def system_prompt(agent: str) -> str:
    """Just the system-prompt text for an agent."""
    return load_prompt(agent).system_prompt


def prompt_version(agent: str) -> int:
    """The version number of an agent's prompt."""
    return load_prompt(agent).version


# In MODEL_CONFIG but not in the pipeline: scratch agents and the company-ranking
# sandbox (scripts/agentic_rank_test.py). They have no LangGraph node, so their
# prompt versions explain nothing about a run - and loading them used to let one
# broken, unrelated YAML raise in the run's last step (#77 item 3).
NON_PIPELINE_AGENTS = frozenset({
    "query_refine", "rerank_critic", "rank_refiner", "rank_verifier",
})


def pipeline_agents() -> list[str]:
    """The agents a run actually calls, in MODEL_CONFIG order."""
    return [a for a in config.MODEL_CONFIG if a not in NON_PIPELINE_AGENTS]


def all_prompt_versions(agents: list[str] | None = None) -> dict[str, int | None]:
    """{agent: version} for the pipeline agents. Log this with evals.

    Never raises: an agent whose prompt is missing, empty or malformed records
    None. Attribution is worth having partially; it is not worth failing a run
    for, least of all in the step that runs after the human already approved
    the CV (#77 item 3).
    """
    versions: dict[str, int | None] = {}
    for agent in (pipeline_agents() if agents is None else agents):
        try:
            versions[agent] = load_prompt(agent).version
        except Exception as exc:
            print(f"(prompt version for '{agent}' unavailable: {type(exc).__name__}: {exc})")
            versions[agent] = None
    return versions
