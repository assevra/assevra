---
layout: ../../layouts/DocsLayout.astro
title: Governance mapping
description: The Agent Card — measured evidence, translated into the language a security review speaks.
eyebrow: The artifact
---

Two stacks exist today and neither ships the bridge. Governance and GRC tools map
frameworks but do not run evaluations. Evaluation tools produce numbers but do
not speak the language of an auditor or a procurement reviewer.

`assevra attest` fills that gap.

```bash
assevra attest --scorecard scorecard.json
assevra attest --scorecard scorecard.json --signature scorecard.sig.json
assevra run --attest                              # or produce it with the run
```

It writes `agent-card.md` and `agent-card.json`, mapping each measured dimension
onto the control families of:

- **the EU AI Act**
- **the NIST AI Risk Management Framework**, including the Generative AI Profile
- **ISO/IEC 42001**
- **the OWASP Top 10 for LLM Applications**

## What it is not

> **An Agent Card is evidence and due-care documentation. It is not a
> certification, a conformity or compliance determination, or legal advice.**

That disclaimer is printed on the card itself, not tucked into a footnote here,
because the failure mode is real: a document that maps to the EU AI Act is one
screenshot away from being presented as EU AI Act _compliance_.

Three things keep it honest:

- **Each framework requires substantially more** than these measurements —
  governance, risk management, technical documentation, human oversight, data
  provenance. The card names those gaps in an explicit "evidence gaps and scope"
  section rather than leaving them as an absence someone might not notice.
- **The mappings are indicative** and point at control _families_, not clauses
  you can claim conformity with. Verify them against the current text of each
  framework and your auditor's requirements.
- **Conformity is decided by auditors and competent authorities**, not by a tool.

## What it maps

| Dimension            | Speaks to                                                                                                                                                             |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `grounding`          | EU AI Act Art. 15 (accuracy) · Annex IV (metrics & test procedures) · NIST MEASURE / GenAI Profile (confabulation) · OWASP LLM09 (misinformation) · ISO 42001 cl. 9.1 |
| `safety`             | EU AI Act Art. 15 (robustness), Art. 9 (risk management) · NIST MEASURE (safety), red-teaming · OWASP LLM01, LLM05 · ISO 42001 cl. 9.1 + Annex A                      |
| `pii`                | EU AI Act Art. 10 (data governance), Art. 15 (cybersecurity) · NIST MEASURE (privacy), GenAI Profile (data leakage) · OWASP LLM02 · ISO 42001 / 27001                 |
| `task_completion`    | EU AI Act Art. 15 (accuracy) · Annex IV (effectiveness) · NIST MEASURE (validity & reliability) · ISO 42001 cl. 9.1                                                   |
| pass^k / consistency | EU AI Act Art. 15 (consistent performance) · NIST MEASURE (reliability)                                                                                               |

A **skipped** dimension contributes no evidence and the card says so, in the row
where the number would otherwise be. That is the point: a governance document
that quietly omits what was not measured is worse than no document.

## What a reviewer receives

A useful evidence package for a security review is four files:

| File                 | What it answers                                    |
| -------------------- | -------------------------------------------------- |
| `agent-card.md`      | "Which of my controls does this touch?"            |
| `scorecard.html`     | "What was actually measured, and how confidently?" |
| `calibration.json`   | "Why should I believe the judged numbers?"         |
| `scorecard.sig.json` | "Was this altered after you produced it?"          |

Passing `--signature` notes the signed provenance on the card itself, so the
governance document and the cryptographic proof travel together.

## Using it well

**Lead with the gaps.** The "evidence gaps and scope" section is the most credible
part of the document, and volunteering it changes the tone of the conversation.
A reviewer who finds an unstated limitation stops trusting the stated ones.

**Attach the dataset description.** Evidence is only as strong as what it was
measured on. "12 synthetic rows" and "400 adversarial rows drawn from six months
of production traces" are different claims, and the card cannot tell them apart.

**Calibrate before quoting a judged number.** An uncalibrated grounding score in a
governance document is an opinion with a decimal point. See
[Judge calibration](/docs/calibration).

**Re-run it per release.** An Agent Card is a snapshot of one run. Dated evidence
from a version that shipped four months ago is a liability, not an asset.

## Project governance

For how the project itself is run — the bar a methodology change has to clear,
how decisions get made, and how to become a maintainer — see
[GOVERNANCE.md](https://github.com/assevra/assevra/blob/main/GOVERNANCE.md) and
the [roadmap](https://github.com/assevra/assevra/blob/main/ROADMAP.md).
