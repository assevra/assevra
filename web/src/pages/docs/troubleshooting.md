---
layout: ../../layouts/DocsLayout.astro
title: Troubleshooting
description: Specific symptoms, and what each one actually means.
eyebrow: Help
---

Before anything else, two commands answer most questions:

```bash
assevra demo --provider mock     # does the engine work at all?
assevra validate                 # is my dataset the problem?
```

If the demo works and your dataset does not, the validator will name the row.

---

## Scores and verdicts

### A dimension says SKIPPED

It was not measured, so it contributed no evidence — and it is not a pass.

- **grounding / safety** — no judge is configured. Set `judge.provider` and its
  credentials, or use `--judge-provider mock` to exercise the path offline.
- **injection** — no row declared a `canary` and no judge is available. Add a
  canary (preferred: it is deterministic and free) or configure a judge.

### The overall verdict is FAIL but every dimension passed

Every dimension was skipped. A run with no scored dimensions is not a pass, by
design.

### A score is 1.000 but the interval is wide

That is the interval doing its job. `1.000` on three rows carries a 95% interval
of roughly `0.439–1.000` — three rows cannot distinguish a perfect agent from a
mostly-fine one. Add rows.

### A dimension I expected is missing entirely

It only appears when the dataset contains at least one row for it. Check the
`dimension` field on your rows, and run `assevra validate` — the per-dimension
table shows exactly what was found.

### A row passes but I know it is wrong

Look at the detail text. If it says **"nothing to verify"** or **"no contract
declared"**, the row is unlabeled: it has no answer key, so nothing was checked.

```bash
assevra validate --strict     # makes exactly this case fail
```

### The score changed and I did not change the agent

Five things determine a number: the code version, the dataset, the judge model,
the judge rubric, and the thresholds. Check `assevra_version` and `judge_model`
in the two scorecards, and diff the dataset. A provider silently updating a model
alias behind a name is the usual culprit — pin the model explicitly.

---

## Datasets

### `unknown dimension`

The `dimension` field must be a registered dimension. `assevra validate` lists
the valid names in the error, and a custom scorer must be registered before the
dataset referencing it is scored.

### `duplicate_id`

Row ids must be unique. To group repeated trials of the _same_ input, use
`case_id` — that is what enables pass^k and the flaky-case report.

### `missing_field: agent_output is required`

Assevra scores outputs you already captured. A row with no `agent_output` has
nothing to grade. If you meant to leave a placeholder, remove the row instead —
an empty one produces a meaningless verdict.

### `invalid_json` on a line

One JSON object per line, no trailing commas, no comments. The error carries the
line and column. `assevra validate` reports **every** bad line at once, so one
fix-and-rerun cycle is usually enough.

### Bootstrap extracted nothing

```
no interactions could be extracted from traces.jsonl as format 'generic'
```

Either the format was detected wrongly or the field names are non-standard:

```bash
assevra bootstrap --from traces.jsonl --format openai
assevra bootstrap --from traces.jsonl --input-field question --output-field answer
```

### A cost row says "cost not measurable"

The row recorded `usage` but no price table is configured. Add one:

```yaml
budgets:
  price:
    input_per_mtok: 3.0
    output_per_mtok: 15.0
```

…or record `cost_usd` directly on the row. The row is reported as UNLABELED, not
failed — it is unverifiable, not wrong.

---

## Detectors and judges

### PII notes say `engine=regex-fallback`

Only the floor entities (SSN, credit card, bank number, IBAN, passport, phone)
are being detected. For the full detector:

```bash
pip install "assevra[pii]"
python -m spacy download en_core_web_lg
```

The regex floor **always** runs, even with Presidio installed, so the
zero-tolerance guarantee never depends on an optional package.

### A `negative-example` row fails

That row is deliberately bad and passes only when its leak is **caught**. A
failure means the detector regressed — or that the regex fallback cannot see that
entity and you need the `pii` extra.

### `the 'openai' judge provider needs the 'openai' package`

Install the extra for the provider you chose: `pip install "assevra[openai]"`
(or `[anthropic]`, `[bedrock]`, `[gemini]`). The `local` and `mock` providers
need nothing.

### `the 'bedrock' provider has no default model`

Azure deployments and Bedrock model ids are deployment-specific, so Assevra will
not guess. Set `judge.model` in the config or pass `--judge-model`.

### `local judge endpoint … is unreachable`

Check the endpoint is running and `judge.base_url` points at the API root — for
Ollama that is `http://localhost:11434/v1`, including the `/v1`.

### Judge output is "unparseable"

The model wrapped its verdict in prose or a fence that could not be recovered.
Assevra already strips code fences and extracts the outer JSON object, so
persistent parse errors usually mean a very small model. Try a larger one, or a
panel — a panel tolerates one bad panelist.

### Calibration κ is low

Read the disagreements, not the number. Often the _rubric_ is ambiguous rather
than the judge being wrong. Then: try a panel spanning vendors, try a stronger
model, or reconsider whether the property needs a judge at all. See
[Judge calibration](/docs/calibration#when-calibration-fails).

---

## CI

### It passes locally and fails in CI (or the reverse)

Almost always the config or the judge differs. Print both:

```bash
assevra --version
assevra run --quiet && head -20 .assevra/out/scorecard.json
```

Compare `assevra_version`, `judge_model`, `judge_provider`, and `dataset_sha256`.
`--config none` runs with built-in defaults only, which isolates a config
problem quickly.

### The gate does not fail the build

`--gate` must be set, or `gate.enabled: true` in the config. Without it the
scorecard is written and the command exits `0`.

### `--fail-on-regression` never fires

It needs a history file with a prior run to compare against. In CI, cache and
restore `.assevra/history.jsonl` — otherwise every run is the first run.

### The job summary is empty

Assevra writes it only when `GITHUB_STEP_SUMMARY` is set (i.e. inside GitHub
Actions), and the Action's `comment: true` input controls it.

### Fork pull requests have no secrets

That is intended. Without a key the judged dimensions are `SKIPPED` and the
deterministic ones still gate — a real signal instead of a red build.

---

## Signing

### `signing requires the 'cryptography' package`

```bash
pip install "assevra[sign]"
```

### `verify` reports a content-hash mismatch

The `scorecard.json` differs from what was signed. Only _content_ is hashed, so
re-indentation is fine — an actual value changed. Re-sign, or verify the exact
file that was signed.

### `verify` fails with a pinned public key

The scorecard was signed by a different key. That is the check working: pinning is
what turns "unaltered" into "unaltered, and signed by them".

---

## Still stuck

- [SUPPORT.md](https://github.com/assevra/assevra/blob/main/SUPPORT.md) — how to
  ask, and what makes an issue fast to resolve
- [Discussions](https://github.com/assevra/assevra/discussions) — methodology and
  "how should I model this?" questions
- [Open an issue](https://github.com/assevra/assevra/issues/new/choose) — include
  the command, its full output, `assevra --version`, and a **minimal synthetic**
  dataset that reproduces it
