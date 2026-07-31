---
layout: ../../layouts/DocsLayout.astro
title: CLI reference
description: Twelve commands, and the exit codes your build pipeline can rely on.
eyebrow: Using it
---

```
assevra demo                     a full worked scorecard, no clone, no key
assevra scan --from traces.jsonl score raw traces — nothing labeled
assevra probe --out probes.jsonl a self-labeling adversarial suite
assevra capture -- python app.py run your agent and record what it did
assevra suggest / confirm        a model proposes labels; a human accepts them
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
```

## Exit codes

Stable, because build pipelines branch on them.

| Code | Meaning                                                                                                                                                      |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `0`  | Success.                                                                                                                                                     |
| `1`  | The gate failed — a dimension below threshold, a regression, an invalid dataset under `--strict`, an uncalibrated judge, or a failed signature verification. |
| `2`  | The command could not run — bad dataset, missing file, bad flag, unusable provider.                                                                          |

Almost every flag has a [`.assevra.yml`](/docs/configuration) equivalent, and
flags always win.

---

## assevra run

Score a dataset, gate the build, write the artifacts.

```bash
assevra run                                   # everything from .assevra.yml
assevra run --dataset evals/agent.jsonl --gate
assevra run --judge-panel claude-opus-4-8,gpt-4o --attest
assevra run --history .assevra/history.jsonl --label "$(git rev-parse --short HEAD)" \
            --fail-on-regression
```

| Flag                      | Meaning                                                                               |
| ------------------------- | ------------------------------------------------------------------------------------- |
| `--dataset PATH`          | The JSONL dataset. Defaults to `dataset:` in the config.                              |
| `--out-dir DIR`           | Where the artifacts land.                                                             |
| `--format {md,json,html}` | Repeatable. Default: all three.                                                       |
| `--judge-provider NAME`   | `auto`, `anthropic`, `openai`, `azure`, `bedrock`, `gemini`, `local`, `mock`, `none`. |
| `--judge-model NAME`      | Model, or Azure deployment / Bedrock model id.                                        |
| `--judge-panel M1,M2`     | A jury. Entries may be `provider:model`.                                              |
| `--pass-k N`              | _k_ for pass^k over `case_id` groups.                                                 |
| `--threshold DIM=VALUE`   | Repeatable per-dimension override.                                                    |
| `--gate`                  | Exit 1 when a scored dimension is below threshold.                                    |
| `--fail-on-regression`    | Exit 1 when a dimension regressed. Needs `--history`.                                 |
| `--sign KEYFILE`          | Sign the scorecard; writes `scorecard.sig.json`.                                      |
| `--attest`                | Also write the Agent Card.                                                            |
| `--history PATH`          | Append this run and compare against the baseline.                                     |
| `--label` / `--baseline`  | Tag this run; compare against a specific labeled run.                                 |
| `--strict`                | Fail when a row carries no answer key.                                                |
| `--no-validate`           | Skip pre-flight validation. Rarely what you want.                                     |
| `--quiet`                 | Do not print the full report.                                                         |

Inside GitHub Actions, `run` also writes a summary table and the failing rows to
the job summary — a red build should say what failed on the page the developer is
already looking at.

## assevra validate

The gate that runs _before_ evaluation.

```bash
assevra validate                       # dataset from .assevra.yml
assevra validate evals/agent.jsonl --strict
assevra validate --json --out report.json
```

| Flag         | Meaning                                |
| ------------ | -------------------------------------- |
| `--strict`   | Treat UNLABELED rows as failures.      |
| `--all`      | List every row, not just the problems. |
| `--json`     | Print the machine-readable report.     |
| `--out PATH` | Write the JSON report to a file.       |

Exits `1` when anything is INVALID (or, with `--strict`, UNLABELED). Every
message carries a stable code — `unknown_dimension`, `missing_answer_key`,
`duplicate_id`, `invalid_json` — and a suggested fix.

## assevra demo

A full worked example. No clone, no API key, no network.

```bash
assevra demo
assevra demo --out-dir /tmp/demo --provider mock   # exercise the judged path offline
```

Writes the HTML report, the JSON scorecard, the Markdown summary, the Agent Card,
the dataset it scored, and the `.assevra.yml` that produced all of it.

## assevra scan

Score raw traces on every dimension that needs no labeling. See
[Zero-label scoring](/docs/zero-label).

```bash
assevra scan --from traces.jsonl
assevra scan --from spans.json --tools tools.json --out-dir .assevra/scan
```

| Flag               | Meaning                                                                                     |
| ------------------ | ------------------------------------------------------------------------------------------- |
| `--from PATH`      | Captured traces, in any format `bootstrap` reads.                                           |
| `--tools PATH`     | The agent's own tool spec (OpenAI/Anthropic/MCP/schema map) — makes `tool_call` zero-label. |
| `--root DIR`       | Where to look for a tool spec when `--tools` is omitted.                                    |
| `--limit N`        | Cap the traces read.                                                                        |
| `--out-dir DIR`    | Also write the scorecard.                                                                   |
| `--judge-provider` | Unlocks `grounding`, which is judged.                                                       |
| `--gate`           | Exit non-zero if the scan fails.                                                            |

It reports what it scored, what it could not, and — for the dimensions that
encode intent — that it will not guess.

## assevra probe

Generate a self-labeling adversarial suite.

```bash
assevra probe --out probes.jsonl
assevra probe --out probes.jsonl --family injection --count 12 \
              --domain "You are a claims assistant for a health insurer."
```

| Flag            | Meaning                                                  |
| --------------- | -------------------------------------------------------- |
| `--out PATH`    | Where to write the probes.                               |
| `--family NAME` | `injection`, `pii-bait`, `over-refusal`; repeatable.     |
| `--count N`     | Probes per family (default: 6).                          |
| `--domain TEXT` | One line describing your agent, woven into each context. |

Canaries are seeded from the probe id, so a regenerated suite is byte-identical.

## assevra capture

Run your agent and record what it produced. The prompt arrives on **stdin**, the
answer comes back on **stdout**.

```bash
assevra capture --from probes.jsonl --out answered.jsonl -- python agent.py
assevra capture --inputs questions.txt --out traces.jsonl --repeat 3 -- python agent.py
```

| Flag            | Meaning                                                     |
| --------------- | ----------------------------------------------------------- |
| `--from PROBES` | Answer a probe suite, preserving its answer key.            |
| `--inputs FILE` | One input per line, or JSONL with `input`/`context`.        |
| `--out PATH`    | Where to write the captured rows.                           |
| `--repeat N`    | Trials per input under a shared `case_id` — unlocks pass^k. |
| `--timeout S`   | Seconds per call (default: 120).                            |

Every row gets a measured `latency_ms`, so the latency dimension turns on for
free. Assevra runs only the command you typed, in your shell.

## assevra suggest / confirm

A model drafts the answer key for the three dimensions that encode intent; a
human accepts it. **An unconfirmed proposal does not count as a label** — the
validator reports it as UNLABELED and `--strict` fails on it.

```bash
assevra suggest --dataset drafted.jsonl
assevra confirm --dataset drafted.jsonl        # y / n / s / q per row
```

| Flag             | Meaning                                                      |
| ---------------- | ------------------------------------------------------------ |
| `--dataset PATH` | The dataset to propose or review labels for.                 |
| `--out PATH`     | Write elsewhere instead of in place.                         |
| `--accept-all`   | `confirm` only: accept everything unreviewed. Loudly warned. |

## assevra init

Detect, then generate.

```bash
assevra init --dry-run                 # show the plan first
assevra init --from traces.jsonl
assevra init --from spans.json --dimension grounding --limit 200
```

Detects trace files (ranked by how much it could actually extract), your agent
framework, and which judge providers have credentials. Writes `.assevra.yml`, a
drafted dataset, a CI workflow, and `EVALUATION.md`. Existing files are kept
unless `--force`.

## assevra integrate

```bash
assevra integrate --list
assevra integrate langgraph
assevra integrate langfuse --out INTEGRATION.md
```

Targets: `otel`, `langgraph`, `langfuse`, `phoenix`, `openai-agents`,
`anthropic`. See [Integrations](/docs/integrations).

## assevra bootstrap

Draft a dataset from traces you already have.

```bash
assevra bootstrap --from traces.jsonl --out evals/agent.jsonl
assevra bootstrap --from openai_logs.jsonl --format openai --dimension safety
assevra bootstrap --from rows.csv --input-field question --output-field answer
```

Formats: `auto`, `generic`, `csv`, `openai`, `anthropic`, `otel`. It fills in what
was captured and leaves the answer key blank, with a per-row `_review` hint
saying exactly what to supply.

## assevra calibrate

```bash
assevra calibrate --dataset holdout.jsonl
assevra calibrate --dataset holdout.jsonl --judge-panel claude-opus-4-8,gpt-4o \
                  --out calibration.json
```

Reports accuracy, Cohen's κ, sensitivity and specificity, per dimension and
overall. Exits `1` below the κ bar. See [Judge calibration](/docs/calibration).

## assevra keygen / sign / verify

```bash
assevra keygen
assevra sign --scorecard scorecard.json --key assevra_ed25519_private.pem
assevra verify --scorecard scorecard.json --signature scorecard.sig.json \
               --public-key assevra_ed25519_public.txt
```

`verify` exits `1` on any mismatch. Pinning `--public-key` proves _authorship_,
not just integrity. See [Security & signing](/docs/security).

## assevra attest

```bash
assevra attest --scorecard scorecard.json
assevra attest --scorecard scorecard.json --signature scorecard.sig.json
```

Writes `agent-card.md` and `agent-card.json`. See
[Governance mapping](/docs/governance).

## assevra history

```bash
assevra history                              # path from .assevra.yml
assevra history --history .assevra/history.jsonl --limit 20
```

Shows the trend across recorded runs. When two runs share row IDs, the comparison
also reports a paired McNemar p-value per dimension.

## assevra schema

```bash
assevra schema --list
assevra schema scorecard
assevra schema --out-dir ./schemas
```

The published [artifact contracts](/docs/schemas).

## Global flags

| Flag            | Meaning                                                                          |
| --------------- | -------------------------------------------------------------------------------- |
| `--version`     | Print the version and exit.                                                      |
| `--config PATH` | Point at a specific `.assevra.yml`. `--config none` uses built-in defaults only. |
