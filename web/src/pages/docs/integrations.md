---
layout: ../../layouts/DocsLayout.astro
title: Integrations
description: One command per tool you already run — OpenTelemetry, LangGraph, Langfuse, Phoenix, the OpenAI Agents SDK, Anthropic.
eyebrow: Using it
---

Assevra provides a Python SDK and recorder, serialized trace adapters, and capture/export recipes. `capture` can execute a command you supply. The integrations below are not vendor partnerships.

| Stack                | Available interface                                       |
| -------------------- | --------------------------------------------------------- |
| Python               | SDK and recorder                                          |
| LangGraph            | Full-message-history capture recipe                       |
| OpenAI Agents        | Run-item and function-call capture recipe                 |
| OTel / Phoenix       | Supported serialized OTLP/OpenInference adapter           |
| Langfuse             | Paginated observation export recipe                       |
| MCP tool definitions | JSON Schema contract import; not a live server connection |

Local fixtures test serialization and normalization. SDK recipes are based on vendor documentation; run a smoke test against your own installed SDK and hosted service. Preserve context, tool results, case identity, and observed final state where relevant. Spans alone do not establish a complete agent trial: select the appropriate root run or export an explicitly assembled trajectory.

```bash
assevra integrate --list
assevra integrate langgraph
```

## LangGraph

```python
import json

records = []
for example_input in inputs:
    state = graph.invoke({"messages": [("user", example_input)]})
    final = state["messages"][-1]
    records.append({
        "input": example_input,
        "agent_output": final.content,
        # Carry the calls through: they feed `tool_call` and `action_correctness`.
        "tool_calls": [
            {"name": c["name"], "arguments": c.get("args", {})}
            for message in state["messages"]
            for c in getattr(message, "tool_calls", []) or []
        ],
    })

with open("traces.jsonl", "w") as fh:
    for record in records:
        fh.write(json.dumps(record) + "\n")
```

```bash
# The capture step above already wrote traces.jsonl.
mv traces.jsonl traces.json
```

```bash
assevra bootstrap --from traces.json --format generic --out evals/agent.jsonl
```

## OpenAI Agents SDK

```python
import json
from agents import Agent, Runner

records = []
for prompt in prompts:
    result = await Runner.run(agent, prompt)
    items = result.to_input_list()
    records.append({
        "input": prompt,
        "agent_output": str(result.final_output),
        "trajectory": items,
        "tool_calls": [{"name": item["name"], "arguments": item.get("arguments", "{}")}
                       for item in items if item.get("type") == "function_call"],
        "tool_results": [item for item in items if item.get("type") == "function_call_output"],
    })

with open("traces.json", "w") as fh:
    json.dump(records, fh)
```

```bash
# The capture step above already wrote traces.json.
```

```bash
assevra bootstrap --from traces.json --format generic --out evals/agent.jsonl
```

## Arize Phoenix

```python
# Phoenix instruments through OpenInference; if traces appear in the Phoenix UI,
# they are already in the shape Assevra reads.
import phoenix as px
px.launch_app()
```

```python
import json
from phoenix.client import Client

spans = Client().spans.get_spans_dataframe()
spans.to_json("traces.json", orient="records")
```

```bash
assevra bootstrap --from traces.json --format otel --out evals/agent.jsonl
```

## Langfuse

```python
# Langfuse's decorators or SDK already record every generation. Nothing to add.
from langfuse import observe

@observe()
def handle(message: str) -> str:
    return agent.run(message)
```

```python
# Export the observations you want to evaluate.
import json
from langfuse import Langfuse

client = Langfuse()
records, page_number = [], 1
while True:
    page = client.api.observations.get_many(type="GENERATION", limit=100, page=page_number)
    records.extend(json.loads(o.json()) for o in page.data)
    if len(page.data) < 100:
        break
    page_number += 1
with open("traces.json", "w") as fh:
    json.dump(records, fh)
```

```bash
assevra bootstrap --from traces.json --format generic --out evals/agent.jsonl
```

## OpenTelemetry

```python
# Any OTel-instrumented LLM app already emits what Assevra needs. If you are
# starting from scratch, record the two attributes that matter:
from opentelemetry import trace

tracer = trace.get_tracer("my-agent")
with tracer.start_as_current_span("agent.turn") as span:
    span.set_attribute("input.value", user_message)
    output = agent.run(user_message)
    span.set_attribute("output.value", output)
```

```bash
# Point your collector at a file exporter, or dump spans you already store:
# any OTLP JSON export works, including a raw `resourceSpans` document.
cp $OTEL_EXPORT_DIR/spans.json traces.json
```

```bash
assevra bootstrap --from traces.json --format otel --out evals/agent.jsonl
```

## Anthropic Messages API

```python
import json

log = []
for prompt in prompts:
    message = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=1024,
        system=policy_text,
        messages=[{"role": "user", "content": prompt}],
    )
    log.append({
        "model": message.model,
        "system": policy_text,
        "messages": [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": message.content[0].text},
        ],
        # Cost and latency become gateable dimensions once you record them.
        "usage": {
            "input_tokens": message.usage.input_tokens,
            "output_tokens": message.usage.output_tokens,
        },
    })

with open("traces.json", "w") as fh:
    json.dump(log, fh)
```

```bash
# The capture step above already wrote traces.json.
```

```bash
assevra bootstrap --from traces.json --format anthropic --out evals/agent.jsonl
```

Review the drafted rows and add acceptance criteria before running a release gate. The generic API export may include sensitive fields; retain only the evidence your evaluation needs.

Vendor references: [Langfuse query SDK](https://langfuse.com/docs/api-and-data-platform/features/query-via-sdk), [Phoenix span exports](https://arize.com/docs/phoenix/tracing/how-to-tracing/importing-and-exporting-traces/extract-data-from-spans), [OpenAI Agents run results](https://openai.github.io/openai-agents-python/results/). Langfuse deployments may use different observation API versions; this recipe uses the paginated v1 compatibility API.
