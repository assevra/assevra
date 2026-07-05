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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
