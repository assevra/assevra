---
layout: ../../layouts/DocsLayout.astro
title: Concepts
description: The vocabulary — and, more usefully, the reason each idea exists.
eyebrow: Start here
---

Assevra has about ten ideas in it. Each one exists because of a specific way
evaluation goes wrong.

## Scorecard

The artifact. One run produces a Markdown summary, a JSON document governed by a
[published schema](/docs/schemas), and a self-contained HTML report with inline
CSS and no external assets.

The scorecard — not the CLI — is the product. A dashboard behind a login is
useful for a week and inaccessible the moment someone leaves the company or the
vendor changes their pricing. A file in git is readable in five years.

## Dimension

One property being measured, with its own scoring method and its own pass
threshold. Nine ship in the box; you can [register your own](/docs/sdk#extending).

The verdict is a **conjunction**: the scorecard passes only if _every_ scored
dimension passes. A strong grounding score does not buy back a PII leak. That is
not strictness for its own sake — reliability failures do not average.

## Deterministic vs. judged

A dimension is scored one of two ways:

**Deterministic** — a rule decides. You scan for a leaked SSN; you do not ask a
model whether it leaked one. Reproducible, free, auditable, and it cannot change
its mind between runs.

**LLM-as-judge** — a model decides, against a rubric that is pinned and hashed
into the scorecard notes. Used only where the property genuinely requires
judgment, like whether a claim is supported by its context.

The rule is **deterministic before judge**. If you can write a regex, a schema
check, or a comparison, write it. Seven of the nine built-in dimensions are
deterministic, which is why the majority of Assevra runs offline, free, and
identically on every machine.

## Skipped ≠ passed

A dimension whose engine is unavailable — no judge configured, no detector
installed — is reported as `SKIPPED` and contributes no evidence. It does not
gate, and it is never counted as a pass.

This matters more than it sounds. The failure mode it prevents is the one where a
CI job loses its API key, the judged dimensions quietly stop running, the build
stays green for three months, and nobody notices that half the gate has been
switched off.

## Labeled, unlabeled, invalid

Every dataset row lands in exactly one state, checked before any scoring
happens:

- **LABELED** — has an answer key; can produce a meaningful verdict.
- **UNLABELED** — parses and will score, but there is nothing to verify. Its pass
  is _vacuous_. Legitimate while you are still labeling; dangerous the moment
  someone quotes the number.
- **INVALID** — structurally unusable. Evaluation must not proceed.

A `task_completion` row with an empty `must_include` list passes every time and
means nothing. `assevra validate` names that row; `--strict` fails the build over
it.

## Confidence interval

Every dimension reports a **95% Wilson score interval** alongside its mean, plus
the sample size it came from.

On a small dataset the interval is uncomfortably wide — `0.500` with an interval
of `0.150–0.850` on four rows. That width is not a flaw in the report. It is the
honest statement of what four rows can support, and it is what stops a team from
reading a two-row improvement as progress.

The Wilson interval is used rather than the normal approximation because it
behaves correctly near 0 and 1, which is exactly where reliability scores live.

## Threshold

The pass rate at or above which a dimension passes. Defaults come from the
methodology; override them per project in [`.assevra.yml`](/docs/configuration).

Zero-tolerance dimensions sit at `1.00` — PII leakage, safety refusal, prompt
injection — because one occurrence is one too many. Setting a threshold below 1.00
on a destructive tool is a policy decision to accept some rate of harm, and it
should be written down as one.

## pass^k and consistency

A pass rate answers "how often does it work?" A deployed agent needs the stricter
answer: "does it work _every_ time?"

Give repeated trials of the same input a shared `case_id`, and the scorecard
gains two metrics over those groups:

- **consistency** — the share of repeated cases whose trials all agree. A case
  that sometimes passes and sometimes fails is flagged as **flaky** and named.
- **pass^k** — the estimated probability that _k_ independent attempts all pass,
  using the unbiased estimator `C(passes, k) / C(trials, k)`.

A dimension scoring 0.667 with consistency 0.000 is not a quality problem. It is
an agent that never behaves the same way twice, and that is a different bug with
a different fix.

## Calibration

An LLM-judge score means nothing until you have shown the judge agrees with
humans. `assevra calibrate` measures that on a labeled hold-out and reports
**Cohen's κ** — chance-corrected agreement, the honest number, since two raters
can agree 90% of the time with κ near zero if the classes are lopsided.

The bar is **κ ≥ 0.85**. Below it, a judged score is an opinion with a decimal
point. See [Judge calibration](/docs/calibration).

## Judge panel

Several models voting as a jury. A panel agrees with humans more often than any
single judge — but the more valuable part is that its **disagreement is itself a
signal**. A split vote means the row is genuinely ambiguous, which is exactly the
row a human should look at, so Assevra surfaces the split instead of hiding it
behind a median.

Panelists can span vendors (`anthropic:claude-opus-4-8,openai:gpt-4o`). Three
models from one lab share failure modes; three from three labs do not.

## Signing

A shared HTML file is convenient. It is not evidence — anyone can edit it.
`assevra sign` attaches a detached **Ed25519** signature over a canonical
serialization of the scorecard's content; `assevra verify` confirms nothing
changed, and pinning the public key proves _authorship_ rather than mere
integrity. See [Security & signing](/docs/security).

## Agent Card

`assevra attest` maps each measured dimension onto the control families of the
EU AI Act, the NIST AI RMF, ISO/IEC 42001, and the OWASP Top 10 for LLM
Applications — the vocabulary a procurement or security review actually speaks.

It is **evidence and due-care documentation, not a certification**, and the card
says so on its face. See [Governance mapping](/docs/governance).

## Provider

Whoever serves the judge: Anthropic, OpenAI, Azure, Bedrock, Gemini, any
OpenAI-compatible local endpoint, or the deterministic offline `mock`. A provider
is just a function from prompt to text; everything above it — rubrics, panels,
calibration — is vendor-agnostic.

`provider: auto` picks the first one whose credentials are present, and returns
nothing when none are, at which point judged dimensions are skipped rather than
failed.
