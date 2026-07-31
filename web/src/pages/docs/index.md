---
layout: ../../layouts/DocsLayout.astro
title: Assevra documentation
description: Assevra turns agent test runs into signed, statistically defensible scorecards that gate every release.
eyebrow: Docs
---

Assevra is not an eval dashboard and not an observability backend. It produces
**release evidence**: a portable artifact — Markdown, JSON, and a self-contained
HTML report — that you commit to git, attach to a pull request, hand to a
security reviewer, and can still verify a year from now.

## Five minutes, start to finish

```bash
pip install assevra
assevra demo                        # a full worked scorecard, offline
assevra scan --from traces.jsonl    # score YOUR traces — nothing labeled
```

`demo` writes a complete worked scorecard — no clone, no API key, no network.
Open `assevra-demo/scorecard.html` and you have seen the whole product. `scan`
then does the same for traces you already have: five dimensions, no answer key.
See [zero-label scoring](/docs/zero-label), or
[try it in your browser](/try) with no install at all.

Then point it at your own system:

```bash
assevra init --from traces.jsonl   # detects your traces, framework and providers
assevra validate --strict          # is every row actually labeled?
assevra run --gate                 # score, gate the build, write the artifacts
```

## What to read next

| If you want to…                                  | Go to                                    |
| ------------------------------------------------ | ---------------------------------------- |
| Score real traces without labeling anything      | [Zero-label scoring](/docs/zero-label)   |
| Try it with no install at all                    | [In your browser](/try)                  |
| Get a scorecard for your own agent               | [Getting started](/docs/getting-started) |
| Understand what a "dimension" or "skipped" means | [Concepts](/docs/concepts)               |
| Know exactly what each dimension checks          | [Dimensions](/docs/dimensions)           |
| Stop typing flags                                | [Configuration](/docs/configuration)     |
| Call it from Python instead of a shell           | [Python SDK](/docs/sdk)                  |
| Wire it to LangGraph, Langfuse, Phoenix, OTel…   | [Integrations](/docs/integrations)       |
| Gate a build on it                               | [CI & the GitHub Action](/docs/ci)       |
| Parse the scorecard from another tool            | [Schemas](/docs/schemas)                 |
| Prove a scorecard was not altered                | [Security & signing](/docs/security)     |
| Answer a security review                         | [Governance mapping](/docs/governance)   |

## The three commitments

Everything in these docs follows from three rules. They are worth reading once,
because they explain most of Assevra's design decisions — including the ones that
look inconvenient.

**Deterministic before judge.** If a property can be decided by a rule — a leaked
SSN, a malformed tool call, a blown latency budget — decide it with a rule. Rules
are reproducible, free, and auditable. Ask a model only for what genuinely
requires judgment, and then pin and hash the rubric so the number stays
comparable.

**Report the interval, not just the mean.** A bare `0.92` hides how few samples it
came from. Every dimension carries its sample size and a 95% Wilson confidence
interval, so nobody over-reads a small-sample move. On a small dataset the
interval is embarrassingly wide — that width _is_ the honest statement of what
the number can support.

**Skipped is not passed.** A dimension whose engine was unavailable — no judge
configured, no detector installed — is reported as `SKIPPED` and does not gate.
It is never silently counted as a pass, because a missing measurement is not a
passing one.

## What Assevra deliberately does not do

- **It does not run your agent.** You capture the outputs; Assevra scores them.
  That boundary is what makes it work with every framework instead of competing
  with them.
- **It does not certify anything.** A pass means the agent behaved on the dataset
  you gave it. Conformity determinations are made by auditors and authorities.
- **It has no backend, account, or login.** The artifact is the product.

## Project

- [GitHub](https://github.com/assevra/assevra) · [PyPI](https://pypi.org/project/assevra/) · [DOI 10.5281/zenodo.21200852](https://doi.org/10.5281/zenodo.21200852)
- [Roadmap](https://github.com/assevra/assevra/blob/main/ROADMAP.md) — what is planned, and what is deliberately not
- [Governance](https://github.com/assevra/assevra/blob/main/GOVERNANCE.md) — the bar a methodology change has to clear
- MIT licensed. A personal open-source research project by Veera Ravindra Divi.
