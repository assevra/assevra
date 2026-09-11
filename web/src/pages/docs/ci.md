---
layout: ../../layouts/DocsLayout.astro
title: CI & the GitHub Action
description: Gate every release on evidence — including on forks, where there are no secrets.
eyebrow: Using it
---

## Gate a declared release suite

```yaml
name: agent-evaluation
on: [push, pull_request]
permissions:
  contents: read
jobs:
  evaluate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      # Run your agent and write evals/agent.jsonl before this step.
      - uses: assevra/assevra@v0.6.0
        with:
          dataset: evals/agent.jsonl
          config: .assevra.yml
          version: 0.6.0
          gate: true
```

Declare `gate.required_dimensions` in the config. Only a complete release PASS succeeds. Failed thresholds, missing required checks, invalid evaluator results, and missing required baselines block the build. The Action uploads available artifacts even on failure and writes a GitHub job summary.

## Cloud judges and forks

Install the provider extra and supply credentials when your scope includes model judgments:

```yaml
- uses: assevra/assevra@v0.6.0
  with:
    dataset: evals/agent.jsonl
    config: .assevra.yml
    extras: anthropic
    judge-provider: anthropic
    gate: true
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

Pin your judge model in the config and calibrate it against representative human labels. Forks without credentials cannot produce release PASS for required judged checks. Run an explicit self-test separately; do not expose secrets to untrusted pull-request code to obtain a passing report.

## Regression baselines

First record a baseline with `fail-on-regression: false`, inspect its evidence, and store the approved history as a reviewed artifact. On later runs, supply `history`, the chosen `baseline` label, and `fail-on-regression: true`.

A missing baseline, different labels, changed policy, or different judge makes a required comparison incomplete. Do not bootstrap an approved baseline silently from the first unreviewed run. Cache restoration alone is not baseline approval.

## Useful inputs and outputs

| Input                                          | Default / purpose                                             |
| ---------------------------------------------- | ------------------------------------------------------------- |
| `version`                                      | `0.6.0`                                                       |
| `gate`                                         | `true`; only complete release PASS succeeds                   |
| `dataset`, `config`                            | Dataset and policy paths                                      |
| `extras`                                       | Optional provider, detector, and signing dependencies         |
| `judge-provider`, `judge-model`, `judge-panel` | Judge configuration                                           |
| `history`, `baseline`, `label`                 | Explicit comparison provenance                                |
| `fail-on-regression`                           | `false`; enable after baseline review                         |
| `sign-key`, `attest`                           | Optional JSON signature and Agent Card                        |
| `skip-install`                                 | Use an already installed build, useful for local Action tests |

Outputs are `passed`, `scorecard`, `html`, and `summary`. Read `decision` in the JSON for the precise status. See [action.yml](https://github.com/assevra/assevra/blob/main/action.yml) for the full input contract.

## Run without GitHub

```bash
pip install assevra==0.6.0
assevra run --dataset evals/agent.jsonl --config .assevra.yml --out-dir evidence --gate
```

Exit 0 means the requested operation succeeded. A blocked gate returns 1; malformed input/configuration returns 2. Always inspect whether a scorecard was produced.
