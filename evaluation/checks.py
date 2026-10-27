"""
The checking module (Q6/Q7, decided 2026-08-27): ATS checks and, later,
writing-instruction compliance. Not the Verifier, not the Critic.

One rule settles the "hybrid vs LLM-free" wording conflict: a check may use an
LLM, but the ATS score is built ONLY from deterministic checks, so the same
document always gets the same score. An LLM-assisted check (e.g. "is the number
in the right proportion") reports misses and never moves `ats_score`.

Built so far: the keyword check. Still to come (stage E): parsing,
section-structure, section-availability, numeric-value, date-format, and the
cv_bullet_generation_v1.json compliance check. How several checks combine into
one score is the user's decision (bugs_audit_fixed.md #53); until then the score
is the keyword check alone.

Usage: run_checks(state.requirements, state.document).ats_score
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from evaluation.ats import keyword_coverage
from state.state import Document, Requirements


@dataclass(frozen=True)
class CheckResult:
    name: str
    score: Optional[float]          # in [0, 1]; None = not measured (missing input)
    misses: list[str] = field(default_factory=list)
    deterministic: bool = True      # only deterministic checks may feed ats_score


@dataclass(frozen=True)
class CheckReport:
    checks: list[CheckResult]

    def get(self, name: str) -> Optional[CheckResult]:
        return next((c for c in self.checks if c.name == name), None)

    @property
    def ats_score(self) -> Optional[float]:
        # One deterministic check today, so no weights yet (#53). None, never 0.0,
        # when it could not be measured: a 0.0 would read as "covered nothing".
        keyword = self.get("keyword")
        return keyword.score if keyword is not None else None


def check_keywords(requirements: Optional[Requirements], document: Optional[Document]) -> CheckResult:
    """in: the JD keywords + the final draft. out: coverage, and the keywords it misses."""
    keywords = [k for k in (requirements.keywords if requirements else []) if k and k.strip()]
    if not keywords or document is None or not document.content.strip():
        return CheckResult(name="keyword", score=None)
    score, missing = keyword_coverage(keywords, document.content)
    return CheckResult(name="keyword", score=score, misses=missing)


def run_checks(requirements: Optional[Requirements], document: Optional[Document]) -> CheckReport:
    """in: what the checks read from state. out: every check's result, in a fixed order."""
    return CheckReport(checks=[check_keywords(requirements, document)])
