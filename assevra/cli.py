"""
Assevra command-line interface.

    python -m assevra run --dataset datasets/golden.jsonl

Loads a JSONL dataset, routes each row to its dimension's scorer, aggregates the
results into an Assevra Reliability Scorecard, and writes `scorecard.md`,
`scorecard.json`, and a styled, self-contained `scorecard.html`. The
deterministic dimensions (PII, task-completion) run with no
API key; the LLM-judge dimensions (grounding, safety) run when ANTHROPIC_API_KEY
is set and are skipped -- not failed -- otherwise.

Exit code is 0 when the scorecard passes, 1 when it fails, so the command can
gate CI directly.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import bootstrap as bootstrap_mod
from .judge import DEFAULT_JUDGE_MODEL, get_judge
from .scorecard import ASSEVRA_DOI, Scorecard
from .scorers import grounding, pii, safety, task_completion

# Maps a dataset row's `dimension` to the scorer module that handles it.
SCORERS = {
    grounding.DIMENSION: grounding.score,
    safety.DIMENSION: safety.score,
    pii.DIMENSION: pii.score,
    task_completion.DIMENSION: task_completion.score,
}

# Deterministic dimensions do not need a judge.
JUDGE_DIMENSIONS = {grounding.DIMENSION, safety.DIMENSION}

# Report dimensions in a stable, meaningful order.
DIMENSION_ORDER = [
    grounding.DIMENSION,
    safety.DIMENSION,
    pii.DIMENSION,
    task_completion.DIMENSION,
]


def load_dataset(path: str) -> list[dict]:
    rows: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{lineno}: invalid JSON: {exc}") from exc
    return rows


def group_by_dimension(rows: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        dim = row.get("dimension")
        if dim not in SCORERS:
            raise SystemExit(
                f"row {row.get('id', '?')!r} has unknown dimension {dim!r}; "
                f"expected one of {sorted(SCORERS)}"
            )
        grouped.setdefault(dim, []).append(row)
    return grouped


def build_scorecard(dataset_path: str, judge_model: str) -> Scorecard:
    rows = load_dataset(dataset_path)
    grouped = group_by_dimension(rows)

    # Build the judge once and share it across the judge dimensions.
    judge = get_judge(judge_model)

    dimensions = []
    for dim in DIMENSION_ORDER:
        if dim not in grouped:
            continue
        scorer = SCORERS[dim]
        if dim in JUDGE_DIMENSIONS:
            dimensions.append(scorer(grouped[dim], judge))
        else:
            dimensions.append(scorer(grouped[dim], None))

    return Scorecard(
        dimensions=dimensions,
        dataset=dataset_path,
        judge_model=judge.model if judge is not None else "",
    )


def cmd_run(args: argparse.Namespace) -> int:
    if not Path(args.dataset).is_file():
        raise SystemExit(f"dataset not found: {args.dataset}")

    scorecard = build_scorecard(args.dataset, args.judge_model)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "scorecard.md"
    json_path = out_dir / "scorecard.json"
    html_path = out_dir / "scorecard.html"
    md_path.write_text(scorecard.render_markdown(), encoding="utf-8")
    json_path.write_text(scorecard.to_json(), encoding="utf-8")
    html_path.write_text(scorecard.render_html(), encoding="utf-8")

    # A short console summary; the full detail is in the written files.
    print(scorecard.render_markdown())
    print(f"[assevra] wrote {md_path}")
    print(f"[assevra] wrote {json_path}")
    print(f"[assevra] wrote {html_path}")
    print(f"[assevra] cite: https://doi.org/{ASSEVRA_DOI}  (see CITATION.cff)")

    if not args.gate:
        return 0
    return 0 if scorecard.overall_pass else 1


def cmd_bootstrap(args: argparse.Namespace) -> int:
    if not Path(args.source).is_file():
        raise SystemExit(f"source not found: {args.source}")

    try:
        rows, resolved = bootstrap_mod.bootstrap(
            args.source,
            fmt=args.format,
            dimension=args.dimension,
            limit=args.limit,
            id_prefix=args.id_prefix,
            input_field=args.input_field,
            output_field=args.output_field,
            context_field=args.context_field,
        )
    except bootstrap_mod.BootstrapError as exc:
        raise SystemExit(f"[assevra] bootstrap: {exc}")

    bootstrap_mod.write_dataset(rows, args.out)

    hint = bootstrap_mod._DIMENSION_TEMPLATE[args.dimension]["hint"]
    print(
        f"[assevra] drafted {len(rows)} rows from {args.source} "
        f"(format: {resolved}) -> {args.out}"
    )
    print(f"[assevra] every row is dimension={args.dimension!r}, tagged needs-review.")
    print(f"[assevra] next: label the answer key on each row. {hint}")
    print(
        "[assevra] rows for other dimensions? re-tag their `dimension` field and "
        "fill that dimension's label."
    )
    print(f"[assevra] then score it:  python -m assevra run --dataset {args.out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="assevra",
        description=(
            "Measure LLM-agent reliability with the Assevra Reliability Scorecard."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="score a dataset and write a scorecard")
    run.add_argument(
        "--dataset",
        required=True,
        help="path to a JSONL dataset (see datasets/golden.jsonl)",
    )
    run.add_argument(
        "--out-dir",
        default=".",
        help="directory to write scorecard.md and scorecard.json (default: .)",
    )
    run.add_argument(
        "--judge-model",
        default=DEFAULT_JUDGE_MODEL,
        help=(
            "judge model for the LLM-as-judge dimensions "
            f"(default: {DEFAULT_JUDGE_MODEL}; use claude-sonnet-5 for volume)"
        ),
    )
    run.add_argument(
        "--gate",
        action="store_true",
        help="exit non-zero if the scorecard fails (for CI gating)",
    )
    run.set_defaults(func=cmd_run)

    boot = sub.add_parser(
        "bootstrap",
        help="draft a dataset from captured traces (removes the blank-page JSONL step)",
    )
    boot.add_argument(
        "--from",
        dest="source",
        required=True,
        help="file of captured interactions (JSONL, JSON array, or OTLP export)",
    )
    boot.add_argument(
        "--out",
        default="drafted.jsonl",
        help="path to write the drafted dataset (default: drafted.jsonl)",
    )
    boot.add_argument(
        "--format",
        choices=["auto", "generic", "openai", "otel"],
        default="auto",
        help="input format (default: auto-detect)",
    )
    boot.add_argument(
        "--dimension",
        choices=sorted(bootstrap_mod._DIMENSION_TEMPLATE),
        default=bootstrap_mod.DEFAULT_DIMENSION,
        help=(
            "dimension to assign drafted rows "
            f"(default: {bootstrap_mod.DEFAULT_DIMENSION}); re-tag per row as needed"
        ),
    )
    boot.add_argument(
        "--limit", type=int, default=None, help="cap the number of drafted rows"
    )
    boot.add_argument(
        "--id-prefix", default="bootstrap", help="id prefix for drafted rows"
    )
    boot.add_argument(
        "--input-field", default=None, help="generic format: field holding the user input"
    )
    boot.add_argument(
        "--output-field", default=None, help="generic format: field holding the agent output"
    )
    boot.add_argument(
        "--context-field", default=None, help="generic format: field holding the context"
    )
    boot.set_defaults(func=cmd_bootstrap)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
