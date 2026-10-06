import threading
from pathlib import Path

from state.state import GraphState, Stage

_parts = None
_parts_lock = threading.Lock()


def _get_parts() -> tuple:
    # Loads the matcher's models and indexes once per process, on the first call.
    # out: (embedder, reranker, profile table, bullet table, profile retriever, bullet retriever);
    #      pass it as Matcher(*_get_parts(), k=...). Raises if the profile index is unusable.
    global _parts
    with _parts_lock:
        if _parts is None:
            from utils.cv_handling.cv_match import load_matcher_parts

            parts = load_matcher_parts()
            if parts is None:
                raise RuntimeError(
                    "cv_link: the profile index is missing or was built with another model. "
                    "Build it with scripts/build_vectordb.py."
                )
            _parts = parts
    return _parts


def node(state: GraphState) -> dict:
    # Step 3: parse state.cv_path -> cv_tree, link its lines -> line_links.
    # in : state.cv_path = path to the CV PDF (required)
    # out: cv_tree + line_links (no vectors), stage -> DOCUMENT
    if not state.cv_path:
        raise ValueError("cv_link needs state.cv_path (a CV PDF) and none was given")
    pdf = Path(state.cv_path)
    # same CV already linked: a rejected gate 3 re-runs matching, which lands here again
    if state.cv_tree is not None and state.cv_tree.source_file == pdf.name:
        return {"stage": Stage.DOCUMENT}

    from utils.cv_handling.cv_extract import parse_cv
    from utils.cv_handling.cv_match import K_CANDIDATES, Matcher

    tree, _lines = parse_cv(pdf)
    matcher = Matcher(*_get_parts(), k=K_CANDIDATES)
    matcher.run(tree)
    return {
        "cv_tree": tree,
        "line_links": list(matcher.links.values()),
        "stage": Stage.DOCUMENT,
    }
