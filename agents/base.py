"""
Shared agent infrastructure. AgentSpec = model + versioned prompt.
make_chat_model routes an agent to its provider, structured_call is the one
door every agent uses to reach an LLM.

No API keys here. config.py already loaded .env and each provider picks up its
own key from the environment. Keys live in one place: config / .env.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

import config
from agents.contracts import CONTRACTS, DEFAULT_MAX_TOKENS, check_schema, max_tokens_for, shape_block
from utils import observability
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


# The door owns retries (_link, config.RETRY). A client's own SDK retries would stack
# under them: a 429 storm becomes door attempts x SDK attempts. 0 = none; Gemini counts
# total attempts, so its "none" is 1.
_SDK_RETRIES = {"groq": 0, "openai": 0, "gemini": 1}


def make_chat_model(agent: str, **kwargs):
    """Chat model for one agent, picked by config.MODEL_CONFIG.

    dev mode = everything on Groq. eval mode = document + critic on Gemini.
    USE_OPENAI overrides both. Extra kwargs pass through.
    """
    fake_responses = kwargs.pop("fake_responses", None)

    if config.fake_llm_active() or fake_responses is not None:
        from langchain_core.language_models.fake_chat_models import FakeListChatModel

        return FakeListChatModel(responses=fake_responses or [f"[fake:{agent}] ok"])
    
    model = config.model_for(agent)
    # Every live client is capped (#111 N3, #76 item 4): a cut-off answer then shows up
    # as finish_reason "length", not as a schema mismatch. Gemini spells it differently.
    cap = kwargs.pop("max_tokens", max_tokens_for(agent))

    if model == config.GROQ_LLAMA:
        from langchain_groq import ChatGroq

        kwargs.setdefault("temperature", 0.2)
        kwargs.setdefault("max_retries", _SDK_RETRIES["groq"])
        kwargs.setdefault("max_tokens", cap)
        return ChatGroq(model=model, **kwargs)

    if model == config.GEMINI_FLASH:
        from langchain_google_genai import ChatGoogleGenerativeAI

        kwargs.setdefault("temperature", 0.4)
        kwargs.setdefault("max_retries", _SDK_RETRIES["gemini"])
        kwargs.setdefault("max_output_tokens", cap)
        return ChatGoogleGenerativeAI(model=model, **kwargs)

    if model == config.OPENAI_MODEL:
        from langchain_openai import ChatOpenAI

        # key comes from the env
        kwargs.setdefault("temperature", 0.2)
        kwargs.setdefault("max_retries", _SDK_RETRIES["openai"])
        kwargs.setdefault("max_tokens", cap)
        return ChatOpenAI(model=model, **kwargs)

    # Everything else in MODEL_CONFIG is served by an OpenAI-compatible endpoint, and
    # `_chat_for` already knows how to build one - the primary just never used it
    # (bugs_audit_fixed.md #114). `profile_enrich` is a real pipeline agent on Cerebras:
    # every live run that answered a gap question died here with "No chat-model factory
    # wired", BEFORE any network call, and a ValueError is not in `_FALL_OVER`, so the
    # lane's Groq fallback never got a turn either.
    #
    # Read off `FALLBACK_CHAINS` rather than naming the two models: a third
    # OpenAI-compatible provider added to MODEL_CONFIG is then wired by the same line,
    # which is the shape of defect this is (a contract piece nothing checks, #112).
    # `.get` keeps a model that is in neither table falling through to the raise below.
    head = (config.FALLBACK_CHAINS.get(model) or [""])[0]
    if head.partition("/")[0] in _OPENAI_COMPATIBLE:
        chat = _chat_for(head, max_tokens=cap, **kwargs)
        if chat is None:
            # _chat_for returns None for a provider with no key. Returning that would
            # hand `_link` a None model; say which key is missing instead.
            raise ValueError(
                f"Agent '{agent}' is routed to '{head}', whose key "
                f"{_KEY_FOR[head.partition('/')[0]]} is not set. Set it in .env, or "
                f"point the agent at another model in config.MODEL_CONFIG."
            )
        return chat

    raise ValueError(
        f"No chat-model factory wired for model '{model}' (agent '{agent}'). "
        f"Add a branch in agents.base.make_chat_model."
    )

class EmptyOutputError(RuntimeError):
    """The model answered, but nothing we could read into the schema."""


class RateLimitedError(RuntimeError):
    """A provider said 429. Wait and retry, then fall over to the next provider."""


class TransientError(RuntimeError):
    """5xx, timeout or connection error. Same handling as a 429."""


class TruncatedOutputError(EmptyOutputError):
    """The answer hit max_tokens. Asking again at the same cap buys the same cut-off,
    so this skips the provider's remaining rungs and falls over to the next one."""


# Lane prefix -> OpenAI-compatible endpoint + its key. groq/gemini/openai have their own classes.
_OPENAI_COMPATIBLE = {
    "cerebras": ("https://api.cerebras.ai/v1", "CEREBRAS_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
}

# Lane prefix -> the config attribute holding that provider's key.
_KEY_FOR = {
    "groq": "GROQ_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "openai": "OPENAI_API_KEY",
    **{p: key for p, (_, key) in _OPENAI_COMPATIBLE.items()},
}


def _has_key(entry: str) -> bool:
    """Does the provider of this lane entry ("provider/model") have a key set?"""
    key_name = _KEY_FOR.get(entry.partition("/")[0])
    if key_name is None:
        raise ValueError(f"No chat-model factory for lane entry '{entry}'.")
    return bool(getattr(config, key_name, ""))


def _chat_for(entry: str, max_tokens: int = DEFAULT_MAX_TOKENS, **kwargs):
    """One lane entry ("provider/model") -> a LangChain chat model, or None when
    that provider has no key, so the chain shrinks to the keys you hold.

    `kwargs` are per-call settings and WIN over the defaults below, the same
    contract `make_chat_model` has - which is what lets it delegate here for an
    OpenAI-compatible primary without silently dropping them (#114)."""
    if not _has_key(entry):
        return None
    provider, _, model = entry.partition("/")
    kwargs.setdefault("max_tokens", max_tokens)
    if provider == "groq":
        from langchain_groq import ChatGroq
        kwargs.setdefault("temperature", 0.2)
        kwargs.setdefault("max_retries", _SDK_RETRIES["groq"])
        return ChatGroq(model=model, **kwargs)
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        kwargs.setdefault("temperature", 0.4)
        kwargs.setdefault("max_retries", _SDK_RETRIES["gemini"])
        kwargs["max_output_tokens"] = kwargs.pop("max_tokens")   # Gemini spells it differently
        return ChatGoogleGenerativeAI(model=model, **kwargs)
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        kwargs.setdefault("temperature", 0.2)
        kwargs.setdefault("max_retries", _SDK_RETRIES["openai"])
        return ChatOpenAI(model=model, **kwargs)
    base_url, key_name = _OPENAI_COMPATIBLE[provider]
    from langchain_openai import ChatOpenAI
    kwargs.setdefault("temperature", 0.2)
    kwargs.setdefault("max_retries", _SDK_RETRIES["openai"])
    return ChatOpenAI(model=model, base_url=base_url, api_key=getattr(config, key_name), **kwargs)


_STATUS_CODE = re.compile(r"(?:^\s*|\)\s*:\s*|[Ee]rror code:\s*)(\d{3})\b")


def _classify(exc: BaseException) -> BaseException:
    """Map a provider's own error to RateLimitedError / TransientError. Anything
    else (400/401/403, schema errors) comes back unchanged: retrying it only burns time."""
    rate, transient = [], []
    for sdk in ("groq", "openai"):  # cerebras + openrouter go through the openai SDK
        try:
            mod = __import__(sdk)
            rate.append(mod.RateLimitError)
            transient += [mod.APIConnectionError, mod.InternalServerError]  # timeout is a connection error
        except ImportError:
            pass
    # The raw google-genai SDK error (what Gemini raises for a 503 before langchain wraps it).
    # Its own try-block: google.api_core below is NOT installed here, and an ImportError from
    # that import must not skip this check (it did, 2026-10-24: the 503 went unclassified).
    try:
        from google.genai import errors as genai_errors
        if isinstance(exc, genai_errors.APIError):
            if exc.code == 429:
                return RateLimitedError(str(exc))
            if exc.code in (500, 502, 503, 504):
                return TransientError(str(exc))
    except ImportError:
        pass
    try:
        from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable, DeadlineExceeded

        rate.append(ResourceExhausted)
        transient += [ServiceUnavailable, DeadlineExceeded]
    except ImportError:
        pass
    if isinstance(exc, tuple(rate)):
        return RateLimitedError(str(exc))
    if isinstance(exc, tuple(transient)):
        return TransientError(str(exc))
    # langchain_google_genai wraps everything in one class; only the text says which.
    if type(exc).__name__ == "ChatGoogleGenerativeAIError":
        text = str(exc)
        m = _STATUS_CODE.search(text)
        code = int(m.group(1)) if m else None
        # A code counts only where the wrapper puts it (start, or after "):"), never a
        # number inside the message ("got 14290 tokens"). Keywords are the fallback.
        if code == 429 or (code is None and "RESOURCE_EXHAUSTED" in text):
            return RateLimitedError(text)
        if code in (500, 503, 504) or (
            code is None and any(s in text for s in ("UNAVAILABLE", "DEADLINE_EXCEEDED"))
        ):
            return TransientError(text)
    # Groq: the model wrote prose/JSON instead of calling the tool. A fresh generation
    # often works; any other 400 (schema, auth) never does and passes through unchanged.
    if getattr(exc, "code", None) == "tool_use_failed" or "tool_use_failed" in str(exc):
        return EmptyOutputError(str(exc))
    return exc


_FALL_OVER = (RateLimitedError, TransientError, EmptyOutputError)


# -----------------------------------------------------------------------------
# Salvaging a rejected generation (bugs_audit_fixed.md #91)
# -----------------------------------------------------------------------------
# A 400 tool_use_failed carries what the model actually wrote, under
# `failed_generation`. The first live run died there: the Profile model wrote one
# valid object PER requirement instead of one object holding the list of them. The
# content was right and paid for; only the packaging was wrong - so read it back
# rather than buy the same answer again. Repackaging only: every field still has to
# validate, so a wrong answer stays wrong and fails as before.

_RETRY_NUDGE = (
    "Your previous answer was rejected: it was not one tool call carrying one JSON "
    "object. Answer again with exactly ONE tool call whose argument is ONE object "
    "holding every field of the schema. Do not send several objects, prose or markdown."
)


def _find_key(blob, key: str):
    """First value stored under `key` anywhere in a nested dict/list."""
    if isinstance(blob, dict):
        if key in blob:
            return blob[key]
        for value in blob.values():
            found = _find_key(value, key)
            if found is not None:
                return found
    elif isinstance(blob, list):
        for value in blob:
            found = _find_key(value, key)
            if found is not None:
                return found
    return None


def _failed_generation(exc: BaseException) -> str | None:
    """What the model wrote, dug out of the provider's tool-call error."""
    import ast

    for holder in (getattr(exc, "body", None), getattr(exc, "response", None)):
        blob = holder
        if blob is not None and not isinstance(blob, (dict, list)):
            try:
                blob = holder.json()
            except Exception:
                continue
        found = _find_key(blob, "failed_generation")
        if isinstance(found, str) and found.strip():
            return found
    # The SDK also prints the body into the message as a python repr:
    # "Error code: 400 - {'error': {... 'failed_generation': '...'}}". literal_eval
    # reads data only - it never executes what came back from the provider.
    match = re.search(r"\{.*\}", str(exc), re.S)
    if match:
        try:
            found = _find_key(ast.literal_eval(match.group(0)), "failed_generation")
        except (ValueError, SyntaxError, MemoryError, RecursionError):
            found = None
        if isinstance(found, str) and found.strip():
            return found
    return None


def _wrapper_field(schema) -> str | None:
    """The one list field of a wrapper schema (ProfileAssessment.assessments,
    MatchAssessment.matches, VerdictSet.verdicts, ...).

    None when the schema is any other shape: two lists and there is no telling which
    one the loose objects belong to; another required field and we do not have it.
    """
    import typing

    chosen = None
    for name, field in schema.model_fields.items():
        if typing.get_origin(field.annotation) is list:
            if chosen is not None:
                return None
            chosen = name
        elif field.is_required():
            return None
    return chosen


def _json_values(text: str) -> list:
    """Every top-level JSON value in `text`, in order. raw_decode rather than loads
    because the shape that caused #91 - several objects in a row, newline-separated
    or not - is a run of valid documents, which is not itself a valid one."""
    import json

    decoder, values, i = json.JSONDecoder(), [], 0
    while i < len(text):
        if text[i].isspace() or text[i] == ",":
            i += 1
            continue
        try:
            value, end = decoder.raw_decode(text, i)
        except ValueError:
            if values:
                break
            # Nothing read yet: skip prose or a ```json fence up to the next { or [.
            starts = [j for j in (text.find("{", i + 1), text.find("[", i + 1)) if j != -1]
            if not starts:
                break
            i = min(starts)
            continue
        values.append(value)
        i = end
    return values


def _rebuild(text: str | None, schema):
    """A validated `schema` instance rebuilt from what the model wrote, or None."""
    from pydantic import ValidationError

    if not text or not text.strip():
        return None
    values = _json_values(text)
    # The whole answer (plain, or wrapped in prose or a fence) - but only if it carries
    # one of the schema's own fields. Requirements defaults every field, so ANY object
    # validates as an empty answer; a lone item must not be mistaken for the wrapper.
    if len(values) == 1 and isinstance(values[0], dict) and set(values[0]) & set(schema.model_fields):
        try:
            return schema.model_validate(values[0])
        except ValidationError:
            pass
    if len(values) == 1 and isinstance(values[0], list):
        values = values[0]                   # a bare array of the items
    field = _wrapper_field(schema)
    if not values or field is None:
        return None
    try:
        return schema.model_validate({field: values})
    except ValidationError:
        return None


def _salvage(exc: BaseException, schema):
    """A validated `schema` instance rebuilt from a rejected generation, or None."""
    return _rebuild(_failed_generation(exc), schema)


# -----------------------------------------------------------------------------
# Reading an answer that came back (bugs_audit_fixed.md #112, #113)
# -----------------------------------------------------------------------------
# Every binding asks for include_raw=True. Without it, a provider that does NOT force
# the tool (everything but Groq) hands back None for a text answer, and the text -
# paid for - is gone before _salvage could see it (#113 item 2). With it, the door
# gets the raw message too: the text to rebuild from, the finish reason that tells a
# cut-off apart from a wrong shape, and the token counts.

def _raw_texts(raw) -> list[str]:
    """Everything in a raw AI message that might hold the answer, best first."""
    import json

    texts = []
    for call in getattr(raw, "tool_calls", None) or []:
        texts.append(json.dumps(call.get("args", {})))
    for call in getattr(raw, "invalid_tool_calls", None) or []:
        if isinstance(call.get("args"), str):
            texts.append(call["args"])
    content = getattr(raw, "content", None)
    if isinstance(content, list):            # content parts (Gemini)
        content = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    if isinstance(content, str):
        texts.append(content)
    return texts


def _cut_off(raw) -> bool:
    meta = getattr(raw, "response_metadata", None) or {}
    reason = str(meta.get("finish_reason") or meta.get("stop_reason") or "").lower()
    return reason in ("length", "max_tokens")


def _read(out, schema, agent: str, label: str):
    """One binding's result -> (answer, how). how is "parsed" or "salvage".

    Raises TruncatedOutputError on a cut-off, EmptyOutputError when nothing fits.
    A plain answer (a client that ignores include_raw) is taken as parsed.
    """
    if not isinstance(out, dict):
        if out is None:
            raise EmptyOutputError(
                f"Agent '{agent}' ({label}) returned no parseable structured output for {schema.__name__}."
            )
        return out, "parsed"
    raw, parsed = out.get("raw"), out.get("parsed")
    if parsed is not None:
        return parsed, "parsed"
    if _cut_off(raw):
        raise TruncatedOutputError(
            f"Agent '{agent}' ({label}): the answer was cut off at max_tokens "
            f"({max_tokens_for(agent)}, agents/contracts.py) before it was complete. "
            f"Raise the cap or shorten the input; this is not a schema problem."
        )
    for text in _raw_texts(raw):
        answer = _rebuild(text, schema)
        if answer is not None:
            return answer, "salvage"
    raise EmptyOutputError(
        f"Agent '{agent}' ({label}) returned nothing that fits {schema.__name__}: "
        f"{out.get('parsing_error') or 'no tool call and no JSON in the text'}"
    )


def _count_tokens(run: dict, out) -> None:
    usage = getattr(out.get("raw") if isinstance(out, dict) else None, "usage_metadata", None) or {}
    run["tokens_in"] += usage.get("input_tokens", 0) or 0
    run["tokens_out"] += usage.get("output_tokens", 0) or 0


def _offline_answer(agent: str, prompt: str, schema, fake_json: str | None):
    """Fake LLM answer. Used by offline mode, and as the fallback after 429s."""
    from pydantic import ValidationError

    llm = make_chat_model(agent, fake_responses=[fake_json or "{}"])
    try:
        return schema.model_validate_json(llm.invoke(prompt).content)
    except ValidationError as exc:
        # Two different causes, two different messages (#79 item 3). The old
        # single message always blamed the missing default, which sent anyone
        # debugging a BROKEN fixture looking for one that was right there. The
        # ValidationError goes in the text, not just __cause__: the bridge and
        # the drivers print the exception, never its chain.
        if fake_json is None:
            raise ValueError(
                f"Offline answer: agent '{agent}' has no fake_json, and the default "
                f"'{{}}' does not satisfy {schema.__name__} (it has required fields). "
                f"Give the structured_call an explicit fake_json. Details: {exc}"
            ) from exc
        raise ValueError(
            f"Offline answer: agent '{agent}' was given a fake_json, but it does not "
            f"satisfy {schema.__name__}. Fix the fixture, not the schema. Details: {exc}"
        ) from exc


# The ladder (#112 4a), per provider, each rung recorded in the run's trace line:
#   1. function_calling (the tool definition built from the schema)
#   2. salvage what came back - a rejected generation, or text instead of a tool call
#   3. retry with a nudge (none_attempts in total on rung 1)
#   4. json_mode on the SAME provider, once - a second way to ask for the same object.
#      It sends no schema, so it is offered only to agents with a contract: their
#      prompt carries the shape block (agents/contracts.py).
#   5. the next provider in the lane (with_fallbacks in _live_answer)
_METHODS = ("function_calling", "json_mode")


def _link(agent: str, label: str, model, schema, run: dict, methods: tuple[str, ...]):
    """One provider in the lane: rungs 1-4 above, then 429 / 5xx retries with a fixed
    wait. Whatever is still failing after that goes up to with_fallbacks."""
    from langchain_core.runnables import RunnableLambda

    # Bound per provider and method: tool calls and response formats differ.
    bindings = [(m, model.with_structured_output(schema, method=m, include_raw=True)) for m in methods]

    def ask(text: str):
        last: Exception | None = None
        for method, bound in bindings:
            tries = config.RETRY["none_attempts"] if method == methods[0] else 1
            for _ in range(tries):
                run["calls"] += 1
                run["by"] = label
                # A retry must differ from the attempt that failed (#76 item 1). The flag is
                # the run's, not the provider's, so a fallback starts nudged (#113 item 3).
                prompt = f"{text}\n\n{_RETRY_NUDGE}" if run["nudged"] else text
                try:
                    out = bound.invoke(prompt)
                except Exception as exc:
                    mapped = _classify(exc)
                    if isinstance(mapped, EmptyOutputError):
                        # The model answered; it just did not package it as a tool call.
                        # If what it wrote fits the schema, that IS the answer (#91).
                        salvaged = _salvage(exc, schema)
                        if salvaged is not None:
                            run["rung"] = f"{method}+salvage"
                            return salvaged
                        run["nudged"], last = True, mapped
                        continue
                    if isinstance(mapped, (RateLimitedError, TransientError)):
                        raise mapped from exc
                    if method != methods[0]:
                        # The second binding is a best effort: a provider/model that refuses
                        # json_mode must not end the run - fall over instead.
                        last = EmptyOutputError(f"{label}: {method} unavailable: {exc}")
                        break
                    raise  # 400 schema / 401 / 403: no rung fixes these
                _count_tokens(run, out)
                try:
                    answer, how = _read(out, schema, agent, label)
                except TruncatedOutputError:
                    raise                              # same cap, same cut-off: next provider
                except EmptyOutputError as exc:
                    run["nudged"], last = True, exc
                    continue
                run["rung"] = method if how == "parsed" else f"{method}+salvage"
                return answer
        raise last or EmptyOutputError(f"Agent '{agent}' ({label}): no answer.")

    # 429 / 5xx: the whole ladder again after the same wait every time
    # (exp_base=1, jitter=0 keeps it fixed).
    wait = config.RETRY["rate_limit_wait_seconds"]
    return RunnableLambda(ask).with_retry(
        retry_if_exception_type=(RateLimitedError, TransientError),
        exponential_jitter_params={"initial": wait, "max": wait, "exp_base": 1, "jitter": 0},
        stop_after_attempt=config.RETRY["rate_limit_attempts"],
    )


def _live_answer(agent: str, prompt: str, schema, fake_json: str | None):
    """Real call: each provider in the agent's lane (config.FALLBACK_CHAINS) gets the
    ladder in _link; when it is used up, the next provider with a key takes over."""
    from langchain_core.runnables import RunnableLambda
    from utils.trace import log, step  # TEMP tracing

    primary = config.model_for(agent)
    run = {"calls": 0, "by": primary, "rung": "?", "nudged": False, "tokens_in": 0, "tokens_out": 0}
    methods = _METHODS if agent in CONTRACTS else _METHODS[:1]
    cap = max_tokens_for(agent)

    # Primary from make_chat_model (keeps its per-agent settings); the rest from the lane.
    # A provider with no key is skipped, the primary included: building its client
    # would raise here, before any fallback could take over.
    lane = config.fallback_chain_for(agent)
    links = []
    if _has_key(lane[0]):
        links.append(_link(agent, primary, make_chat_model(agent), schema, run, methods))
    for entry in lane[1:]:
        model = _chat_for(entry, max_tokens=cap)
        if model is not None:
            links.append(_link(agent, entry, model, schema, run, methods))

    # Last resort, off for production: a fake answer is fake data in a live run.
    if config.RETRY["fallback_offline"]:
        def offline(text: str):
            run["by"], run["rung"] = "offline fake LLM", "offline"
            return _offline_answer(agent, text, schema, fake_json)

        links.append(RunnableLambda(offline))

    if not links:
        raise RuntimeError(
            f"Agent '{agent}': no provider in its lane has an API key ({', '.join(lane)}). "
            f"Set one of {sorted({_KEY_FOR[e.partition('/')[0]] for e in lane})} in .env."
        )
    chain = links[0].with_fallbacks(links[1:], exceptions_to_handle=_FALL_OVER) if len(links) > 1 else links[0]

    started = time.monotonic()
    with step(f"calling {agent} LLM ({config.model_for(agent)}) - waiting for response"):
        result = chain.invoke(prompt, config=observability.callbacks(agent))
    log(
        f"{agent}: served by {run['by']} via {run['rung']}{' (nudged)' if run['nudged'] else ''} | "
        f"model calls {run['calls']} | tokens in {run['tokens_in']} out {run['tokens_out']} | "
        f"fallback {'no' if run['by'] == primary else 'YES'} | {time.monotonic() - started:.1f}s"
    )
    return result


def structured_call(agent: str, user_input: str, schema, *, fake_json: str | None = None, system_prompt:str | None = None):
    """Run an agent's model, return a validated `schema` instance.

    The single door every agent uses to reach an LLM. Call + parse plumbing lives
    here so a node only says what it wants, not how to get it.
    """
    check_schema(agent, schema)  # a registered agent answers with its own schema only
    system = system_prompt if system_prompt is not None else spec_for(agent).system_prompt
    if agent in CONTRACTS:
        # The shape comes from the schema itself, so no prompt can leave out or rename a
        # field again (#91, #112). The YAML keeps only the judgement rules.
        prompt = f"{system}\n\n{shape_block(schema)}\n\n{user_input}"
    else:
        prompt = f"{system}\n\n{user_input}"

    if config.fake_llm_active():
        return _offline_answer(agent, prompt, schema, fake_json)
    return _live_answer(agent, prompt, schema, fake_json)
