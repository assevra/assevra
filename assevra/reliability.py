"""
pass^k and run-to-run consistency: reliability across *repeated* trials.

A pass rate answers "how often does the agent succeed?" The reliability question
a deployed system actually cares about is stricter: "does it succeed *every*
time?" Answering that needs more than one attempt per input. When a dataset
groups repeated trials of the same case with a shared ``case_id``, Assevra reports
two metrics over those groups:

- **consistency** — the share of repeated cases whose trials *all agree* (all pass
  or all fail). A flaky case (some pass, some fail) is the opposite of reliable,
  and this surfaces it directly.
- **pass^k** — the estimated probability that *k independent attempts all pass*.
  Following the standard unbiased combinatorial estimator (cf. pass@k): from a
  case with ``n`` trials of which ``c`` passed, the chance that a random choice of
  ``k`` trials are all successes is ``C(c, k) / C(n, k)``. This is the reliability
  analogue of pass@k — it rewards succeeding every time, not merely once.

Both metrics require at least one case with more than one trial; on a
single-trial dataset (the default) there is nothing to report and the section is
omitted entirely — existing scorecards are unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import comb
from typing import Optional


def pass_hat_k(passes: int, n: int, k: int) -> Optional[float]:
    """Unbiased estimate that k independent trials of a case all pass.

    Choosing k of the n trials, the chance all k are successes is
    ``C(passes, k) / C(n, k)``. Returns None when there are fewer than k trials
    (not enough attempts to assess "k in a row")."""
    if k < 1 or n < k:
        return None
    if passes < k:
        return 0.0
    return comb(passes, k) / comb(n, k)


@dataclass
class CaseReliability:
    dimension: str
    n_cases: int          # distinct logical cases (a single-trial row is one case)
    n_repeated: int       # cases with more than one trial
    total_trials: int
    consistency: float    # unanimity rate over repeated cases
    flaky_cases: list     # case_ids with mixed pass/fail across trials
    k: int
    passk: Optional[float]  # mean per-case pass^k over cases with n >= k
    passk_cases: int        # how many cases had enough trials to count

    def to_dict(self) -> dict:
        return {
            "dimension": self.dimension,
            "cases": self.n_cases,
            "repeated_cases": self.n_repeated,
            "trials": self.total_trials,
            "consistency": round(self.consistency, 4),
            "flaky_cases": self.flaky_cases,
            "k": self.k,
            "pass_hat_k": None if self.passk is None else round(self.passk, 4),
            "pass_hat_k_cases": self.passk_cases,
        }


def group_passed_by_case(row_results, id_to_case: dict) -> dict:
    """Group per-row pass/fail into per-case lists.

    `row_results` is any iterable of objects with `.row_id` and `.passed`;
    `id_to_case` maps a row id to its case id (defaulting to the row id itself,
    so an ungrouped row is its own single-trial case)."""
    groups: dict[str, list] = {}
    for r in row_results:
        case = id_to_case.get(r.row_id, r.row_id)
        groups.setdefault(case, []).append(bool(r.passed))
    return groups


def compute_dimension(
    dimension: str, passed_by_case: dict, k: int
) -> Optional[CaseReliability]:
    """Reliability for one dimension, or None if it has no repeated-trial case."""
    repeated = {c: v for c, v in passed_by_case.items() if len(v) > 1}
    if not repeated:
        return None

    unanimous = sum(1 for v in repeated.values() if all(v) or not any(v))
    consistency = unanimous / len(repeated)
    flaky = sorted(c for c, v in repeated.items() if any(v) and not all(v))

    ks = [pass_hat_k(sum(v), len(v), k) for v in passed_by_case.values()]
    ks = [x for x in ks if x is not None]
    passk = sum(ks) / len(ks) if ks else None

    return CaseReliability(
        dimension=dimension,
        n_cases=len(passed_by_case),
        n_repeated=len(repeated),
        total_trials=sum(len(v) for v in passed_by_case.values()),
        consistency=consistency,
        flaky_cases=flaky,
        k=k,
        passk=passk,
        passk_cases=len(ks),
    )


# --------------------------------------------------------------------------- #
# Rendering (shared by the Markdown and HTML scorecards)                       #
# --------------------------------------------------------------------------- #
_INTRO = (
    "Trials sharing a case_id are grouped. Consistency is the share of repeated "
    "cases whose trials all agree; pass^k is the estimated chance that k "
    "independent attempts all pass."
)


def render_markdown_section(reliability: list) -> str:
    if not reliability:
        return ""
    lines = ["## Reliability across repeated trials", "", f"_{_INTRO}_", ""]
    lines.append("| Dimension | Cases (repeated) | Trials | Consistency | pass^k |")
    lines.append("|---|---|---|---|---|")
    for r in reliability:
        pk = "—" if r.passk is None else f"{r.passk:.3f} (k={r.k})"
        lines.append(
            f"| {r.dimension} | {r.n_cases} ({r.n_repeated}) | {r.total_trials} | "
            f"{r.consistency:.3f} | {pk} |"
        )
    lines.append("")
    flaky = [(r.dimension, r.flaky_cases) for r in reliability if r.flaky_cases]
    if flaky:
        lines.append("Flaky cases (mixed outcomes across trials):")
        for dim, cases in flaky:
            lines.append(f"- {dim}: {', '.join(cases)}")
        lines.append("")
    return "\n".join(lines)


def render_html_section(reliability: list, esc) -> str:
    if not reliability:
        return ""
    rows = []
    for r in reliability:
        pk = "&mdash;" if r.passk is None else f"{r.passk:.3f} <span class='raw'>k={r.k}</span>"
        rows.append(
            "<tr>"
            f"<td>{esc(r.dimension)}</td>"
            f"<td class='num'>{r.n_cases}</td>"
            f"<td class='num'>{r.n_repeated}</td>"
            f"<td class='num'>{r.total_trials}</td>"
            f"<td class='num'>{r.consistency:.3f}</td>"
            f"<td class='num'>{pk}</td>"
            "</tr>"
        )
    flaky = [(r.dimension, r.flaky_cases) for r in reliability if r.flaky_cases]
    flaky_html = ""
    if flaky:
        items = "; ".join(
            f"{esc(dim)}: {esc(', '.join(cases))}" for dim, cases in flaky
        )
        flaky_html = f"<p class='note'>Flaky cases (mixed outcomes): {items}</p>"
    return (
        '<h3 class="section">Reliability across repeated trials</h3>'
        f"<p class='note'>{esc(_INTRO)}</p>"
        "<table><thead><tr>"
        "<th>Dimension</th><th class='num'>Cases</th><th class='num'>Repeated</th>"
        "<th class='num'>Trials</th><th class='num'>Consistency</th>"
        "<th class='num'>pass^k</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
        + flaky_html
    )
