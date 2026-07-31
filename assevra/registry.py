"""
The extension point: how Assevra learns about scorers, reporters, adapters, and
judge providers.

Everything Assevra can do is registered here rather than hard-coded in the CLI.
That is what makes the project extensible without a fork: a team with a domain
metric of their own — "did the agent cite a policy id?", "did it stay inside the
tenant's data?" — writes a scorer, registers it, and it appears in the scorecard,
the validator, the config, and the CI gate with no changes to Assevra itself.

Four registries, one shape:

``scorers``      dimension name -> :class:`ScorerSpec` (how to score, and what a
                 labeled row for it looks like)
``reporters``    format name -> callable rendering a scorecard to text
``adapters``     trace format name -> callable extracting interactions
``providers``    judge provider name -> factory returning a judge client

A scorer is registered from a *module* that declares a handful of module-level
constants. Keeping the declaration in the scorer module (rather than in a central
table) means one file fully describes a dimension: how it scores, what fields
label it, and what to tell a user whose row is missing the answer key.

    DIMENSION          = "policy_citation"
    MODE               = "deterministic"
    DIMENSION_THRESHOLD = 0.95
    SUMMARY            = "Did the answer cite the governing policy id?"
    ANSWER_KEY         = ("expected_policy_id",)   # any one of these labels a row
    REQUIRES           = ("agent_output",)         # structurally required
    LABEL_HINT         = "Set expected_policy_id to the id the answer must cite."
    def score(rows, judge=None, options=None) -> DimensionResult: ...

Then, once, anywhere before you run:

    from assevra import register_scorer_module
    import my_scorers.policy_citation as m
    register_scorer_module(m)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional


class RegistryError(Exception):
    """Raised on a bad or conflicting registration."""


@dataclass
class ScorerSpec:
    """Everything Assevra needs to know about one reliability dimension."""

    dimension: str
    mode: str
    threshold: float
    score: Callable[..., Any]
    summary: str = ""
    # Any ONE of these fields, present and non-empty, means the row carries an
    # answer key. An empty tuple means the dimension is self-labeling (the PII
    # detector, for instance, needs no human verdict to know what a leak is).
    answer_key: tuple[str, ...] = ()
    # Fields without which the row cannot be scored at all.
    requires: tuple[str, ...] = ("agent_output",)
    label_hint: str = ""
    # Optional extra per-row checks: (row, options) -> list[(level, code, message, field, fix)]
    validate_row: Optional[Callable[..., list]] = None
    # Optional: decide labeled-ness with full knowledge of the config (the cost
    # and latency dimensions can be labeled by a project-wide budget rather than
    # a per-row field).
    is_labeled: Optional[Callable[..., bool]] = None
    # Optional: (interaction, options) -> dict of extra row fields, or None.
    # A scorer implements this when a *raw captured trace* can be scored with no
    # human labeling at all — either because the dimension is self-labeling (a
    # PII detector defines its own failure), because the answer key is already in
    # the trace (grounding's context), or because the policy lives in the config
    # rather than the row (the cost and latency budgets). This is what
    # `assevra scan` runs on.
    autolabel: Optional[Callable[..., Optional[dict]]] = None
    autolabel_note: str = ""
    builtin: bool = False

    @property
    def zero_label(self) -> bool:
        return self.autolabel is not None

    @property
    def needs_judge(self) -> bool:
        return self.mode == "llm-judge"


_SCORERS: dict[str, ScorerSpec] = {}
_REPORTERS: dict[str, Callable[..., str]] = {}
_ADAPTERS: dict[str, Callable[..., Any]] = {}
_PROVIDERS: dict[str, Callable[..., Any]] = {}

# Report dimensions in a stable, meaningful order: the four founding dimensions
# first (in methodology order), then agent-behaviour dimensions, then budgets.
# Anything registered later sorts after, alphabetically, so a third-party scorer
# never reshuffles an existing report.
_ORDER = [
    "grounding",
    "safety",
    "pii",
    "task_completion",
    "tool_call",
    "action_correctness",
    "injection",
    "cost",
    "latency",
]


# --------------------------------------------------------------------------- #
# Scorers                                                                      #
# --------------------------------------------------------------------------- #
def register_scorer(spec: ScorerSpec, replace: bool = False) -> ScorerSpec:
    if spec.dimension in _SCORERS and not replace:
        raise RegistryError(
            f"dimension {spec.dimension!r} is already registered; "
            "pass replace=True to override it deliberately"
        )
    if spec.mode not in ("deterministic", "llm-judge"):
        raise RegistryError(
            f"scorer {spec.dimension!r}: mode must be 'deterministic' or 'llm-judge'"
        )
    if not callable(spec.score):
        raise RegistryError(f"scorer {spec.dimension!r}: score must be callable")
    _SCORERS[spec.dimension] = spec
    return spec


def register_scorer_module(module: Any, replace: bool = False, builtin: bool = False) -> ScorerSpec:
    """Register a scorer from a module declaring the constants above."""
    try:
        spec = ScorerSpec(
            dimension=module.DIMENSION,
            mode=getattr(module, "MODE", "deterministic"),
            threshold=float(module.DIMENSION_THRESHOLD),
            score=module.score,
            summary=getattr(module, "SUMMARY", ""),
            answer_key=tuple(getattr(module, "ANSWER_KEY", ())),
            requires=tuple(getattr(module, "REQUIRES", ("agent_output",))),
            label_hint=getattr(module, "LABEL_HINT", ""),
            validate_row=getattr(module, "validate_row", None),
            is_labeled=getattr(module, "is_labeled", None),
            autolabel=getattr(module, "autolabel", None),
            autolabel_note=getattr(module, "AUTOLABEL_NOTE", ""),
            builtin=builtin,
        )
    except AttributeError as exc:
        raise RegistryError(f"{module!r} is not a valid scorer module: {exc}") from exc
    return register_scorer(spec, replace=replace)


def get_scorer(dimension: str) -> ScorerSpec:
    try:
        return _SCORERS[dimension]
    except KeyError:
        raise RegistryError(
            f"unknown dimension {dimension!r}; known dimensions: {', '.join(dimensions())}"
        ) from None


def has_scorer(dimension: str) -> bool:
    return dimension in _SCORERS


def dimensions() -> list[str]:
    """All registered dimensions, in report order."""
    known = set(_SCORERS)
    ordered = [d for d in _ORDER if d in known]
    return ordered + sorted(known - set(ordered))


def scorers() -> dict[str, ScorerSpec]:
    return dict(_SCORERS)


# --------------------------------------------------------------------------- #
# Reporters / adapters / providers                                             #
# --------------------------------------------------------------------------- #
def register_reporter(name: str, render: Callable[..., str], replace: bool = False) -> None:
    """A reporter turns a Scorecard into text. Built-ins: md, json, html."""
    if name in _REPORTERS and not replace:
        raise RegistryError(f"reporter {name!r} is already registered")
    _REPORTERS[name] = render


def get_reporter(name: str) -> Callable[..., str]:
    try:
        return _REPORTERS[name]
    except KeyError:
        raise RegistryError(
            f"unknown report format {name!r}; known: {', '.join(sorted(_REPORTERS))}"
        ) from None


def reporters() -> dict[str, Callable[..., str]]:
    return dict(_REPORTERS)


def register_adapter(name: str, extract: Callable[..., Any], replace: bool = False) -> None:
    """A trace adapter turns records from some tool into Assevra interactions."""
    if name in _ADAPTERS and not replace:
        raise RegistryError(f"adapter {name!r} is already registered")
    _ADAPTERS[name] = extract


def get_adapter(name: str) -> Callable[..., Any]:
    try:
        return _ADAPTERS[name]
    except KeyError:
        raise RegistryError(
            f"unknown trace format {name!r}; known: {', '.join(sorted(_ADAPTERS))}"
        ) from None


def adapters() -> dict[str, Callable[..., Any]]:
    return dict(_ADAPTERS)


def register_provider(name: str, factory: Callable[..., Any], replace: bool = False) -> None:
    """A judge provider builds a client exposing ``score_json(prompt) -> dict``."""
    if name in _PROVIDERS and not replace:
        raise RegistryError(f"judge provider {name!r} is already registered")
    _PROVIDERS[name] = factory


def get_provider(name: str) -> Callable[..., Any]:
    try:
        return _PROVIDERS[name]
    except KeyError:
        raise RegistryError(
            f"unknown judge provider {name!r}; known: {', '.join(sorted(_PROVIDERS))}"
        ) from None


def providers() -> dict[str, Callable[..., Any]]:
    return dict(_PROVIDERS)
