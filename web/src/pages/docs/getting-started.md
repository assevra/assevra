---
layout: ../../layouts/DocsLayout.astro
title: Getting started
description: From pip install to a scorecard that gates your build — in four commands.
eyebrow: Start here
---

## 1. Run a complete local example

```bash
pip install assevra==0.6.0
python -m assevra.reference --out-dir reference-output
```

Python 3.10+ is required. Open `reference-output/before/scorecard.html` and `reference-output/after/scorecard.html`.

The example runs a local refund workflow against eligible, unauthorized, over-limit, and boundary cases, three times each. It checks action sequences, tool contracts, final order state, and supported PII patterns. The buggy workflow fails; the repaired workflow passes the same scope. This is synthetic fixture evidence, not a production-model benchmark.

## 2. Read the finding and verify the change

The JSON `findings` array carries case identity, available trace identity, severity, evidence, suggested actions, and verification steps. The HTML report presents the same guidance. Suggestions require review; they do not patch your agent.

```bash
assevra run --dataset reference-output/after/cases.jsonl \
  --config reference-output/after/policy.json --out-dir evidence --gate
```

The command exits successfully only for a complete release PASS. Open `evidence/scorecard.html` to inspect the scope and uncertainty.

## 3. Bring your own runs

```bash
assevra integrate --list
assevra integrate langgraph
assevra scan --from traces.jsonl --tools tools.json --out-dir triage
assevra init --from traces.jsonl
```

The scan is TRIAGE. Review the generated dataset and fill in answer keys. Add explicit business assertions such as the expected final state; substring completion checks alone do not establish a successful workflow.

You can also use `evaluate(records=...)` in Python, or `assevra capture --inputs inputs.txt --out traces.jsonl -- python your_agent.py` to execute a command you supply. Capture errors are retained, and a completion manifest accompanies the output.

## 4. Declare your release scope

```yaml
gate:
  enabled: true
  purpose: release
  required_dimensions: [action_correctness, tool_call, pii]
  fail_on_regression: false
```

Every included dimension must complete. `required_dimensions` also detects a dimension whose rows are entirely absent. Without an explicit list, the recorded scope is the dimensions present in the dataset. Choose thresholds and representative sample sizes for your use case.

Release evaluations validate strictly even when `--no-validate` is passed. Missing judges or invalid evaluator output yield INCOMPLETE. Mock judging yields SELF_TEST. Neither qualifies for release.

## 5. Add CI and a reviewed baseline

Follow [CI & the GitHub Action](/docs/ci). Record an initial baseline with regression blocking disabled, review it, then select that baseline and enable required comparison. If its suite, labels, policy, or judge differs, collect and approve a new baseline.

Installation downloads packages. Deterministic evaluation runs locally afterward; cloud model judges receive the fields in their evaluation prompts. Review [security and data flow](/docs/security).
