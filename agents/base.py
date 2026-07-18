"""
Shared agent infrastructure.

`AgentSpec` bundles an agent's assigned model with its versioned prompt.
`make_chat_model` is the provider-routing factory-- it maps the agent's canonical
model name (from configuration file(config)) to the right LangChain chat model.

API keys are NOT passed here - config.py has already loaded .env into the
environment, and each LangChain provider reads its key from the standard env var
(GROQ_API_KEY, GOOGLE_API_KEY). Keys live in exactly one place: config / .env.
"""

from __future__ import annotations

from dataclasses import dataclass

import config
from utils.prompt_loader import Prompt, load_prompt


@dataclass(frozen=True)
class AgentSpec:
    """An agent's assigned model plus its loaded, versioned prompt."""

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
    """Builds the spec for an agent from config + its prompt(learning) file."""
    return AgentSpec(name=agent, model=config.model_for(agent), prompt=load_prompt(agent))


def make_chat_model(agent: str, **kwargs):
    """
    Construct the LangChain chat model for an agent, routed by config.MODEL_CONFIG.

    In dev mode every agent routes to Groq; in eval mode Document and Critic route
    to Gemini. Extra kwargs (temperature, max_tokens, ...) pass through.
    """
    fake_responses = kwargs.pop("fake_responses", None)

    if config.USE_FAKE_LLM:
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

        # ChatOpenAI reads OPENAI_API_KEY from the env (loaded by config.py).
        kwargs.setdefault("temperature", 0.2)
        return ChatOpenAI(model=model, **kwargs)

    raise ValueError(
        f"No chat-model factory wired for model '{model}' (agent '{agent}'). "
        f"Add a branch in agents.base.make_chat_model."
    )


def structured_call(agent: str, user_input: str, schema, *, fake_json: str | None = None):
    """
    Run an agent's model and return a validated `schema` instance.

    This is the single door every agent uses to talk to an LLM. All call/parse plumbing
    lives here, so agent nodes only express intent ("give me a <schema> from this
    input")

    """
    from utils.trace import step  # TEMP tracing

    spec = spec_for(agent)
    prompt = f"{spec.system_prompt}\n\n{user_input}"

    if config.USE_FAKE_LLM:
        from pydantic import ValidationError

        llm = make_chat_model(agent, fake_responses=[fake_json or "{}"])
        try:
            return schema.model_validate_json(llm.invoke(prompt).content)
        except ValidationError as exc:
            # "{}" only satisfies all-default schemas; anything with required
            # fields needs an explicit fake_json — fail loudly, name the agent.
            raise ValueError(
                f"Offline mode: agent '{agent}' needs an explicit fake_json that "
                f"satisfies {schema.__name__} (default '{{}}' was rejected)."
            ) from exc

    llm = make_chat_model(agent)
    with step(f"calling {agent} LLM ({config.model_for(agent)}) - waiting for response"):
        result = llm.with_structured_output(schema).invoke(prompt)
    if result is None:
        # with_structured_output returns None when the provider fails to emit a
        # parseable tool call — never let a silent None flow into graph state.
        raise RuntimeError(
            f"Agent '{agent}' ({config.model_for(agent)}) returned no parseable "
            f"structured output for {schema.__name__}. Retry the call."
        )
    return result
