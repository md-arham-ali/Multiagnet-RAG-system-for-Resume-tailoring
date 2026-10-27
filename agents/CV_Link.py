import threading
from pathlib import Path

from state.state import GraphState, LineLink, MatchStatus, Stage

_parts = None
_parts_lock = threading.Lock()


def _get_parts() -> tuple:
    # Loads the matcher's models once per process; the tables and retrievers are rebuilt on every call (#44).
    # out: (embedder, reranker, profile table, bullet table, profile retriever, bullet retriever),
    #      fresh for this run; pass it as Matcher(*_get_parts(), k=...). Raises if the profile index is unusable.
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
        from utils.cv_handling.cv_match import refresh_matcher_parts

        # Never hand out the cached tuple itself: a run writes its query vectors into the retrievers
        # it is given, and a record added since the first run must be in the table it matches against.
        return refresh_matcher_parts(_parts)


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

    from utils.cv_handling.cv_extract import has_sections, has_text, parse_cv
    from utils.cv_handling.cv_match import K_CANDIDATES, Matcher

    tree, lines = parse_cv(pdf)
    # Check BEFORE _get_parts() (#79 item 4). The upload path has refused these
    # two since 10-09 (backend/cv_store.py, CvNoText / CvNoSections), but the
    # pipeline path never did, so a CLI run or any direct cv_path could load the
    # embedder, the reranker and both indexes - ~20s cold - to link an empty
    # tree, then hand Document a CV with nothing in it and no error anywhere.
    if not has_text(lines):
        raise ValueError(
            f"cv_link: '{pdf.name}' has no extractable text (a scan or an image-only "
            f"PDF?). Nothing was parsed, so there is nothing to link or patch."
        )
    if not has_sections(tree):
        raise ValueError(
            f"cv_link: '{pdf.name}' parsed to a header only - no Experience, Projects, "
            f"Skills or Education section was found. There is nothing for Document to patch."
        )
    matcher = Matcher(*_get_parts(), k=K_CANDIDATES)
    matcher.run(tree)
    links = list(matcher.links.values())
    # Account scope (#73 item 7). The matcher reads the shared `profile` collection,
    # so a line could link to another account's entry, and Document then fetches
    # that record's text into its writer prompt. Unscoped runs are unchanged.
    from agents.base import run_profile_id
    from learning.profile_store import foreign_entry_ids

    profile_id = run_profile_id(state)
    if profile_id:
        links = _without_foreign(links, foreign_entry_ids(profile_id))
    return {
        "cv_tree": tree,
        "line_links": links,
        "stage": Stage.DOCUMENT,
    }


def _without_foreign(links: list[LineLink], foreign: set[str]) -> list[LineLink]:
    # Drops other accounts' record ids from every link.
    # in : links from the matcher, foreign = manual-entry ids this account must not see
    # out: the same links; a link whose picked record was foreign is no longer `matched`
    from learning.profile_store import is_foreign
    from utils.trace import log

    out, touched = [], 0
    for link in links:
        kept = [i for i in link.source_ids if not is_foreign(i, foreign)]
        if kept == link.source_ids:
            out.append(link)
            continue
        touched += 1
        if not kept:
            out.append(link.model_copy(update={"source_ids": [], "status": MatchStatus.UNMATCHED, "score": 0.0}))
        elif kept[0] != link.source_ids[0]:
            # The status and score were earned by the dropped record; the rest only
            # cleared the partial threshold, and their own scores are not on the link.
            out.append(link.model_copy(update={"source_ids": kept, "status": MatchStatus.PARTIAL, "score": 0.0}))
        else:
            out.append(link.model_copy(update={"source_ids": kept}))
    if touched:
        log(f"cv_link: removed other accounts' records from {touched} line link(s)")
    return out
