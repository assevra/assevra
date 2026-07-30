---
layout: ../../layouts/DocsLayout.astro
title: FAQ
description: The questions people actually ask before adopting Assevra.
eyebrow: Help
---

## Is this another eval framework?

No, and the difference is worth being precise about. Most evaluation tools answer
_"how good is my model?"_ and give you a dashboard. Assevra answers _"can I safely
release this agent?"_ and gives you a **file**.

The scorecard is the product: a portable artifact you commit, attach to a pull
request, hand to a reviewer, and verify a year later. There is no backend, no
account, and nothing to log into.

## Does Assevra run my agent?

No. You capture the outputs; Assevra scores them.

That boundary is deliberate. It is what makes Assevra work with LangGraph, the
OpenAI Agents SDK, a bespoke loop, or anything else, instead of competing with
them — and it means Assevra never executes your code or calls your tools.

## Do I need an API key?

No. Seven of the nine dimensions are deterministic and run offline at zero cost.
`assevra demo` produces a complete artifact set with no key and no network.

The two judged dimensions (grounding, safety) need a provider — Anthropic,
OpenAI, Azure, Bedrock, Gemini, or **any OpenAI-compatible local endpoint**, which
needs no third-party package and sends nothing off the machine. Without one they
are reported as `SKIPPED`, never as passing.

## Why is my grounding score "SKIPPED" instead of 1.00?

Because it was not measured, and a missing measurement is not a passing one.

That semantic exists to prevent a specific, common failure: a CI job loses its
API key, the judged dimensions quietly stop running, the build stays green, and
three months later nobody can say when half the gate was switched off.

## Why are the confidence intervals so wide?

Because your dataset is small, and the interval is telling you so.

Four rows at 0.500 produce a 95% interval of `0.150–0.850`. That width is the
honest statement that four rows cannot distinguish an agent that is half-right
from one that is nearly always wrong. Widen the dataset, not the claim.

## How many rows do I need?

There is no threshold that makes a number "valid" — that is what the interval is
for. As rough orientation:

- **10–20 rows**: enough to find obvious breakage and to wire up CI.
- **50–100 rows per dimension**: intervals get narrow enough to detect real
  movement.
- **200+**: you can start slicing by tag and mean it.

Better guidance than a row count: add a row every time something goes wrong in
production. A dataset that grew out of real incidents beats a bigger one that did
not.

## Can I trust an LLM judging an LLM?

Not by default — which is why Assevra makes you measure it. `assevra calibrate`
reports Cohen's κ against a human-labeled hold-out, and the bar is **κ ≥ 0.85**.
Below that, the judged score is an opinion with a decimal point.

You can also run a **panel**: several models voting as a jury, with disagreement
surfaced rather than averaged away. A split vote flags a genuinely ambiguous row,
which is exactly the row a human should read.

And the deeper answer: only two of nine dimensions use a judge at all. If a
property can be decided by a rule, Assevra decides it with a rule.

## What is the mock provider for?

Testing the plumbing, and nothing else. `--judge-provider mock` runs the judged
path deterministically offline, which is what lets CI exercise rubric parsing,
panel aggregation, calibration arithmetic, and skip semantics on every pull
request, including from forks with no secrets.

It is **not a judge**. Its verdicts carry no evidentiary weight, `auto` never
selects it, and a scorecard produced with it records `judge_model: mock-judge` on
its face.

## Can I add my own dimension?

Yes, and it becomes first-class — it appears in the scorecard, the validator, the
config, and the gate with no changes to Assevra. See
[Python SDK → Extending](/docs/sdk#extending).

It should meet the same bar as a built-in: a definition, an explicit scoring
method, a stated threshold, a reported interval, and a stated limit.

## What does "vacuous pass" mean?

A row that scores as a pass without verifying anything. A `task_completion` row
with an empty `must_include` list passes every time and means nothing.

`assevra validate` marks such rows **UNLABELED** and names them; `--strict` fails
the build over them. Turn that on once labeling is finished.

## Can I use it for non-agent LLM apps?

Yes. Nothing about grounding, PII leakage, refusal correctness, injection
resistance, cost, or latency is agent-specific. The tool-call and
action-correctness dimensions simply will not appear if your dataset has no rows
for them.

## Does it work in an air-gapped environment?

Yes. The core has no third-party dependencies, the schemas and demo dataset ship
inside the wheel, the HTML report has no external assets, and the `local`
provider talks to an on-premise endpoint over plain `urllib`.

## How is this different from `promptfoo`, `DeepEval`, `Ragas`, `LangSmith`…?

Those are good tools solving an adjacent problem: iterating on quality. Assevra
is aimed at the release decision, and three choices follow from that.

- **The artifact, not the dashboard.** Signed, schema-governed, portable, and
  readable without the tool that made it.
- **Deterministic before judge.** Most dimensions are rules, so most runs are free
  and reproducible.
- **Honest statistics as a default, not a feature.** Every number carries its
  interval and sample size, and a skipped dimension is never a pass.

There is no reason not to use both. Iterate with whatever you like; gate on
evidence.

## Is it free? Is there a paid version?

MIT licensed, free, with no paid tier and no hosted service on the roadmap. It is
a personal open-source research project by Veera Ravindra Divi, archived on
Zenodo with a citable DOI.

## Is it production-ready?

It is `0.4` and honest about that. The scorecard schema is stable within major
version 1 and validated in CI on every commit; the CLI surface is settled; the
methodology has been consistent since 0.1.

The project gates itself on its own scorer on every pull request. Whether that is
enough for your risk tolerance is a judgment only you can make — which is, in a
sense, the whole point of the tool.

## How do I cite it?

> Divi, Veera Ravindra. _Assevra: A Reliability Scorecard for LLM Agents_, v0.4, 2026. <https://doi.org/10.5281/zenodo.21200852>

When you report a number, say it was _measured with Assevra v0.4_ — the version
is part of the claim.
