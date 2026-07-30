"""
The Assevra command line.

Twelve commands, one arc: get a dataset, prove it is worth scoring, score it,
prove the judge, seal the result, map it for a reviewer, and gate the build.

    assevra demo                     a full worked scorecard, no clone, no key
    assevra init --from traces.jsonl detect, then generate config + dataset + CI
    assevra integrate langgraph      how to feed Assevra from the tool you use
    assevra bootstrap --from ...     draft a dataset from captured traces
    assevra validate                 LABELED / UNLABELED / INVALID, before scoring
    assevra run                      score, gate, and write the artifacts
    assevra calibrate                judge-vs-human agreement (Cohen's κ)
    assevra keygen / sign / verify   Ed25519 provenance for the artifact
    assevra attest                   map evidence to governance frameworks
    assevra history                  the reliability trend across runs
    assevra schema                   the published artifact contracts

Almost every flag has a ``.assevra.yml`` equivalent, and the precedence is the
one you would guess: **defaults < config file < environment < flags.** A team
should be able to type ``assevra run`` and get the same evaluation on every
machine.

Exit codes are stable, because CI depends on them: **0** success, **1** the gate
failed (a dimension below threshold, a regression, or an uncalibrated judge),
**2** the command could not run at all (bad dataset, missing file, bad flag).
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from typing import NoReturn, Optional

from . import api, bootstrap as bootstrap_mod, config as config_mod
from . import demo as demo_mod
from . import integrations as integrations_mod
from . import providers, registry, schemas, validate as validate_mod
from .judge import build_judge
from .scorecard import ASSEVRA_DOI, ASSEVRA_VERSION

EXIT_OK = 0
EXIT_GATE_FAILED = 1
EXIT_USAGE = 2


def _die(message: str, code: int = EXIT_USAGE) -> NoReturn:
    """Fail with a single actionable line on stderr and a stable exit code."""
    print(f"[assevra] {message}", file=sys.stderr)
    raise SystemExit(code)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _load_config(args: argparse.Namespace) -> config_mod.Config:
    requested = getattr(args, "config", None)
    # `--config none` runs with built-in defaults only. Useful when debugging a
    # project whose config is itself the suspect, and what the test suite uses to
    # stay independent of whatever config happens to sit above the working
    # directory.
    if requested and requested.strip().lower() in ("none", "off", "-"):
        return config_mod.Config(config_mod._deep_merge(config_mod.DEFAULTS, {}), None, [])
    try:
        cfg = config_mod.load(requested)
    except config_mod.ConfigError as exc:
        _die(str(exc))
    for key in cfg.unknown_keys:
        print(
            f"[assevra] warning: {cfg.path}: unknown config key {key!r} (ignored). "
            "Check the spelling against https://assevra.ai/docs/configuration",
            file=sys.stderr,
        )
    return cfg


def _resolve_dataset(args: argparse.Namespace, cfg: config_mod.Config) -> str:
    dataset = getattr(args, "dataset", None) or cfg.get("dataset", "")
    if not dataset:
        _die(
            "no dataset given. Pass --dataset PATH, or set `dataset:` in .assevra.yml "
            "(`assevra init` writes one for you)."
        )
    if not Path(dataset).is_file():
        _die(f"dataset not found: {dataset}")
    return dataset


def _parse_panel(spec: Optional[str]) -> Optional[list]:
    if not spec:
        return None
    models = [m.strip() for m in spec.split(",") if m.strip()]
    return models or None


def _parse_thresholds(pairs: Optional[list]) -> dict:
    out: dict[str, float] = {}
    for pair in pairs or []:
        if "=" not in pair:
            _die(f"--threshold expects DIMENSION=VALUE, got {pair!r}")
        name, _, value = pair.partition("=")
        if not registry.has_scorer(name.strip()):
            _die(
                f"--threshold names unknown dimension {name.strip()!r}; "
                f"known: {', '.join(registry.dimensions())}"
            )
        try:
            out[name.strip()] = float(value)
        except ValueError:
            _die(f"--threshold value must be a number, got {value!r}")
    return out


# --------------------------------------------------------------------------- #
# run                                                                          #
# --------------------------------------------------------------------------- #
def cmd_run(args: argparse.Namespace) -> int:
    cfg = _load_config(args)
    dataset = _resolve_dataset(args, cfg)

    out_dir = args.out_dir or cfg.get("out_dir", ".")
    formats = args.format or cfg.get("reports.formats", ["md", "json", "html"])
    panel = _parse_panel(args.judge_panel) or cfg.get("judge.panel", []) or None

    try:
        scorecard = api.evaluate(
            dataset=dataset,
            config=cfg,
            judge_provider=args.judge_provider,
            judge_model=args.judge_model,
            judge_panel=panel,
            pass_k=args.pass_k,
            thresholds=_parse_thresholds(args.threshold),
            validate=False if args.no_validate else None,
            strict=True if args.strict else None,
        )
    except api.DatasetError as exc:
        print(f"[assevra] {exc}", file=sys.stderr)
        if exc.report is not None:
            print(validate_mod.render(exc.report), file=sys.stderr)
        return EXIT_USAGE
    except providers.ProviderError as exc:
        _die(str(exc))

    written = api.write_reports(scorecard, out_dir, formats)
    if not args.quiet:
        print(scorecard.render_markdown())
    for path in written:
        print(f"[assevra] wrote {path}")
    print(f"[assevra] cite: https://doi.org/{ASSEVRA_DOI}  (see CITATION.cff)")

    directory = Path(out_dir)
    json_path = directory / "scorecard.json"

    signature_block = None
    sign_key = args.sign or cfg.get("signing.key", "")
    if sign_key:
        from . import signing

        if not Path(sign_key).is_file():
            _die(f"signing key not found: {sign_key}")
        try:
            signature_block = signing.sign_scorecard(
                scorecard.to_dict(),
                Path(sign_key).read_text(encoding="utf-8"),
                signed_at=_now(),
            )
        except signing.SigningError as exc:
            _die(str(exc))
        sig_path = directory / "scorecard.sig.json"
        sig_path.write_text(json.dumps(signature_block, indent=2) + "\n", encoding="utf-8")
        print(f"[assevra] wrote {sig_path}  (detached signature)")
        print(
            f"[assevra] verify: assevra verify --scorecard {json_path} --signature {sig_path}"
        )

    if cfg.pick(args.attest, "attest.enabled", False):
        from . import attest as attest_mod

        card = attest_mod.build_card_dict(
            scorecard.to_dict(), signature=signature_block, generated_at=_now()
        )
        (directory / "agent-card.md").write_text(
            attest_mod.render_markdown(card), encoding="utf-8"
        )
        (directory / "agent-card.json").write_text(
            attest_mod.render_json(card), encoding="utf-8"
        )
        print(f"[assevra] wrote {directory / 'agent-card.md'}")
        print(f"[assevra] wrote {directory / 'agent-card.json'}")

    regressed = False
    history_path = args.history or cfg.get("history.path", "")
    if history_path:
        from . import history as history_mod

        label = args.label or cfg.get("history.label", "")
        baseline_label = args.baseline or cfg.get("history.baseline", "")
        record = history_mod.record_from_scorecard(scorecard, label, _now())
        past = history_mod.load_history(history_path)
        baseline = history_mod.find_baseline(past, baseline_label or None)
        if baseline is not None:
            deltas = history_mod.compare(baseline, record)
            print()
            print(history_mod.render_comparison(baseline, record, deltas))
            regressed = history_mod.is_overall_regression(baseline, record, deltas)
        else:
            where = f"label {baseline_label!r}" if baseline_label else "empty history"
            print(f"[assevra] history: no prior run to compare ({where}); recording baseline.")
        history_mod.append_record(history_path, record)
        note = f" (label: {label})" if label else ""
        print(f"[assevra] appended this run to {history_path}{note}")

    _write_ci_summary(scorecard, written, regressed)

    exit_code = EXIT_OK
    if cfg.pick(args.gate, "gate.enabled", False) and not scorecard.overall_pass:
        exit_code = EXIT_GATE_FAILED
        print("[assevra] gate: FAILED — a scored dimension is below its threshold.")
    if cfg.pick(args.fail_on_regression, "gate.fail_on_regression", False) and regressed:
        if exit_code == EXIT_OK:
            print("[assevra] gate: FAILED — a dimension regressed against the baseline.")
        exit_code = EXIT_GATE_FAILED
    return exit_code


def _write_ci_summary(scorecard, written, regressed: bool) -> None:
    """Render a compact summary into GitHub's job summary, when running there.

    A build that fails should say *what* failed on the page the developer is
    already looking at, not only inside a downloaded artifact.
    """
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    verdict = "✅ PASS" if scorecard.overall_pass else "❌ FAIL"
    lines = [
        "## Assevra reliability scorecard",
        "",
        f"**Overall: {verdict}** · measured with Assevra v{scorecard.version}",
        "",
        "| Dimension | Mode | Score | 95% CI | n | Threshold | Result |",
        "|---|---|---|---|---|---|---|",
    ]
    for dimension in scorecard.dimensions:
        if dimension.skipped:
            lines.append(
                f"| `{dimension.name}` | {dimension.mode} | — | — | {dimension.n} | "
                f"{dimension.threshold:.2f} | ⏭️ SKIPPED |"
            )
            continue
        low, high = dimension.ci
        mark = "✅" if dimension.passed else "❌"
        lines.append(
            f"| `{dimension.name}` | {dimension.mode} | {dimension.score:.3f} | "
            f"{low:.3f}–{high:.3f} | {dimension.n} | {dimension.threshold:.2f} | "
            f"{mark} {'PASS' if dimension.passed else 'FAIL'} |"
        )
    failures = scorecard.failures()
    if failures:
        lines += ["", f"### {len(failures)} failing row(s)", ""]
        for name, row in failures[:15]:
            lines.append(f"- **{name}** `{row.row_id}` — {row.detail}")
        if len(failures) > 15:
            lines.append(f"- …and {len(failures) - 15} more")
    if regressed:
        lines += ["", "> ⚠️ A dimension regressed against the recorded baseline."]
    lines += [
        "",
        "<sub>A skipped dimension is not a passing one. Every score carries its sample "
        "size and a 95% Wilson interval.</sub>",
        "",
    ]
    try:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# validate                                                                     #
# --------------------------------------------------------------------------- #
def cmd_validate(args: argparse.Namespace) -> int:
    cfg = _load_config(args)
    dataset = _resolve_dataset(args, cfg)
    strict = bool(args.strict or cfg.get("validate.strict", False))

    report = validate_mod.validate_dataset(
        dataset,
        strict=strict,
        options=cfg.scorer_options(),
        assevra_version=ASSEVRA_VERSION,
        generated_at=_now(),
    )
    if args.json:
        print(report.to_json())
    else:
        print(validate_mod.render(report, show="all" if args.all else "problems"))
    if args.out:
        Path(args.out).write_text(report.to_json() + "\n", encoding="utf-8")
        print(f"[assevra] wrote {args.out}")
    return EXIT_OK if report.ok else EXIT_GATE_FAILED


# --------------------------------------------------------------------------- #
# demo                                                                         #
# --------------------------------------------------------------------------- #
def cmd_demo(args: argparse.Namespace) -> int:
    try:
        scorecard, _ = demo_mod.run(
            out_dir=args.out_dir, provider=args.provider, judge_model=args.judge_model or ""
        )
    except providers.ProviderError as exc:
        _die(str(exc))
    print(scorecard.render_markdown())
    print(demo_mod.summary(scorecard, args.out_dir))
    return EXIT_OK


# --------------------------------------------------------------------------- #
# init                                                                         #
# --------------------------------------------------------------------------- #
def cmd_init(args: argparse.Namespace) -> int:
    from . import init as init_mod

    try:
        plan, found = init_mod.plan(
            root=args.root,
            dataset=args.dataset,
            from_traces=args.source,
            workflow=not args.no_workflow,
            docs=not args.no_docs,
        )
    except FileNotFoundError as exc:
        _die(str(exc))

    print(init_mod.render_detection(found))
    print()
    targets = [plan.config_path, plan.dataset_path, plan.workflow_path, plan.doc_path]
    print("[assevra] will write:")
    for target in targets:
        if target is not None:
            print(f"[assevra]   {target}")
    if plan.dataset_path is None:
        print(
            "[assevra]   (no dataset — no traces found. Re-run with "
            "--from <file>, or start from `assevra demo`.)"
        )

    if args.dry_run:
        print("\n[assevra] --dry-run: nothing written.")
        return EXIT_OK

    try:
        plan = init_mod.apply(
            plan, dimension=args.dimension, limit=args.limit, force=args.force
        )
    except bootstrap_mod.BootstrapError as exc:
        _die(f"bootstrap: {exc}")

    print()
    if plan.drafted_rows:
        print(
            f"[assevra] drafted {plan.drafted_rows} rows from {plan.source_trace} "
            f"(format: {plan.trace_format}) -> {plan.dataset_path}"
        )
        print(
            "[assevra] every drafted row is tagged needs-review: fill the answer key "
            "each row's `_review` hint asks for."
        )
    for path in plan.skipped:
        print(f"[assevra] kept existing {path} (use --force to overwrite)")

    print()
    print("[assevra] next:")
    if plan.dataset_path is not None:
        print(f"[assevra]   1. label the rows in {plan.dataset_path}")
        print("[assevra]   2. assevra validate --strict")
        print("[assevra]   3. assevra run --gate")
    else:
        print("[assevra]   1. capture some agent outputs")
        print("[assevra]   2. assevra bootstrap --from traces.jsonl --out evals/agent.jsonl")
        print("[assevra]   3. assevra run --gate")
    if plan.frameworks:
        print(f"[assevra]   see also: assevra integrate {plan.frameworks[0]}")
    return EXIT_OK


# --------------------------------------------------------------------------- #
# integrate                                                                    #
# --------------------------------------------------------------------------- #
def cmd_integrate(args: argparse.Namespace) -> int:
    if args.list or not args.target:
        print("Available integrations:\n")
        for name in integrations_mod.names():
            integration = integrations_mod.INTEGRATIONS[name]
            print(f"  {name:<16} {integration.title}")
        print("\nUse:  assevra integrate <name> [--out INTEGRATION.md]")
        return EXIT_OK
    try:
        integration = integrations_mod.get(args.target)
    except KeyError as exc:
        _die(str(exc))
    text = integration.render(dataset=args.dataset or "evals/agent.jsonl")
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"[assevra] wrote {args.out}")
    else:
        print(text)
    return EXIT_OK


# --------------------------------------------------------------------------- #
# schema                                                                       #
# --------------------------------------------------------------------------- #
def cmd_schema(args: argparse.Namespace) -> int:
    if args.list or (not args.name and not args.out_dir):
        print(f"Assevra artifact contracts (schema version {schemas.SCHEMA_VERSION}):\n")
        for name in schemas.NAMES:
            print(f"  {name:<14} {schemas.schema_url(name)}")
        print(
            "\nWithin schema major version 1, fields are only added — never removed,"
            "\nrenamed, or repurposed. Validate your artifacts against these in CI."
        )
        return EXIT_OK
    if args.out_dir:
        directory = Path(args.out_dir)
        directory.mkdir(parents=True, exist_ok=True)
        for name in schemas.NAMES:
            target = directory / f"{name}.schema.json"
            target.write_text(schemas.schema_path(name).read_text(encoding="utf-8"), encoding="utf-8")
            print(f"[assevra] wrote {target}")
        return EXIT_OK
    try:
        print(json.dumps(schemas.load(args.name), indent=2))
    except KeyError as exc:
        _die(str(exc))
    return EXIT_OK


# --------------------------------------------------------------------------- #
# bootstrap / keygen / sign / verify / history / attest / calibrate            #
# --------------------------------------------------------------------------- #
def cmd_bootstrap(args: argparse.Namespace) -> int:
    if not Path(args.source).is_file():
        _die(f"source not found: {args.source}")
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
        _die(f"bootstrap: {exc}")

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
    print(f"[assevra] then check it:  assevra validate {args.out}")
    return EXIT_OK


def cmd_keygen(args: argparse.Namespace) -> int:
    from . import signing

    try:
        priv_pem, pub_b64 = signing.generate_keypair()
    except signing.SigningError as exc:
        _die(str(exc))

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
    return EXIT_OK


def cmd_sign(args: argparse.Namespace) -> int:
    from . import signing

    if not Path(args.scorecard).is_file():
        _die(f"scorecard not found: {args.scorecard}")
    if not Path(args.key).is_file():
        _die(f"signing key not found: {args.key}")
    try:
        scorecard = json.loads(Path(args.scorecard).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _die(f"{args.scorecard}: invalid JSON: {exc}")

    signed_at = args.timestamp or _now()
    try:
        block = signing.sign_scorecard(
            scorecard, Path(args.key).read_text(encoding="utf-8"), signed_at=signed_at
        )
    except signing.SigningError as exc:
        _die(str(exc))

    out = args.out or str(Path(args.scorecard).with_suffix(".sig.json"))
    Path(out).write_text(json.dumps(block, indent=2) + "\n", encoding="utf-8")
    print(f"[assevra] signed {args.scorecard} -> {out}")
    print(f"[assevra] content sha256: {block['content_sha256']}")
    print(f"[assevra] verify: assevra verify --scorecard {args.scorecard} --signature {out}")
    return EXIT_OK


def cmd_verify(args: argparse.Namespace) -> int:
    from . import signing

    if not Path(args.scorecard).is_file():
        _die(f"scorecard not found: {args.scorecard}")
    if not Path(args.signature).is_file():
        _die(f"signature not found: {args.signature}")
    try:
        scorecard = json.loads(Path(args.scorecard).read_text(encoding="utf-8"))
        sig_block = json.loads(Path(args.signature).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _die(f"invalid JSON: {exc}")

    expected = None
    if args.public_key:
        pk = Path(args.public_key)
        expected = (
            pk.read_text(encoding="utf-8").strip() if pk.is_file() else args.public_key.strip()
        )

    try:
        result = signing.verify_scorecard(scorecard, sig_block, expected_public_key_b64=expected)
    except signing.SigningError as exc:
        _die(str(exc))

    print(f"[assevra] verification: {'OK' if result.ok else 'FAILED'}")
    print(f"[assevra] {result.reason}")
    if result.signed_at:
        print(f"[assevra] signed_at: {result.signed_at}")
    if result.public_key:
        print(f"[assevra] public key: {result.public_key}")
    return EXIT_OK if result.ok else EXIT_GATE_FAILED


def cmd_history(args: argparse.Namespace) -> int:
    from . import history as history_mod

    cfg = _load_config(args)
    path = args.history or cfg.get("history.path", "")
    if not path:
        _die("no history file given. Pass --history PATH or set history.path in .assevra.yml")
    hist = history_mod.load_history(path)
    print(history_mod.render_history(hist, limit=args.limit))
    return EXIT_OK


def cmd_attest(args: argparse.Namespace) -> int:
    from . import attest as attest_mod

    if not Path(args.scorecard).is_file():
        _die(f"scorecard not found: {args.scorecard}")
    try:
        scorecard = json.loads(Path(args.scorecard).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _die(f"{args.scorecard}: invalid JSON: {exc}")

    signature = None
    if args.signature:
        if not Path(args.signature).is_file():
            _die(f"signature not found: {args.signature}")
        signature = json.loads(Path(args.signature).read_text(encoding="utf-8"))

    card = attest_mod.build_card_dict(scorecard, signature=signature, generated_at=_now())
    directory = Path(args.out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "agent-card.md").write_text(attest_mod.render_markdown(card), encoding="utf-8")
    (directory / "agent-card.json").write_text(attest_mod.render_json(card), encoding="utf-8")
    print(f"[assevra] wrote {directory / 'agent-card.md'}")
    print(f"[assevra] wrote {directory / 'agent-card.json'}")
    print(
        "[assevra] the Agent Card maps evidence to control families — it is NOT a "
        "certification, a compliance determination, or legal advice."
    )
    return EXIT_OK


def cmd_calibrate(args: argparse.Namespace) -> int:
    from . import calibration as calib

    cfg = _load_config(args)
    dataset = _resolve_dataset(args, cfg)
    label_field = args.label_field or cfg.get("calibration.label_field", "human_label")
    bar = float(cfg.get("calibration.kappa_bar", 0.85))

    rows = api.load_dataset(dataset)
    id_to_human = {}
    for row in rows:
        if label_field in row:
            value = calib.to_bool(row[label_field])
            if value is not None:
                id_to_human[row.get("id", "?")] = value
    if not id_to_human:
        _die(f"no usable '{label_field}' labels found in {dataset}.")

    panel = _parse_panel(args.judge_panel) or cfg.get("judge.panel", []) or None
    try:
        judge = build_judge(
            provider=args.judge_provider or cfg.get("judge.provider", "auto"),
            model=args.judge_model or cfg.get("judge.model", ""),
            panel=panel,
        )
    except providers.ProviderError as exc:
        _die(str(exc))
    if judge is None:
        _die(
            "calibration needs a judge. Configure a provider (e.g. set ANTHROPIC_API_KEY "
            'and pip install "assevra[anthropic]"), or use --judge-provider mock to '
            "exercise the plumbing offline."
        )

    grouped = api.group_by_dimension(rows)
    per_dim_labels = {}
    for name in registry.dimensions():
        spec = registry.get_scorer(name)
        if not spec.needs_judge or name not in grouped:
            continue
        result = spec.score(grouped[name], judge, cfg.scorer_options())
        judged, human = [], []
        for row_result in result.rows:
            if row_result.row_id in id_to_human:
                judged.append(bool(row_result.passed))
                human.append(id_to_human[row_result.row_id])
        if judged:
            per_dim_labels[name] = (judged, human)

    if not per_dim_labels:
        _die(
            "no judged-dimension rows carried human labels. Add the label field to "
            "grounding/safety rows and re-run."
        )

    all_judged = [x for (j, _) in per_dim_labels.values() for x in j]
    all_human = [x for (_, h) in per_dim_labels.values() for x in h]
    overall = calib.compute(all_judged, all_human)
    per_dim = {d: calib.compute(j, h) for d, (j, h) in per_dim_labels.items()}
    print(calib.render(overall, per_dim, bar=bar))
    print(f"\n[assevra] judge: {judge.model}")

    if args.out:
        payload = calib.to_artifact(
            overall,
            per_dim,
            judge_model=judge.model,
            judge_provider=getattr(judge, "provider", ""),
            dataset=dataset,
            label_field=label_field,
            bar=bar,
            assevra_version=ASSEVRA_VERSION,
            generated_at=_now(),
        )
        Path(args.out).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"[assevra] wrote {args.out}")

    return EXIT_OK if overall.trustworthy_at(bar) else EXIT_GATE_FAILED


# --------------------------------------------------------------------------- #
# Parser                                                                       #
# --------------------------------------------------------------------------- #
def _add_config_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        default=None,
        metavar="PATH",
        help=(
            "path to .assevra.yml (default: found by walking up from the cwd); "
            "pass 'none' to ignore any project config and use built-in defaults"
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="assevra",
        description=(
            "Release evidence for AI agents: turn agent test runs into signed, "
            "statistically defensible scorecards that gate every release."
        ),
        epilog="Docs: https://assevra.ai/docs · Start with: assevra demo",
    )
    parser.add_argument("--version", action="version", version=f"assevra {ASSEVRA_VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    # -- run ---------------------------------------------------------------- #
    run = sub.add_parser("run", help="score a dataset, gate the build, write the artifacts")
    _add_config_flag(run)
    run.add_argument("--dataset", default=None, help="JSONL dataset (default: from .assevra.yml)")
    run.add_argument("--out-dir", default=None, help="where to write the artifacts")
    run.add_argument(
        "--format",
        action="append",
        choices=["md", "markdown", "json", "html"],
        default=None,
        help="report format; repeatable (default: md, json, html)",
    )
    run.add_argument(
        "--judge-provider",
        default=None,
        choices=sorted(providers.PROVIDERS) + ["auto", "none"],
        help="which vendor serves the judge (default: auto — the first with credentials)",
    )
    run.add_argument("--judge-model", default=None, help="judge model (or deployment) name")
    run.add_argument(
        "--judge-panel",
        default=None,
        metavar="M1,M2,...",
        help="comma-separated models to use as a jury; entries may be provider:model",
    )
    run.add_argument(
        "--pass-k", type=int, default=None,
        help="k for pass^k over repeated-trial cases sharing a case_id (default: 2)",
    )
    run.add_argument(
        "--threshold", action="append", metavar="DIM=VALUE", default=None,
        help="override a dimension's pass threshold; repeatable",
    )
    run.add_argument("--gate", action="store_true", help="exit non-zero if the scorecard fails")
    run.add_argument(
        "--fail-on-regression", action="store_true",
        help="exit non-zero if a dimension regressed against the baseline",
    )
    run.add_argument("--sign", metavar="KEYFILE", default=None, help="Ed25519 private key (PEM)")
    run.add_argument("--attest", action="store_true", help="also write the Agent Card")
    run.add_argument("--history", metavar="PATH", default=None, help="run-history JSONL file")
    run.add_argument("--label", default=None, help="label for this run (e.g. a git SHA)")
    run.add_argument("--baseline", default=None, help="compare against this labeled run")
    run.add_argument("--strict", action="store_true", help="fail if any row carries no answer key")
    run.add_argument("--no-validate", action="store_true", help="skip pre-flight validation")
    run.add_argument("--quiet", action="store_true", help="do not print the full report")
    run.set_defaults(func=cmd_run)

    # -- validate ------------------------------------------------------------ #
    val = sub.add_parser(
        "validate", help="check a dataset before scoring it (LABELED / UNLABELED / INVALID)"
    )
    _add_config_flag(val)
    val.add_argument("dataset", nargs="?", default=None, help="JSONL dataset to check")
    val.add_argument("--strict", action="store_true", help="treat unlabeled rows as failures")
    val.add_argument("--all", action="store_true", help="list every row, not just the problems")
    val.add_argument("--json", action="store_true", help="print the machine-readable report")
    val.add_argument("--out", default=None, metavar="PATH", help="write the JSON report to a file")
    val.set_defaults(func=cmd_validate)

    # -- demo ---------------------------------------------------------------- #
    demo = sub.add_parser("demo", help="run a full worked example — no clone, no key, no network")
    demo.add_argument("--out-dir", default="assevra-demo", help="where to write the artifacts")
    demo.add_argument(
        "--provider", default="auto",
        choices=sorted(providers.PROVIDERS) + ["auto", "none"],
        help="judge provider; 'mock' runs the judged path deterministically offline",
    )
    demo.add_argument("--judge-model", default=None, help="judge model name")
    demo.set_defaults(func=cmd_demo)

    # -- init ---------------------------------------------------------------- #
    init = sub.add_parser("init", help="detect traces/framework/providers and scaffold everything")
    init.add_argument("--root", default=".", help="project directory to inspect (default: .)")
    init.add_argument("--from", dest="source", default=None, help="trace file to draft rows from")
    init.add_argument("--dataset", default=None, help="where to write the drafted dataset")
    init.add_argument(
        "--dimension", default=bootstrap_mod.DEFAULT_DIMENSION,
        choices=sorted(bootstrap_mod._DIMENSION_TEMPLATE),
        help="dimension to assign drafted rows",
    )
    init.add_argument("--limit", type=int, default=None, help="cap the number of drafted rows")
    init.add_argument("--no-workflow", action="store_true", help="do not write a CI workflow")
    init.add_argument("--no-docs", action="store_true", help="do not write EVALUATION.md")
    init.add_argument("--force", action="store_true", help="overwrite existing files")
    init.add_argument("--dry-run", action="store_true", help="show what would be written")
    init.set_defaults(func=cmd_init)

    # -- integrate ----------------------------------------------------------- #
    integrate = sub.add_parser("integrate", help="wiring guide for the tool you already use")
    integrate.add_argument("target", nargs="?", default=None, help=", ".join(integrations_mod.names()))
    integrate.add_argument("--list", action="store_true", help="list the supported integrations")
    integrate.add_argument("--dataset", default=None, help="dataset path to use in the snippets")
    integrate.add_argument("--out", default=None, help="write the guide to a file")
    integrate.set_defaults(func=cmd_integrate)

    # -- schema -------------------------------------------------------------- #
    schema = sub.add_parser("schema", help="print or export the published artifact contracts")
    schema.add_argument("name", nargs="?", default=None, choices=list(schemas.NAMES) + [None])
    schema.add_argument("--list", action="store_true", help="list the schemas and their URLs")
    schema.add_argument("--out-dir", default=None, help="write every schema into a directory")
    schema.set_defaults(func=cmd_schema)

    # -- bootstrap ----------------------------------------------------------- #
    boot = sub.add_parser("bootstrap", help="draft a dataset from captured traces")
    boot.add_argument("--from", dest="source", required=True, help="file of captured interactions")
    boot.add_argument("--out", default="drafted.jsonl", help="path to write the drafted dataset")
    boot.add_argument(
        "--format", choices=["auto", "generic", "csv", "openai", "anthropic", "otel"],
        default="auto", help="input format (default: auto-detect)",
    )
    boot.add_argument(
        "--dimension", choices=sorted(bootstrap_mod._DIMENSION_TEMPLATE),
        default=bootstrap_mod.DEFAULT_DIMENSION, help="dimension to assign drafted rows",
    )
    boot.add_argument("--limit", type=int, default=None, help="cap the number of drafted rows")
    boot.add_argument("--id-prefix", default="bootstrap", help="id prefix for drafted rows")
    boot.add_argument("--input-field", default=None, help="generic: field holding the user input")
    boot.add_argument("--output-field", default=None, help="generic: field holding the output")
    boot.add_argument("--context-field", default=None, help="generic: field holding the context")
    boot.set_defaults(func=cmd_bootstrap)

    # -- keygen / sign / verify ---------------------------------------------- #
    keygen = sub.add_parser("keygen", help="generate an Ed25519 keypair for signing scorecards")
    keygen.add_argument("--out-private", default="assevra_ed25519_private.pem")
    keygen.add_argument("--out-public", default="assevra_ed25519_public.txt")
    keygen.set_defaults(func=cmd_keygen)

    sign = sub.add_parser("sign", help="sign a scorecard.json, producing a detached signature")
    sign.add_argument("--scorecard", required=True)
    sign.add_argument("--key", required=True, help="Ed25519 private key (PEM)")
    sign.add_argument("--out", default=None, help="signature output path")
    sign.add_argument("--timestamp", default=None, help="ISO-8601 signing timestamp")
    sign.set_defaults(func=cmd_sign)

    verify = sub.add_parser("verify", help="verify a scorecard against its detached signature")
    verify.add_argument("--scorecard", required=True)
    verify.add_argument("--signature", required=True)
    verify.add_argument(
        "--public-key", default=None,
        help="pin the expected public key (a path or the base64 string) to prove authorship",
    )
    verify.set_defaults(func=cmd_verify)

    # -- history ------------------------------------------------------------- #
    hist = sub.add_parser("history", help="show the reliability trend across recorded runs")
    _add_config_flag(hist)
    hist.add_argument("--history", default=None, help="path to the JSONL history file")
    hist.add_argument("--limit", type=int, default=None, help="show only the last N runs")
    hist.set_defaults(func=cmd_history)

    # -- calibrate ----------------------------------------------------------- #
    cal = sub.add_parser(
        "calibrate", help="measure judge-vs-human agreement (Cohen's κ) on a labeled hold-out"
    )
    _add_config_flag(cal)
    cal.add_argument("--dataset", default=None, help="hold-out JSONL with a human label per row")
    cal.add_argument("--label-field", default=None, help="row field with the human verdict")
    cal.add_argument("--judge-provider", default=None, choices=sorted(providers.PROVIDERS) + ["auto"])
    cal.add_argument("--judge-model", default=None)
    cal.add_argument("--judge-panel", default=None, metavar="M1,M2,...")
    cal.add_argument("--out", default=None, help="write the calibration artifact (JSON) here")
    cal.set_defaults(func=cmd_calibrate)

    # -- attest -------------------------------------------------------------- #
    att = sub.add_parser("attest", help="map a scorecard to AI-governance control families")
    att.add_argument("--scorecard", required=True)
    att.add_argument("--signature", default=None, help="optional scorecard.sig.json")
    att.add_argument("--out-dir", default=".", help="where to write the Agent Card")
    att.set_defaults(func=cmd_attest)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
