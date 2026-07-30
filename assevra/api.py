"""
The Python SDK — Assevra as a library, not just a command.

The CLI is the right interface for CI. It is the wrong interface for the place
most evaluation actually happens: inside a notebook, a pytest suite, or the
harness that just finished running the agent and is holding the results in
memory. Making those users serialize to JSONL, shell out, and parse a file back
is friction with no payoff, so the same engine is available directly:

    from assevra import evaluate

    result = evaluate(records=rows)
    print(result.overall_pass, result.dimension("grounding").score)

``records`` are the same objects a dataset file holds, so anything you can put in
a ``.jsonl`` you can pass as a list of dicts — and vice versa. Configuration
resolution is identical too: pass a :class:`~assevra.config.Config`, a path, a
plain dict, or nothing at all and let it find ``.assevra.yml``.

One deliberate behaviour: **validation runs first, and a structurally invalid
dataset raises.** In a notebook it is even easier than in CI to score a typo and
believe the number, so ``evaluate`` refuses rather than returning a confident
scorecard built on rows it could not understand. Pass ``validate=False`` if you
genuinely want the old behaviour.

Extending Assevra is the other half of this module. Scorers, reporters, trace
adapters, and judge providers are all registrable, so a team's domain metric is a
first-class dimension rather than a fork:

    from assevra import register_scorer_module
    import my_evals.policy_citation as m
    register_scorer_module(m)
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any, Iterable, Optional, Union

from . import config as config_mod
from . import registry, reliability as reliability_mod, validate as validate_mod
from .judge import build_judge
from .scorecard import ASSEVRA_VERSION, DimensionResult, Scorecard

# Importing the scorers package registers the nine built-in dimensions.
from . import scorers as _scorers  # noqa: F401


class DatasetError(Exception):
    """Raised when a dataset cannot be scored as given."""

    def __init__(self, message: str, report: Optional[validate_mod.Report] = None):
        super().__init__(message)
        self.report = report


ConfigLike = Union[None, str, Path, dict, config_mod.Config]


def resolve_config(config: ConfigLike = None) -> config_mod.Config:
    """Accept whatever the caller has: a Config, a path, a dict, or nothing."""
    if isinstance(config, config_mod.Config):
        return config
    if isinstance(config, (str, Path)):
        return config_mod.load(str(config))
    if isinstance(config, dict):
        merged = config_mod._deep_merge(config_mod.DEFAULTS, config)
        return config_mod.Config(merged, None, [])
    return config_mod.load()


def load_dataset(path: str) -> list[dict]:
    """Read a JSONL dataset into a list of rows."""
    rows: list[dict] = []
    with open(path, encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                rows.append(json.loads(text))
            except json.JSONDecodeError as exc:
                raise DatasetError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
    return rows


def write_dataset(rows: Iterable[dict], path: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def group_by_dimension(rows: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        dimension = row.get("dimension")
        if not registry.has_scorer(dimension):
            raise DatasetError(
                f"row {row.get('id', '?')!r} has unknown dimension {dimension!r}; "
                f"expected one of {', '.join(registry.dimensions())}"
            )
        grouped.setdefault(dimension, []).append(row)
    return grouped


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def evaluate(
    records: Optional[list[dict]] = None,
    dataset: Optional[str] = None,
    config: ConfigLike = None,
    judge: Any = None,
    judge_provider: Optional[str] = None,
    judge_model: Optional[str] = None,
    judge_panel: Optional[list] = None,
    pass_k: Optional[int] = None,
    thresholds: Optional[dict] = None,
    options: Optional[dict] = None,
    validate: Optional[bool] = None,
    strict: Optional[bool] = None,
) -> Scorecard:
    """Score records (or a dataset file) and return a :class:`Scorecard`.

    Args:
        records: rows to score, as dicts. Mutually exclusive with `dataset`.
        dataset: path to a JSONL dataset.
        config: a Config, a path to one, a dict, or None to auto-discover.
        judge: a prebuilt judge/panel. When omitted, one is built from config —
            and when none is available, judged dimensions are skipped.
        judge_provider / judge_model / judge_panel: override the config's judge.
        pass_k: k for pass^k over repeated-trial cases sharing a case_id.
        thresholds: per-dimension overrides, e.g. ``{"grounding": 0.95}``.
        options: extra options handed to every scorer (budgets, price table).
        validate: run dataset validation first (default: from config, on).
        strict: also refuse rows carrying no answer key.

    Raises:
        DatasetError: if neither/both inputs are given, or validation fails.
    """
    if (records is None) == (dataset is None):
        raise DatasetError("pass exactly one of `records` or `dataset`")

    cfg = resolve_config(config)
    rows = list(records) if records is not None else load_dataset(dataset)
    dataset_label = dataset or "(in-memory records)"

    scorer_options = dict(cfg.scorer_options())
    if options:
        scorer_options.update(options)

    should_validate = cfg.get("validate.on_run", True) if validate is None else validate
    is_strict = cfg.get("validate.strict", False) if strict is None else strict
    if should_validate:
        report = _validate_rows(rows, dataset_label, is_strict, scorer_options)
        if not report.ok:
            raise DatasetError(
                f"dataset validation failed: {report.count(validate_mod.INVALID)} invalid, "
                f"{report.count(validate_mod.UNLABELED)} unlabeled row(s). "
                "Run `assevra validate` for the details.",
                report,
            )

    if judge is None:
        panel = judge_panel if judge_panel is not None else cfg.get("judge.panel", [])
        judge = build_judge(
            provider=judge_provider or cfg.get("judge.provider", "auto"),
            model=judge_model or cfg.get("judge.model", ""),
            panel=panel or None,
            base_url=cfg.get("judge.base_url", ""),
            api_key_env=cfg.get("judge.api_key_env", ""),
            max_tokens=cfg.get("judge.max_tokens", 512),
            temperature=cfg.get("judge.temperature", 0.0),
        )

    grouped = group_by_dimension(rows)
    effective_thresholds = dict(cfg.get("thresholds", {}) or {})
    if thresholds:
        effective_thresholds.update(thresholds)

    dimensions: list[DimensionResult] = []
    for name in registry.dimensions():
        if name not in grouped:
            continue
        spec = registry.get_scorer(name)
        result = spec.score(grouped[name], judge, scorer_options)
        override = effective_thresholds.get(name)
        if override is not None:
            result.threshold = float(override)
        dimensions.append(result)

    # pass^k / consistency over any repeated-trial cases (empty otherwise).
    id_to_case = {
        row.get("id", "?"): row.get("case_id", row.get("id", "?")) for row in rows
    }
    k = int(pass_k if pass_k is not None else cfg.get("reliability.pass_k", 2))
    reliability = []
    for dimension in dimensions:
        passed_by_case = reliability_mod.group_passed_by_case(dimension.rows, id_to_case)
        computed = reliability_mod.compute_dimension(dimension.name, passed_by_case, k)
        if computed is not None:
            reliability.append(computed)

    return Scorecard(
        dimensions=dimensions,
        dataset=dataset_label,
        dataset_sha256=validate_mod.dataset_sha256(dataset) if dataset else None,
        judge_model=getattr(judge, "model", "") if judge is not None else "",
        judge_provider=getattr(judge, "provider", "") if judge is not None else "",
        reliability=reliability,
        generated_at=_utc_now(),
    )


def _validate_rows(
    rows: list[dict], label: str, strict: bool, options: dict
) -> validate_mod.Report:
    seen: set = set()
    reports = [
        validate_mod.validate_row(row, index, seen, options)
        for index, row in enumerate(rows, start=1)
    ]
    return validate_mod.Report(
        dataset=label,
        rows=reports,
        strict=strict,
        assevra_version=ASSEVRA_VERSION,
        generated_at=_utc_now(),
    )


def validate_dataset(
    path: str, strict: bool = False, config: ConfigLike = None
) -> validate_mod.Report:
    """Validate a dataset file without scoring it."""
    cfg = resolve_config(config)
    return validate_mod.validate_dataset(
        path,
        strict=strict,
        options=cfg.scorer_options(),
        assevra_version=ASSEVRA_VERSION,
        generated_at=_utc_now(),
    )


# --------------------------------------------------------------------------- #
# Built-in reporters                                                           #
# --------------------------------------------------------------------------- #
registry.register_reporter("md", lambda sc: sc.render_markdown(), replace=True)
registry.register_reporter("markdown", lambda sc: sc.render_markdown(), replace=True)
registry.register_reporter("json", lambda sc: sc.to_json(), replace=True)
registry.register_reporter("html", lambda sc: sc.render_html(), replace=True)

_EXTENSIONS = {"md": "md", "markdown": "md", "json": "json", "html": "html"}


def write_reports(
    scorecard: Scorecard, out_dir: str, formats: Iterable[str] = ("md", "json", "html")
) -> list[Path]:
    """Render a scorecard into `out_dir` in each requested format."""
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for fmt in formats:
        render = registry.get_reporter(fmt)
        path = directory / f"scorecard.{_EXTENSIONS.get(fmt, fmt)}"
        path.write_text(render(scorecard), encoding="utf-8")
        written.append(path)
    return written
