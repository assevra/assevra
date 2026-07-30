# Contributing to Assevra

Assevra is a personal open-source research project maintained by Veera Ravindra
Divi. Contributions from the research and engineering community are welcome.

New here? [`good first issue`](https://github.com/assevra/assevra/labels/good%20first%20issue)
collects small, self-contained tasks — each with the file to change and the test
to add. [GOVERNANCE.md](GOVERNANCE.md) covers how decisions get made and the bar
a methodology change has to clear; [ROADMAP.md](ROADMAP.md) covers what is
planned and what is deliberately not.

## Setting up

```bash
git clone https://github.com/assevra/assevra.git && cd assevra
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

python -m pytest                 # the whole suite, offline, in under a second
assevra demo --provider mock     # exercise the judged path with no API key
```

## What is in scope

- **New dimensions** that meet the methodology bar (below).
- **Trace adapters, judge providers, and reporters** — all registrable, see the
  [SDK docs](https://assevra.ai/docs/sdk#extending).
- **Fixes to the deterministic detectors and the judge rubrics**, ideally with a
  failing case that motivated them.
- **Golden dataset rows** that exercise a dimension more thoroughly. Rows must be
  clearly synthetic; never contribute real personal data.
- **Case studies** from a domain not yet covered. These are among the most useful
  contributions, because they bring a failure mode nobody here thought of.
- **Documentation** that makes the methodology clearer or the tool faster to
  adopt.

Out of scope, deliberately: running your agent, a hosted service or dashboard,
and anything that reads as certification. See
[GOVERNANCE.md](GOVERNANCE.md#what-is-in-scope).

## Ground rules

1. **Every reliability claim ties to a metric and a threshold.** A scorer that
   returns a number without a pass threshold and a sample-size-aware interval is
   not complete.
2. **Deterministic before judge.** If a property can be detected with a rule —
   a leaked SSN, a malformed tool call, a missing required slot — detect it. Do
   not ask a model.
3. **Freeze what affects a score.** The judge model, the judge prompt, a
   detector's patterns, a threshold, and the dataset are all inputs to a score.
   Changing any of them changes the number; say so in the PR and update the
   golden snapshot.
4. **State what a scorer does not measure.** Honesty about scope is part of the
   methodology, not an afterthought — and it travels with the artifact in the
   dimension notes.
5. **Skipped is not passed.** A dimension that could not run must never be
   reported as passing.

## Adding a dimension

Open an **issue first** (there is a
[template](https://github.com/assevra/assevra/issues/new?template=new_dimension.md)).
The definition is the hard part, and agreeing on it before the implementation
saves you a rewrite.

A scorer module declares a handful of constants and one function:

```python
DIMENSION           = "policy_citation"
MODE                = "deterministic"      # or "llm-judge"
DIMENSION_THRESHOLD = 1.00
SUMMARY             = "Did the answer cite the governing policy id?"
ANSWER_KEY          = ("expected_policy_id",)   # any one of these labels a row
REQUIRES            = ("agent_output",)         # structurally required
LABEL_HINT          = "Set expected_policy_id to the id the answer must cite."

def score(rows, judge=None, options=None) -> DimensionResult: ...
```

That declaration is all Assevra needs to wire the dimension into the scorecard,
the validator, the config, and the CI gate. Optional hooks: `validate_row(row,
options)` for extra structural checks, and `is_labeled(row, options)` when
labeling depends on the config.

Built-ins register in `assevra/scorers/__init__.py`; third-party scorers use
`assevra.register_scorer_module(...)`.

## Before you open a PR

```bash
python -m pytest                                  # unit + integration + snapshot
assevra validate datasets/golden.jsonl --strict   # the golden set stays fully labeled
assevra run --gate --judge-provider mock --config none --dataset datasets/golden.jsonl
python tests/snapshot.py --check                  # did any number move?
```

If a number *should* move, run `python tests/snapshot.py --update` and commit the
diff — so a reviewer agrees with the change rather than absorbing it.

Tests live in `tests/` and run both under pytest and standalone
(`python tests/test_pii.py`). Write a test as the failure it is meant to catch,
not as a description of the code.

## Touching the artifact JSON

The schemas in `assevra/schemas/` are a **published contract**. Within major
version 1, fields are only added — never removed, renamed, or repurposed.

If you change them: update `assevra/schemas/*.json`, re-sync
`web/public/schema/v1/` (CI compares the two byte-for-byte), and make sure
`tests/test_schemas.py` passes.

## The website and docs

The site and documentation live in `web/` (Astro). Docs pages are Markdown under
`web/src/pages/docs/`; the sidebar order lives in `web/src/data/docs-nav.ts`.

```bash
cd web && npm ci && npm run dev
npm run validate      # astro check + eslint + prettier + build
```

## Reporting a vulnerability

Privately, never in a public issue — see [SECURITY.md](SECURITY.md).
