---
layout: ../../layouts/DocsLayout.astro
title: Concepts
description: The vocabulary — and, more usefully, the reason each idea exists.
eyebrow: Start here
---

## Scorecard and release scope

A scorecard records the dimensions, sample sizes, confidence intervals, findings, validation, coverage, and decision for a specific evaluation. The HTML, Markdown, and JSON reports describe the same evidence.

| Decision   | Interpretation                                                                  |
| ---------- | ------------------------------------------------------------------------------- |
| PASS       | Complete release evidence meets every included and required threshold           |
| FAIL       | A measured threshold or required compatible regression comparison fails         |
| INCOMPLETE | Required evaluation evidence or comparison is missing or unusable               |
| TRIAGE     | A partial scan; never a passing release gate                                    |
| SELF_TEST  | An evaluator demonstration, including mock judges; never a passing release gate |

`overall_pass` is true only for PASS. Declare `gate.required_dimensions` to detect entirely absent dimensions. Otherwise scope is inferred from the included rows and recorded in the artifact.

## Measurement and evaluator status

PASS and FAIL rows are agent measurements. ERROR and ABSTAIN rows are missing evaluator evidence and do not enter pass-rate denominators. A skipped dimension contributes no evidence and blocks a release evaluation. Invalid judge values, incomplete panels, and tied votes cannot become passing measurements.

A known-bad PII detector test checks the evaluator. Such rows are reported under `controls`, outside agent scores.

## Labeled, unlabeled, and invalid

Validation classifies rows before scoring. A release requires valid, labeled rows. Empty completion criteria or a missing tool contract cannot establish success. Strict validation is mandatory for release-purpose evaluations; an exploratory scan still cannot produce release PASS.

## Actions and outcomes

A structurally valid tool call can still be unauthorized or achieve the wrong result. `action_correctness` checks expected and forbidden action sequences. It can also compare `expected_state` with `observed_state`: objects match recursively as subsets, arrays match exactly in order, and scalar types are significant. Missing observed state is missing evidence.

## Suggested fixes

Findings contain deterministic guidance keyed to the failing dimension and case. They help prioritize investigation, but do not prove root cause. Review the suggested change, execute the agent again, and rerun the full declared suite. Re-scoring old captured output does not verify a changed agent.

## Confidence and repeated trials

Dimension pass rates include sample sizes and 95% Wilson intervals. Repeated trials sharing `case_id` also provide consistency and pass^k summaries. These measurements apply to the supplied cases; repeated trials may be correlated. Choose case coverage and sample sizes appropriate to the release risk.

## Comparable history

History records suite and policy hashes plus judge identity. Required regression checks block missing or incompatible baselines. Suite hashes include inputs and assertions while excluding measured agent output, actions, usage, and final state. Policy hashes capture scoring version, thresholds, and options. This permits comparing a changed agent against unchanged expectations.

## Signing and governance

Optional Ed25519 signatures protect canonical JSON. Pin a trusted public key to verify authorship; the embedded key alone establishes integrity. An Agent Card maps the evidence to governance control families, not legal compliance or certification.
