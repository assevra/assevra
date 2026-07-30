"""
First-party integrations: one command per tool you already run.

Assevra deliberately does not execute your agent. It scores outputs you have
already captured — which means the only thing standing between a team and a
scorecard is getting their existing traces into Assevra's shape. Every hour spent
writing that glue is an hour not spent evaluating, so the glue ships here.

    assevra integrate langfuse

prints (or writes) exactly what that tool needs: the export command, the
``bootstrap`` invocation that reads its format, and the two or three lines of
Python for capturing traces going forward. Six targets are supported today, all
of them chosen because they are where agent traces actually live:

``otel``           OpenTelemetry / OpenInference / OpenLLMetry spans
``langgraph``      LangGraph run state and message history
``langfuse``       Langfuse observations exported as JSON
``phoenix``        Arize Phoenix spans (OpenInference)
``openai-agents``  the OpenAI Agents SDK trace export
``anthropic``      Anthropic Messages API logs

The reading side is already generic — :mod:`assevra.bootstrap` understands OTel,
OpenAI, Anthropic, CSV, and generic JSONL — so most of these resolve to "export,
then bootstrap with this format". That is the honest answer, and printing it is
worth more than a wrapper that hides one flag.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Integration:
    name: str
    title: str
    bootstrap_format: str
    summary: str
    capture: str
    export: str
    notes: str = ""

    def render(self, dataset: str = "evals/agent.jsonl") -> str:
        lines = [
            f"# {self.title}",
            "",
            self.summary,
            "",
            "## 1. Capture",
            "",
            self.capture.strip(),
            "",
            "## 2. Export what you captured",
            "",
            self.export.strip(),
            "",
            "## 3. Draft an Assevra dataset from it",
            "",
            "```bash",
            f"assevra bootstrap --from traces.json --format {self.bootstrap_format} \\",
            f"    --out {dataset}",
            "```",
            "",
            "Every drafted row arrives tagged `needs-review` with a one-line hint for the",
            "answer key it still needs. Fill those in, then:",
            "",
            "```bash",
            f"assevra validate {dataset}   # confirm every row is LABELED",
            "assevra run --gate            # score, gate, and write the artifacts",
            "```",
        ]
        if self.notes:
            lines += ["", "## Notes", "", self.notes.strip()]
        return "\n".join(lines) + "\n"


INTEGRATIONS: dict[str, Integration] = {
    "otel": Integration(
        name="otel",
        title="OpenTelemetry",
        bootstrap_format="otel",
        summary=(
            "Assevra reads OTLP exports directly — both the OpenInference "
            "(`input.value` / `output.value`) and OpenLLMetry (`gen_ai.prompt.*` / "
            "`gen_ai.completion.*`) conventions, in nested `resourceSpans` form or as "
            "a flat list of spans. If your agent is already instrumented, there is "
            "nothing to add."
        ),
        capture="""\
```python
# Any OTel-instrumented LLM app already emits what Assevra needs. If you are
# starting from scratch, record the two attributes that matter:
from opentelemetry import trace

tracer = trace.get_tracer("my-agent")
with tracer.start_as_current_span("agent.turn") as span:
    span.set_attribute("input.value", user_message)
    output = agent.run(user_message)
    span.set_attribute("output.value", output)
```""",
        export="""\
```bash
# Point your collector at a file exporter, or dump spans you already store:
# any OTLP JSON export works, including a raw `resourceSpans` document.
cp $OTEL_EXPORT_DIR/spans.json traces.json
```""",
        notes=(
            "OTel spans carry no answer key — nothing in a trace knows whether the "
            "agent *should* have refused. That judgment is the part only you can "
            "supply, which is exactly what `bootstrap` leaves blank for you."
        ),
    ),
    "langgraph": Integration(
        name="langgraph",
        title="LangGraph",
        bootstrap_format="generic",
        summary=(
            "LangGraph state is a dict, so it maps cleanly onto Assevra rows: the last "
            "human message is the input, the last AI message the output, and the tool "
            "calls come across intact for the tool-call and action-correctness "
            "dimensions."
        ),
        capture="""\
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
            for c in getattr(final, "tool_calls", []) or []
        ],
    })

with open("traces.jsonl", "w") as fh:
    for record in records:
        fh.write(json.dumps(record) + "\\n")
```""",
        export="""\
```bash
# The capture step above already wrote traces.jsonl.
mv traces.jsonl traces.json
```""",
        notes=(
            "Running the same input several times and giving those runs a shared "
            "`case_id` unlocks pass^k and the flaky-case report — worth doing for "
            "graphs with any branching, where run-to-run variance is the whole risk."
        ),
    ),
    "langfuse": Integration(
        name="langfuse",
        title="Langfuse",
        bootstrap_format="generic",
        summary=(
            "Langfuse observations export as JSON with `input` and `output` fields, "
            "which are two of Assevra's own field aliases — so the generic adapter "
            "reads them with no mapping."
        ),
        capture="""\
```python
# Langfuse's decorators or SDK already record every generation. Nothing to add.
from langfuse.decorators import observe

@observe()
def handle(message: str) -> str:
    return agent.run(message)
```""",
        export="""\
```python
# Export the observations you want to evaluate.
import json
from langfuse import Langfuse

client = Langfuse()
page = client.api.observations.get_many(type="GENERATION", limit=200)
with open("traces.json", "w") as fh:
    json.dump([o.dict() for o in page.data], fh)
```""",
        notes=(
            "If your Langfuse project nests the prompt under a custom key, map it "
            "explicitly: `--input-field <key> --output-field <key>`."
        ),
    ),
    "phoenix": Integration(
        name="phoenix",
        title="Arize Phoenix",
        bootstrap_format="otel",
        summary=(
            "Phoenix stores OpenInference spans, which Assevra's `otel` adapter reads "
            "natively via `input.value` / `output.value`."
        ),
        capture="""\
```python
# Phoenix instruments through OpenInference; if traces appear in the Phoenix UI,
# they are already in the shape Assevra reads.
import phoenix as px
px.launch_app()
```""",
        export="""\
```python
import json
import phoenix as px

spans = px.Client().get_spans_dataframe()
spans.to_json("traces.json", orient="records")
```""",
    ),
    "openai-agents": Integration(
        name="openai-agents",
        title="OpenAI Agents SDK",
        bootstrap_format="openai",
        summary=(
            "The Agents SDK records the full message list per run. Assevra's `openai` "
            "adapter reads that shape directly, including `{request, response}` pairs."
        ),
        capture="""\
```python
import json
from agents import Agent, Runner

records = []
for prompt in prompts:
    result = await Runner.run(agent, prompt)
    records.append({
        "messages": [{"role": "user", "content": prompt}],
        "choices": [{"message": {"role": "assistant", "content": result.final_output}}],
    })

with open("traces.json", "w") as fh:
    json.dump(records, fh)
```""",
        export="""\
```bash
# The capture step above already wrote traces.json.
```""",
    ),
    "anthropic": Integration(
        name="anthropic",
        title="Anthropic Messages API",
        bootstrap_format="anthropic",
        summary=(
            "Log the request and the response and you have an Assevra dataset draft: "
            "the `anthropic` adapter reads user/assistant messages and the system "
            "prompt (which usually *is* the grounding context)."
        ),
        capture="""\
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
```""",
        export="""\
```bash
# The capture step above already wrote traces.json.
```""",
        notes=(
            "Recording `usage` is what turns the `cost` dimension on: set "
            "`budgets.price` in `.assevra.yml` and Assevra prices each row and gates "
            "on the budget."
        ),
    ),
}


def names() -> list[str]:
    return sorted(INTEGRATIONS)


def get(name: str) -> Integration:
    key = name.strip().lower()
    aliases = {
        "opentelemetry": "otel",
        "openinference": "otel",
        "openllmetry": "otel",
        "arize": "phoenix",
        "openai_agents": "openai-agents",
        "openai": "openai-agents",
        "claude": "anthropic",
    }
    key = aliases.get(key, key)
    if key not in INTEGRATIONS:
        raise KeyError(f"unknown integration {name!r}; known: {', '.join(names())}")
    return INTEGRATIONS[key]
