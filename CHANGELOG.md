# Changelog

All notable changes to Assevra are recorded here. The project follows
semantic-ish versioning; the reported "measured with Assevra vX.Y" number is
bumped whenever a scorer or rubric change could change a reported score.

## [0.3.0] — 2026-07-05

### Added
- **Agent Card (`assevra attest`).** Maps a scorecard's measured evidence to the
  control families of the EU AI Act, NIST AI RMF (incl. the Generative AI
  Profile), ISO/IEC 42001, and the OWASP Top 10 for LLM Applications — the
  auditor/procurement-facing artifact that bridges eval results and a security
  review. Writes `agent-card.md` and `agent-card.json`, notes signed provenance
  when given a `--signature`, and is framed throughout as evidence/due-care, **not
  a certification, compliance determination, or legal advice** (mappings are
  indicative).
- **Judge panels (a jury).** `run --judge-panel m1,m2,m3` scores the judge
  dimensions with several models and aggregates them — a 1–5 grounding score by
  median, a safety refusal verdict by majority — surfacing panelist
  *disagreement* (a split vote) on the row, since disagreement is itself a signal.
- **Judge calibration.** `assevra calibrate --dataset holdout.jsonl` runs the
  judge (or panel) over a human-labeled hold-out and reports judge-vs-human
  agreement: raw accuracy, Cohen's κ (chance-corrected), and
  sensitivity/specificity, per dimension and overall. Exits non-zero below the
  κ ≥ 0.85 trust bar (METHODOLOGY.md §4), automating a step previously only
  described.
- **pass^k and run-to-run consistency** — group repeated trials of the same input
  with a shared `case_id` and the scorecard reports, per dimension, the
  **consistency** (share of repeated cases whose trials all agree, with flaky
  cases listed) and **pass^k** (unbiased estimate that k independent attempts all
  pass, `C(passes,k)/C(trials,k)`). `run --pass-k K` sets k (default 2). Surfaces
  in Markdown, JSON, and HTML; omitted entirely on single-trial datasets, so
  existing scorecards are unchanged.
- **Reliability trend tracking** — `assevra run --history <file>` records each run
  and compares it to the previous one, flagging a per-dimension move only when it
  falls outside the previous 95% interval or crosses a threshold. `--label`,
  `--baseline`, and `--fail-on-regression`; new `assevra history` command.

### Fixed
- Judge prompts embedded a literal JSON example whose braces collided with
  `str.format` fields, raising `KeyError` on any real judge run (never hit in CI,
  where judge dimensions are skipped without an API key). Escaped the braces so
  grounding and safety judging work.

## [0.2.0] — 2026-07-05

### Added
- **`assevra bootstrap`** — draft a dataset from captured traces instead of
  hand-authoring JSONL from a blank page. Fills the captured fields
  (`input`, `agent_output`, `context`) and leaves only the answer key for you,
  with a per-row `_review` hint. Three dependency-free, auto-detected adapters:
  generic JSONL (field-alias detection), OpenAI chat logs, and OpenTelemetry
  spans (OpenInference `input.value`/`output.value` and OpenLLMetry
  `gen_ai.prompt.*`/`gen_ai.completion.*`).
- **Cryptographic signing** — `assevra keygen`, `assevra sign` / `run --sign`,
  and `assevra verify`. Ed25519 detached signatures over a canonical
  serialization of the scorecard make it tamper-evident; `verify --public-key`
  pins the signer to prove authorship. Behind the optional `[sign]` extra.
- `SECURITY.md` with scorecard-verification and vulnerability-reporting guidance.
- First test suite: `tests/test_bootstrap.py`, `tests/test_signing.py`,
  `tests/test_pii.py` (run under pytest or standalone).
- Pages deployed via a concurrency-controlled GitHub Actions workflow.

### Changed
- README and landing page repositioned around the differentiated wedge: a
  portable, signable **artifact** (not a dashboard), honest 95% Wilson error
  bars, and offline/deterministic-first scoring.

### Fixed
- **PII scorer / eval-gate:** the regex hard-block patterns (SSN, credit card,
  bank number) now always run as a guaranteed floor and Presidio augments them,
  so the zero-tolerance guarantee no longer depends on Presidio's per-entity
  confidence scoring (which could score a bare SSN below the floor and let a
  planted leak slip past the gate).

## [0.1.0] — 2026-07-04

- Initial release: the Assevra Reliability Scorecard — four dimensions
  (grounding, safety/refusal, PII-leak, task-completion), each scored against a
  fixed threshold with a 95% Wilson confidence interval and a conjunction
  verdict. Markdown, JSON, and self-contained HTML reports. CI gate via
  `--gate`. Archived on Zenodo with a citable DOI.
