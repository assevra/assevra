---
layout: ../../layouts/DocsLayout.astro
title: Integrations
description: One command per tool you already run — OpenTelemetry, LangGraph, Langfuse, Phoenix, the OpenAI Agents SDK, Anthropic.
eyebrow: Using it
---

Assevra deliberately does not execute your agent. It scores outputs you have
already captured — so the only thing between a team and a scorecard is getting
their existing traces into Assevra's shape.

Every hour spent writing that glue is an hour not spent evaluating, so the glue
ships with the tool:

```bash
assevra integrate --list
assevra integrate langgraph
assevra integrate langfuse --out INTEGRATION.md
```

Each guide prints the capture snippet, the export command, and the exact
`bootstrap` invocation for that format.

| Target          | Format      | Notes                                             |
| --------------- | ----------- | ------------------------------------------------- |
| `otel`          | `otel`      | OpenTelemetry / OpenInference / OpenLLMetry spans |
| `langgraph`     | `generic`   | Run state and message history                     |
| `langfuse`      | `generic`   | Observations exported as JSON                     |
| `phoenix`       | `otel`      | Arize Phoenix spans (OpenInference)               |
| `openai-agents` | `openai`    | The Agents SDK trace export                       |
| `anthropic`     | `anthropic` | Messages API logs                                 |

## OpenTelemetry

If your agent is already instrumented, there is nothing to add. Assevra reads
OTLP exports directly — both the OpenInference convention (`input.value` /
`output.value`) and OpenLLMetry (`gen_ai.prompt.*` / `gen_ai.completion.*`), in
nested `resourceSpans` form or as a flat list of spans.

```python
from opentelemetry import trace

tracer = trace.get_tracer("my-agent")
with tracer.start_as_current_span("agent.turn") as span:
    span.set_attribute("input.value", user_message)
    output = agent.run(user_message)
    span.set_attribute("output.value", output)
```

```bash
assevra bootstrap --from spans.json --format otel --out evals/agent.jsonl
```

Spans carry no answer key — nothing in a trace knows whether the agent _should_
have refused. That judgment is the part only you can supply, and it is exactly
what `bootstrap` leaves blank with a per-row hint.

## LangGraph

LangGraph state is a dict, so it maps cleanly onto rows: the last human message
is the input, the last AI message the output, and the tool calls come across
intact for the `tool_call` and `action_correctness` dimensions.

```python
import json

records = []
for example_input in inputs:
    state = graph.invoke({"messages": [("user", example_input)]})
    final = state["messages"][-1]
    records.append({
        "input": example_input,
        "agent_output": final.content,
        "tool_calls": [
            {"name": c["name"], "arguments": c.get("args", {})}
            for c in getattr(final, "tool_calls", []) or []
        ],
    })

with open("traces.jsonl", "w") as fh:
    for record in records:
        fh.write(json.dumps(record) + "\n")
```

Running the same input several times and giving those runs a shared `case_id`
unlocks pass^k and the flaky-case report — worth doing for any graph with
branching, where run-to-run variance is the whole risk.

## Langfuse

Langfuse observations export with `input` and `output` fields, which are already
two of Assevra's field aliases — the generic adapter reads them with no mapping.

```python
import json
from langfuse import Langfuse

client = Langfuse()
page = client.api.observations.get_many(type="GENERATION", limit=200)
with open("traces.json", "w") as fh:
    json.dump([o.dict() for o in page.data], fh)
```

```bash
assevra bootstrap --from traces.json --out evals/agent.jsonl
```

If your project nests the prompt under a custom key, map it explicitly:
`--input-field <key> --output-field <key>`.

## Arize Phoenix

Phoenix stores OpenInference spans, which the `otel` adapter reads natively.

```python
import phoenix as px

spans = px.Client().get_spans_dataframe()
spans.to_json("traces.json", orient="records")
```

```bash
assevra bootstrap --from traces.json --format otel --out evals/agent.jsonl
```

## OpenAI Agents SDK

```python
import json
from agents import Runner

records = []
for prompt in prompts:
    result = await Runner.run(agent, prompt)
    records.append({
        "messages": [{"role": "user", "content": prompt}],
        "choices": [{"message": {"role": "assistant", "content": result.final_output}}],
    })

with open("traces.json", "w") as fh:
    json.dump(records, fh)
```

```bash
assevra bootstrap --from traces.json --format openai --out evals/agent.jsonl
```

## Anthropic Messages API

Log the request and the response and you have a dataset draft. The `anthropic`
adapter reads user/assistant messages and the system prompt — which is usually
_the grounding context itself_.

```python
message = client.messages.create(
    model="claude-opus-4-8",
    max_tokens=1024,
    system=policy_text,
    messages=[{"role": "user", "content": prompt}],
)

record = {
    "model": message.model,
    "system": policy_text,
    "messages": [
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": message.content[0].text},
    ],
    "usage": {
        "input_tokens": message.usage.input_tokens,
        "output_tokens": message.usage.output_tokens,
    },
}
```

Recording `usage` is what turns the `cost` dimension on: set `budgets.price` in
`.assevra.yml` and Assevra prices each row and gates on the budget.

## CSV and anything else

```bash
assevra bootstrap --from rows.csv --input-field question --output-field answer
```

Column and field names are matched against a list of common aliases
(`prompt`/`question`/`query`, `response`/`completion`/`answer`,
`context`/`reference`/`retrieved_context`), or mapped explicitly.

For a house format worth reusing, register an adapter through the
[SDK](/docs/sdk#extending) and `--format your-name` will find it.

## Judge providers

Separate from trace formats: which vendor serves the judged dimensions. Anthropic,
OpenAI, Azure, Bedrock, Gemini, any OpenAI-compatible local endpoint (Ollama,
vLLM, LM Studio — with **no third-party package**), or the deterministic offline
`mock`. See [Configuration → judge](/docs/configuration#judge).
