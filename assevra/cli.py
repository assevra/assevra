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
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Optional

from . import bootstrap as bootstrap_mod
from .judge import DEFAULT_JUDGE_MODEL, get_judge, get_panel
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


def build_scorecard(
    dataset_path: str,
    judge_model: str,
    pass_k: int = 2,
    judge_panel: Optional[list] = None,
) -> Scorecard:
    from . import reliability as reliability_mod

    rows = load_dataset(dataset_path)
    grouped = group_by_dimension(rows)

    # Map each row id to its case id (rows sharing a case_id are repeated trials
    # of one logical case; an ungrouped row is its own single-trial case).
    id_to_case = {row.get("id", "?"): row.get("case_id", row.get("id", "?")) for row in rows}

    # Build the judge once and share it across the judge dimensions. A panel of
    # models (if given) is used as a jury; otherwise a single judge.
    judge = get_panel(judge_panel) if judge_panel else get_judge(judge_model)

    dimensions = []
    for dim in DIMENSION_ORDER:
        if dim not in grouped:
            continue
        scorer = SCORERS[dim]
        if dim in JUDGE_DIMENSIONS:
            dimensions.append(scorer(grouped[dim], judge))
        else:
            dimensions.append(scorer(grouped[dim], None))

    # pass^k / consistency over any repeated-trial cases (empty otherwise).
    reliability = []
    for dim in dimensions:
        passed_by_case = reliability_mod.group_passed_by_case(dim.rows, id_to_case)
        cr = reliability_mod.compute_dimension(dim.name, passed_by_case, pass_k)
        if cr is not None:
            reliability.append(cr)

    return Scorecard(
        dimensions=dimensions,
        dataset=dataset_path,
        judge_model=judge.model if judge is not None else "",
        reliability=reliability,
    )


def _parse_panel(spec: Optional[str]) -> Optional[list]:
    if not spec:
        return None
    models = [m.strip() for m in spec.split(",") if m.strip()]
    return models or None


def cmd_run(args: argparse.Namespace) -> int:
    if not Path(args.dataset).is_file():
        raise SystemExit(f"dataset not found: {args.dataset}")

    panel = _parse_panel(args.judge_panel)
    scorecard = build_scorecard(args.dataset, args.judge_model, args.pass_k, judge_panel=panel)

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

    if args.sign:
        from . import signing

        if not Path(args.sign).is_file():
            raise SystemExit(f"[assevra] signing key not found: {args.sign}")
        signed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            block = signing.sign_scorecard(
                scorecard.to_dict(),
                Path(args.sign).read_text(encoding="utf-8"),
                signed_at=signed_at,
            )
        except signing.SigningError as exc:
            raise SystemExit(f"[assevra] {exc}")
        sig_path = out_dir / "scorecard.sig.json"
        sig_path.write_text(json.dumps(block, indent=2) + "\n", encoding="utf-8")
        print(f"[assevra] wrote {sig_path}  (detached signature)")
        print(
            f"[assevra] verify: python -m assevra verify "
            f"--scorecard {json_path} --signature {sig_path}"
        )

    regressed = False
    if args.history:
        from . import history as history_mod

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        record = history_mod.record_from_scorecard(scorecard, args.label or "", now)
        past = history_mod.load_history(args.history)
        baseline = history_mod.find_baseline(past, args.baseline)
        if baseline is not None:
            deltas = history_mod.compare(baseline, record)
            print()
            print(history_mod.render_comparison(baseline, record, deltas))
            regressed = history_mod.is_overall_regression(baseline, record, deltas)
        else:
            where = f"label {args.baseline!r}" if args.baseline else "empty history"
            print(f"[assevra] history: no prior run to compare ({where}); recording baseline.")
        history_mod.append_record(args.history, record)
        label_note = f" (label: {args.label})" if args.label else ""
        print(f"[assevra] appended this run to {args.history}{label_note}")

    exit_code = 0
    if args.gate and not scorecard.overall_pass:
        exit_code = 1
    if args.fail_on_regression and regressed:
        if exit_code == 0:
            print("[assevra] failing the build on regression (--fail-on-regression).")
        exit_code = 1
    return exit_code


def cmd_keygen(args: argparse.Namespace) -> int:
    from . import signing

    try:
        priv_pem, pub_b64 = signing.generate_keypair()
    except signing.SigningError as exc:
        raise SystemExit(f"[assevra] {exc}")

    Path(args.out_private).write_text(priv_pem, encoding="utf-8")
    try:
        os.chmod(args.out_private, 0o600)
    except OSError:
        pass
    Path(args.out_public).write_text(pub_b64 + "\n", encoding="utf-8")

    print(f"[assevra] wrote private key -> {args.out_private}  (KEEP SECRET — never commit)")
    print(f"[assevra] wrote public key  -> {args.out_public}")
    print(f"[assevra] public key: {pub_b64}")
    print("[assevra] publish the PUBLIC key so anyone can verify your scorecards.")
    return 0


def cmd_sign(args: argparse.Namespace) -> int:
    from . import signing

    if not Path(args.scorecard).is_file():
        raise SystemExit(f"[assevra] scorecard not found: {args.scorecard}")
    if not Path(args.key).is_file():
        raise SystemExit(f"[assevra] signing key not found: {args.key}")

    try:
        scorecard = json.loads(Path(args.scorecard).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[assevra] {args.scorecard}: invalid JSON: {exc}")

    signed_at = args.timestamp or datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        block = signing.sign_scorecard(
            scorecard, Path(args.key).read_text(encoding="utf-8"), signed_at=signed_at
        )
    except signing.SigningError as exc:
        raise SystemExit(f"[assevra] {exc}")

    out = args.out or str(Path(args.scorecard).with_suffix(".sig.json"))
    Path(out).write_text(json.dumps(block, indent=2) + "\n", encoding="utf-8")
    print(f"[assevra] signed {args.scorecard} -> {out}")
    print(f"[assevra] content sha256: {block['content_sha256']}")
    print(
        f"[assevra] verify: python -m assevra verify "
        f"--scorecard {args.scorecard} --signature {out}"
    )
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    from . import signing

    if not Path(args.scorecard).is_file():
        raise SystemExit(f"[assevra] scorecard not found: {args.scorecard}")
    if not Path(args.signature).is_file():
        raise SystemExit(f"[assevra] signature not found: {args.signature}")

    try:
        scorecard = json.loads(Path(args.scorecard).read_text(encoding="utf-8"))
        sig_block = json.loads(Path(args.signature).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[assevra] invalid JSON: {exc}")

    expected = None
    if args.public_key:
        pk = Path(args.public_key)
        expected = pk.read_text(encoding="utf-8").strip() if pk.is_file() else args.public_key.strip()

    try:
        result = signing.verify_scorecard(scorecard, sig_block, expected_public_key_b64=expected)
    except signing.SigningError as exc:
        raise SystemExit(f"[assevra] {exc}")

    print(f"[assevra] verification: {'OK' if result.ok else 'FAILED'}")
    print(f"[assevra] {result.reason}")
    if result.signed_at:
        print(f"[assevra] signed_at: {result.signed_at}")
    if result.public_key:
        print(f"[assevra] public key: {result.public_key}")
    return 0 if result.ok else 1


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


def cmd_history(args: argparse.Namespace) -> int:
    from . import history as history_mod

    hist = history_mod.load_history(args.history)
    print(history_mod.render_history(hist, limit=args.limit))
    return 0


def cmd_calibrate(args: argparse.Namespace) -> int:
    from . import calibration as calib

    if not Path(args.dataset).is_file():
        raise SystemExit(f"dataset not found: {args.dataset}")
    rows = load_dataset(args.dataset)

    id_to_human = {}
    for r in rows:
        if args.label_field in r:
            b = calib.to_bool(r[args.label_field])
            if b is not None:
                id_to_human[r.get("id", "?")] = b
    if not id_to_human:
        raise SystemExit(
            f"[assevra] no usable '{args.label_field}' labels found in {args.dataset}."
        )

    panel = _parse_panel(args.judge_panel)
    judge = get_panel(panel) if panel else get_judge(args.judge_model)
    if judge is None:
        raise SystemExit(
            "[assevra] calibration needs a judge (set ANTHROPIC_API_KEY and "
            'install the judge extra: pip install "assevra[judge]").'
        )

    grouped = group_by_dimension(rows)
    per_dim_labels = {}
    for dim in DIMENSION_ORDER:
        if dim in JUDGE_DIMENSIONS and dim in grouped:
            result = SCORERS[dim](grouped[dim], judge)
            jl, hl = [], []
            for rr in result.rows:
                if rr.row_id in id_to_human:
                    jl.append(bool(rr.passed))
                    hl.append(id_to_human[rr.row_id])
            if jl:
                per_dim_labels[dim] = (jl, hl)

    if not per_dim_labels:
        raise SystemExit(
            "[assevra] no judge-dimension rows with human labels to calibrate "
            "(need grounding/safety rows carrying the label field)."
        )

    all_j = [x for (jl, _) in per_dim_labels.values() for x in jl]
    all_h = [x for (_, hl) in per_dim_labels.values() for x in hl]
    overall = calib.compute(all_j, all_h)
    per_dim = {d: calib.compute(jl, hl) for d, (jl, hl) in per_dim_labels.items()}
    print(calib.render(overall, per_dim))
    print(f"\n[assevra] judge: {judge.model}")
    return 0 if overall.trustworthy else 1


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
        "--judge-panel",
        default=None,
        metavar="M1,M2,...",
        help="comma-separated judge models to use as a jury (overrides --judge-model)",
    )
    run.add_argument(
        "--pass-k",
        type=int,
        default=2,
        help="k for pass^k over repeated-trial cases (default: 2); needs case_id-grouped rows",
    )
    run.add_argument(
        "--gate",
        action="store_true",
        help="exit non-zero if the scorecard fails (for CI gating)",
    )
    run.add_argument(
        "--sign",
        metavar="KEYFILE",
        default=None,
        help="Ed25519 private key (PEM) to sign the scorecard; writes scorecard.sig.json",
    )
    run.add_argument(
        "--history",
        metavar="PATH",
        default=None,
        help="append this run to a JSONL history file and compare against the last run",
    )
    run.add_argument(
        "--label",
        default=None,
        help="label for this run in history (e.g. a git SHA or version)",
    )
    run.add_argument(
        "--baseline",
        default=None,
        help="compare against the most recent history run with this label (default: the previous run)",
    )
    run.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="exit non-zero if a dimension regressed (fell below its prior 95%% interval or now fails)",
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

    keygen = sub.add_parser(
        "keygen", help="generate an Ed25519 keypair for signing scorecards"
    )
    keygen.add_argument(
        "--out-private",
        default="assevra_ed25519_private.pem",
        help="path for the private key (default: assevra_ed25519_private.pem)",
    )
    keygen.add_argument(
        "--out-public",
        default="assevra_ed25519_public.txt",
        help="path for the public key (default: assevra_ed25519_public.txt)",
    )
    keygen.set_defaults(func=cmd_keygen)

    sign = sub.add_parser(
        "sign", help="sign a scorecard.json, producing a detached signature"
    )
    sign.add_argument("--scorecard", required=True, help="path to scorecard.json")
    sign.add_argument("--key", required=True, help="Ed25519 private key (PEM)")
    sign.add_argument(
        "--out", default=None, help="signature output path (default: <scorecard>.sig.json)"
    )
    sign.add_argument(
        "--timestamp",
        default=None,
        help="ISO-8601 signing timestamp (default: current UTC time)",
    )
    sign.set_defaults(func=cmd_sign)

    verify = sub.add_parser(
        "verify", help="verify a scorecard against its detached signature"
    )
    verify.add_argument("--scorecard", required=True, help="path to scorecard.json")
    verify.add_argument("--signature", required=True, help="path to the .sig.json")
    verify.add_argument(
        "--public-key",
        default=None,
        help="pin the expected public key (a file path or the base64 string) to prove authorship",
    )
    verify.set_defaults(func=cmd_verify)

    hist = sub.add_parser(
        "history", help="show the reliability trend from a run-history file"
    )
    hist.add_argument("--history", required=True, help="path to the JSONL history file")
    hist.add_argument(
        "--limit", type=int, default=None, help="show only the last N runs"
    )
    hist.set_defaults(func=cmd_history)

    cal = sub.add_parser(
        "calibrate",
        help="measure judge-vs-human agreement (Cohen's κ) on a labeled hold-out",
    )
    cal.add_argument(
        "--dataset", required=True, help="hold-out JSONL with a human label per row"
    )
    cal.add_argument(
        "--label-field",
        default="human_label",
        help="row field holding the human pass/fail label (default: human_label)",
    )
    cal.add_argument(
        "--judge-model", default=DEFAULT_JUDGE_MODEL, help="single judge model"
    )
    cal.add_argument(
        "--judge-panel",
        default=None,
        metavar="M1,M2,...",
        help="comma-separated judge models to use as a jury",
    )
    cal.set_defaults(func=cmd_calibrate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
