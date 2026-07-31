"""
``assevra scan`` — a scorecard in sixty seconds, with nothing labeled.

The honest bottleneck in adopting an evaluation tool was never the CLI. Installing
Assevra and running `init` takes about two minutes; writing the answer key takes
an afternoon. Every command added to the front of that is optimising the two
minutes.

So `scan` attacks the afternoon instead, by noticing something that had been true
all along: **most dimensions never needed a human.**

* ``pii`` is self-labeling — the detector defines the failure.
* ``grounding``'s answer key is the retrieved context, which the trace captured.
* ``cost`` and ``latency`` are governed by a budget, which is one line of project
  policy rather than a per-row judgment.
* ``tool_call``'s contract is the agent's *own tool specification* — already
  machine-readable, because the model needed it to call anything at all.

That is five of nine dimensions with no labeling whatsoever. `scan` runs exactly
those, on raw traces, and produces a real scorecard:

    assevra scan --from traces.jsonl --tools tools.json

What it will not do is guess. ``safety``, ``task_completion`` and
``action_correctness`` encode intent — whether a request *should* have been
refused, which facts a correct answer owes, which action was right — and no
amount of trace inspection recovers intent. Those are reported as **not scored,
and why**, with the command that starts labeling them. A tool that quietly
invented those labels would produce a number that looks like the real thing and
means nothing, which is the exact failure this project exists to prevent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import api, bootstrap as bootstrap_mod, registry, toolspec
from .scorecard import Scorecard


@dataclass
class Coverage:
    """Why each dimension was, or was not, scored in a zero-label pass."""

    scored: dict = field(default_factory=dict)      # dimension -> row count
    needs_labels: list = field(default_factory=list)  # dimension names
    unavailable: dict = field(default_factory=dict)   # dimension -> reason

    @property
    def any_scored(self) -> bool:
        return bool(self.scored)


@dataclass
class ScanResult:
    scorecard: Optional[Scorecard]
    coverage: Coverage
    interactions: int
    source: str
    trace_format: str
    tool_spec: Optional[str] = None
    tool_contract: dict = field(default_factory=dict)


def _reason_unavailable(dimension: str, interactions: list, options: dict) -> str:
    """Say specifically why a zero-label dimension produced no rows."""
    budgets = options.get("budgets", {}) or {}
    if dimension == "cost":
        if budgets.get("cost_usd") is None:
            return "no budgets.cost_usd in config — set one and every priced trace becomes scorable"
        priced = any(r.get("usage") or r.get("cost_usd") is not None for r in interactions)
        if not priced:
            return "no trace recorded usage or cost_usd"
        return "traces record usage but budgets.price is not configured, so cost cannot be computed"
    if dimension == "latency":
        if budgets.get("latency_ms") is None:
            return "no budgets.latency_ms in config — set one and every timed trace becomes scorable"
        return "no trace recorded a duration"
    if dimension == "tool_call":
        if not options.get("tool_contract"):
            return "no tool spec given — pass --tools <openai|anthropic|mcp spec>.json"
        return "no trace recorded any tool calls"
    if dimension == "grounding":
        return "no trace carried both a context and an output"
    if dimension == "pii":
        return "no trace carried an agent output"
    return "no scorable rows"


def scan(
    source: str,
    fmt: str = "auto",
    config=None,
    tools: Optional[str] = None,
    limit: Optional[int] = None,
    judge=None,
    judge_provider: Optional[str] = None,
    judge_model: Optional[str] = None,
    root: str = ".",
) -> ScanResult:
    """Score raw traces on every dimension that needs no human labeling."""
    cfg = api.resolve_config(config)
    options = dict(cfg.scorer_options())

    interactions, trace_format = bootstrap_mod.bootstrap(source, fmt=fmt, limit=limit)
    # `bootstrap` returns drafted *rows*; for scanning we want the captured
    # signals without its task_completion scaffolding.
    interactions = [
        {k: v for k, v in row.items() if k not in ("dimension", "must_include", "_review")}
        for row in interactions
    ]

    tool_spec_shape = None
    contract: dict = {}
    if tools:
        contract, tool_spec_shape = toolspec.load(tools)
    else:
        found = toolspec.discover(root, limit=1)
        if found:
            path, contract, tool_spec_shape = found[0]
            tool_spec_shape = f"{tool_spec_shape} ({path})"
    if contract:
        options["tool_contract"] = contract

    coverage = Coverage()
    rows: list[dict] = []
    for name in registry.dimensions():
        spec = registry.get_scorer(name)
        if not spec.zero_label:
            coverage.needs_labels.append(name)
            continue
        made = 0
        for index, interaction in enumerate(interactions, start=1):
            extra = spec.autolabel(interaction, options)
            if extra is None:
                continue
            rows.append(
                {
                    **interaction,
                    **extra,
                    "id": f"scan-{name}-{index:04d}",
                    "dimension": name,
                    "tags": list(interaction.get("tags", [])) + ["scan", "auto-labeled"],
                }
            )
            made += 1
        if made:
            coverage.scored[name] = made
        else:
            coverage.unavailable[name] = _reason_unavailable(name, interactions, options)

    scorecard = None
    if rows:
        scorecard = api.evaluate(
            records=rows,
            config=cfg,
            judge=judge,
            judge_provider=judge_provider,
            judge_model=judge_model,
            options=options,
            # These rows were built by the scorers themselves, so re-deriving
            # their labeled-ness would only restate what we just decided.
            validate=False,
        )
        scorecard.dataset = f"{source} (scan, auto-labeled)"

        # Reconcile the plan against what actually happened. Building rows for a
        # judged dimension is not the same as scoring it: with no judge, those
        # rows are skipped. Reporting them as "scored" would be the precise kind
        # of overstatement this tool exists to avoid.
        for dimension in scorecard.dimensions:
            if dimension.skipped and dimension.name in coverage.scored:
                del coverage.scored[dimension.name]
                coverage.unavailable[dimension.name] = dimension.skip_reason

    return ScanResult(
        scorecard=scorecard,
        coverage=coverage,
        interactions=len(interactions),
        source=source,
        trace_format=trace_format,
        tool_spec=tool_spec_shape,
        tool_contract=contract,
    )


def render(result: ScanResult) -> str:
    """The console report: what was scored, what was not, and what to do next."""
    lines: list[str] = []
    cov = result.coverage

    lines.append(
        f"[assevra] read {result.interactions} interaction(s) from {result.source} "
        f"(format: {result.trace_format})"
    )
    if result.tool_spec:
        lines.append(
            f"[assevra] tool spec: {result.tool_spec} — {toolspec.describe(result.tool_contract)}"
        )

    if cov.scored:
        lines.append("")
        lines.append("[assevra] scored with no labeling:")
        for name, count in cov.scored.items():
            note = registry.get_scorer(name).autolabel_note
            lines.append(f"[assevra]   {name:<18} {count:>4} rows  — {note}")

    if cov.unavailable:
        lines.append("")
        lines.append("[assevra] zero-label dimensions that produced nothing:")
        for name, reason in cov.unavailable.items():
            lines.append(f"[assevra]   {name:<18} {reason}")

    if cov.needs_labels:
        lines.append("")
        lines.append(
            "[assevra] NOT scored — these encode intent, which no trace contains:"
        )
        for name in cov.needs_labels:
            spec = registry.get_scorer(name)
            lines.append(f"[assevra]   {name:<18} {spec.label_hint}")
        lines.append("")
        lines.append("[assevra] two ways to cover them without hand-writing a dataset:")
        lines.append(
            "[assevra]   assevra probe --out probes.jsonl     "
            "# generated adversarial cases; the canary IS the label"
        )
        lines.append(
            "[assevra]   assevra suggest --dataset d.jsonl    "
            "# a model proposes labels; you confirm them"
        )

    lines.append("")
    if not cov.any_scored:
        lines.append(
            "[assevra] nothing could be scored without labels. Start with "
            "`assevra probe --out probes.jsonl`, or `assevra init --from "
            f"{result.source}` to draft a dataset."
        )
    else:
        scored = len(cov.scored)
        total = scored + len(cov.needs_labels) + len(cov.unavailable)
        lines.append(
            f"[assevra] {scored} of {total} dimensions scored from raw traces, with "
            "nothing labeled. This is a triage pass, not a release gate — the "
            "dimensions above still need answer keys before the scorecard "
            "characterizes your agent."
        )
    return "\n".join(lines)
