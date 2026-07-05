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
ASSEVRA_VERSION = "0.3"

# Citation provenance. Stamped into every report so attribution travels with the
# artifact: anyone who shares a scorecard carries the DOI with it. Concept DOI
# (always resolves to the latest version).
ASSEVRA_DOI = "10.5281/zenodo.21200852"

# Per-dimension row cap in the HTML report: on large datasets, listing every row
# would produce an unwieldy file, so we show failing rows first (the informative
# ones) up to this many and summarize the rest.
_HTML_ROW_CAP = 24
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

        scored = [d for d in self.dimensions if not d.skipped]
        n_scored = len(scored)
        n_passed = sum(1 for d in scored if d.passed)
        n_skipped = sum(1 for d in self.dimensions if d.skipped)
        total_rows = sum(d.n for d in scored)

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
            # Failing rows first, then passing, capped -- a reviewer cares about
            # failures, and a huge dataset should not produce a huge file.
            ordered = [r for r in d.rows if not r.passed] + [r for r in d.rows if r.passed]
            shown = ordered[:_HTML_ROW_CAP]
            hidden = len(d.rows) - len(shown)
            items = []
            for r in shown:
                dot = "pass" if r.passed else "fail"
                extra = f" <span class='raw'>judge={esc(str(r.raw_score))}</span>" if r.raw_score is not None else ""
                items.append(
                    f"<li><span class='dot dot-{dot}'></span>"
                    f"<code>{esc(r.row_id)}</code>{extra} "
                    f"<span class='detail'>{esc(r.detail)}</span></li>"
                )
            if hidden > 0:
                items.append(
                    f"<li class='more'>&#8230; and {hidden} more rows not shown "
                    f"(failing rows are listed first)</li>"
                )
            cibar = self._ci_bar(d.score, d.ci[0], d.ci[1], d.threshold, d.passed)
            body = f"{cibar}{note}<ul class='rows'>{''.join(items)}</ul></div>"
            sections.append(head + body)

        dataset = esc(self.dataset or "n/a")
        judge = esc(self.judge_model or "none (judge dimensions skipped)")

        return _HTML_TEMPLATE.format(
            version=esc(self.version),
            overall=overall,
            overall_label=overall_label,
            dataset=dataset,
            judge=judge,
            n_passed=n_passed,
            n_scored=n_scored,
            total_rows=total_rows,
            n_skipped=n_skipped,
            summary_rows="\n".join(summary_rows),
            sections="\n".join(sections),
            reliability=_reliability.render_html_section(self.reliability, esc),
            scope_note=esc(self._SCOPE_NOTE),
            doi=esc(ASSEVRA_DOI),
        )

    @staticmethod
    def _ci_bar(score: float, lo: float, hi: float, threshold: float, passed: bool) -> str:
        """A small self-contained bar visualizing a score, its 95% interval, and
        the threshold on a 0..1 track — the visual form of "report the interval,
        not just the mean." All positions are inline styles; no assets."""
        def pct(x: float) -> float:
            return max(0.0, min(100.0, x * 100.0))

        s, l, h, t = pct(score), pct(lo), pct(hi), pct(threshold)
        band_w = max(0.8, h - l)
        cls = "pass" if passed else "fail"
        return (
            "<div class='ci'><div class='ci-track'>"
            f"<div class='ci-band ci-band-{cls}' style='left:{l:.1f}%;width:{band_w:.1f}%'></div>"
            f"<div class='ci-thr' style='left:{t:.1f}%' title='threshold'></div>"
            f"<div class='ci-mark ci-mark-{cls}' style='left:{s:.1f}%'></div>"
            "</div><div class='ci-cap'>"
            f"<span>score&nbsp;<b>{score:.3f}</b></span>"
            f"<span>95% CI {lo:.3f}&ndash;{hi:.3f}</span>"
            f"<span>threshold {threshold:.2f}</span>"
            "</div></div>"
        )


# Self-contained report template. No external fonts, scripts, or stylesheets:
# a strict-CSP-safe, offline, shareable single file.
_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Assevra Reliability Scorecard</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%233f3fb0'/%3E%3Cpath d='M9 16.5l4.5 4.5L23 11' stroke='white' stroke-width='3' fill='none' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E">
<style>
  :root {{
    --ink:#14161c; --ink-soft:#2b3140; --muted:#5a6472; --faint:#8a93a3;
    --border:#e6e9ef; --border-soft:#eef1f6; --bg:#f4f5fb; --card:#fff;
    --brand:#3f3fb0; --brand-2:#6d5ae6; --brand-wash:#eef0fb; --track:#eceff5;
    --pass:#1a7f37; --pass-bg:#e6f6ec; --pass-band:#bfe6cb;
    --fail:#cf222e; --fail-bg:#fdecea; --fail-band:#f3c6c2;
    --skip:#6a7178; --skip-bg:#eef1f4;
    --shadow:0 2px 4px rgba(20,22,28,.05), 0 24px 48px -24px rgba(43,47,120,.24);
  }}
  * {{ box-sizing:border-box; }}
  body {{
    margin:0; color:var(--ink);
    background:radial-gradient(720px 320px at 50% -80px, var(--brand-wash), transparent 70%), linear-gradient(180deg,#f6f7fc,#fbfbfe);
    font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    -webkit-font-smoothing:antialiased; padding:36px 16px 60px;
  }}
  .sheet {{ max-width:860px; margin:0 auto; background:var(--card); border:1px solid var(--border);
    border-radius:16px; box-shadow:var(--shadow); overflow:hidden; }}

  .head {{ padding:26px 30px 24px; color:#fff;
    background:linear-gradient(135deg,#3a3aa6,#6d5ae6); }}
  .head-top {{ display:flex; align-items:center; justify-content:space-between; gap:14px; }}
  .brand {{ display:flex; align-items:center; gap:11px; }}
  .brand .mark {{ width:30px; height:30px; border-radius:8px; flex:none;
    background:rgba(255,255,255,.16); padding:4px; }}
  .brand .name {{ font-weight:750; font-size:18px; letter-spacing:-.01em; line-height:1.1; }}
  .brand .name small {{ display:block; font-weight:500; font-size:12px; opacity:.82;
    letter-spacing:.02em; text-transform:none; }}
  .verdict-pill {{ display:inline-flex; align-items:center; gap:8px; background:#fff;
    padding:8px 16px; border-radius:22px; font-weight:750; font-size:14.5px;
    box-shadow:0 2px 8px rgba(0,0,0,.15); }}
  .verdict-pill .vdot {{ width:9px; height:9px; border-radius:50%; }}
  .verdict-pill.pass {{ color:var(--pass); }} .verdict-pill.pass .vdot {{ background:var(--pass); }}
  .verdict-pill.fail {{ color:var(--fail); }} .verdict-pill.fail .vdot {{ background:var(--fail); }}
  .head-meta {{ margin-top:16px; font-size:12.5px; opacity:.9; }}
  .head-meta code {{ background:rgba(255,255,255,.18); padding:1px 7px; border-radius:5px;
    font-size:12px; color:#fff; }}

  .body {{ padding:24px 30px 30px; }}

  .stats {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin:2px 0 26px; }}
  .stat {{ background:#fbfcff; border:1px solid var(--border-soft); border-radius:11px;
    padding:14px 16px; }}
  .stat .n {{ font-size:23px; font-weight:750; letter-spacing:-.02em; font-variant-numeric:tabular-nums; }}
  .stat.pass .n {{ color:var(--pass); }} .stat.fail .n {{ color:var(--fail); }}
  .stat .l {{ font-size:12px; color:var(--faint); margin-top:2px; }}

  h3.section {{ font-size:12px; text-transform:uppercase; letter-spacing:.06em;
    color:var(--brand); font-weight:700; margin:28px 0 10px; }}

  table {{ width:100%; border-collapse:collapse; background:var(--card);
    border:1px solid var(--border); border-radius:11px; overflow:hidden; font-size:13.5px; }}
  th, td {{ text-align:left; padding:10px 14px; border-bottom:1px solid var(--border-soft); }}
  th {{ background:#fbfcfd; font-size:11px; letter-spacing:.04em; text-transform:uppercase;
    color:var(--faint); font-weight:650; }}
  tr:last-child td {{ border-bottom:none; }}
  td.num, th.num {{ text-align:right; font-variant-numeric:tabular-nums;
    font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12.5px; }}
  .chip {{ display:inline-block; padding:2px 10px; border-radius:20px; font-size:11.5px;
    font-weight:650; }}
  .chip-pass {{ background:var(--pass-bg); color:var(--pass); }}
  .chip-fail {{ background:var(--fail-bg); color:var(--fail); }}
  .chip-skip {{ background:var(--skip-bg); color:var(--skip); }}

  .dim {{ background:var(--card); border:1px solid var(--border); border-radius:12px;
    padding:16px 18px; margin-top:14px; }}
  .dim-head {{ display:flex; align-items:center; justify-content:space-between; gap:10px; }}
  .dim h2 {{ font-size:15.5px; margin:0; text-transform:capitalize; letter-spacing:-.01em; }}

  .ci {{ margin:14px 0 4px; }}
  .ci-track {{ position:relative; height:8px; background:var(--track); border-radius:6px; }}
  .ci-band {{ position:absolute; top:0; height:8px; border-radius:6px; }}
  .ci-band-pass {{ background:var(--pass-band); }}
  .ci-band-fail {{ background:var(--fail-band); }}
  .ci-thr {{ position:absolute; top:-3px; width:2px; height:14px; background:var(--ink-soft);
    border-radius:2px; opacity:.55; }}
  .ci-mark {{ position:absolute; top:-2px; width:12px; height:12px; border-radius:50%;
    transform:translateX(-6px); border:2px solid #fff; box-shadow:0 1px 3px rgba(0,0,0,.28); }}
  .ci-mark-pass {{ background:var(--pass); }}
  .ci-mark-fail {{ background:var(--fail); }}
  .ci-cap {{ display:flex; justify-content:space-between; gap:8px; flex-wrap:wrap;
    font-size:11.5px; color:var(--muted); margin-top:7px; font-variant-numeric:tabular-nums; }}
  .ci-cap b {{ color:var(--ink); }}

  .note {{ color:var(--muted); font-size:13px; margin:10px 0 10px; }}
  ul.rows {{ list-style:none; margin:0; padding:0; }}
  ul.rows li {{ padding:6px 0; border-top:1px solid var(--border-soft); font-size:13.5px;
    display:flex; align-items:baseline; gap:8px; flex-wrap:wrap; }}
  ul.rows li:first-child {{ border-top:none; }}
  ul.rows li.more {{ color:var(--faint); font-style:italic; }}
  .dot {{ width:8px; height:8px; border-radius:50%; flex:none; position:relative; top:1px; }}
  .dot-pass {{ background:var(--pass); }}
  .dot-fail {{ background:var(--fail); }}
  code {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12.5px;
    background:var(--skip-bg); padding:1px 6px; border-radius:5px; }}
  .raw {{ color:var(--muted); font-size:12px; }}
  .detail {{ color:var(--ink-soft); }}

  .verify {{ margin-top:26px; background:var(--brand-wash); border:1px solid #dfe1f6;
    border-radius:11px; padding:14px 16px; font-size:13px; color:var(--ink-soft);
    display:flex; gap:11px; align-items:flex-start; }}
  .verify svg {{ width:18px; height:18px; color:var(--brand); flex:none; margin-top:1px; }}
  .verify code {{ background:#fff; border:1px solid #dfe1f6; }}

  footer {{ margin-top:24px; padding-top:18px; border-top:1px solid var(--border-soft);
    color:var(--faint); font-size:12.5px; }}
  footer a {{ color:var(--brand); text-decoration:none; }}

  @media(max-width:560px){{ .stats {{ grid-template-columns:1fr 1fr; }}
    .head, .body {{ padding-left:20px; padding-right:20px; }} }}
</style>
</head>
<body>
  <div class="sheet">
    <div class="head">
      <div class="head-top">
        <div class="brand">
          <svg class="mark" viewBox="0 0 32 32" aria-hidden="true"><path d="M9 16.5l4.5 4.5L23 11" stroke="#fff" stroke-width="3.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>
          <div class="name">Assevra<small>Reliability Scorecard</small></div>
        </div>
        <div class="verdict-pill {overall}"><span class="vdot"></span>{overall_label}</div>
      </div>
      <div class="head-meta">Measured with Assevra v{version} &middot;
        dataset <code>{dataset}</code> &middot; judge <code>{judge}</code></div>
    </div>

    <div class="body">
      <div class="stats">
        <div class="stat {overall}"><div class="n">{n_passed}/{n_scored}</div><div class="l">dimensions passed</div></div>
        <div class="stat"><div class="n">{total_rows}</div><div class="l">rows scored</div></div>
        <div class="stat"><div class="n">{n_skipped}</div><div class="l">skipped (not passed)</div></div>
      </div>

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

      <div class="verify">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M9 12l2 2 4-4"/></svg>
        <div>Sign this scorecard with <code>assevra sign</code> so a reviewer can verify with
        <code>assevra verify</code> that it was produced by you and not altered &mdash; a signed
        artifact is evidence, not just a report.</div>
      </div>

      <footer>{scope_note}<br>
        Generated by <a href="https://github.com/assevra/assevra">Assevra</a>
        v{version} &middot; an open reference implementation of the Assevra Reliability Scorecard.<br>
        If you report or share this scorecard, cite:
        <a href="https://doi.org/{doi}">doi.org/{doi}</a></footer>
    </div>
  </div>
</body>
</html>
"""
