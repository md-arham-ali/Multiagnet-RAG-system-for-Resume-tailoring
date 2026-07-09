"""
Versioned prompt loader.

Agent system prompts live as YAML under prompts/<agent>/system.yaml — versioned,
not hardcoded in agent logic (Instructions.md step 4). This module is the single
way agents read their prompt, so the prompt text never leaks into code and the
version travels with it (Build.md #19: store version IDs alongside eval scores).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

import config

# Accepted filenames, in priority order (.txt is a plain-text fallback).
_FILENAMES = ("system.yaml", "system.yml", "system.txt")


@dataclass(frozen=True)
class Prompt:
    """A loaded, versioned prompt plus its metadata."""

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

    # Plain-text fallback: the whole file is the system prompt, version defaults to 1.
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
    """{agent: prompt_version} for every agent in MODEL_CONFIG — log this with evals."""
    return {agent: load_prompt(agent).version for agent in config.MODEL_CONFIG}
