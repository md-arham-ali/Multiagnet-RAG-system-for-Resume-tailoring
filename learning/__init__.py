"""
Learning Store.

Storage strategy (Build.md): structured per-agent records (scores / corrections)
are kept as plain JSON — "agent storage to be limited to JSON files" — while
exemplar retrieval by role-type is a vector + metadata-filter concern layered on
top. Records land under knowledge_base/learning/. Written post-approval by the
Evaluation Agent; read by the Supervisor when selecting exemplars to inject.
"""

from learning.store import LearningStore

__all__ = ["LearningStore"]
