---
layout: ../../layouts/DocsLayout.astro
title: Python SDK
description: Assevra as a library — and how to add a dimension of your own without forking it.
eyebrow: Using it
---

The CLI is the right interface for CI. It is the wrong interface for the place
most evaluation actually happens: inside a notebook, a pytest suite, or the
harness that just finished running the agent and is holding the results in
memory.

```python
from assevra import evaluate

result = evaluate(records=rows)
print(result.overall_pass)
print(result.dimension("grounding").score)
```

`records` are the same objects a dataset file holds, so anything you can put in a
`.jsonl` you can pass as a list of dicts, and vice versa.

## evaluate

```python
def evaluate(
    records=None,          # list[dict] — the rows to score
    dataset=None,          # or a path to a .jsonl (exactly one of the two)
    config=None,           # a Config, a path, a dict, or None to auto-discover
    judge=None,            # a prebuilt judge/panel; else built from config
    judge_provider=None,
    judge_model=None,
    judge_panel=None,
    pass_k=None,
    thresholds=None,       # {"grounding": 0.95}
    options=None,          # extra options handed to every scorer
    validate=None,         # pre-flight validation (default: on)
    strict=None,           # also refuse rows with no answer key
) -> Scorecard
```

**Validation runs first, and an invalid dataset raises.** In a notebook it is even
easier than in CI to score a typo and believe the number, so `evaluate` refuses
rather than returning a confident scorecard built on rows it could not
understand:

```python
from assevra import DatasetError, evaluate

try:
    result = evaluate(dataset="evals/agent.jsonl")
except DatasetError as exc:
    print(exc)
    print(exc.report.count("INVALID"), "unusable rows")
```

Pass `validate=False` if you genuinely want the old behaviour.

## Scorecard

```python
result.overall_pass                  # bool — a conjunction over scored dimensions
result.dimensions                    # list[DimensionResult]
result.dimension("pii")              # one by name, or None
result.failures()                    # [(dimension_name, RowResult), ...]
result.reliability                   # pass^k / consistency, when case_id groups exist

result.to_dict()                     # schema-governed JSON
result.to_json()
result.render_markdown()
result.render_html()                 # self-contained, inline CSS, no assets
```

Each `DimensionResult` carries `name`, `mode`, `threshold`, `skipped`,
`skip_reason`, `notes`, `n`, `passes`, `score`, `ci` (the 95% Wilson interval),
`passed`, and `rows`.

`passed` is `None` when the dimension was skipped — never `True`. A missing
measurement is not a passing one, in the API as much as in the report.

## In a test suite

Assevra composes with pytest without a plugin:

```python
import pytest
from assevra import evaluate

@pytest.fixture(scope="session")
def scorecard():
    return evaluate(dataset="evals/agent.jsonl")

def test_no_pii_leaks(scorecard):
    pii = scorecard.dimension("pii")
    assert pii.passed, [r.detail for r in pii.rows if not r.passed]

def test_grounding_meets_threshold(scorecard):
    grounding = scorecard.dimension("grounding")
    if grounding.skipped:
        pytest.skip(grounding.skip_reason)   # skipped is not passed
    assert grounding.score >= grounding.threshold

def test_no_regression_in_the_lower_bound(scorecard):
    # The honest assertion on a small dataset is on the interval, not the mean.
    low, _high = scorecard.dimension("task_completion").ci
    assert low >= 0.75
```

## Writing reports

```python
from assevra import write_reports

paths = write_reports(result, "out/", formats=("md", "json", "html"))
```

## Loading and writing datasets

```python
from assevra import load_dataset, write_dataset, validate_dataset

rows = load_dataset("evals/agent.jsonl")
report = validate_dataset("evals/agent.jsonl", strict=True)
print(report.counts if False else report.to_dict()["counts"])
write_dataset(rows, "evals/agent.jsonl")
```

## Configuration from Python

```python
from assevra import load_config

cfg = load_config()                   # walks up from the cwd
cfg = load_config("path/.assevra.yml")
cfg.get("judge.provider")
cfg.threshold("grounding")

result = evaluate(records=rows, config={"thresholds": {"grounding": 0.95}})
```

A dict config is merged over the built-in defaults and never reads a file, which
makes it the right choice in tests.

<h2 id="extending">Extending</h2>

Four registries, one shape. A team's domain metric should be a first-class
dimension, not a fork.

### A scorer

Declare a module with a handful of constants and register it. That declaration is
all Assevra needs to wire it into the scorecard, the validator, the config, and
the CI gate.

```python
# my_evals/policy_citation.py
from assevra import DimensionResult, RowResult

DIMENSION = "policy_citation"
MODE = "deterministic"
DIMENSION_THRESHOLD = 1.00
SUMMARY = "Did the answer cite the governing policy id?"
ANSWER_KEY = ("expected_policy_id",)     # any one of these labels a row
REQUIRES = ("agent_output",)             # structurally required
LABEL_HINT = "Set expected_policy_id to the id the answer must cite."

def score(rows, judge=None, options=None) -> DimensionResult:
    result = DimensionResult(name=DIMENSION, mode=MODE, threshold=DIMENSION_THRESHOLD)
    result.notes = "pass = the expected policy id appears verbatim in the output."
    for row in rows:
        wanted = row.get("expected_policy_id", "")
        result.rows.append(
            RowResult(
                row_id=row["id"],
                passed=wanted in row.get("agent_output", ""),
                detail=f"expected citation {wanted!r}",
            )
        )
    return result
```

```python
import assevra
import my_evals.policy_citation as m

assevra.register_scorer_module(m)
```

From that point `dimension: policy_citation` is valid in a dataset, the validator
knows what a labeled row looks like and what to tell someone who has not written
one, `thresholds.policy_citation` works in `.assevra.yml`, and the dimension
gates like any other.

Optional hooks: `validate_row(row, options)` for extra structural checks, and
`is_labeled(row, options)` when labeling depends on the config (as it does for
the cost and latency budgets).

> A new dimension should meet the same bar as a built-in one: a definition, an
> explicit scoring method, a stated threshold, a reported interval, and a stated
> limit. See [GOVERNANCE.md](https://github.com/assevra/assevra/blob/main/GOVERNANCE.md#the-methodology-bar).

### A reporter

```python
import assevra

def render_slack(scorecard) -> str:
    mark = "✅" if scorecard.overall_pass else "❌"
    lines = [f"{mark} Assevra v{scorecard.version}"]
    for d in scorecard.dimensions:
        if d.skipped:
            lines.append(f"• {d.name}: skipped")
            continue
        low, high = d.ci
        lines.append(f"• {d.name}: {d.score:.3f} ({low:.2f}–{high:.2f}, n={d.n})")
    return "\n".join(lines)

assevra.register_reporter("slack", render_slack)
```

### A trace adapter

```python
import assevra

def extract(record, *_args):
    return {
        "input": record["question"],
        "agent_output": record["final_answer"],
        "context": "\n".join(record.get("retrieved", [])),
    }

assevra.register_adapter("our-house-format", extract)
```

### A judge provider

A provider is a function from prompt to text. Everything above it — rubrics,
panels, calibration — is vendor-agnostic.

```python
import assevra

def my_provider(model: str, opts: dict):
    client = MyGateway(base_url=opts.get("base_url"))
    return lambda prompt: client.complete(model=model, prompt=prompt)

assevra.register_provider("my-gateway", my_provider)
```

Then `judge: {provider: my-gateway, model: whatever}`.

## Everything exported

```python
from assevra import (
    evaluate, load_dataset, write_dataset, validate_dataset, write_reports,
    Scorecard, DimensionResult, RowResult, wilson_ci,
    Config, load_config, ConfigError, DatasetError, RegistryError,
    register_scorer, register_scorer_module, register_reporter,
    register_adapter, register_provider, dimensions,
    LABELED, UNLABELED, INVALID,
    ASSEVRA_VERSION, ASSEVRA_DOI, SCHEMA_VERSION,
)
```
