"""
Reliability trend tracking: persist scorecards over time and compare runs.

A single scorecard answers "is my agent reliable right now?" The failure mode
teams actually report is quieter — a score that *drifts* ("the model provider
updated, grounding fell to 71%, no alert fired, we found out from a customer").
This module turns a one-shot scorecard into a tracked series: each run appends a
compact record to a history file, and the next run reports what changed — and,
crucially, whether the change is beyond the previous confidence interval (a real
move) or inside it (noise).

The comparison is deliberately conservative about calling a regression: a
dimension has "regressed" only if its new score falls **below the previous
95% interval**, or if it crossed its pass/fail threshold. Movement inside the
prior interval is reported as "stable" — the small-sample honesty that the rest
of Assevra insists on, applied to trends.

History is a JSONL file (one run per line); nothing here needs a database.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional


def record_from_scorecard(scorecard, label: str, timestamp: str) -> dict:
    """Build a compact, comparable record from a Scorecard."""
    dims = []
    for d in scorecard.dimensions:
        lo, hi = d.ci
        dims.append(
            {
                "name": d.name,
                "skipped": d.skipped,
                "score": round(d.score, 4),
                "ci_lo": round(lo, 4),
                "ci_hi": round(hi, 4),
                "n": d.n,
                "passes": d.passes,
                "threshold": d.threshold,
                "passed": d.passed,
            }
        )
    return {
        "timestamp": timestamp,
        "label": label,
        "dataset": scorecard.dataset,
        "judge_model": scorecard.judge_model,
        "overall_pass": scorecard.overall_pass,
        "dimensions": dims,
    }


def load_history(history_path: str) -> list[dict]:
    if not os.path.isfile(history_path):
        return []
    records: list[dict] = []
    with open(history_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def append_record(history_path: str, record: dict) -> None:
    parent = os.path.dirname(history_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(history_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def find_baseline(history: list[dict], label: Optional[str]) -> Optional[dict]:
    """The record to compare against: the most recent one matching `label`, or
    the most recent record overall when no label is given."""
    if not history:
        return None
    if label is None:
        return history[-1]
    for rec in reversed(history):
        if rec.get("label") == label:
            return rec
    return None


@dataclass
class DimensionDelta:
    name: str
    prev_score: Optional[float]
    curr_score: Optional[float]
    delta: Optional[float]
    status: str  # regressed | improved | stable | now failing | now passing | new | skipped

    @property
    def is_regression(self) -> bool:
        return self.status in ("regressed", "now failing")


def _dim_by_name(record: dict, name: str) -> Optional[dict]:
    for d in record.get("dimensions", []):
        if d["name"] == name:
            return d
    return None


def compare(prev: dict, curr: dict) -> list[DimensionDelta]:
    """Per-dimension change from `prev` to `curr`, judged against the previous
    confidence interval and the pass/fail threshold."""
    deltas: list[DimensionDelta] = []
    for cd in curr.get("dimensions", []):
        name = cd["name"]
        pd = _dim_by_name(prev, name)
        if pd is None:
            deltas.append(DimensionDelta(name, None, cd["score"], None, "new"))
            continue
        if cd["skipped"] or pd["skipped"]:
            deltas.append(
                DimensionDelta(name, pd.get("score"), cd.get("score"), None, "skipped")
            )
            continue

        delta = round(cd["score"] - pd["score"], 4)
        # Threshold crossings dominate — they change the gate outcome.
        if pd["passed"] and not cd["passed"]:
            status = "now failing"
        elif not pd["passed"] and cd["passed"]:
            status = "now passing"
        # Otherwise, is the move beyond the previous interval (real) or inside it?
        elif cd["score"] < pd["ci_lo"]:
            status = "regressed"
        elif cd["score"] > pd["ci_hi"]:
            status = "improved"
        else:
            status = "stable"
        deltas.append(DimensionDelta(name, pd["score"], cd["score"], delta, status))
    return deltas


def is_overall_regression(prev: dict, curr: dict, deltas: list[DimensionDelta]) -> bool:
    if prev.get("overall_pass") and not curr.get("overall_pass"):
        return True
    return any(d.is_regression for d in deltas)


def render_comparison(prev: dict, curr: dict, deltas: list[DimensionDelta]) -> str:
    """A console-friendly 'what changed' section."""
    ref = prev.get("label") or prev.get("timestamp") or "previous run"
    lines: list[str] = []
    lines.append(f"## Change since {ref}")
    lines.append("")
    lines.append("| Dimension | Prev | Now | Delta | Status |")
    lines.append("|---|---|---|---|---|")
    for d in deltas:
        prev_s = "—" if d.prev_score is None else f"{d.prev_score:.3f}"
        curr_s = "—" if d.curr_score is None else f"{d.curr_score:.3f}"
        if d.delta is None:
            delta_s = "—"
        else:
            delta_s = f"{d.delta:+.3f}"
        lines.append(f"| {d.name} | {prev_s} | {curr_s} | {delta_s} | {d.status} |")
    lines.append("")
    if is_overall_regression(prev, curr, deltas):
        regressed = [d.name for d in deltas if d.is_regression]
        detail = f" ({', '.join(regressed)})" if regressed else ""
        lines.append(f"**Regression detected{detail}.**")
    else:
        lines.append("_No regression: every dimension is stable, improved, or newly passing._")
    lines.append(
        "\n_A move is flagged only when it falls outside the previous 95% interval "
        "or crosses a threshold; smaller moves are reported as stable._"
    )
    return "\n".join(lines)


def render_history(history: list[dict], limit: Optional[int] = None) -> str:
    """A compact trend table of past runs (most recent last)."""
    if not history:
        return "No runs recorded yet."
    rows = history[-limit:] if limit else history
    # Union of dimension names across shown runs, in first-seen order.
    names: list[str] = []
    for rec in rows:
        for d in rec.get("dimensions", []):
            if d["name"] not in names:
                names.append(d["name"])

    header = ["When", "Label", "Overall"] + names
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    for rec in rows:
        when = (rec.get("timestamp") or "")[:19]
        label = rec.get("label") or "—"
        overall = "PASS" if rec.get("overall_pass") else "FAIL"
        cells = [when, label, overall]
        for name in names:
            d = _dim_by_name(rec, name)
            if d is None:
                cells.append("—")
            elif d["skipped"]:
                cells.append("skip")
            else:
                cells.append(f"{d['score']:.3f}")
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)
