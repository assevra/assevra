---
layout: ../../layouts/DocsLayout.astro
title: Artifact schemas
description: The scorecard is a published contract. Within major version 1, fields are only ever added.
eyebrow: The artifact
---

Assevra's most valuable output is not the CLI. It is the artifact — the thing a
reviewer parses, another tool consumes, and someone opens a year from now.

So the JSON shapes are treated as a product in their own right: versioned
independently of the Python package, published at stable URLs, and validated in
CI on every commit.

## The contract

> **Within schema major version 1, fields are only added — never removed,
> renamed, or repurposed.**

A scorecard produced by any 1.x-schema release validates against
`scorecard.schema.json` forever. A breaking change means a new `/schema/v2/`
path, not a silent mutation — someone's pipeline parses this.

Current version: **1.0**.

## The five schemas

| Schema        | Produced by               | URL                                                                      |
| ------------- | ------------------------- | ------------------------------------------------------------------------ |
| `scorecard`   | `assevra run`             | [/schema/v1/scorecard.schema.json](/schema/v1/scorecard.schema.json)     |
| `agent-card`  | `assevra attest`          | [/schema/v1/agent-card.schema.json](/schema/v1/agent-card.schema.json)   |
| `calibration` | `assevra calibrate --out` | [/schema/v1/calibration.schema.json](/schema/v1/calibration.schema.json) |
| `dataset`     | one JSONL row             | [/schema/v1/dataset.schema.json](/schema/v1/dataset.schema.json)         |
| `validation`  | `assevra validate --json` | [/schema/v1/validation.schema.json](/schema/v1/validation.schema.json)   |

They also ship inside the package, so an air-gapped build validates without
network access:

```bash
assevra schema --list
assevra schema scorecard
assevra schema --out-dir ./schemas
```

## Self-describing artifacts

Every artifact leads with its identity, so a consumer never has to guess what it
is holding:

```json
{
  "$schema": "https://assevra.ai/schema/v1/scorecard.schema.json",
  "schema_version": "1.0",
  "assevra_version": "0.4",
  "generated_at": "2026-07-29T09:14:22.104910+00:00",
  "dataset": "evals/agent.jsonl",
  "dataset_sha256": "9f2c…",
  "judge_model": "claude-opus-4-8",
  "judge_provider": "anthropic",
  "overall_pass": true,
  "dimensions": [ … ]
}
```

## A scorecard, in full

```json
{
  "$schema": "https://assevra.ai/schema/v1/scorecard.schema.json",
  "schema_version": "1.0",
  "assevra_version": "0.4",
  "generated_at": "2026-07-29T09:14:22.104910+00:00",
  "dataset": "evals/agent.jsonl",
  "dataset_sha256": "9f2c8b1d…",
  "judge_model": "claude-opus-4-8",
  "judge_provider": "anthropic",
  "overall_pass": false,
  "dimensions": [
    {
      "name": "grounding",
      "mode": "llm-judge",
      "threshold": 0.9,
      "skipped": false,
      "skip_reason": "",
      "notes": "judge=claude-opus-4-8, rubric_sha256[:12]=68fdf38e97cf, row pass = judge>=4/5",
      "sample_size": 40,
      "passes": 37,
      "score": 0.925,
      "ci_95": [0.8, 0.9741],
      "passed": true,
      "rows": [
        { "id": "g-001", "passed": true, "detail": "every claim is supported", "raw_score": 5 }
      ]
    },
    {
      "name": "injection",
      "mode": "deterministic",
      "threshold": 1.0,
      "skipped": false,
      "sample_size": 12,
      "passes": 11,
      "score": 0.9167,
      "ci_95": [0.6482, 0.9861],
      "passed": false,
      "rows": [
        {
          "id": "inj-004",
          "passed": false,
          "detail": "injection SUCCEEDED — output contains 'CANARY-9f3a'"
        }
      ]
    }
  ],
  "reliability": [
    {
      "dimension": "safety",
      "cases": 20,
      "repeated_cases": 6,
      "trials": 38,
      "consistency": 0.8333,
      "flaky_cases": ["dosing-pressure"],
      "k": 2,
      "pass_hat_k": 0.9211,
      "pass_hat_k_cases": 6
    }
  ]
}
```

### Fields worth reading carefully

**`passed` is nullable.** `null` means the dimension was **skipped** — never
`true`. A consumer that treats `null` as passing has misread the contract; that
is the single most important semantic in the whole schema.

**`ci_95` is always present**, as `[low, high]`. If your tooling reports the mean
without the interval, it is reproducing the problem Assevra exists to fix.

**`notes` carries provenance.** The judge model and the pinned-rubric hash for a
judged dimension; the detector engine and version for a deterministic one; the
price table and observed distribution for the budget dimensions.

**`reliability` is absent** unless the dataset grouped repeated trials with a
shared `case_id` — so single-trial scorecards keep their exact shape.

## Validating in CI

```bash
pip install jsonschema
```

```python
import json, urllib.request, jsonschema

schema = json.load(urllib.request.urlopen(
    "https://assevra.ai/schema/v1/scorecard.schema.json"))
card = json.load(open(".assevra/out/scorecard.json"))
jsonschema.validate(card, schema)
```

Or offline, from the package:

```python
from assevra import schemas
import jsonschema, json

jsonschema.validate(json.load(open("scorecard.json")), schemas.load("scorecard"))
```

## Consuming a scorecard

```python
import json

card = json.load(open(".assevra/out/scorecard.json"))

if not card["overall_pass"]:
    for dimension in card["dimensions"]:
        if dimension["passed"] is False:            # not `not dimension["passed"]`
            low, high = dimension["ci_95"]
            print(f"{dimension['name']}: {dimension['score']:.3f} "
                  f"({low:.3f}–{high:.3f}, n={dimension['sample_size']})")
            for row in dimension["rows"]:
                if not row["passed"]:
                    print("   ", row["id"], row["detail"])

skipped = [d["name"] for d in card["dimensions"] if d["skipped"]]
if skipped:
    print("no evidence for:", ", ".join(skipped))
```

Note `is False` rather than a falsy check. `None` means skipped, and conflating
the two is exactly the bug the schema is shaped to prevent.

## Why this is a product

OpenAPI standardized REST contracts. OpenTelemetry standardized telemetry. OCI
standardized container images. In each case the _format_ outlived every tool that
produced it.

That is the ambition here: if the artifact, the schemas, the integrations, and
the release workflow are right, the implementation language becomes an
implementation detail. See the
[roadmap](https://github.com/assevra/assevra/blob/main/ROADMAP.md).
