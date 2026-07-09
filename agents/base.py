"""
Shared agent infrastructure.

`AgentSpec` bundles an agent's assigned model with its versioned prompt.
`make_chat_model` is the provider-routing factory: it maps the agent's canonical
model name (from config) to the right LangChain chat model. Provider packages are
lazy-imported so importing this module stays cheap and side-effect-free.

API keys are NOT passed here — config.py has already loaded .env into the
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
    """Builds the spec for an agent from config + its prompt file."""
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

    raise ValueError(
        f"No chat-model factory wired for model '{model}' (agent '{agent}'). "
        f"Add a branch in agents.base.make_chat_model."
    )


def structured_call(agent: str, user_input: str, schema, *, fake_json: str | None = None):
    """
    Run an agent's model and return a validated `schema` instance.

    The single door every agent uses to talk to an LLM. All call/parse plumbing
    lives here, so agent nodes only express intent ("give me a <schema> from this
    input"):
      - offline (fake LLM): parse the canned `fake_json` reply,
      - real model: use the provider's native structured output.

    Anything added later (fence-stripping, retries, Langfuse tracing) is added
    once, here, and every agent inherits it.
    """
    from utils.trace import step  # TEMP tracing

    spec = spec_for(agent)
    prompt = f"{spec.system_prompt}\n\n{user_input}"

    if config.USE_FAKE_LLM:
        llm = make_chat_model(agent, fake_responses=[fake_json or "{}"])
        return schema.model_validate_json(llm.invoke(prompt).content)

    llm = make_chat_model(agent)
    with step(f"calling {agent} LLM ({config.model_for(agent)}) — waiting for response"):
        return llm.with_structured_output(schema).invoke(prompt)
