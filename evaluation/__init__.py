"""
Evaluation package.

Runs post-approval and scores a completed run across:
  - deterministic ATS checks (checks.py runs them; ats.py is the keyword check — Build.md #15),
  - retrieval precision + faithfulness (deepeval metrics — Build.md #13/#16;
    ragas is the intended tool but is currently incompatible with the langgraph
    1.x stack, see requirements.txt),
  - generation quality (LLM-as-judge, via the Evaluation Agent).

Scores are written to the Learning Store with the prompt version + learning slice
used, so a future score change can be attributed (Build.md #24).
"""

from evaluation.ats import keyword_coverage

__all__ = ["keyword_coverage"]
