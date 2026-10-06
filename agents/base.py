"""
Shared agent infrastructure. AgentSpec = model + versioned prompt.
make_chat_model routes an agent to its provider, structured_call is the one
door every agent uses to reach an LLM.

No API keys here. config.py already loaded .env and each provider picks up its
own key from the environment. Keys live in one place: config / .env.
"""

from __future__ import annotations

from dataclasses import dataclass

import config
from utils.prompt_loader import Prompt, load_prompt


@dataclass(frozen=True)
class AgentSpec:
    """Model + versioned prompt for one agent."""

    name: str
    model: str
    prompt: Prompt

    @property
    def system_prompt(self) -> str:
        return self.prompt.system_prompt

    @property
    def prompt_version(self) -> int:
        return self.prompt.version


def spec_for(agent: str) -> AgentSpec:
    """Spec for one agent: model from config, prompt from its yaml."""
    return AgentSpec(name=agent, model=config.model_for(agent), prompt=load_prompt(agent))


def make_chat_model(agent: str, **kwargs):
    """Chat model for one agent, picked by config.MODEL_CONFIG.

    dev mode = everything on Groq. eval mode = document + critic on Gemini.
    USE_OPENAI overrides both. Extra kwargs pass through.
    """
    fake_responses = kwargs.pop("fake_responses", None)

    if config.fake_llm_active():
        from langchain_core.language_models.fake_chat_models import FakeListChatModel

        return FakeListChatModel(responses=fake_responses or [f"[fake:{agent}] ok"])
    
    model = config.model_for(agent)


    if model == config.GROQ_LLAMA:
        from langchain_groq import ChatGroq

        kwargs.setdefault("temperature", 0.2)
        return ChatGroq(model=model, **kwargs)

    if model == config.GEMINI_FLASH:
        from langchain_google_genai import ChatGoogleGenerativeAI

        kwargs.setdefault("temperature", 0.4)
        return ChatGoogleGenerativeAI(model=model, **kwargs)

    if model == config.OPENAI_MODEL:
        from langchain_openai import ChatOpenAI

        # key comes from the env
        kwargs.setdefault("temperature", 0.2)
        return ChatOpenAI(model=model, **kwargs)

    raise ValueError(
        f"No chat-model factory wired for model '{model}' (agent '{agent}'). "
        f"Add a branch in agents.base.make_chat_model."
    )


def structured_call(agent: str, user_input: str, schema, *, fake_json: str | None = None, system_prompt:str | None = None):
    """Run an agent's model, return a validated `schema` instance.

    The single door every agent uses to reach an LLM. Call + parse plumbing lives
    here so a node only says what it wants, not how to get it.
    """
    from utils.trace import step  # TEMP tracing

    system = system_prompt if system_prompt is not None else spec_for(agent).system_prompt
    prompt = f"{system}\n\n{user_input}"

    if config.fake_llm_active():
        from pydantic import ValidationError

        llm = make_chat_model(agent, fake_responses=[fake_json or "{}"])
        try:
            return schema.model_validate_json(llm.invoke(prompt).content)
        except ValidationError as exc:
            # "{}" only works when every field has a default. Anything with a
            # required field needs its own fake_json, so fail loud and name the
            # agent instead of dying inside pydantic.
            raise ValueError(
                f"Offline mode: agent '{agent}' needs an explicit fake_json that "
                f"satisfies {schema.__name__} (default '{{}}' was rejected)."
            ) from exc

    llm = make_chat_model(agent)
    with step(f"calling {agent} LLM ({config.model_for(agent)}) - waiting for response"):
        result = llm.with_structured_output(schema).invoke(prompt)
    if result is None:
        # Returns None when the model fails to emit a parseable tool call (Groq
        # does this under load). Never let a silent None into state, the next
        # agent would blow up far away from the real cause.
        raise RuntimeError(
            f"Agent '{agent}' ({config.model_for(agent)}) returned no parseable "
            f"structured output for {schema.__name__}. Retry the call."
        )
    return result
