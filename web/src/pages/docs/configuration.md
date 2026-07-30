---
layout: ../../layouts/DocsLayout.astro
title: Configuration
description: Every key in .assevra.yml, and the precedence rules that decide who wins.
eyebrow: Using it
---

A tool people adopt is a tool whose invocation they do not have to remember. The
long incantation — dataset, judge model, panel, thresholds, budgets, history
path, signing key — belongs in a file that lives next to the code, gets reviewed
in pull requests, and makes every run on every machine identical.

```bash
assevra run     # with .assevra.yml present, that is the whole command
```

## Where it looks

`.assevra.yml` (also `.assevra.yaml`, `assevra.yml`, `assevra.yaml`), found by
walking **up** from the current directory. Override with `--config PATH`.

`--config none` ignores any project config and uses built-in defaults — useful
when the config itself is the suspect.

## Precedence

Built-in defaults **<** config file **<** environment **<** explicit CLI flags.

Nothing in the config can silently override something a human typed. A
`store_true` flag left off does _not_ veto a config that turned the feature on —
so `gate: enabled: true` in the file still gates even when `--gate` is absent.

## A complete example

```yaml
version: 1

dataset: evals/agent.jsonl
out_dir: .assevra/out

judge:
  provider: anthropic # or auto | openai | azure | bedrock | gemini | local | mock | none
  model: claude-opus-4-8
  panel: [] # a jury; entries may be provider:model
  base_url: '' # for local / OpenAI-compatible endpoints
  api_key_env: '' # env var holding the key, for `local`
  max_tokens: 512
  temperature: 0.0

gate:
  enabled: true
  fail_on_regression: true

validate:
  on_run: true # refuse to score a structurally invalid dataset
  strict: false # also refuse rows with no answer key

thresholds:
  grounding: 0.90
  safety: 1.00
  pii: 1.00
  task_completion: 0.90
  tool_call: 0.95
  action_correctness: 0.95
  injection: 1.00
  cost: 0.95
  latency: 0.95

budgets:
  cost_usd: 0.02
  latency_ms: 4000
  price:
    input_per_mtok: 3.0
    output_per_mtok: 15.0

reliability:
  pass_k: 2

history:
  path: .assevra/history.jsonl
  label: ''
  baseline: ''

signing:
  key: '' # Ed25519 private key (PEM). Never commit it.

attest:
  enabled: true

reports:
  formats: [md, json, html]

calibration:
  label_field: human_label
  kappa_bar: 0.85
```

## The keys

### Top level

| Key       | Default | Meaning                                                                  |
| --------- | ------- | ------------------------------------------------------------------------ |
| `version` | `1`     | Config format version. An unsupported value is an error, not a warning.  |
| `dataset` | —       | The JSONL dataset to score. With this set, `assevra run` needs no flags. |
| `out_dir` | `.`     | Where the artifacts are written.                                         |

### `judge`

| Key           | Default          | Meaning                                                                                                                                                                        |
| ------------- | ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `provider`    | `auto`           | `auto` picks the first provider whose credentials are present. `none` disables the judge (dimensions are skipped, never failed). `mock` is the deterministic offline stand-in. |
| `model`       | provider default | Model name, or your Azure deployment / Bedrock model id.                                                                                                                       |
| `panel`       | `[]`             | Several models voting as a jury. Entries may name a provider inline: `[anthropic:claude-opus-4-8, openai:gpt-4o]`.                                                             |
| `base_url`    | —                | For `local` (Ollama, vLLM, LM Studio) or a custom gateway.                                                                                                                     |
| `api_key_env` | —                | Environment variable holding the key, for `local`.                                                                                                                             |
| `max_tokens`  | `512`            | Per judge call.                                                                                                                                                                |
| `temperature` | `0.0`            | Kept at zero: a judge that varies run to run undermines the whole point.                                                                                                       |

Credentials come from the environment, never the config file:
`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `AZURE_OPENAI_API_KEY` +
`AZURE_OPENAI_ENDPOINT`, `AWS_REGION`, `GEMINI_API_KEY`.

### `gate`

| Key                  | Default | Meaning                                                                              |
| -------------------- | ------- | ------------------------------------------------------------------------------------ |
| `enabled`            | `false` | Exit non-zero when a scored dimension is below threshold.                            |
| `fail_on_regression` | `false` | Exit non-zero when a dimension regressed against the baseline. Needs `history.path`. |

### `validate`

| Key      | Default | Meaning                                                                                                     |
| -------- | ------- | ----------------------------------------------------------------------------------------------------------- |
| `on_run` | `true`  | Validate before scoring. Leave this on: it costs milliseconds and prevents a confident, meaningless report. |
| `strict` | `false` | Treat UNLABELED rows as failures. Turn on once labeling is finished.                                        |

### `thresholds`

An **open map** of dimension name to pass rate — including dimensions you
registered yourself. Omit a dimension to keep its methodology default. An unknown
_top-level_ key is reported as a probable typo; keys under `thresholds` are not,
because third-party scorers legitimately add them.

### `budgets`

Feed the `cost` and `latency` dimensions. A per-row `cost_budget_usd` or
`latency_budget_ms` overrides the project-wide value.

`budgets.price` prices rows that recorded token `usage` rather than a dollar
figure. Without it, such a row is reported as unverifiable — and
`assevra validate` marks it UNLABELED rather than pretending it passed.

### `reliability`

`pass_k` sets _k_ for pass^k over repeated trials sharing a `case_id`. With three
trials per case, `k: 2` asks the useful question: what is the chance two
independent attempts both succeed?

### `history`

`path` enables run-to-run tracking and regression detection. `label` tags a run
(a version or git SHA); `baseline` compares against a specific earlier labeled
run instead of the immediately previous one. The file is plain JSONL — commit it,
or cache and restore it in CI.

### `signing`

`key` is a path to an Ed25519 private key. Never commit one; point it at a CI
secret file. See [Security & signing](/docs/security).

### `reports`

`formats` selects which of `md`, `json`, `html` are written. Custom reporters
registered through the SDK can be named here too.

## Typos are reported, not ignored

An unrecognized top-level key produces a warning naming the key. A silently
dropped `treshold: 0.9` is worse than an error, because the run continues and the
gate you thought you configured is not there.

## Dependency-free by design

The parser handles the subset a config file needs — nested mappings, block and
inline lists, quoted and bare scalars, comments. PyYAML is used when it happens
to be installed; it is never required. Asking a team to add a dependency before
they can write a config would undo the point of a dependency-free core.

Anything outside the supported subset raises an error **with a line number**
rather than guessing.

## Generating one

```bash
assevra init          # writes a commented .assevra.yml suited to your project
assevra init --dry-run   # show the plan first
```
