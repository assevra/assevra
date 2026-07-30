"""
Assevra — release evidence for AI agents.

Assevra turns agent test runs into signed, statistically defensible scorecards
that gate every release. It is not an eval dashboard and not an observability
backend: the deliverable is a **portable artifact** — Markdown, JSON, and a
self-contained HTML report — that you commit to git, attach to a pull request,
hand to a security reviewer, and can still verify a year later.

Three commitments run through the whole project:

* **Deterministic before judge.** If a property can be detected with a rule — a
  leaked SSN, a malformed tool call, a blown latency budget — detect it. Ask a
  model only for the things that genuinely require judgment.
* **Report the interval, not just the mean.** Every dimension carries a 95%
  Wilson confidence interval and its sample size, so nobody over-reads a
  small-sample move.
* **Skipped is not passed.** A dimension whose engine was unavailable is reported
  as skipped and does not gate. A missing measurement is never a passing one.

The five-minute path::

    pip install assevra
    assevra demo                 # a full worked scorecard, no clone, no key
    assevra init --from traces.jsonl
    assevra run                  # reads .assevra.yml

The library path::

    from assevra import evaluate
    result = evaluate(records=rows)
    result.overall_pass

A personal open-source research project by Veera Ravindra Divi. MIT licensed.
See METHODOLOGY.md for the dimension specifications and their limits.
"""
from .api import (
    DatasetError,
    evaluate,
    load_dataset,
    validate_dataset,
    write_dataset,
    write_reports,
)
from .config import Config, ConfigError
from .config import load as load_config
from .registry import (
    RegistryError,
    ScorerSpec,
    dimensions,
    register_adapter,
    register_provider,
    register_reporter,
    register_scorer,
    register_scorer_module,
)
from .schemas import SCHEMA_VERSION
from .scorecard import (
    ASSEVRA_DOI,
    ASSEVRA_VERSION,
    DimensionResult,
    RowResult,
    Scorecard,
    wilson_ci,
)
from .validate import INVALID, LABELED, UNLABELED

__all__ = [
    "ASSEVRA_DOI",
    "ASSEVRA_VERSION",
    "SCHEMA_VERSION",
    "Config",
    "ConfigError",
    "DatasetError",
    "DimensionResult",
    "INVALID",
    "LABELED",
    "RegistryError",
    "RowResult",
    "Scorecard",
    "ScorerSpec",
    "UNLABELED",
    "dimensions",
    "evaluate",
    "load_config",
    "load_dataset",
    "register_adapter",
    "register_provider",
    "register_reporter",
    "register_scorer",
    "register_scorer_module",
    "validate_dataset",
    "wilson_ci",
    "write_dataset",
    "write_reports",
]

__version__ = ASSEVRA_VERSION
