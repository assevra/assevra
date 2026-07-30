"""
Latency budget (deterministic).

A correct answer that arrives after the user has given up is a failed
interaction. Latency is the reliability property teams most often measure in
production and least often gate on before release, and the gap between those two
is where regressions live: a retrieval change adds a second, nobody notices until
support tickets do.

Assevra scores latency the same way it scores everything else — against a
declared budget, as a pass rate with a confidence interval — rather than
reporting an average. Averages hide the tail, and the tail is the user
experience. The dimension notes therefore also report p50/p95/max over the rows
that carried a measurement.

Row fields:

``latency_ms``         measured wall-clock latency of the run.
``latency_budget_ms``  this case's allowance; falls back to ``budgets.latency_ms``
                       in ``.assevra.yml``.

A row passes when its measured latency is at or under budget. The default
threshold is 0.95 — a small share of slow runs is normal; a *quarter* of them is
a regression. Set it to 1.00 for a hard real-time path.
"""
from __future__ import annotations

from typing import Optional

from ..scorecard import DimensionResult, RowResult

DIMENSION = "latency"
MODE = "deterministic"
DIMENSION_THRESHOLD = 0.95
SUMMARY = "Did each run finish inside its latency budget?"
ANSWER_KEY = ("latency_budget_ms",)
REQUIRES = ()
LABEL_HINT = (
    "Set latency_budget_ms on the row, or budgets.latency_ms in .assevra.yml, "
    "and record latency_ms."
)


def _default_budget(options: Optional[dict]):
    budgets = (options or {}).get("budgets", {}) or {}
    return budgets.get("latency_ms")


def measured_latency(row: dict) -> Optional[float]:
    for key in ("latency_ms", "duration_ms", "elapsed_ms"):
        value = row.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    seconds = row.get("latency_s")
    if isinstance(seconds, (int, float)):
        return float(seconds) * 1000.0
    return None


def resolve_budget(row: dict, options: Optional[dict] = None) -> Optional[float]:
    value = row.get("latency_budget_ms")
    if isinstance(value, (int, float)):
        return float(value)
    default = _default_budget(options)
    return float(default) if isinstance(default, (int, float)) else None


def is_labeled(row: dict, options: Optional[dict] = None) -> bool:
    """Both halves have to be there: a budget, and a measurement to compare."""
    return resolve_budget(row, options) is not None and measured_latency(row) is not None


def _percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, int(round(q * (len(sorted_values) - 1))))
    return sorted_values[index]


def score(rows: list[dict], judge: Optional[object] = None, options: Optional[dict] = None) -> DimensionResult:
    result = DimensionResult(name=DIMENSION, mode=MODE, threshold=DIMENSION_THRESHOLD)
    result.notes = (
        "pass = measured latency is at or under the row's budget "
        "(latency_budget_ms, else budgets.latency_ms)."
    )

    observed: list[float] = []
    for row in rows:
        row_id = row.get("id", "?")
        budget = resolve_budget(row, options)
        latency = measured_latency(row)

        if budget is None:
            result.rows.append(
                RowResult(row_id=row_id, passed=True, detail="no latency budget set (nothing to verify)")
            )
            continue
        if latency is None:
            # Unverifiable, not failed — `assevra validate` reports the row as
            # UNLABELED, and --strict is what makes that fatal.
            result.rows.append(
                RowResult(
                    row_id=row_id,
                    passed=True,
                    detail="no latency_ms recorded, nothing verified",
                )
            )
            continue
        observed.append(latency)
        if latency <= budget:
            result.rows.append(
                RowResult(
                    row_id=row_id,
                    passed=True,
                    detail=f"{latency:.0f} ms of {budget:.0f} ms budget",
                    raw_score=round(latency, 3),
                )
            )
        else:
            result.rows.append(
                RowResult(
                    row_id=row_id,
                    passed=False,
                    detail=f"{latency:.0f} ms exceeds the {budget:.0f} ms budget",
                    raw_score=round(latency, 3),
                )
            )

    if observed:
        observed.sort()
        result.notes += (
            f" Observed: p50 {_percentile(observed, 0.5):.0f} ms, "
            f"p95 {_percentile(observed, 0.95):.0f} ms, max {observed[-1]:.0f} ms "
            f"over {len(observed)} timed rows."
        )
    return result


def validate_row(row: dict, options: Optional[dict] = None) -> list[tuple]:
    messages: list[tuple] = []
    if resolve_budget(row, options) is not None and measured_latency(row) is None:
        messages.append(
            (
                "warning",
                "unmeasurable_latency",
                "a latency budget applies but the row records no latency_ms",
                "latency_ms",
                "record the measured wall-clock latency when you capture the trace",
            )
        )
    for key in ("latency_ms", "latency_budget_ms"):
        if key in row and not isinstance(row[key], (int, float)):
            messages.append(("error", "bad_type", f"{key} must be a number", key, None))
    return messages
