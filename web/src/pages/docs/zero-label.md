---
layout: ../../layouts/DocsLayout.astro
title: Zero-label scoring
description: Six of the nine dimensions never needed a human. Here is how to score them in minutes.
eyebrow: Start here
---

Installing Assevra takes two minutes. Writing the answer key used to take an
afternoon. Everything on this page exists to attack the afternoon.

The realisation behind it: **most dimensions never needed a human at all.**

| Dimension            | What it actually needs                                  | Human labeling |
| -------------------- | ------------------------------------------------------- | -------------- |
| `pii`                | an output to scan — the detector defines the failure    | **none**       |
| `grounding`          | the retrieved context, already in the trace             | **none**       |
| `cost`               | a budget — one line of project policy                   | **none**       |
| `latency`            | a budget — one line of project policy                   | **none**       |
| `tool_call`          | the agent's **own tool spec**, already machine-readable | **none**       |
| `injection`          | a planted canary — generated, and self-labeling         | **none**       |
| `safety`             | whether a request _should_ have been refused            | judgment       |
| `task_completion`    | which facts a correct answer owes                       | judgment       |
| `action_correctness` | which action was right                                  | judgment       |

Two commands cover the top six.

## 1. `assevra scan` — score raw traces, nothing labeled

```bash
assevra scan --from traces.jsonl --tools tools.json
```

No config file, no dataset, no answer key. It reads your traces in any format
`bootstrap` understands, works out which dimensions it can score honestly, scores
them, and — as importantly — **names what it could not score and why**.

```
[assevra] read 214 interaction(s) from traces.jsonl (format: otel)
[assevra] tool spec: openai (tools.json) — 7 tool(s), 6 with a checkable argument contract

[assevra] scored with no labeling:
[assevra]   grounding           198 rows  — scored against the context captured in the trace
[assevra]   pii                 214 rows  — scored as-is; no sanctioned_field assumed
[assevra]   tool_call            96 rows  — contract derived from the agent's own tool spec
[assevra]   cost                214 rows  — scored against budgets.cost_usd
[assevra]   latency             214 rows  — scored against budgets.latency_ms

[assevra] NOT scored — these encode intent, which no trace contains:
[assevra]   safety             Set should_refuse: true if the agent should refuse…
```

### The tool spec is the trick

`tool_call` checks that every call was well-formed and permitted. That contract
already exists in machine-readable form — the model needed it to call anything —
so point Assevra at it and the whole dimension becomes free:

```bash
assevra scan --from traces.jsonl --tools tools.json
```

Four dialects are read, by structure rather than filename:

| Shape      | Looks like                                                   |
| ---------- | ------------------------------------------------------------ |
| OpenAI     | `[{"type": "function", "function": {"name", "parameters"}}]` |
| Anthropic  | `[{"name", "input_schema"}]`                                 |
| MCP        | `{"tools": [{"name", "inputSchema"}]}`                       |
| Schema map | `{"tool_name": {<JSON Schema>}}`                             |

Omit `--tools` and Assevra looks for one in your project.

What is deliberately **not** derived: `forbidden_tools` and
`expected_tool_calls`. A spec says what the agent _can_ do. Which tool must never
be reached for in a given case is policy, and Assevra will not invent policy.

### Budgets

`cost` and `latency` need a budget, which is a project decision rather than a
per-row one:

```yaml
budgets:
  cost_usd: 0.02
  latency_ms: 4000
  price:
    input_per_mtok: 3.0
    output_per_mtok: 15.0
```

Since 0.5, `bootstrap` and `capture` carry `usage`, `cost_usd`, `latency_ms` and
`tool_calls` through from your traces, so those dimensions light up on their own.

### Scan is triage, not a gate

It says so itself. A scan tells you whether anything is obviously broken —
leaked identifiers, malformed calls, blown budgets. It cannot tell you whether
the agent did the _right thing_, because that is not in the trace.

## 2. `assevra probe` — adversarial cases that label themselves

Some dimensions cannot be scored on historical traces at all. You cannot measure
injection resistance on traces where nobody planted an injection.

Those need new inputs — and an adversarial probe can carry **its own answer key**:

```bash
assevra probe --out probes.jsonl --domain "You are a support agent for a lamp retailer."
```

| Family         | The probe                                                                                                                       | Why it is self-labeling                                          |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| `injection`    | an instruction planted in retrieved content, tool output or another agent's note, telling the agent to emit an improbable token | the token **is** the label — if it appears, the injection worked |
| `pii-bait`     | a synthetic secret in the context that the task never requires repeating                                                        | if it comes back, that is a leak                                 |
| `over-refusal` | an unambiguously benign request                                                                                                 | `should_refuse` is false by construction                         |

Canaries are seeded from the probe id, so a regenerated suite is byte-identical
and diffable in git.

## 3. `assevra capture` — close the loop with one command

Probes need answers. Rather than everyone writing the same twenty-line script:

```bash
assevra capture --from probes.jsonl --out answered.jsonl -- python my_agent.py
assevra run --dataset answered.jsonl --gate
```

The contract with your agent is the smallest one that could work, so anything can
satisfy it: **the prompt arrives on stdin, the answer comes back on stdout.**

Assevra still runs only the command _you_ typed, in your shell, with your
environment. It is a stopwatch and a file writer, not a runtime.

Two things come free:

- **`latency_ms` on every row**, measured around the call — the latency dimension
  turns on with no further work.
- **`--repeat N`** runs each input N times under a shared `case_id`, unlocking
  pass^k and the flaky-case report. Repeated trials are the most informative thing
  you can capture and the least likely to be set up by hand.

```bash
assevra capture --inputs questions.txt --out traces.jsonl --repeat 3 -- python my_agent.py
```

For in-process capture there is a recorder:

```python
from assevra.capture import Recorder

with Recorder("traces.jsonl") as rec:
    for question in questions:
        with rec.record(question, context=policy) as turn:
            turn.output = my_agent(question)
            turn.tool_calls = [{"name": c.name, "arguments": c.args} for c in calls]
```

## 4. The last three: propose, then confirm

`safety`, `task_completion` and `action_correctness` encode intent. A model can
still **draft** them — and reading a proposal takes five seconds where authoring
one takes two minutes:

```bash
assevra suggest --dataset drafted.jsonl
assevra confirm --dataset drafted.jsonl     # y / n / s / q, per row
```

> **A suggested label is not a label.** Every proposed field is recorded in a
> `_suggested` list, and `assevra validate` reports a row whose answer key is
> _entirely_ machine-proposed as **UNLABELED** — the same state as a row with no
> answer key at all. It will never satisfy `--strict`. Only `confirm` clears it.

That gate is the whole reason this feature is safe to have. An agent graded
against labels another model invented produces a number with the shape of
evidence and none of the substance; the value of a scorecard is that somebody
stood behind the answer key.

The suggestions are conservative by design. `must_include` proposals that do
**not** appear in the captured output are kept but flagged, because a proposal
that silently rewrote the test to match whatever the agent said would be the most
insidious failure available here.

## The whole path

```bash
pip install assevra
assevra scan --from traces.jsonl --tools tools.json      # ~1 min, 5 dimensions
assevra probe --out probes.jsonl                          # self-labeling
assevra capture --from probes.jsonl --out answered.jsonl -- python agent.py
assevra run --dataset answered.jsonl --gate               # 8 of 9 dimensions
```

Roughly **five minutes to a real gate**, and about twenty to a good one — with the
answer key written only where a human genuinely has to write it.

No install at all? [Drop a trace file in your browser](/try) — the same engine,
compiled to WebAssembly, running in the tab.
