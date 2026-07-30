# Case studies

Three complete, runnable walkthroughs. Each one is the same shape: a real agent,
a scorecard that fails, the specific rows that failed, the fix, and the scorecard
that passes.

Every number quoted in these write-ups came from running the datasets in this
directory. Reproduce any of them:

```bash
cd examples/case-studies/<case>
assevra validate before.jsonl --strict
assevra run --dataset before.jsonl --out-dir out/before   # FAIL
assevra run --dataset after.jsonl  --out-dir out/after    # PASS
```

Nothing needs an API key. Where a judged dimension is involved, the case pins
`judge.provider: mock` — a deterministic offline stand-in that makes the
walkthrough reproducible byte-for-byte. The mock is **not a judge**, and each
write-up says so where it matters.

| Case | Agent | Dimensions exercised | The lesson |
|---|---|---|---|
| [**RAG assistant**](rag-assistant/) | Policy Q&A over a retrieved corpus | grounding, injection, pii, task_completion | An indirect prompt injection arriving through a *product review* — nothing the user did wrong, and nothing input validation would have caught. |
| [**Commerce agent**](commerce-agent/) | Support agent with refund and cancel tools | tool_call, action_correctness, cost, latency | A malformed call and a wrong decision look identical in a trace and are completely different problems. Also: 41,000 tokens to answer "where is my order?" |
| [**Multi-agent workflow**](multi-agent-workflow/) | Claims intake → router → adjudicator | task_completion, action_correctness, pii, safety, injection + pass^k | A dimension scoring 0.667 with **consistency 0.000** is not a quality problem. It is an agent that never behaves the same way twice. |

## What they have in common

Read across all three and the same three things keep happening:

**The interesting finding is rarely the model's fault.** A missing fact in an
answer template. A tool the agent should never have been handed. A retrieval step
pulling in the whole catalogue. Scorecards find the boring bug more often than
the exotic one, and the boring bug is the one that was going to page someone.

**The fix usually moves work out of the model.** Six of the fixes across these
three cases replace something generated with something deterministic — a
structured handoff instead of a written summary, a routing rule instead of a
judgement call, a schema check at the tool boundary. That pattern is not a
coincidence; it is what "deterministic before judge" looks like applied to the
agent rather than to the evaluation.

**The honest conclusion is always narrower than the green checkmark.** Every one
of these datasets is small, and every write-up ends by saying what the run does
*not* license you to claim. That section is not modesty. It is the part that
makes the rest of the number worth anything.

## Using these as a starting point

The fastest way to start your own evaluation is to copy the case closest to your
system and replace the rows:

```bash
cp -r examples/case-studies/commerce-agent evals/
cd evals && $EDITOR before.jsonl
```

Then generate the rest of the dataset from traces you already have:

```bash
assevra bootstrap --from your_traces.jsonl --out evals/agent.jsonl
assevra validate evals/agent.jsonl        # tells you exactly what is still unlabeled
```

## Contributing one

A case study from a domain not covered here — finance, healthcare intake, code
agents, internal tooling — is one of the most useful contributions to this
project, because it brings a failure mode nobody here thought of.

Requirements: clearly synthetic data (never real personal information), a
`before` set that genuinely fails, an `after` set that genuinely passes, and a
write-up that states what the result does *not* prove. Open an issue first so we
can agree on the shape.
