"""
Durable checkpointer for the human gates.

interrupt() unwinds the whole run when a gate pauses, so state has to live on
disk. Without it a paused run dies with the process and every agent before the
gate runs again. SQLite for now, swap make_checkpointer to PostgresSaver later.

    graph = build_graph(checkpointer=make_checkpointer())
    graph.invoke(state, config={"configurable": {"thread_id": run_id}})
"""

from __future__ import annotations

import sqlite3
from enum import Enum
from inspect import isclass
from pathlib import Path

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import BaseModel

import config
from state import state as _state_module


def state_types() -> list[type]:
    """
    Every model / Enum in state/state.py, found by inspection.

    Not hand-listed on purpose: a manual list goes stale the moment someone adds
    an artifact, and brings the deserialization warning back.
    """
    return [
        obj
        for obj in vars(_state_module).values()
        if isclass(obj)
        and obj.__module__ == _state_module.__name__
        and issubclass(obj, (BaseModel, Enum))
    ]


def make_serde() -> JsonPlusSerializer:
    """
    Serde that knows our state types.

    LangGraph's default is warn-and-allow-anything on unknown types. A checkpoint
    DB is deserialized input, so allowlist our own models instead of trusting it:
    ours load silently, langchain's own safe types still load, rest is blocked.
    """
    return JsonPlusSerializer(allowed_msgpack_modules=state_types())


def make_checkpointer(db_path: str | Path | None = None) -> SqliteSaver:
    """
    Open the checkpoint DB (creating it if needed) and return a saver.

    Connection opened by hand because from_conn_string takes no `serde`.
    check_same_thread=False since the bridge runs graphs in worker threads.
    """
    path = Path(db_path) if db_path is not None else config.CHECKPOINT_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    return SqliteSaver(conn, serde=make_serde())
