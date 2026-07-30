---
name: New reliability dimension
about: Propose a new thing Assevra should measure
title: "dimension: "
labels: dimension, methodology
---

<!--
Please open this issue BEFORE writing the code. The definition is the hard part,
and agreeing on it first saves you a rewrite. See GOVERNANCE.md for the bar.
-->

**The failure this catches**
What goes wrong in a real agent that no existing dimension catches? A concrete
incident is worth more than a category.

**Definition — one sentence**
What property is being measured, stated so a non-specialist can check whether a
given row passes.

**Can a rule decide it?**
Deterministic before judge. If a regex, a schema check, or a comparison can
decide this, say how. If it genuinely needs judgment, say what makes it
irreducible — and propose the pinned rubric.

- [ ] Deterministic
- [ ] LLM-as-judge (rubric drafted below)

**Answer key**
What fields does a dataset row need in order to be *labeled* for this dimension?
What should the validator tell someone whose row is missing them?

**Threshold**
What pass rate should this dimension require, and why that level? Zero-tolerance
(1.00) needs a justification; so does anything below 0.90.

**What it will NOT measure**
The limits, stated plainly. This goes into the dimension notes and travels with
every scorecard, so it matters as much as the definition.

**Example rows**
Two or three synthetic rows — at least one that passes and one that fails.

```jsonl
{"id": "example-pass", "dimension": "your_dimension", "agent_output": "...", "...": "..."}
{"id": "example-fail", "dimension": "your_dimension", "agent_output": "...", "...": "..."}
```
