---
layout: ../../layouts/DocsLayout.astro
title: FAQ
description: The questions people actually ask before adopting Assevra.
eyebrow: Help
---

## Does Assevra execute my agent?

`run` and `scan` evaluate captured records. `capture` executes the command you explicitly provide. The Python recorder can wrap your own in-process execution. None of these automatically replays side-effecting tools from a trace.

## Can I run locally?

Yes. Install the package, then use deterministic checks or configure a local judge endpoint. Installation downloads packages. Cloud judges receive the rubric's input/context/output fields.

## Can a scan pass my release?

No. A scan is TRIAGE, and mock judging is SELF_TEST. Declare release dimensions and supply labeled business assertions to obtain release evidence.

## What happens when a judge is missing?

Its dimension is skipped and release evaluation is INCOMPLETE. Invalid verdicts or incomplete/tied panels also produce missing evidence, not passing measurements.

## Does a suggested action fix the agent automatically?

No. Suggestions guide review. Execute the changed agent again and rerun the same complete suite to verify a fix.

## Are integrations native vendor connections?

The SDK and recorder are direct Python interfaces. Other integrations include serialized trace adapters, tool-contract imports, and capture/export recipes. See the [maturity table](/docs/integrations). They do not imply vendor partnerships or validation of your hosted deployment.

## Does signing certify reliability or compliance?

No. A signature verifies canonical JSON integrity; a trusted pinned key establishes authorship. Scores describe the supplied cases. Governance mappings are indicative evidence organization, not certification.

## Is the core dependency-free?

No. Assevra 0.6 uses `jsonschema` for complete imported tool contracts. Provider SDKs, Presidio, and signing remain optional extras.

## How do I upgrade from 0.5?

Use schema v2 and branch on `decision`. Required missing evidence blocks release, detector controls are separate, and mock runs cannot qualify as agent release evidence. Read the [migration guide](https://github.com/assevra/assevra/blob/main/docs/MIGRATING-0.6.md).
