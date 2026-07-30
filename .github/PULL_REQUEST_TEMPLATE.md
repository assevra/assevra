<!--
Thanks for contributing. Most of this is a two-minute checklist; the one section
that genuinely matters is "Does this change a reported number?" — please do not
skip it.
-->

## What this changes

<!-- One or two sentences. What is different afterwards? -->

## Why

<!-- The failure it fixes, or the gap it closes. A concrete case beats a category. -->

## Does this change a reported number?

The judge model, a judge prompt, a detector's patterns, a threshold, and the
dataset are all **inputs to a score**. Changing any of them changes what
"measured with Assevra v0.4" means.

- [ ] **No** — behaviour is identical for every existing dataset.
- [ ] **Yes** — and I have:
  - [ ] said so explicitly here, with which dimension moves and in which direction
  - [ ] run `python tests/snapshot.py --update` and committed the diff
  - [ ] bumped `ASSEVRA_VERSION` if the change alters what a reported number means

## Checklist

- [ ] `python -m pytest` passes.
- [ ] New behaviour has a test, and the test is written as the failure it catches.
- [ ] `assevra validate datasets/golden.jsonl --strict` passes.
- [ ] `assevra run --gate --judge-provider mock --config none --dataset datasets/golden.jsonl` passes.

### If this adds or changes a dimension

- [ ] It ships a definition, a scoring method, a threshold, an interval, and a
      stated limit (see [GOVERNANCE.md](../GOVERNANCE.md)).
- [ ] It is deterministic, or the pull request explains why judgment is
      irreducible for this property.
- [ ] The rubric is pinned and hashed into the dimension notes.
- [ ] `ANSWER_KEY` / `LABEL_HINT` are declared, so `assevra validate` knows what a
      labeled row looks like and what to tell someone who has not written one.
- [ ] The demo dataset and `datasets/golden.jsonl` cover it.

### If this touches the artifact JSON

- [ ] Fields are **added**, never removed, renamed, or repurposed — the schema is
      a published contract within major version 1.
- [ ] `assevra/schemas/*.json` updated, and `web/public/schema/v1/` re-synced.
- [ ] `tests/test_schemas.py` passes.
