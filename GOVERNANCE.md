# Governance

Assevra is a small project with a large claim: that a number in its scorecard
means something specific. Governance here exists to protect that claim.

## Current model: BDFL, stated plainly

Assevra is maintained by **Veera Ravindra Divi**, who has final say on scope,
methodology, and releases. This is not aspiration-as-documentation: an
open-source project with one maintainer should say so, because a contributor
deserves to know who decides and how long a review will take.

The intent is to grow past this. The path is written down below rather than left
implicit, so it is a commitment and not a hope.

## What is in scope

Assevra measures the reliability of agent outputs you have already captured, and
emits portable evidence about them. In scope:

- New **dimensions** that meet the methodology bar (below).
- New **trace adapters**, **judge providers**, and **reporters**.
- Detector and rubric fixes, especially ones backed by a failing case.
- Documentation that makes the methodology clearer, or the tool faster to adopt.

Out of scope, deliberately:

- **Running your agent.** Assevra scores outputs; orchestration belongs to your
  framework. This boundary is what keeps Assevra usable with every framework
  rather than competing with them.
- **A hosted service, a dashboard, or an account.** The artifact is the product.
- **Certification.** Assevra produces evidence. Conformity determinations are
  made by auditors and authorities, not by a tool, and any wording that blurs
  that line will be rejected.

## The methodology bar

A change that can move a reported number has to clear all five:

1. **A definition.** What property is being measured, in one sentence a
   non-specialist can check.
2. **An explicit scoring method.** Deterministic if a rule can decide it; a
   pinned, hashed rubric if it genuinely needs judgment.
3. **A stated threshold**, with the reasoning for its level.
4. **A reported interval.** Every dimension carries its sample size and a 95%
   Wilson interval. A number without a bar is not a gate.
5. **A stated limit.** What the scorer does *not* measure, written into the
   dimension notes so it travels with the artifact.

"Deterministic before judge" is not a style preference. A rule is reproducible,
free, and auditable; a model is none of those. Proposals that ask a model to do
something a regex already does will be sent back.

## Changes that move numbers

The judge model, the judge prompt, a detector's patterns, a threshold, and the
dataset are all **inputs to a score**. Changing any of them changes the number,
which means:

- The pull request must say so in its description.
- `python tests/snapshot.py --update` must be run, so the diff in
  `tests/snapshots/golden.json` is reviewed rather than absorbed.
- `ASSEVRA_VERSION` is bumped when a change would alter a reported number, so
  "measured with Assevra v0.4" stays a meaningful statement.

## The artifact contract

The JSON schemas in `assevra/schemas/` are a published API. Within schema major
version 1, fields are **only added** — never removed, renamed, or repurposed. A
scorecard produced by any 1.x-schema release validates against the published
schema forever.

Breaking that means a new `/schema/v2/` path and a major release, and it needs a
reason stronger than tidiness. Someone's pipeline parses this.

## Decisions

- **Ordinary changes** — bug fixes, docs, new adapters and providers, new
  patterns for existing detectors: a maintainer review and a green CI run.
- **Methodology changes** — new dimensions, threshold moves, rubric edits: open
  an **issue first**. Agreeing on the definition before the implementation saves
  everyone a rewrite, and the definition is the hard part.
- **Scope changes** — anything that touches the boundaries above: a Discussion,
  then an issue, then code.

Disagreements are settled in the open on the issue. If consensus does not
emerge, the maintainer decides and records why.

## Releases

- **Patch** (0.4.x) — fixes that cannot move a reported number.
- **Minor** (0.x.0) — new dimensions, commands, providers; additive schema
  changes.
- **Major** — a change to the artifact contract or the methodology's shape.

Every release: `CHANGELOG.md` updated, the golden snapshot regenerated and
reviewed, CI green across the Python matrix, the wheel smoke-tested from a clean
environment, and a Zenodo archive minted so the DOI keeps resolving.

## Becoming a maintainer

There is no secret bar and no invitation-only list. Sustained, high-quality
contribution — several merged pull requests, useful review of others' work, and
demonstrated care about the methodology rather than only the code — is the whole
criterion. If that describes you, say so on an issue; the maintainer will either
agree or explain what is missing.

Maintainers get commit access and a vote on methodology changes. Once there are
three, this document is replaced by a version that no longer says "BDFL".

## Security

Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).
Never in a public issue.

## Code of conduct

Participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
