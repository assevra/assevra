"""
Cost budget (deterministic).

Reliability is not only about being right. An agent that answers correctly and
costs eleven dollars per conversation is not shippable, and the failure shows up
in a finance review rather than a test suite — which is exactly why it should be
in the scorecard. Cost is a release-gating property with a threshold, so it
belongs next to grounding and safety rather than in a dashboard nobody opens.

The measured cost of a row comes from whichever the trace recorded:

* ``cost_usd`` — the provider already priced the call. Preferred; nothing to
  assume.
* ``usage`` (``{"input_tokens": ..., "output_tokens": ...}``) priced with the
  table in ``.assevra.yml``::

      budgets:
        price:
          input_per_mtok: 3.0
          output_per_mtok: 15.0

The budget comes from the row's ``cost_budget_usd`` when the case has its own
allowance, else the project-wide ``budgets.cost_usd``. A row passes when its
measured cost is at or under budget.

Note what this does *not* claim: it prices the run you recorded, on the price
table you supplied. It is not a forecast, and a scorecard cost figure is only as
current as the price table behind it — which is why the table is written into the
dimension notes.
"""
from __future__ import annotations

from typing import Optional

from ..scorecard import DimensionResult, RowResult

DIMENSION = "cost"
MODE = "deterministic"
DIMENSION_THRESHOLD = 0.95
SUMMARY = "Did each run stay inside its cost budget?"
ANSWER_KEY = ("cost_budget_usd",)
REQUIRES = ()
LABEL_HINT = (
    "Set cost_budget_usd on the row, or budgets.cost_usd in .assevra.yml, and "
    "record either cost_usd or usage.{input_tokens,output_tokens}."
)


# Zero-label: a budget is a project-wide policy line, not a per-row judgment, so
# a trace carrying usage or a cost figure is scorable the moment `budgets.cost_usd`
# exists in the config.
AUTOLABEL_NOTE = "scored against budgets.cost_usd; no per-row labeling needed"


def autolabel(interaction: dict, options: Optional[dict] = None):
    if resolve_budget(interaction, options) is None:
        return None
    return {} if measured_cost(interaction, options)[0] is not None else None


def _price_table(options: Optional[dict]) -> dict:
    budgets = (options or {}).get("budgets", {}) or {}
    return budgets.get("price", {}) or {}


def _default_budget(options: Optional[dict]):
    budgets = (options or {}).get("budgets", {}) or {}
    return budgets.get("cost_usd")


def measured_cost(row: dict, options: Optional[dict] = None) -> tuple[Optional[float], str]:
    """(cost in USD, how it was derived) — or (None, why not)."""
    if isinstance(row.get("cost_usd"), (int, float)):
        return float(row["cost_usd"]), "reported by the trace"
    usage = row.get("usage")
    if isinstance(usage, dict):
        price = _price_table(options)
        inp = price.get("input_per_mtok")
        out = price.get("output_per_mtok")
        if isinstance(inp, (int, float)) and isinstance(out, (int, float)):
            in_tok = float(usage.get("input_tokens", 0) or 0)
            out_tok = float(usage.get("output_tokens", 0) or 0)
            total = in_tok / 1e6 * float(inp) + out_tok / 1e6 * float(out)
            return total, f"priced from usage ({in_tok:.0f} in / {out_tok:.0f} out)"
        return None, "usage recorded but no budgets.price table configured"
    return None, "no cost_usd and no usage recorded"


def resolve_budget(row: dict, options: Optional[dict] = None) -> Optional[float]:
    value = row.get("cost_budget_usd")
    if isinstance(value, (int, float)):
        return float(value)
    default = _default_budget(options)
    return float(default) if isinstance(default, (int, float)) else None


def is_labeled(row: dict, options: Optional[dict] = None) -> bool:
    """A cost row is only meaningful when both halves are present: a budget to
    compare against, and a cost that can actually be computed."""
    return resolve_budget(row, options) is not None and measured_cost(row, options)[0] is not None


def score(rows: list[dict], judge: Optional[object] = None, options: Optional[dict] = None) -> DimensionResult:
    result = DimensionResult(name=DIMENSION, mode=MODE, threshold=DIMENSION_THRESHOLD)
    price = _price_table(options)
    price_note = (
        f" price table: ${price.get('input_per_mtok')}/Mtok in, "
        f"${price.get('output_per_mtok')}/Mtok out."
        if price.get("input_per_mtok") is not None
        else ""
    )
    result.notes = (
        "pass = measured cost is at or under the row's budget "
        "(cost_budget_usd, else budgets.cost_usd)." + price_note
    )

    costs = []
    for row in rows:
        row_id = row.get("id", "?")
        budget = resolve_budget(row, options)
        cost, how = measured_cost(row, options)

        if budget is None:
            result.rows.append(
                RowResult(row_id=row_id, passed=True, detail="no cost budget set (nothing to verify)")
            )
            continue
        if cost is None:
            # Unverifiable, not failed — the same contract every other scorer
            # honours. `assevra validate` reports the row as UNLABELED, and
            # --strict is the switch that makes that fatal.
            result.rows.append(
                RowResult(
                    row_id=row_id,
                    passed=True,
                    detail=f"cost not measurable, nothing verified: {how}",
                )
            )
            continue
        costs.append(cost)
        if cost <= budget:
            result.rows.append(
                RowResult(
                    row_id=row_id,
                    passed=True,
                    detail=f"${cost:.4f} of ${budget:.4f} budget ({how})",
                    raw_score=round(cost, 6),
                )
            )
        else:
            over = (cost / budget - 1) * 100 if budget else float("inf")
            result.rows.append(
                RowResult(
                    row_id=row_id,
                    passed=False,
                    detail=f"${cost:.4f} exceeds the ${budget:.4f} budget by {over:.0f}% ({how})",
                    raw_score=round(cost, 6),
                )
            )

    if costs:
        costs.sort()
        total = sum(costs)
        p95 = costs[min(len(costs) - 1, int(round(0.95 * (len(costs) - 1))))]
        result.notes += (
            f" Observed: total ${total:.4f}, mean ${total / len(costs):.4f}, "
            f"p95 ${p95:.4f} over {len(costs)} priced rows."
        )
    return result


def validate_row(row: dict, options: Optional[dict] = None) -> list[tuple]:
    messages: list[tuple] = []
    cost, how = measured_cost(row, options)
    if cost is None and resolve_budget(row, options) is not None:
        messages.append(
            (
                "warning",
                "unmeasurable_cost",
                f"a cost budget applies but the cost cannot be computed: {how}",
                "cost_usd",
                "record cost_usd, or record usage and set budgets.price in .assevra.yml",
            )
        )
    for key in ("cost_usd", "cost_budget_usd"):
        if key in row and not isinstance(row[key], (int, float)):
            messages.append(("error", "bad_type", f"{key} must be a number", key, None))
    return messages
