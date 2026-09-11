# Migrating to Assevra 0.6

0.6 changes the meaning of release success and therefore publishes schema v2. Hosted v1 contracts remain unchanged.

- `overall_pass` is true only when `decision == "PASS"`. Use `decision` to distinguish FAIL, INCOMPLETE, TRIAGE, and SELF_TEST.
- Release evaluations always perform strict dataset validation. `--no-validate` is effective only outside release purpose. Empty acceptance criteria do not constitute evidence.
- Every included dimension must complete. Use `gate.required_dimensions` (or repeated `--require-dimension`) to name dimensions even if their rows are absent.
- Mock judges and `purpose: self_test` cannot pass a release gate. Use them to exercise the evaluator, and use `python -m assevra.reference` for a runnable deterministic release example.
- Invalid judge JSON, wrong boolean types, scores outside 1–5, incomplete panels, and tied votes produce missing evidence. ERROR/ABSTAIN rows do not enter pass-rate denominators.
- Known-bad PII detector controls move to `controls`. They no longer count as successful agent runs. PII match values are redacted from diagnostic details.
- `findings` contains suggested actions and verification guidance. These are reviewed suggestions, not automatic patches or guaranteed root causes.
- `coverage`, `validation`, `required_dimensions`, and provenance hashes travel with JSON reports. A scan stays TRIAGE in downloaded JSON and HTML.
- Full imported tool schemas are retained in `json_schema` and validated using `jsonschema>=4.23,<5`. Bundle references locally. The old compact `required`/`types`/`enum` format remains supported.
- Action correctness accepts `expected_state` and `observed_state`. Expected objects match recursively as subsets; lists are exact/ordered and scalar types are significant. Missing observed state is an evaluator error.
- Required regression checks block missing or incompatible baselines. Suite hashes exclude changing agent outputs but include inputs and assertions; policy hashes include thresholds/options/scorer version. Changed datasets or judges require a newly reviewed baseline.
- The composite Action pins package 0.6.0 by default and passes inputs through environment variables and argument arrays.
- Capture preserves failed attempts and writes `<output>.manifest.json`; a partially completed capture exits nonzero.

Re-review thresholds and baseline approval with your actual use case. This release does not establish a universal minimum sample size or automatically validate a judge's calibration for your domain. Dimension confidence intervals are descriptive; repeated trials may be correlated.
