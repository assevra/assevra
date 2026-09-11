---
layout: ../../layouts/DocsLayout.astro
title: Artifact schemas
description: The scorecard is a published contract. Versioned v2 contracts with preserved v1 compatibility URLs.
eyebrow: The artifact
---

Version **2.0** accompanies Assevra 0.6. The meaning of release success changed, so new artifacts use `/schema/v2/`. Existing `/schema/v1/` contracts remain hosted unchanged. Within a schema major, fields are not renamed or repurposed.

| Schema      | URL                                                                      |
| ----------- | ------------------------------------------------------------------------ |
| Scorecard   | [/schema/v2/scorecard.schema.json](/schema/v2/scorecard.schema.json)     |
| Agent Card  | [/schema/v2/agent-card.schema.json](/schema/v2/agent-card.schema.json)   |
| Calibration | [/schema/v2/calibration.schema.json](/schema/v2/calibration.schema.json) |
| Dataset row | [/schema/v2/dataset.schema.json](/schema/v2/dataset.schema.json)         |
| Validation  | [/schema/v2/validation.schema.json](/schema/v2/validation.schema.json)   |

Schemas ship in the package, so installed applications can validate without fetching them:

```python
import json
from jsonschema import validate
from assevra import schemas

card = json.load(open("evidence/scorecard.json"))
validate(card, schemas.load("scorecard"))
print(card["decision"], card["required_dimensions"])
for finding in card["findings"]:
    print(finding["id"], finding["suggested_action"], finding["verification"])
```

`overall_pass` is true only for a complete release PASS. Read `decision` to distinguish FAIL, INCOMPLETE, TRIAGE, and SELF_TEST. Row `status` separates agent PASS/FAIL from evaluator ERROR/ABSTAIN. `sample_size` counts completed agent measurements; `attempted` includes evaluator errors.

`coverage`, `validation`, `required_dimensions`, `missing_dimensions`, `controls`, `comparison`, `suite_sha256`, and `policy_sha256` preserve the decision's scope and provenance. `findings` carries reviewed-action guidance. A signature covers canonical JSON, so these fields travel with the signed evidence.

See the [generated example JSON](/examples/refund/after/scorecard.json) for a complete current artifact, and the [migration notes](https://github.com/assevra/assevra/blob/main/docs/MIGRATING-0.6.md) for upgrade details.
