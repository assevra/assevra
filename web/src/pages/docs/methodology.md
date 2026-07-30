---
layout: ../../layouts/DocsLayout.astro
title: Methodology
description: Why the numbers are shaped the way they are — and what they are not allowed to claim.
eyebrow: What it measures
---

This page is the reasoning. The normative specification lives in
[METHODOLOGY.md](https://github.com/assevra/assevra/blob/main/METHODOLOGY.md) in
the repository, which is versioned and citable.

## The question Assevra is answering

Most evaluation tools answer _"how good is my model?"_ Assevra answers a
different and much narrower question:

> **Can I safely release this agent?**

That reframing drives everything else. A release decision needs a threshold, not
a leaderboard. It needs to know what was _not_ measured. It needs to survive
being read by someone who was not in the room. And it needs to fail closed when a
measurement did not happen.

## Deterministic before judge

If a property can be decided by a rule, decide it with a rule.

You do not ask a model whether an SSN leaked — you scan for one. You do not ask a
model whether a tool call was well-formed — you validate it against the schema.
You do not ask a model whether a run exceeded its latency budget — you compare two
numbers.

Rules are reproducible, free, auditable, and they never disagree with themselves
between runs. Seven of the nine built-in dimensions are deterministic, which is
why most of Assevra runs offline, at zero cost, identically on every machine —
including a fork with no secrets.

A judge is reserved for properties where judgment is genuinely irreducible:
whether a claim is supported by its context, whether an answer constitutes a
refusal. When a judge is used, the rubric is **frozen and hashed**, and the hash
is written into the scorecard, because changing a rubric changes the number and
that has to be visible.

## Report the interval, not just the mean

Every dimension reports a **95% Wilson score interval** and the sample size it
came from.

Wilson rather than the normal approximation, because reliability scores live near
0 and 1 where the normal approximation misbehaves badly — it produces intervals
that extend past 1.0, and it collapses to zero width at the boundary, which is
precisely wrong for a dimension sitting at 1.00 on twelve rows.

The consequence is uncomfortable on purpose. Four rows at 0.500 produce an
interval of `0.150–0.850`. That width says: _this dataset cannot distinguish an
agent that is half-right from one that is nearly always wrong._ The correct next
action is more rows, not a fix — and without the interval, nobody would know that.

## The verdict is a conjunction

A scorecard passes only if **every** scored dimension passes. Reliability failures
do not average: a strong grounding score does not buy back a PII leak, and a 99%
task-completion rate is not consolation for a successful prompt injection.

A run in which every relevant dimension was skipped is not a pass either.

## Skipped is not passed

A dimension whose engine was unavailable is reported as `SKIPPED`, contributes no
evidence, and does not gate.

The failure this prevents is specific and common: a CI job loses its API key, the
judged dimensions stop running, the build stays green, and three months later
nobody can say when half the gate was switched off. Under Assevra's semantics the
scorecard says `SKIPPED` in the summary table, the overall verdict fails if
nothing else was scored, and the artifact records it permanently.

## Thresholds, and what a threshold means

A threshold is a policy statement, not a tuning parameter. Setting `tool_call` to
0.95 on a refund tool is a decision to accept one bad refund in twenty. That may
well be the right call — but it should be written down as a sentence someone
signed, which is what putting it in `.assevra.yml` accomplishes.

Zero-tolerance dimensions sit at 1.00: PII leakage, safety refusal, prompt
injection. One occurrence is one too many — and an interval around a 1.00 score
still tells you how much confidence twelve rows actually buy.

## Judged scores are not evidence until calibrated

An LLM-judge number means nothing until you have shown the judge agrees with
humans on a labeled hold-out. `assevra calibrate` measures **Cohen's κ** —
chance-corrected agreement, because two raters can agree 90% of the time with κ
near zero when the classes are lopsided.

The bar is **κ ≥ 0.85**. Below it, the score is an opinion with a decimal point.
See [Judge calibration](/docs/calibration).

## Reliability is not accuracy

A pass rate answers "how often does it work?" A deployed agent needs "does it
work _every_ time?"

Repeated trials sharing a `case_id` produce two further metrics:

- **consistency** — the share of repeated cases whose trials all agree, with the
  flaky cases named.
- **pass^k** — the unbiased estimate that _k_ independent attempts all pass,
  `C(passes, k) / C(trials, k)`. The reliability analogue of pass@k: it rewards
  succeeding every time, not merely once.

A dimension at 0.667 with consistency 0.000 is not a mediocre agent. It is an
unpredictable one, and the fix is different.

## What a scorecard does not claim

Stated plainly, because it travels in the footer of every report:

- **It is not a certification.** A pass means the agent behaved on the dataset you
  gave it.
- **It characterizes the dataset, not the agent.** Small datasets support small
  claims; the interval says how small.
- **Each scorer has scope.** Task-completion checks fact presence, not phrasing.
  The regex PII floor sees only hard-block entities. A canary proves resistance to
  the attack you wrote.
- **A skipped dimension contributed nothing.**

Reliability claims are only as strong as what they honestly exclude. That
sentence is the methodology in one line.

## Reproducibility

Five things determine a number: the code version, the dataset, the judge model,
the judge rubric, and the thresholds. All five are recorded in the artifact — the
version, the dataset path and its SHA-256, the judge model and provider, the
rubric hash in the dimension notes, and every threshold in the summary table.

Change any of them and the number changes. The repository's own
[golden snapshot test](https://github.com/assevra/assevra/blob/main/tests/snapshot.py)
exists so that such a change appears as a reviewed diff rather than a silent
drift.

## Citing

> Divi, Veera Ravindra. _Assevra: A Reliability Scorecard for LLM Agents_, v0.4, 2026. <https://doi.org/10.5281/zenodo.21200852>

When you report a number, say it was _measured with Assevra v0.4_ — the version
is part of the claim.
