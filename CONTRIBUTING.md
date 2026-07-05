# Contributing to Assevra

Assevra is a personal open-source research project maintained by Veera Ravindra
Divi. Contributions from the research and engineering community are welcome.

## What is in scope

- New scorer families that follow the methodology (a definition, an explicit
  scoring method, a stated threshold, and a reported confidence interval — see
  [METHODOLOGY.md](METHODOLOGY.md)).
- Additional golden dataset rows that exercise a dimension more thoroughly.
  Rows must be clearly synthetic; do not contribute real personal data.
- Fixes to the deterministic detectors and the judge rubrics.
- Documentation that makes the methodology clearer or easier to cite.

## Ground rules

1. **Every reliability claim ties to a metric and a threshold.** A scorer that
   returns a number without a pass threshold and a sample-size-aware interval is
   not complete.
2. **Deterministic before judge.** If a property can be detected with a rule
   (a leaked SSN, a missing required slot), detect it — do not ask a model.
3. **Freeze what affects a score.** The judge model, the judge prompt, and the
   dataset are all inputs to a score. Changing any of them changes the number;
   say so in the PR.
4. **State what a scorer does not measure.** Honesty about scope is part of the
   methodology, not an afterthought.

## Before you open a PR

- Make sure every Python file compiles: `python -m compileall assevra`.
- Make sure the dataset parses and the CLI runs end-to-end on the deterministic
  scorers (no API key needed):

  ```bash
  python -m assevra run --dataset datasets/golden.jsonl
  ```

- Make sure the `eval-gate` workflow passes.

For a new scorer family or a change to a rubric or threshold, please open an
issue first so we can agree on the definition before you build it.
