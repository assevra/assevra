"""
Task-completion scorer (deterministic).

Did the agent actually finish the job? Each task row lists `must_include`: the
required slots or facts a correct completion must contain (a member ID prompt, a
confirmation number, a follow-up date). A row passes only if every required item
appears in the output. Matching is case-insensitive substring matching, which is
deterministic and dependency-free.

This is a floor, not a ceiling: substring presence proves the required facts are
there, not that the wording is good. It deliberately does not judge tone or
phrasing -- that is a separate concern (and, if you want it scored, a judge
dimension). METHODOLOGY.md states this limitation explicitly.
"""
from __future__ import annotations

from typing import Optional

from ..scorecard import DimensionResult, RowResult

DIMENSION = "task_completion"
DIMENSION_THRESHOLD = 0.90


def _output(row: dict) -> str:
    return row.get("agent_output") or row.get("expected", "")


def _missing_items(output: str, must_include: list[str]) -> list[str]:
    low = output.lower()
    return [item for item in must_include if item.lower() not in low]


def score(rows: list[dict], judge: Optional[object] = None) -> DimensionResult:
    """Score all task-completion rows deterministically. `judge` is ignored
    (kept for a uniform scorer signature)."""
    result = DimensionResult(
        name=DIMENSION,
        mode="deterministic",
        threshold=DIMENSION_THRESHOLD,
    )
    result.notes = (
        "pass = every required item in the row's must_include list appears in "
        "the output (case-insensitive substring). Presence only; not phrasing."
    )

    for row in rows:
        output = _output(row)
        must_include = row.get("must_include", [])
        missing = _missing_items(output, must_include)
        if not must_include:
            # No required items declared: nothing to verify -> treat as a pass
            # but say so, so an under-specified row is visible in the report.
            result.rows.append(
                RowResult(
                    row_id=row.get("id", "?"),
                    passed=True,
                    detail="no must_include declared (nothing to verify)",
                )
            )
        elif missing:
            result.rows.append(
                RowResult(
                    row_id=row.get("id", "?"),
                    passed=False,
                    detail="missing required: " + ", ".join(repr(m) for m in missing),
                )
            )
        else:
            result.rows.append(
                RowResult(
                    row_id=row.get("id", "?"),
                    passed=True,
                    detail=f"all {len(must_include)} required items present",
                )
            )
    return result
