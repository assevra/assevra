# Changelog

All notable changes to Assevra are recorded here. The project follows
semantic-ish versioning; the reported "measured with Assevra vX.Y" number is
bumped whenever a scorer or rubric change could change a reported score.

## [0.5.0] — 2026-07-31

The zero-label release. 0.4 made Assevra adoptable in about five minutes of
*plumbing* — and then asked for an afternoon of labeling before the numbers meant
anything. 0.5 attacks the afternoon, on a single observation: **six of the nine
dimensions never needed a human.**

### Added

- **`assevra scan --from traces.jsonl`** — a scorecard from raw traces with
  nothing labeled. It scores PII leakage (self-labeling), grounding (the answer
  key is the captured context), cost and latency (governed by a budget, which is
  project policy rather than a per-row judgment), and tool calls (see below).
  It then **names the dimensions it refused to guess at**, because `safety`,
  `task_completion` and `action_correctness` encode intent and no trace contains
  intent. Reported coverage is reconciled against the scorecard afterwards, so a
  judged dimension that was skipped is never reported as scored.
- **`assevra probe --out probes.jsonl`** — a generated adversarial suite that
  carries its own answer key. An **injection** probe plants an instruction telling
  the agent to emit an improbable token, and the token *is* the label; **PII bait**
  plants a synthetic secret the task never needs; **over-refusal** probes are
  unambiguously benign, so `should_refuse` is false by construction. Canaries are
  seeded from the probe id, so a regenerated suite is byte-identical and diffable.
- **`assevra capture -- python my_agent.py`** — the twenty-line script everyone
  was writing, shipped. The prompt arrives on stdin, the answer on stdout, which
  anything can satisfy. Two things come free: a measured `latency_ms` on every
  row, and `--repeat N` to run each input several times under a shared `case_id`,
  which unlocks pass^k and the flaky-case report. Also a `Recorder` for in-process
  capture. Assevra still runs only the command you typed.
- **`assevra suggest` / `assevra confirm`** — a model drafts the answer key for
  the three dimensions that need judgment; a human accepts or rejects it, which
  turns two minutes a row into five seconds. **The gate is the feature:** a
  proposed field is recorded in `_suggested`, and `assevra validate` reports a row
  whose answer key is entirely machine-proposed as **UNLABELED**, so it can never
  satisfy `--strict` until a human confirms it. A `must_include` proposal that is
  absent from the captured output is kept but flagged, because a proposal that
  silently rewrote the test to match the agent would be the worst available bug.
- **Tool contracts derived from the agent's own tool spec** (`--tools`). OpenAI
  functions, Anthropic tools, MCP manifests and plain `{name: JSON Schema}` maps
  are recognised **by structure, not filename**, and become `allowed_tools` +
  `tool_schemas`. `forbidden_tools` and `expected_tool_calls` are deliberately not
  derived: a spec says what the agent *can* do, never what it must not.
- **[assevra.ai/try](https://assevra.ai/try)** — drop a trace file into the
  browser and get a scorecard. The real package runs in the tab under
  WebAssembly, installed from the wheel the site was built from. There is no
  server to upload to, and the page says so.
- **`assevra.toolspec`, `assevra.scan`, `assevra.probe`, `assevra.capture`,
  `assevra.suggest`** are importable modules, not just commands.

### Changed

- **Trace extraction now carries the signals it always had.** `usage`,
  `cost_usd`, `latency_ms` and `tool_calls` survive `bootstrap` — including OTel
  span durations and `gen_ai.usage.*` attributes, OpenAI/Anthropic tool-call
  shapes, and numeric CSV columns. Dropping them, as every earlier version did,
  forced a human to re-supply data the trace was already holding.
- **Scorers may declare an `autolabel` hook**, which is what `scan` runs on. A
  third-party scorer that can be scored from a raw trace gets the same treatment
  as a built-in.
- `assevra capture` strips the shell's `--` separator before running your command.
- The Pages workflow builds the wheel and re-syncs the published schemas, so
  `/try` and `/schema/v1/` always match the commit that deployed them.

### Notes on comparability

No scorer, rubric, threshold or detector changed: an existing dataset scores
exactly as it did under 0.4, and `tests/snapshots/golden.json` pins that.
`ASSEVRA_VERSION` moves to `0.5` because auto-labeled rows are a new provenance
that a reader of a scorecard should be able to distinguish — scanned rows are
tagged `scan` and `auto-labeled`, and generated probes are tagged `probe` and
`synthetic`.

## [0.4.0] — 2026-07-31

The adoption release. 0.1–0.3 were about making the *measurement* honest; 0.4 is
about making it something a team can actually adopt on a Tuesday afternoon. The
guiding sequence: schema validation → correct dataset semantics → complete CI →
configuration → init wizard → high-level SDK → GitHub Action → official
integrations → public case studies.

### Added

- **`assevra demo`** — a complete worked scorecard in one command, with **no
  clone, no API key and no network**. The demo dataset ships inside the wheel and
  covers all nine dimensions plus repeated trials; the command writes the HTML
  report, the JSON scorecard, the Markdown summary, the Agent Card, the dataset it
  scored, and the `.assevra.yml` that produced all of it.
- **`.assevra.yml` project configuration.** Dataset, out-dir, judge, gate,
  thresholds, budgets, history, signing, reports and calibration all live in one
  reviewable file, so `assevra run` needs no flags and every machine runs the same
  evaluation. Precedence is defaults < file < environment < flags; unknown keys
  are **reported, never silently dropped**. The parser is dependency-free (PyYAML
  is used when present, never required), and `--config none` ignores any project
  config.
- **`assevra validate`** — the gate that runs *before* evaluation. Every row is
  classified **LABELED / UNLABELED / INVALID** with a stable error code and a
  suggested fix. `run` calls the same check first, so a broken dataset fails in a
  second instead of producing a confident, meaningless report. `--strict` treats
  an unlabeled row (a *vacuous pass*) as a failure.
- **`assevra init`** — detects candidate trace files (ranked by how much it could
  actually extract), your agent framework, and which judge providers have
  credentials; then writes `.assevra.yml`, a drafted dataset, a GitHub Actions
  workflow, and an `EVALUATION.md`. Nothing is overwritten without `--force`;
  `--dry-run` shows the plan.
- **Published artifact contracts.** Five JSON Schemas — `scorecard`,
  `agent-card`, `calibration`, `dataset`, `validation` — versioned independently
  of the package, shipped inside the wheel, and served from
  `https://assevra.ai/schema/v1/`. Every emitted artifact carries `$schema` and
  `schema_version`. **Within major version 1, fields are only ever added — never
  removed, renamed, or repurposed.** `assevra schema` prints or exports them.
- **Python SDK.** `from assevra import evaluate` scores records in memory —
  notebooks, pytest, the harness that just ran the agent. Validation runs first
  and an invalid dataset raises. Plus registries for **scorers, reporters, trace
  adapters and judge providers**, so a team's domain metric becomes a first-class
  dimension (appearing in the scorecard, the validator, the config and the gate)
  rather than a fork.
- **Judge-provider abstraction.** Anthropic, OpenAI, Azure, Bedrock, Gemini, any
  OpenAI-compatible **local** endpoint (Ollama, vLLM, LM Studio — over `urllib`,
  with no third-party package and no data leaving the machine), and a
  deterministic offline **mock**. `auto` selects the first provider with
  credentials and never selects `mock`. Panels may span vendors
  (`anthropic:claude-opus-4-8,openai:gpt-4o`).
- **Five new dimensions**, chosen for how agents actually fail in production:
  - `tool_call` — were the calls well-formed and permitted? Parses raw JSON
    argument strings (truncated blobs are a first-class finding), enforces
    allow/deny lists, required arguments, types and enums.
  - `action_correctness` — did it do the right thing? Ordered / exact / set
    matching, with forbidden actions failing a row even when the expected ones
    happened. Reads actions from `tool_calls` when not recorded explicitly.
  - `injection` — prompt-injection resistance, deterministically, via a **canary**
    string; escalates to a judge only for rows with no canary, and is skipped —
    never passed — when neither is available.
  - `cost` — priced from `cost_usd` or from token `usage` with a configured price
    table, against a per-row or project budget. Notes report total, mean and p95.
  - `latency` — a pass rate against a budget, with p50/p95/max in the notes,
    because averages hide the tail.
- **A GitHub Action** (`uses: assevra/assevra@v1`). Installs, validates, scores,
  gates, writes a summary table and the failing rows to the **job summary**, and
  uploads the artifacts. Outputs `passed`, `scorecard`, `html`, `summary`. Works
  with no key: judged dimensions report as SKIPPED, so forks get a real gate
  instead of a red build.
- **`assevra integrate`** — the wiring for OpenTelemetry, LangGraph, Langfuse,
  Arize Phoenix, the OpenAI Agents SDK, and Anthropic Messages, printed as capture
  snippet, export command and the exact `bootstrap` invocation.
- **A real CI pipeline** (`ci.yml`): Python 3.10–3.13 matrix, a check that the
  core imports with no third-party packages, unit tests, CLI integration tests,
  the **judged path exercised offline via the mock provider**, calibration,
  package build + `twine check`, a clean-venv **wheel install smoke test**, JSON
  Schema validation of every artifact, a served-schemas-match-packaged-schemas
  check, an HTML self-containment check, a **golden snapshot** (`tests/snapshot.py`),
  and the project gating itself on its own scorer.
- **Three runnable case studies** under `examples/case-studies/` — RAG assistant,
  commerce agent, multi-agent workflow — each with a failing `before.jsonl`, a
  passing `after.jsonl`, the config, and a write-up that states what the result
  does *not* prove. Every number quoted was produced by running them.
- **A documentation site** at [assevra.ai/docs](https://assevra.ai/docs): getting
  started, concepts, dimensions, methodology, calibration, configuration, CLI,
  SDK, integrations, CI, schemas, security, governance, FAQ, troubleshooting.
- **Community and governance files**: `GOVERNANCE.md` (including the bar a
  methodology change must clear), `ROADMAP.md`, `CODE_OF_CONDUCT.md`,
  `SUPPORT.md`, a pull-request template, and a "new dimension" issue template.

### Changed

- **Positioning.** Assevra is *release evidence for AI agents*. The artifact — not
  the CLI — is the product, and the schemas are versioned as such.
- **Richer HTML scorecard.** The generated report is redesigned to match the
  project site: a gradient header with the mark and verdict pill, an at-a-glance
  stat strip (dimensions passed / rows scored / skipped), and — per dimension — a
  **confidence-interval bar** that plots the score, its 95% Wilson band, and the
  threshold line, making "report the interval, not just the mean" visual. Row
  lists now show failing rows first and cap long datasets with a "+N more"
  summary, and a footer prompts signing for a verifiable artifact. Purely a
  rendering change — the scorecard JSON (and thus any signature) is unaffected.
  The bundled `docs/example-scorecard.html` is regenerated as a full example.
- **Scorecard JSON gains provenance fields** (additive, schema-compatible):
  `$schema`, `schema_version`, `generated_at`, `dataset_sha256`, and
  `judge_provider`. Because the signature covers the scorecard's content, a
  scorecard produced by 0.4 has a different content hash than the same run under
  0.3 — re-sign rather than re-using an old signature.
- **Scorer signature** is now `score(rows, judge=None, options=None)`. Custom
  scorers written against 0.3 need the extra optional parameter.
- **`assevra history`** and **`assevra calibrate`** read their paths and settings
  from `.assevra.yml` when not passed explicitly. `calibrate` gained `--out` to
  write the calibration artifact, and its κ bar is configurable.
- **Exit codes are now explicit and documented**: 0 success, 1 gate failed, 2 the
  command could not run.
- **Extras split by vendor** — `[anthropic]`, `[openai]`, `[azure]`, `[bedrock]`,
  `[gemini]` — so you install only the SDK you use. `[judge]` is kept as an alias
  for the pre-0.4 name.
- The `eval-gate` workflow now runs through the published composite action, so the
  action itself is exercised on every pull request.

### Notes on comparability

Existing dimensions score identically to 0.3 — no rubric, threshold, or detector
was changed, and `tests/snapshots/golden.json` pins that. `ASSEVRA_VERSION` moves
to `0.4` because the artifact gained fields and five new dimensions can now
appear in a report.

## [0.3.0] — 2026-07-05

### Added
- **Agent Card (`assevra attest`).** Maps a scorecard's measured evidence to the
  control families of the EU AI Act, NIST AI RMF (incl. the Generative AI
  Profile), ISO/IEC 42001, and the OWASP Top 10 for LLM Applications — the
  auditor/procurement-facing artifact that bridges eval results and a security
  review. Writes `agent-card.md` and `agent-card.json`, notes signed provenance
  when given a `--signature`, and is framed throughout as evidence/due-care, **not
  a certification, compliance determination, or legal advice** (mappings are
  indicative).
- **Judge panels (a jury).** `run --judge-panel m1,m2,m3` scores the judge
  dimensions with several models and aggregates them — a 1–5 grounding score by
  median, a safety refusal verdict by majority — surfacing panelist
  *disagreement* (a split vote) on the row, since disagreement is itself a signal.
- **Judge calibration.** `assevra calibrate --dataset holdout.jsonl` runs the
  judge (or panel) over a human-labeled hold-out and reports judge-vs-human
  agreement: raw accuracy, Cohen's κ (chance-corrected), and
  sensitivity/specificity, per dimension and overall. Exits non-zero below the
  κ ≥ 0.85 trust bar (METHODOLOGY.md §4), automating a step previously only
  described.
- **pass^k and run-to-run consistency** — group repeated trials of the same input
  with a shared `case_id` and the scorecard reports, per dimension, the
  **consistency** (share of repeated cases whose trials all agree, with flaky
  cases listed) and **pass^k** (unbiased estimate that k independent attempts all
  pass, `C(passes,k)/C(trials,k)`). `run --pass-k K` sets k (default 2). Surfaces
  in Markdown, JSON, and HTML; omitted entirely on single-trial datasets, so
  existing scorecards are unchanged.
- **Reliability trend tracking** — `assevra run --history <file>` records each run
  and compares it to the previous one, flagging a per-dimension move only when it
  falls outside the previous 95% interval or crosses a threshold. `--label`,
  `--baseline`, and `--fail-on-regression`; new `assevra history` command.

### Fixed
- Judge prompts embedded a literal JSON example whose braces collided with
  `str.format` fields, raising `KeyError` on any real judge run (never hit in CI,
  where judge dimensions are skipped without an API key). Escaped the braces so
  grounding and safety judging work.

## [0.2.0] — 2026-07-05

### Added
- **`assevra bootstrap`** — draft a dataset from captured traces instead of
  hand-authoring JSONL from a blank page. Fills the captured fields
  (`input`, `agent_output`, `context`) and leaves only the answer key for you,
  with a per-row `_review` hint. Three dependency-free, auto-detected adapters:
  generic JSONL (field-alias detection), OpenAI chat logs, and OpenTelemetry
  spans (OpenInference `input.value`/`output.value` and OpenLLMetry
  `gen_ai.prompt.*`/`gen_ai.completion.*`).
- **Cryptographic signing** — `assevra keygen`, `assevra sign` / `run --sign`,
  and `assevra verify`. Ed25519 detached signatures over a canonical
  serialization of the scorecard make it tamper-evident; `verify --public-key`
  pins the signer to prove authorship. Behind the optional `[sign]` extra.
- `SECURITY.md` with scorecard-verification and vulnerability-reporting guidance.
- First test suite: `tests/test_bootstrap.py`, `tests/test_signing.py`,
  `tests/test_pii.py` (run under pytest or standalone).
- Pages deployed via a concurrency-controlled GitHub Actions workflow.

### Changed
- README and landing page repositioned around the differentiated wedge: a
  portable, signable **artifact** (not a dashboard), honest 95% Wilson error
  bars, and offline/deterministic-first scoring.

### Fixed
- **PII scorer / eval-gate:** the regex hard-block patterns (SSN, credit card,
  bank number) now always run as a guaranteed floor and Presidio augments them,
  so the zero-tolerance guarantee no longer depends on Presidio's per-entity
  confidence scoring (which could score a bare SSN below the floor and let a
  planted leak slip past the gate).

## [0.1.0] — 2026-07-04

- Initial release: the Assevra Reliability Scorecard — four dimensions
  (grounding, safety/refusal, PII-leak, task-completion), each scored against a
  fixed threshold with a 95% Wilson confidence interval and a conjunction
  verdict. Markdown, JSON, and self-contained HTML reports. CI gate via
  `--gate`. Archived on Zenodo with a citable DOI.
