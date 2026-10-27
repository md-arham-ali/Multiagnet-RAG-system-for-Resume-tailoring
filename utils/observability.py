"""Langfuse tracing for live runs: one trace per run, LLM calls nested inside it.

Off unless both LANGFUSE keys are set (config.LANGFUSE_ENABLED) and the run is
live. Tracing never fails a run: any setup or export problem is logged once and
the work carries on untraced.
"""

from __future__ import annotations

import re
from contextlib import ExitStack, contextmanager

import config

_client = None
_broken = False

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
# Attributes the SDK fills with prompts and answers; everything else is left alone.
_TEXT_KEYS = (
    "langfuse.observation.input", "langfuse.observation.output",
    "langfuse.trace.input", "langfuse.trace.output",
)


def _redact(text: str) -> str:
    text = _EMAIL.sub("[email]", text)
    return _PHONE.sub(lambda m: "[phone]" if sum(c.isdigit() for c in m.group()) >= 10 else m.group(), text)


def _mask_otel_spans(*, params):
    """Safety net: contact details never leave the machine, even if one reaches a prompt.
    The CV tree is already scrubbed upstream (cv_link), so this normally changes nothing."""
    from langfuse.types import MaskOtelSpansResult, OtelSpanPatch

    patches = {}
    for ident, span in params.spans.items():
        changed = {}
        for key in _TEXT_KEYS:
            value = span.attributes.get(key)
            if isinstance(value, str) and (clean := _redact(value)) != value:
                changed[key] = clean
        if changed:
            patches[ident] = OtelSpanPatch(set_attributes={**changed, "masking.applied": True})
    return MaskOtelSpansResult(span_patches=patches)


def _get_client():
    global _client, _broken
    if _client is not None or _broken:
        return _client
    try:
        from langfuse import Langfuse

        _client = Langfuse(
            public_key=config.LANGFUSE_PUBLIC_KEY,
            secret_key=config.LANGFUSE_SECRET_KEY,
            base_url=config.LANGFUSE_HOST,
            environment=config.TEST_MODE,
            mask_otel_spans=_mask_otel_spans,
        )
    except Exception as exc:
        _broken = True
        print(f"   … langfuse off: {type(exc).__name__}: {exc}")
    return _client


def active() -> bool:
    return config.LANGFUSE_ENABLED and not config.fake_llm_active()


def callbacks(agent: str) -> dict:
    """LangChain config for one LLM call; empty when tracing is off. The handler joins
    whatever trace is open on this context (see segment), else starts its own."""
    if not active() or _get_client() is None:
        return {}
    try:
        from langfuse.langchain import CallbackHandler

        return {"callbacks": [CallbackHandler()], "run_name": agent}
    except Exception as exc:
        print(f"   … langfuse tracing off for {agent}: {type(exc).__name__}: {exc}")
        return {}


@contextmanager
def segment(run: dict, label: str):
    """One stretch of a run between human gates. Every segment of a run lands in the same
    trace (id derived from the run id), so a run paused for minutes, or resumed after a
    restart, still reads as one trace in Langfuse."""
    stack = ExitStack()
    client = _get_client() if active() else None
    if client is not None:
        try:
            from langfuse import propagate_attributes

            span = stack.enter_context(client.start_as_current_observation(
                trace_context={"trace_id": client.create_trace_id(seed=run["id"])},
                name=label,
                as_type="agent",
                metadata={"run_id": run["id"], "mode": run["mode"]},
            ))
            stack.enter_context(propagate_attributes(
                trace_name="tailor-cv-run",
                session_id=run["id"],
                user_id=str(run.get("owner") or "")[:200] or None,
                tags=[run["mode"]],
                metadata={"run_id": run["id"]},
            ))
        except Exception as exc:
            stack.close()
            stack = ExitStack()
            print(f"   … langfuse segment off: {type(exc).__name__}: {exc}")
    try:
        yield
    finally:
        try:
            stack.close()
            if client is not None:
                client.flush()  # a gate can wait for minutes; show what happened so far
        except Exception as exc:
            print(f"   … langfuse flush failed: {type(exc).__name__}: {exc}")
