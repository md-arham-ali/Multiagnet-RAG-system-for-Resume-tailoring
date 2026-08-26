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
            version=int(data.get("version", 1)),
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


def all_prompt_versions() -> dict[str, int]:
    """{agent: version} for every agent in MODEL_CONFIG. Log this with evals."""
    return {agent: load_prompt(agent).version for agent in config.MODEL_CONFIG}
