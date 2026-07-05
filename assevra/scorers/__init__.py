"""
The four Assevra reliability scorers.

Each scorer module exposes:
  - DIMENSION: the dimension name it handles.
  - score(rows, judge) -> DimensionResult: score its rows.

Grounding and safety are LLM-as-judge; PII and task-completion are deterministic
(their `score` accepts a `judge` argument for a uniform signature but ignores it).
"""
from . import grounding, pii, safety, task_completion

__all__ = ["grounding", "pii", "safety", "task_completion"]
