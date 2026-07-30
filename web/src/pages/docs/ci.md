---
layout: ../../layouts/DocsLayout.astro
title: CI & the GitHub Action
description: Gate every release on evidence — including on forks, where there are no secrets.
eyebrow: Using it
---

An evaluation that runs when someone remembers to run it is not a gate. Put it in
the build.

## The GitHub Action

```yaml
- uses: assevra/assevra@v1
  with:
    dataset: evals/agent.jsonl
    gate: true
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

That installs Assevra, validates the dataset, scores it, writes a summary table
and the failing rows into the **job summary**, uploads the artifacts, and fails
the build when a dimension drops below its threshold.

The `env:` block is optional. Without it, the deterministic dimensions still run
and the judged ones report as `SKIPPED` — never as passing. That is what lets a
pull request from a fork get a real gate instead of a red build.

### Inputs

| Input                | Default        | Meaning                                                                       |
| -------------------- | -------------- | ----------------------------------------------------------------------------- |
| `dataset`            | from config    | The labeled JSONL dataset.                                                    |
| `config`             | discovered     | Path to `.assevra.yml`.                                                       |
| `out-dir`            | `.assevra/out` | Where the artifacts land.                                                     |
| `gate`               | `true`         | Fail when a scored dimension is below threshold.                              |
| `strict`             | `false`        | Also fail when a row carries no answer key.                                   |
| `fail-on-regression` | `false`        | Fail on a regression against the baseline.                                    |
| `history`            | —              | Run-history JSONL, enabling regression detection.                             |
| `label` / `baseline` | —              | Tag this run in the history; compare against a specific labeled run.          |
| `judge-provider`     | `auto`         | `anthropic`, `openai`, `azure`, `bedrock`, `gemini`, `local`, `mock`, `none`. |
| `judge-model`        | —              | Model or deployment name.                                                     |
| `judge-panel`        | —              | Comma-separated jury; entries may be `provider:model`.                        |
| `attest`             | `false`        | Also emit the Agent Card.                                                     |
| `sign-key`           | —              | Ed25519 private key path. Use a secret file.                                  |
| `extras`             | —              | pip extras, e.g. `pii,anthropic,sign`.                                        |
| `version`            | latest         | Pin an Assevra version.                                                       |
| `skip-install`       | `false`        | Assume `assevra` is already on PATH.                                          |
| `python-version`     | `3.12`         | Python to run on.                                                             |
| `comment`            | `true`         | Write the summary to the job summary.                                         |
| `upload-artifact`    | `true`         | Upload the artifacts to the run.                                              |

### Outputs

| Output      | Example                                          |
| ----------- | ------------------------------------------------ |
| `passed`    | `true`                                           |
| `scorecard` | `.assevra/out/scorecard.json`                    |
| `html`      | `.assevra/out/scorecard.html`                    |
| `summary`   | `7/8 dimensions passed over 214 rows, 1 skipped` |

```yaml
- id: assevra
  uses: assevra/assevra@v1
  with: { dataset: evals/agent.jsonl, gate: true }

- if: always()
  run: echo "${{ steps.assevra.outputs.summary }}"
```

## A complete workflow

```yaml
name: assevra

on:
  pull_request:
  push:
    branches: [main]

jobs:
  reliability:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4

      # Keep the history across runs so regressions are measured against a real
      # baseline rather than a vibe.
      - uses: actions/cache@v4
        with:
          path: .assevra/history.jsonl
          key: assevra-history-${{ github.ref_name }}-${{ github.run_id }}
          restore-keys: assevra-history-${{ github.ref_name }}-

      - uses: assevra/assevra@v1
        with:
          dataset: evals/agent.jsonl
          extras: pii
          gate: true
          strict: true
          history: .assevra/history.jsonl
          fail-on-regression: true
          attest: true
          label: ${{ github.sha }}
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

## Without the Action

Assevra is a normal Python package; nothing here is GitHub-specific.

```bash
pip install assevra
assevra validate --strict
assevra run --gate
```

GitLab CI:

```yaml
reliability:
  image: python:3.12
  script:
    - pip install assevra
    - assevra validate --strict
    - assevra run --gate
  artifacts:
    when: always
    paths: [.assevra/out/]
```

A pre-commit hook, for the deterministic dimensions only — they are fast and free:

```yaml
- repo: local
  hooks:
    - id: assevra
      name: assevra reliability gate
      entry: assevra run --gate --judge-provider none --quiet
      language: system
      pass_filenames: false
```

## Regression detection

`--history` records every run and compares against the baseline. A move is
flagged only when it falls **outside the previous confidence interval** or crosses
a threshold, so ordinary noise never triggers a false alarm. When two runs share
row IDs, the comparison also reports a paired McNemar p-value per dimension.

```bash
assevra run --history .assevra/history.jsonl --label "$(git rev-parse --short HEAD)" \
            --fail-on-regression
```

The history file is plain JSONL. Commit it, or cache and restore it in CI.

## Gating on judge calibration

A judged dimension is only trustworthy while its judge still agrees with humans —
and a model version bump can silently break that. Gate on it:

```yaml
- run: assevra calibrate --dataset evals/holdout.jsonl --out calibration.json
- uses: actions/upload-artifact@v4
  with: { name: calibration, path: calibration.json }
```

`calibrate` exits non-zero below the κ bar.

## Two things worth doing

**Publish the HTML report.** It is self-contained with inline CSS and no external
assets, so it can be uploaded as an artifact, attached to a release, or served
from a static host with no build step. A reviewer who can open the report is a
reviewer who does not have to ask you for it.

**Sign the release scorecard.** In CI, write the key from a secret to a file,
point `sign-key` at it, and publish the public key. A scorecard attached to a
release that anyone can verify is evidence; one that anyone could have edited is
a screenshot. See [Security & signing](/docs/security).
