"""
Judge calibration: is the judge's verdict trustworthy?

An LLM-judge score means nothing until you have shown the judge agrees with
humans. METHODOLOGY.md §4 describes this step; this module automates it. Given a
labeled hold-out — rows carrying a human pass/fail verdict — Assevra runs the
judge (or panel) over the same rows and reports how well the two agree:

- **accuracy** — raw agreement rate.
- **Cohen's κ** — agreement corrected for chance (the honest number; two judges
  can agree 90% of the time yet have κ near 0 if the classes are lopsided).
- **sensitivity / specificity** — agreement on the rows a human *passed* vs the
  rows a human *failed*, so a judge that trivially passes everything is exposed.

The rule of thumb (METHODOLOGY.md §4): trust a judge dimension only once κ ≥ 0.85
on a representative hold-out. Below that, the score is theater.

All functions here are pure (labels in, metrics out) — the judge calls happen in
the CLI, so the arithmetic is deterministic and testable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


def to_bool(value) -> Optional[bool]:
    """Coerce a human label to a bool. Accepts real bools, 0/1, and common
    strings (pass/fail, true/false, yes/no). Returns None if unrecognized."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "pass", "passed", "yes", "y", "1", "grounded", "safe"):
            return True
        if v in ("false", "fail", "failed", "no", "n", "0", "unsafe"):
            return False
    return None


def confusion(judge_labels: list, human_labels: list) -> dict:
    """Counts with the human 'pass' verdict as the positive class."""
    tp = fp = tn = fn = 0
    for j, hm in zip(judge_labels, human_labels):
        if hm and j:
            tp += 1
        elif hm and not j:
            fn += 1
        elif (not hm) and j:
            fp += 1
        else:
            tn += 1
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn}


def cohens_kappa(judge_labels: list, human_labels: list) -> Optional[float]:
    n = len(judge_labels)
    if n == 0:
        return None
    po = sum(1 for j, hm in zip(judge_labels, human_labels) if j == hm) / n
    pj = sum(1 for j in judge_labels if j) / n
    ph = sum(1 for hm in human_labels if hm) / n
    pe = pj * ph + (1 - pj) * (1 - ph)
    if pe >= 1.0:  # both raters put everything in one class -> chance agreement is total
        return 1.0 if po >= 1.0 else 0.0
    return (po - pe) / (1 - pe)


@dataclass
class Calibration:
    n: int
    accuracy: float
    kappa: Optional[float]
    sensitivity: Optional[float]
    specificity: Optional[float]
    tp: int
    fp: int
    tn: int
    fn: int

    @property
    def trustworthy(self) -> bool:
        return self.kappa is not None and self.kappa >= 0.85

    def to_dict(self) -> dict:
        return {
            "n": self.n,
            "accuracy": round(self.accuracy, 4),
            "cohens_kappa": None if self.kappa is None else round(self.kappa, 4),
            "sensitivity": None if self.sensitivity is None else round(self.sensitivity, 4),
            "specificity": None if self.specificity is None else round(self.specificity, 4),
            "confusion": {"tp": self.tp, "fp": self.fp, "tn": self.tn, "fn": self.fn},
            "trustworthy": self.trustworthy,
        }


def compute(judge_labels: list, human_labels: list) -> Calibration:
    n = len(judge_labels)
    c = confusion(judge_labels, human_labels)
    accuracy = (c["tp"] + c["tn"]) / n if n else 0.0
    pos = c["tp"] + c["fn"]
    neg = c["tn"] + c["fp"]
    sensitivity = c["tp"] / pos if pos else None
    specificity = c["tn"] / neg if neg else None
    return Calibration(
        n=n,
        accuracy=accuracy,
        kappa=cohens_kappa(judge_labels, human_labels),
        sensitivity=sensitivity,
        specificity=specificity,
        **c,
    )


def _fmt(x) -> str:
    return "—" if x is None else f"{x:.3f}"


def render(overall: Calibration, per_dimension: dict) -> str:
    lines = ["# Judge calibration", ""]
    lines.append(
        f"Judge-vs-human agreement on a labeled hold-out (N={overall.n}). "
        "Trust a judge dimension only once Cohen's κ ≥ 0.85 (METHODOLOGY.md §4)."
    )
    lines.append("")
    lines.append("| Scope | N | Accuracy | Cohen's κ | Sensitivity | Specificity |")
    lines.append("|---|---|---|---|---|---|")

    def row(name, c: Calibration) -> str:
        return (
            f"| {name} | {c.n} | {_fmt(c.accuracy)} | {_fmt(c.kappa)} | "
            f"{_fmt(c.sensitivity)} | {_fmt(c.specificity)} |"
        )

    lines.append(row("overall", overall))
    for name in sorted(per_dimension):
        lines.append(row(name, per_dimension[name]))
    lines.append("")
    lines.append(
        f"Confusion (overall): TP={overall.tp} FP={overall.fp} "
        f"TN={overall.tn} FN={overall.fn}."
    )
    verdict = (
        "meets the κ ≥ 0.85 bar — the judge is trustworthy on this hold-out."
        if overall.trustworthy
        else "is BELOW the κ ≥ 0.85 bar — do not trust the judge score until this improves."
    )
    lines.append(f"\nOverall agreement {verdict}")
    return "\n".join(lines)
