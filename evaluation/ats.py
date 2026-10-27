"""
Deterministic ATS check — no LLM (Build.md #15).

Given the JD keywords (exact phrasing preserved by the JD Analysis Agent) and the
final document text, compute a reproducible keyword-coverage score using fuzzy
matching. Cheap, measurable, repeatable — the same inputs always give the same score.

Called by evaluation/checks.py (the checking module), never by an agent directly.
"""

from __future__ import annotations

import re

# Keywords shorter than this are matched exactly only. partial_ratio scores a short
# needle 100 against any word containing it ("go" in "good", "sql" in "nosql"),
# which would count a keyword the document never states.
MIN_FUZZY_LEN = 5


def keyword_coverage(
    keywords: list[str],
    text: str,
    threshold: int = 88,
) -> tuple[float, list[str]]:
    """
    Fraction of JD keywords present in `text` (whole-word or fuzzy match).

    Returns (coverage_score in [0, 1], list of missing keywords). A keyword counts
    as covered if it appears as a whole word/phrase, or - for keywords of at least
    MIN_FUZZY_LEN characters - its best fuzzy partial match scores at or above
    `threshold` (0-100). The fuzzy pass is what still catches PDF-glued text
    ("Learningsystem"). No keywords gives 0.0; callers that need "not measured"
    must check for that themselves. A keyword listed twice (any case) counts
    once, and a miss is reported in its first spelling.
    """
    from rapidfuzz import fuzz

    text_lower = text.lower()
    # one entry per keyword, case-insensitive: the JD LLM can repeat one (#66)
    cleaned: dict[str, str] = {}
    for kw in keywords:
        if kw and kw.strip():
            cleaned.setdefault(kw.strip().lower(), kw.strip())
    if not cleaned:
        return 0.0, []

    missing: list[str] = []
    hits = 0
    for needle, kw in cleaned.items():
        # (?<!\w) / (?!\w) instead of \b, so keywords that end in a symbol
        # ("c++", "c#", ".net") still get a boundary check. "++", "#" and "&"+letter
        # also end a match, so "c" isn't found in "c++"/"c#", nor "r" in "r&d" (#66).
        exact = re.search(
            rf"(?<!\w)(?<!\w&){re.escape(needle)}(?!\w|\+\+|#|&\w)", text_lower
        ) is not None
        if exact or (len(needle) >= MIN_FUZZY_LEN and fuzz.partial_ratio(needle, text_lower) >= threshold):
            hits += 1
        else:
            missing.append(kw)

    return hits / len(cleaned), missing
