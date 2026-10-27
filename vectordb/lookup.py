"""
Read profile records by id straight from the Chroma index. No embedding model is
loaded, so it is cheap enough to call from a node that only needs the text of a
few records it was pointed at (a CV line's linked records, for instance).

    from vectordb.lookup import profile_blocks
    blocks = profile_blocks(["project:derivatives_trading_bot_001", "work_experience:exp_003"])
"""

from __future__ import annotations

import chromadb

import config
from state.state import ProfileBlock

PROFILE_COLLECTION = "profile"


def profile_blocks(ids: list[str]) -> list[ProfileBlock]:
    # in : ids = profile record ids (the Chroma ids); duplicates and unknown ids are allowed
    # out: ProfileBlocks shaped the way agents/profile.py shapes retrieved evidence, in the order of
    #      `ids`, duplicates removed; an id that is not in the index is skipped
    # raises: RuntimeError if the profile collection does not exist
    ids = list(dict.fromkeys(ids))
    if not ids:
        return []
    client = chromadb.PersistentClient(path=str(config.VECTORDB_DIR))
    try:
        col = client.get_collection(PROFILE_COLLECTION)
    except Exception as exc:
        raise RuntimeError(
            f"No '{PROFILE_COLLECTION}' collection in {config.VECTORDB_DIR}. "
            f"Build it: python scripts/build_vectordb.py"
        ) from exc
    got = col.get(ids=ids, include=["documents", "metadatas"])
    by_id = {i: (doc or "", meta or {}) for i, doc, meta in zip(got["ids"], got["documents"], got["metadatas"])}
    return [
        ProfileBlock(source_id=i, content=by_id[i][0], category=by_id[i][1].get("type"), skills=[])
        for i in ids
        if i in by_id
    ]
