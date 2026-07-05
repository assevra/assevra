"""
The Assevra Reliability Scorecard: the aggregation and reporting layer.

A scorer produces a `DimensionResult` (one per reliability dimension). The
`Scorecard` collects those, decides overall pass/fail against per-dimension
thresholds, and renders to Markdown and JSON. Every dimension carries its
sample size and a Wilson confidence interval so a reader never over-reads a
small-sample move.

See METHODOLOGY.md for the definitions and thresholds these objects encode.
"""
from __future__ import annotations

import html
import json
import math
from dataclasses import dataclass, field
from typing import Optional

from . import reliability as _reliability

# Bump this when a change to a scorer or rubric would change a reported number.
# Report scores as "measured with Assevra v0.1".
ASSEVRA_VERSION = "0.2"

# Citation provenance. Stamped into every report so attribution travels with the
# artifact: anyone who shares a scorecard carries the DOI with it. Concept DOI
# (always resolves to the latest version).
ASSEVRA_DOI = "10.5281/zenodo.21200852"
ASSEVRA_REPO = "https://github.com/assevra/assevra"


def wilson_ci(passes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a pass rate.

    Reported next to every dimension mean. On small datasets the interval is
    wide on purpose -- that width is the honest statement of what the number
    can and cannot support.
    """
    if n == 0:
        return (0.0, 0.0)
    p = passes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, center - half), min(1.0, center + half))


@dataclass
class RowResult:
    """The outcome of scoring one dataset row within a dimension."""

    row_id: str
    passed: bool
    detail: str = ""
    # Raw judge score (e.g. 1-5) when a dimension is scored by an LLM judge.
    raw_score: Optional[float] = None

    def to_dict(self) -> dict:
        d = {"id": self.row_id, "passed": self.passed, "detail": self.detail}
        if self.raw_score is not None:
            d["raw_score"] = self.raw_score
        return d


@dataclass
class DimensionResult:
    """The scored result for one reliability dimension."""

    name: str
    # "deterministic" or "llm-judge" -- how the dimension is scored.
    mode: str
    # Pass rate at or above which the dimension passes. See METHODOLOGY.md.
    threshold: float
    rows: list[RowResult] = field(default_factory=list)
    # A dimension is skipped (not failed) when its engine is unavailable --
    # e.g. the LLM judge has no API key. Skipped dimensions do not gate.
    skipped: bool = False
    skip_reason: str = ""
    # Free-text notes: judge model + pinned-rubric hash, detector version, etc.
    notes: str = ""

    @property
    def n(self) -> int:
        return len(self.rows)

    @property
    def passes(self) -> int:
        return sum(1 for r in self.rows if r.passed)

    @property
    def score(self) -> float:
        return self.passes / self.n if self.n else 0.0

    @property
    def ci(self) -> tuple[float, float]:
        return wilson_ci(self.passes, self.n)

    @property
    def passed(self) -> Optional[bool]:
        """True/False against the threshold, or None if skipped."""
        if self.skipped:
            return None
        return self.score >= self.threshold

    def to_dict(self) -> dict:
        lo, hi = self.ci
        return {
            "name": self.name,
            "mode": self.mode,
            "threshold": self.threshold,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "notes": self.notes,
            "sample_size": self.n,
            "passes": self.passes,
            "score": round(self.score, 4),
            "ci_95": [round(lo, 4), round(hi, 4)],
            "passed": self.passed,
            "rows": [r.to_dict() for r in self.rows],
        }


@dataclass
class Scorecard:
    """A full Assevra Reliability Scorecard for one agent-under-test."""

    dimensions: list[DimensionResult]
    version: str = ASSEVRA_VERSION
    dataset: str = ""
    judge_model: str = ""
    # Per-dimension pass^k / consistency over repeated-trial cases. Empty unless
    # the dataset groups trials with a shared case_id.
    reliability: list = field(default_factory=list)

    def scored_dimensions(self) -> list[DimensionResult]:
        return [d for d in self.dimensions if not d.skipped]

    @property
    def overall_pass(self) -> bool:
        """Passes only if every scored (non-skipped) dimension passes.

        Reliability is a conjunction: a strong grounding score does not buy back
        a PII leak. A run with every relevant dimension skipped is not a pass.
        """
        scored = self.scored_dimensions()
        if not scored:
            return False
        return all(d.passed for d in scored)

    def to_dict(self) -> dict:
        d = {
            "assevra_version": self.version,
            "dataset": self.dataset,
            "judge_model": self.judge_model,
            "overall_pass": self.overall_pass,
            "dimensions": [dim.to_dict() for dim in self.dimensions],
        }
        # Only present when the dataset had repeated-trial cases, so existing
        # single-trial scorecards keep their exact shape.
        if self.reliability:
            d["reliability"] = [r.to_dict() for r in self.reliability]
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    # Status labels are shared verbatim by the Markdown and HTML renderers so the
    # two reports read identically. Glyphs are text (not emoji) to stay plain.
    _DIM_STATUS = {True: "PASS", False: "FAIL", None: "SKIPPED"}

    @staticmethod
    def _display_name(name: str) -> str:
        """Human-readable dimension name for headings (CSS title-cases it)."""
        special = {"pii": "PII"}
        return special.get(name, name.replace("_", " "))

    # The scope note printed at the foot of every report, in both formats.
    _SCOPE_NOTE = (
        "Reliability is reported as a per-dimension pass rate against a fixed "
        "threshold, with a 95% Wilson interval on a small labeled dataset. This "
        "scorecard does not certify safety; it measures four specific properties "
        "on the rows provided. See METHODOLOGY.md for scope and limitations."
    )

    def render_markdown(self) -> str:
        lines: list[str] = []
        lines.append("# Assevra Reliability Scorecard")
        lines.append("")
        verdict = "PASS" if self.overall_pass else "FAIL"
        lines.append(f"**Overall: {verdict}**  ")
        lines.append(f"Measured with Assevra v{self.version}.")
        lines.append("")
        lines.append(f"- Dataset: `{self.dataset or 'n/a'}`")
        lines.append(f"- Judge model: `{self.judge_model or 'none (judge dimensions skipped)'}`")
        lines.append("")
        lines.append("| Dimension | Mode | Score | 95% CI | n | Threshold | Result |")
        lines.append("|---|---|---|---|---|---|---|")
        for d in self.dimensions:
            if d.skipped:
                lines.append(
                    f"| {d.name} | {d.mode} | — | — | {d.n} | {d.threshold:.2f} | "
                    f"SKIPPED |"
                )
                continue
            lo, hi = d.ci
            result = self._DIM_STATUS[d.passed]
            lines.append(
                f"| {d.name} | {d.mode} | {d.score:.3f} | "
                f"{lo:.3f}–{hi:.3f} | {d.n} | {d.threshold:.2f} | {result} |"
            )
        lines.append("")

        for d in self.dimensions:
            lines.append(f"## {d.name}")
            lines.append("")
            if d.skipped:
                lines.append(f"_Skipped: {d.skip_reason}_")
                lines.append("")
                continue
            if d.notes:
                lines.append(f"_{d.notes}_")
                lines.append("")
            for r in d.rows:
                flag = "PASS" if r.passed else "FAIL"
                extra = f" (judge={r.raw_score})" if r.raw_score is not None else ""
                lines.append(f"- `[{flag}]` `{r.row_id}`{extra} — {r.detail}")
            lines.append("")

        rel_md = _reliability.render_markdown_section(self.reliability)
        if rel_md:
            lines.append(rel_md)

        lines.append("---")
        lines.append("")
        lines.append(self._SCOPE_NOTE)
        lines.append("")
        lines.append(
            f"_Generated by [Assevra]({ASSEVRA_REPO}) v{self.version}. "
            f"If you report or share this scorecard, cite: "
            f"https://doi.org/{ASSEVRA_DOI}_"
        )
        lines.append("")
        return "\n".join(lines)

    def render_html(self) -> str:
        """Render a self-contained, styled HTML scorecard.

        All CSS is inlined and there are no external assets, so the file opens
        in any browser and can be shared or attached as-is. The structure and
        wording mirror `render_markdown()`.
        """
        esc = html.escape
        overall = "pass" if self.overall_pass else "fail"
        overall_label = "PASS" if self.overall_pass else "FAIL"

        summary_rows = []
        for d in self.dimensions:
            dname = esc(self._display_name(d.name))
            if d.skipped:
                cells = (
                    f"<td>{dname}</td><td>{esc(d.mode)}</td>"
                    f"<td class='num'>&mdash;</td><td class='num'>&mdash;</td>"
                    f"<td class='num'>{d.n}</td><td class='num'>{d.threshold:.2f}</td>"
                    f"<td><span class='chip chip-skip'>SKIPPED</span></td>"
                )
            else:
                lo, hi = d.ci
                cls = "pass" if d.passed else "fail"
                label = self._DIM_STATUS[d.passed]
                cells = (
                    f"<td>{dname}</td><td>{esc(d.mode)}</td>"
                    f"<td class='num'>{d.score:.3f}</td>"
                    f"<td class='num'>{lo:.3f}&ndash;{hi:.3f}</td>"
                    f"<td class='num'>{d.n}</td><td class='num'>{d.threshold:.2f}</td>"
                    f"<td><span class='chip chip-{cls}'>{label}</span></td>"
                )
            summary_rows.append(f"<tr>{cells}</tr>")

        sections = []
        for d in self.dimensions:
            head = (
                f"<div class='dim'><div class='dim-head'>"
                f"<h2>{esc(self._display_name(d.name))}</h2>"
            )
            if d.skipped:
                head += "<span class='chip chip-skip'>SKIPPED</span></div>"
                body = f"<p class='note'>Skipped: {esc(d.skip_reason)}</p></div>"
                sections.append(head + body)
                continue
            cls = "pass" if d.passed else "fail"
            head += f"<span class='chip chip-{cls}'>{self._DIM_STATUS[d.passed]}</span></div>"
            note = f"<p class='note'>{esc(d.notes)}</p>" if d.notes else ""
            items = []
            for r in d.rows:
                dot = "pass" if r.passed else "fail"
                extra = f" <span class='raw'>judge={esc(str(r.raw_score))}</span>" if r.raw_score is not None else ""
                items.append(
                    f"<li><span class='dot dot-{dot}'></span>"
                    f"<code>{esc(r.row_id)}</code>{extra} "
                    f"<span class='detail'>{esc(r.detail)}</span></li>"
                )
            body = f"{note}<ul class='rows'>{''.join(items)}</ul></div>"
            sections.append(head + body)

        dataset = esc(self.dataset or "n/a")
        judge = esc(self.judge_model or "none (judge dimensions skipped)")

        return _HTML_TEMPLATE.format(
            version=esc(self.version),
            overall=overall,
            overall_label=overall_label,
            dataset=dataset,
            judge=judge,
            summary_rows="\n".join(summary_rows),
            sections="\n".join(sections),
            reliability=_reliability.render_html_section(self.reliability, esc),
            scope_note=esc(self._SCOPE_NOTE),
            doi=esc(ASSEVRA_DOI),
        )


# Self-contained report template. No external fonts, scripts, or stylesheets:
# a strict-CSP-safe, offline, shareable single file.
_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Assevra Reliability Scorecard</title>
<style>
  :root {{
    --ink:#1f2328; --muted:#6a7178; --border:#e2e6ea; --bg:#f6f8fa; --card:#fff;
    --accent:#3a3f9e;
    --pass:#1a7f37; --pass-bg:#e6f6ec; --fail:#cf222e; --fail-bg:#fdecea;
    --skip:#6a7178; --skip-bg:#eef1f4;
  }}
  * {{ box-sizing:border-box; }}
  body {{
    margin:0; background:var(--bg); color:var(--ink);
    font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    -webkit-font-smoothing:antialiased;
  }}
  .wrap {{ max-width:820px; margin:0 auto; padding:40px 20px 64px; }}
  header {{ border-bottom:1px solid var(--border); padding-bottom:20px; margin-bottom:24px; }}
  .brand {{ font-weight:700; letter-spacing:.14em; text-transform:uppercase;
    font-size:12px; color:var(--accent); }}
  h1 {{ font-size:26px; margin:6px 0 4px; }}
  .meta {{ color:var(--muted); font-size:13px; }}
  .meta code {{ background:var(--skip-bg); padding:1px 6px; border-radius:5px; font-size:12px; }}
  .verdict {{ display:inline-flex; align-items:center; gap:10px; margin:8px 0 28px;
    padding:12px 22px; border-radius:10px; font-weight:700; font-size:20px; }}
  .verdict small {{ font-weight:500; font-size:13px; opacity:.8; }}
  .verdict.pass {{ background:var(--pass-bg); color:var(--pass); }}
  .verdict.fail {{ background:var(--fail-bg); color:var(--fail); }}
  table {{ width:100%; border-collapse:collapse; background:var(--card);
    border:1px solid var(--border); border-radius:10px; overflow:hidden; font-size:14px; }}
  th, td {{ text-align:left; padding:10px 14px; border-bottom:1px solid var(--border); }}
  th {{ background:#fbfcfd; font-size:12px; letter-spacing:.03em; text-transform:uppercase;
    color:var(--muted); font-weight:600; }}
  tr:last-child td {{ border-bottom:none; }}
  td.num, th.num {{ text-align:right; font-variant-numeric:tabular-nums;
    font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }}
  .chip {{ display:inline-block; padding:2px 10px; border-radius:20px; font-size:12px;
    font-weight:600; }}
  .chip-pass {{ background:var(--pass-bg); color:var(--pass); }}
  .chip-fail {{ background:var(--fail-bg); color:var(--fail); }}
  .chip-skip {{ background:var(--skip-bg); color:var(--skip); }}
  .dim {{ background:var(--card); border:1px solid var(--border); border-radius:10px;
    padding:16px 18px; margin-top:16px; }}
  .dim-head {{ display:flex; align-items:center; justify-content:space-between; }}
  .dim h2 {{ font-size:16px; margin:0; text-transform:capitalize; }}
  .note {{ color:var(--muted); font-size:13px; margin:8px 0 12px; }}
  ul.rows {{ list-style:none; margin:0; padding:0; }}
  ul.rows li {{ padding:6px 0; border-top:1px solid var(--border); font-size:14px;
    display:flex; align-items:baseline; gap:8px; flex-wrap:wrap; }}
  ul.rows li:first-child {{ border-top:none; }}
  .dot {{ width:9px; height:9px; border-radius:50%; flex:none; position:relative; top:1px; }}
  .dot-pass {{ background:var(--pass); }}
  .dot-fail {{ background:var(--fail); }}
  code {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:13px;
    background:var(--skip-bg); padding:1px 6px; border-radius:5px; }}
  .raw {{ color:var(--muted); font-size:12px; }}
  .detail {{ color:var(--ink); }}
  h3.section {{ font-size:13px; text-transform:uppercase; letter-spacing:.05em;
    color:var(--muted); margin:32px 0 4px; }}
  footer {{ margin-top:32px; padding-top:18px; border-top:1px solid var(--border);
    color:var(--muted); font-size:12.5px; }}
  footer a {{ color:var(--accent); text-decoration:none; }}
</style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="brand">Assevra</div>
      <h1>Reliability Scorecard</h1>
      <div class="meta">Measured with Assevra v{version} &middot;
        dataset <code>{dataset}</code> &middot; judge <code>{judge}</code></div>
    </header>

    <div class="verdict {overall}">Overall: {overall_label}</div>

    <h3 class="section">Summary</h3>
    <table>
      <thead><tr>
        <th>Dimension</th><th>Mode</th><th class="num">Score</th>
        <th class="num">95% CI</th><th class="num">n</th>
        <th class="num">Threshold</th><th>Result</th>
      </tr></thead>
      <tbody>
{summary_rows}
      </tbody>
    </table>

    <h3 class="section">Dimensions</h3>
{sections}

    {reliability}

    <footer>{scope_note}<br>
      Generated by <a href="https://github.com/assevra/assevra">Assevra</a>
      v{version} &middot; an open-source reliability toolkit for LLM agents.<br>
      If you report or share this scorecard, cite:
      <a href="https://doi.org/{doi}">doi.org/{doi}</a></footer>
  </div>
</body>
</html>
"""
