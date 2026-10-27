"""
The hard-constraint claim list (knowledge_base/do_not_claim/do_not_claim.json).

The file's own header states the contract: "Injected WHOLE into the Document
Agent and the Verifier - never embedded, never retrieved top-k. Checked
exhaustively; a near-miss is a violation." So this module does two things and
nothing else:

  describe_claims   the list as prompt text, for the writer's packet
  check_text        the same list matched over a piece of text, for a code guard

Both read the one file, so the text the model is shown and the check that
enforces it cannot drift apart (the pattern utils/bullet_rules.py already uses
for the bullet rules).

Matching is per `match` term, not on the claim sentence: the file carries the
terms precisely because "Worked at Google" has to be caught as "google". Terms
are matched as phrases, never as substrings - a bare `in` test makes "mba" fire
inside "ambassador".

    from utils.do_not_claim import check_text
    check_text("Holds a PhD in CS")   # -> [DoNotClaimHit(text='phd', matched_entry='PhD in Computer Science')]
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

import config
from state.state import DoNotClaimHit

DNC_FILE = config.KB_DO_NOT_CLAIM_DIR / "do_not_claim.json"


def phrase_pattern(phrase: str) -> Optional[re.Pattern[str]]:
    """A regex matching `phrase` as a phrase, case-insensitively.

    Lookarounds on a word character rather than a word boundary, so a phrase
    ending in punctuation ("C++", "ph.d", "$100m") still anchors instead of
    never matching; the tokens are joined loosely so "10+  years" and
    "10+-years" count as the same phrase. Returns None for an empty phrase,
    which would otherwise compile to a pattern matching everywhere.
    """
    tokens = [re.escape(t) for t in (phrase or "").split()]
    if not tokens:
        return None
    return re.compile(r"(?<!\w)" + r"\W+".join(tokens) + r"(?!\w)", re.IGNORECASE)


@lru_cache(maxsize=1)
def load_claims(path: Path = DNC_FILE) -> list[dict]:
    # in : path = the do-not-claim JSON
    # out: its forbidden_claims entries. Cached, so an edit to the file needs a
    #      restart (or load_claims.cache_clear()), like load_rules.
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return list(data.get("forbidden_claims", []))


@lru_cache(maxsize=1)
def _terms(path: Path = DNC_FILE) -> tuple[tuple[str, str, re.Pattern[str]], ...]:
    # (match term, the claim it belongs to, its compiled pattern) for every term.
    # The claim sentence itself is matched too: a draft that writes it out in
    # full is a hit even if the file forgot to list it as a term.
    out = []
    for entry in load_claims(path):
        claim = entry.get("claim", "")
        for term in [*entry.get("match", []), claim]:
            pattern = phrase_pattern(term)
            if pattern is not None:
                out.append((term, claim, pattern))
    return tuple(out)


def check_text(text: str, location: Optional[str] = None) -> list[DoNotClaimHit]:
    # in : text = any draft text, location = where it came from (a node id, a section)
    # out: one hit per claim the text touches, in file order (empty = clean).
    #      One hit per CLAIM, not per term: two terms of the same claim are one
    #      violation, and the caller reports the claim, never the term list.
    hits: list[DoNotClaimHit] = []
    seen: set[str] = set()
    for term, claim, pattern in _terms():
        if claim in seen:
            continue
        found = pattern.search(text or "")
        if found:
            seen.add(claim)
            hits.append(DoNotClaimHit(text=found.group(0), matched_entry=claim, location=location))
    return hits


DNC_HEADER = "DO NOT CLAIM (never write any of these, in any wording):"


def describe_claims() -> str:
    # The list in plain words for a writer prompt. Claim sentences only: the
    # match terms are the guard's business, and listing "google" as forbidden
    # text would read as an instruction to avoid the word, not the claim.
    claims = [c["claim"] for c in load_claims() if c.get("claim")]
    return "\n".join([DNC_HEADER, *([f"- {c}" for c in claims] or ["(none)"])])
