---
layout: ../../layouts/DocsLayout.astro
title: Assevra documentation
description: Assevra turns agent test runs into signed, statistically defensible scorecards that gate every release.
eyebrow: Docs
---

# From an agent run to a verified fix

Assevra evaluates captured runs and produces portable scorecards with explicit release decisions and suggested next actions.

```bash
pip install assevra==0.6.0
python -m assevra.reference --out-dir reference-output
```

Open the before and after HTML reports. The executable synthetic refund workflow fails before its authorization fix and passes the same declared assertions after it. Installation downloads packages; the example runs locally without a model or API key.

- [Getting started](/docs/getting-started): run the example and adapt it.
- [Integrations](/docs/integrations): choose an SDK, recorder, trace adapter, or export recipe.
- [Concepts](/docs/concepts): understand scope, missing evidence, and decisions.
- [CI](/docs/ci): block failed or incomplete releases.
- [Methodology](/docs/methodology): read the assumptions behind each measurement.
- [Schema contracts](/docs/schemas): consume versioned artifacts.
- [Migration from 0.5](https://github.com/assevra/assevra/blob/main/docs/MIGRATING-0.6.md): account for the v2 release semantics.

The framework does not infer your business requirements from a trace. Declare the required dimensions, supply representative labeled cases, and calibrate model judgments with human labels before relying on them.
