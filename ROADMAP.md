# Roadmap

The long-term goal is not to be a better evaluation library. It is to make
Assevra's scorecard **the standard evidence format for AI agent releases** — the
thing you attach to a release the way you attach a test report, and the thing a
security reviewer knows how to read without being taught.

OpenAPI did this for REST contracts, OpenTelemetry for telemetry, OCI for
container images. In each case the format outlived every tool that produced it.
That is the bet here: if the artifact, the schemas, the integrations, and the
release workflow are right, the implementation language becomes an
implementation detail.

Everything below is subject to change, and the fastest way to change it is to
open an issue with a case the current design handles badly.

---

## Shipped in 0.4 — "easy to adopt"

The 0.4 line was about closing the distance between installing Assevra and
getting value from it.

- **`assevra demo`** — a full worked scorecard in one command: no clone, no API
  key, no network.
- **`.assevra.yml`** — project configuration, so `assevra run` needs no flags and
  every machine runs the same evaluation.
- **`assevra init`** — detects your traces, framework, and providers, then writes
  the config, a drafted dataset, a CI workflow, and an `EVALUATION.md`.
- **`assevra validate`** — LABELED / UNLABELED / INVALID, enforced before scoring,
  so a broken dataset fails in a second instead of producing a confident,
  meaningless report.
- **Published JSON schemas** — the scorecard, Agent Card, calibration report,
  dataset row, and validation report, versioned independently of the package and
  served from `assevra.ai/schema/v1/`.
- **Python SDK** — `from assevra import evaluate`, plus registries for scorers,
  reporters, trace adapters, and judge providers.
- **Provider abstraction** — Anthropic, OpenAI, Azure, Bedrock, Gemini, any
  OpenAI-compatible local endpoint, and a deterministic offline mock judge.
- **Five new dimensions** — tool-call validation, action correctness,
  prompt-injection resistance, cost budget, latency budget.
- **A GitHub Action** — `uses: assevra/assevra@v1`, with PR job summaries,
  artifact upload, and gating.
- **A real CI pipeline** — Python matrix, unit and integration tests, mock-judge
  coverage of the judged path, package build, clean-environment install smoke
  test, schema validation, HTML self-containment check, golden snapshot, and the
  project gating itself on its own scorer.

---

## Next: 0.5 — "easy to trust at scale"

Everything here is about the same question: *does this number hold up when the
dataset gets big and the stakes get real?*

- **Slice reporting.** A single pass rate hides the segment where the agent is
  failing. Score by tag, so "0.94 overall" becomes "0.99 on booking, 0.71 on
  refunds" — which is the sentence that actually changes what a team does next.
- **Statistical regression testing.** Today a regression is flagged when a score
  falls outside the previous interval. Add a two-proportion test with a
  configurable significance level and a minimum detectable effect, so a team can
  state the size of the regression they intend to catch.
- **Calibration as a first-class artifact.** Store calibration reports alongside
  scorecards, warn on a judged dimension whose calibration is stale or absent,
  and surface κ on the scorecard next to the judged number it qualifies.
- **A prompt-injection suite.** A maintained corpus of indirect-injection
  patterns — retrieved content, tool output, HTML comments, multi-turn setups —
  runnable as a starting dataset rather than something every team rewrites.
- **Sampling and cost control.** Confidence-driven sampling for large datasets:
  score enough rows to reach a stated interval width, then stop.
- **Concurrency.** Judged dimensions run serially today; a dataset of thousands
  of rows should not take an afternoon.

## Then: 0.6 — "evidence a reviewer already knows how to read"

- **Case studies, published.** Three end-to-end walkthroughs live in
  `examples/case-studies/` today; the goal is a maintained set with real failure
  modes, the fix, and the improved scorecard.
- **Richer Agent Cards.** Per-control evidence tables, coverage gaps stated
  explicitly, and an export shape that maps onto common security-review
  questionnaires.
- **Transparency-report export.** A single document combining the scorecard, the
  calibration report, the dataset description, and the signature — the artifact
  a procurement review asks for.
- **Multi-run evidence.** Aggregate a series of runs into a trend artifact, so
  "reliable" can be claimed over time rather than at one instant.

## Standing: v1.0 — "the format outlives the tool"

`1.0` is not a feature list. It is a promise about the artifact:

- The scorecard schema is **frozen** at v1 — additive changes only, forever.
- A reference **conformance suite** so a non-Python implementation can prove it
  emits valid Assevra evidence.
- The methodology document versioned and citable independently of the code.

At that point Assevra-the-Python-package is one implementation of Assevra-the-
format, which is the only outcome that makes the project matter more than its
own maintenance.

---

## Explicitly not planned

Saying no is part of a roadmap.

- **A hosted service, dashboard, or account.** The artifact is the product. A
  login would make the evidence depend on someone else staying in business.
- **Running your agent.** Assevra scores what you captured. Every framework can
  produce those captures; none of them needs Assevra to orchestrate.
- **Dozens of niche metrics.** The dimension list grows slowly and only for
  failure modes that take real systems down. A scorecard with forty numbers is a
  dashboard, and dashboards are what this project is a reaction to.
- **Vendor lock-in of any kind**, including to Anthropic. The judge is pluggable
  and always will be.

---

## How to influence this

- **Open an issue** with a case the current design handles badly. A failing
  example moves the roadmap faster than a feature request.
- **Tell us you are using it.** Real datasets and real failure modes are what
  sharpen the methodology — see the "Who's using Assevra?" section of the README.
- Look for **`good first issue`** if you want to start small; the
  [contributing guide](CONTRIBUTING.md) has the ground rules and
  [GOVERNANCE.md](GOVERNANCE.md) has the bar a methodology change must clear.
