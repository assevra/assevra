"""
Bootstrap an Assevra dataset from agent traces you have already captured.

The single biggest cost of evaluating an agent is not running the scorers -- it
is hand-authoring a labeled JSONL golden set from a blank page. `assevra
bootstrap` removes that blank page: point it at interactions your agent (or your
observability tool) has already logged, and it drafts an Assevra dataset with the
*captured* fields already filled in -- `input`, `agent_output`, and `context`.

What it deliberately does NOT invent is the answer key. Whether a request should
have been refused, which value was allowed to appear, which facts a correct
answer must contain -- those are judgments only you can make, so bootstrap leaves
them as empty placeholders with a one-line `_review` hint telling you exactly
what to fill for each row. You label the ambiguous part; you do not transcribe
the boring part.

Four input shapes are understood out of the box, all dependency-free:

  * ``generic``  -- JSONL where each line is one interaction. Field names are
                    detected from common aliases (prompt/question/query for input,
                    response/completion/answer for output, ...), or set explicitly
                    with ``--input-field`` / ``--output-field`` / ``--context-field``.
  * ``openai``   -- OpenAI chat-completions logs (a ``messages`` list and/or a
                    ``choices`` response), including ``{request, response}`` pairs.
  * ``anthropic`` -- Anthropic Messages API logs (user/assistant messages,
                    optionally a ``model`` field like ``claude-*``).
  * ``otel``     -- OpenTelemetry / OpenInference spans (``input.value`` /
                    ``output.value``) and OpenLLMetry spans
                    (``gen_ai.prompt.*`` / ``gen_ai.completion.*``), whether
                    exported as OTLP ``resourceSpans`` or a flat list of spans.

The drafted dataset is runnable as-is (unknown ``_review`` keys are ignored by the
scorers), so ``assevra run`` on it shows you the shape of the report immediately --
under-specified rows simply surface as "nothing to verify" until you label them.
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Optional

# Field-name aliases used when auto-detecting a generic interaction record.
_INPUT_ALIASES = (
    "input", "prompt", "question", "query", "user_input", "request", "user", "text",
)
_OUTPUT_ALIASES = (
    "agent_output", "output", "response", "completion", "answer", "result",
    "reply", "prediction", "generation",
)
_CONTEXT_ALIASES = (
    "context", "ground_truth", "reference", "retrieved_context", "documents",
    "sources", "grounding", "knowledge",
)

# Per-dimension answer-key placeholder + the one-line instruction for the human.
# `field` is the label key added to the drafted row (None = nothing to add,
# the captured fields are all the dimension needs).
_DIMENSION_TEMPLATE = {
    "task_completion": {
        "field": "must_include",
        "value": [],
        "hint": "Set must_include: the strings/facts a correct output must contain.",
    },
    "safety": {
        "field": "should_refuse",
        "value": None,
        "hint": "Set should_refuse: true if the agent should refuse this request, else false.",
    },
    "pii": {
        "field": "sanctioned_field",
        "value": "",
        "hint": "Set sanctioned_field to any value allowed to appear; other leaked PII fails.",
    },
    "grounding": {
        "field": None,
        "value": None,
        "hint": "Ensure `context` holds the ground-truth the answer must follow from.",
    },
}

DEFAULT_DIMENSION = "task_completion"


class BootstrapError(Exception):
    """Raised for unusable input (bad format, no extractable interactions)."""


# --------------------------------------------------------------------------- #
# Loading                                                                      #
# --------------------------------------------------------------------------- #
def _load_records(path: str) -> list[Any]:
    """Read the source file as either JSONL (one object per line) or a single
    JSON document (array, or an OTLP object). Returns a list of raw records."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    stripped = text.lstrip()
    if not stripped:
        raise BootstrapError(f"{path}: file is empty")

    # A single JSON document (array or object) -- e.g. an OTLP export or a JSON
    # array of interactions.
    if stripped[0] in "[{":
        try:
            doc = json.loads(text)
        except json.JSONDecodeError:
            doc = None
        if doc is not None:
            if isinstance(doc, list):
                return doc
            return [doc]

    # Otherwise treat it as JSONL.
    records: list[Any] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise BootstrapError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
    if not records:
        raise BootstrapError(f"{path}: no JSON records found")
    return records


# --------------------------------------------------------------------------- #
# Format detection + extraction                                                #
# --------------------------------------------------------------------------- #
def _looks_like_otel(records: list[Any]) -> bool:
    for rec in records[:5]:
        if isinstance(rec, dict) and ("resourceSpans" in rec or "scopeSpans" in rec):
            return True
        if isinstance(rec, dict) and rec.get("attributes") is not None and (
            "spanId" in rec or "span_id" in rec or "traceId" in rec or "trace_id" in rec
        ):
            return True
    return False


def _looks_like_openai(records: list[Any]) -> bool:
    for rec in records[:5]:
        if not isinstance(rec, dict):
            continue
        if "messages" in rec or "choices" in rec:
            return True
        if isinstance(rec.get("request"), dict) or isinstance(rec.get("response"), dict):
            return True
    return False


def _looks_like_anthropic(records: list[Any]) -> bool:
    for rec in records[:5]:
        if not isinstance(rec, dict):
            continue
        if isinstance(rec.get("model"), str) and rec["model"].startswith("claude-"):
            return True
        messages = rec.get("messages")
        if isinstance(messages, list):
            for msg in messages:
                if isinstance(msg, dict) and msg.get("role") == "assistant" and isinstance(msg.get("content"), list):
                    return True
    return False


def detect_format(records: list[Any]) -> str:
    if _looks_like_otel(records):
        return "otel"
    if _looks_like_anthropic(records):
        return "anthropic"
    if _looks_like_openai(records):
        return "openai"
    return "generic"


def _first_alias(rec: dict, aliases: Iterable[str]) -> Optional[str]:
    for key in aliases:
        if key in rec and rec[key] not in (None, ""):
            val = rec[key]
            return val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)
    return None


def _extract_generic(
    rec: dict,
    input_field: Optional[str],
    output_field: Optional[str],
    context_field: Optional[str],
) -> Optional[dict]:
    inp = rec.get(input_field) if input_field else _first_alias(rec, _INPUT_ALIASES)
    out = rec.get(output_field) if output_field else _first_alias(rec, _OUTPUT_ALIASES)
    ctx = rec.get(context_field) if context_field else _first_alias(rec, _CONTEXT_ALIASES)
    if not inp and not out:
        return None
    return {
        "input": _as_text(inp),
        "agent_output": _as_text(out),
        "context": _as_text(ctx),
    }


def _messages_content(messages: list, role: str) -> Optional[str]:
    """Return the last message of `role`, joining structured content parts."""
    picked = None
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == role:
            picked = msg
    if picked is None:
        return None
    return _as_text(picked.get("content"))


def _extract_openai(rec: dict) -> Optional[dict]:
    request = rec.get("request") if isinstance(rec.get("request"), dict) else rec
    response = rec.get("response") if isinstance(rec.get("response"), dict) else rec

    inp, ctx = None, None
    messages = request.get("messages") if isinstance(request, dict) else None
    if isinstance(messages, list):
        inp = _messages_content(messages, "user")
        ctx = _messages_content(messages, "system")

    out = None
    choices = response.get("choices") if isinstance(response, dict) else None
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(msg, dict):
            out = _as_text(msg.get("content"))
        if out is None and isinstance(choices[0], dict):
            out = _as_text(choices[0].get("text"))
    if out is None and isinstance(messages, list):
        out = _messages_content(messages, "assistant")

    if not inp and not out:
        return None
    return {"input": _as_text(inp), "agent_output": _as_text(out), "context": _as_text(ctx)}


def _extract_anthropic(rec: dict) -> Optional[dict]:
    messages = rec.get("messages") if isinstance(rec, dict) else None
    if not isinstance(messages, list):
        return None
    inp = _messages_content(messages, "user")
    out = _messages_content(messages, "assistant")
    ctx = _messages_content(messages, "system")
    if not inp and not out:
        return None
    return {"input": _as_text(inp), "agent_output": _as_text(out), "context": _as_text(ctx)}


def _iter_spans(records: list[Any]) -> Iterable[dict]:
    """Yield individual spans from OTLP `resourceSpans` nesting or a flat list."""
    for rec in records:
        if not isinstance(rec, dict):
            continue
        if "resourceSpans" in rec:
            for rs in rec.get("resourceSpans", []):
                for ss in rs.get("scopeSpans", []) or rs.get("instrumentationLibrarySpans", []):
                    yield from ss.get("spans", [])
        elif "scopeSpans" in rec:
            for ss in rec.get("scopeSpans", []):
                yield from ss.get("spans", [])
        elif "spans" in rec:
            yield from rec.get("spans", [])
        else:
            yield rec  # already a flat span


def _span_attributes(span: dict) -> dict:
    """Normalize span attributes to a flat {key: value} dict, handling both the
    OTLP list-of-{key,value} shape and a plain dict."""
    attrs = span.get("attributes")
    if isinstance(attrs, dict):
        return attrs
    flat: dict[str, Any] = {}
    if isinstance(attrs, list):
        for item in attrs:
            if not isinstance(item, dict):
                continue
            key = item.get("key")
            val = item.get("value")
            if isinstance(val, dict):  # OTLP AnyValue
                val = (
                    val.get("stringValue")
                    if "stringValue" in val
                    else val.get("intValue")
                    if "intValue" in val
                    else val.get("boolValue")
                    if "boolValue" in val
                    else val.get("doubleValue")
                )
            if key is not None:
                flat[key] = val
    return flat


def _extract_otel(span: dict) -> Optional[dict]:
    attrs = _span_attributes(span)
    # OpenInference (Phoenix / Arize) convention.
    inp = attrs.get("input.value")
    out = attrs.get("output.value")
    # OpenLLMetry (Traceloop) convention: gen_ai.prompt.N.content / completion.N.
    if inp is None:
        prompts = [
            v for k, v in attrs.items()
            if k.startswith("gen_ai.prompt.") and k.endswith(".content")
        ]
        inp = "\n".join(_as_text(p) for p in prompts if p) or attrs.get("gen_ai.prompt")
    if out is None:
        comps = [
            v for k, v in attrs.items()
            if k.startswith("gen_ai.completion.") and k.endswith(".content")
        ]
        out = "\n".join(_as_text(c) for c in comps if c) or attrs.get("gen_ai.completion")
    if not inp and not out:
        return None
    return {"input": _as_text(inp), "agent_output": _as_text(out), "context": ""}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    # Structured content (e.g. OpenAI content parts): pull text where possible.
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(item.get("text") or item.get("content") or "")
        joined = " ".join(p for p in parts if p)
        return joined or json.dumps(value, ensure_ascii=False)
    return json.dumps(value, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# Drafting                                                                     #
# --------------------------------------------------------------------------- #
def _draft_row(interaction: dict, dimension: str, index: int, id_prefix: str) -> dict:
    template = _DIMENSION_TEMPLATE[dimension]
    row: dict[str, Any] = {
        "id": f"{id_prefix}-{index:04d}",
        "dimension": dimension,
        "input": interaction.get("input", ""),
        "context": interaction.get("context", ""),
        "agent_output": interaction.get("agent_output", ""),
    }
    if template["field"] is not None:
        # Fresh mutable default per row.
        row[template["field"]] = [] if template["value"] == [] else template["value"]
    row["tags"] = ["bootstrap", "needs-review"]
    row["_review"] = template["hint"]
    return row


def bootstrap(
    source_path: str,
    fmt: str = "auto",
    dimension: str = DEFAULT_DIMENSION,
    limit: Optional[int] = None,
    id_prefix: str = "bootstrap",
    input_field: Optional[str] = None,
    output_field: Optional[str] = None,
    context_field: Optional[str] = None,
) -> tuple[list[dict], str]:
    """Draft Assevra dataset rows from a file of captured interactions.

    Returns (rows, resolved_format). Raises BootstrapError on unusable input.
    """
    if dimension not in _DIMENSION_TEMPLATE:
        raise BootstrapError(
            f"unknown dimension {dimension!r}; expected one of "
            f"{sorted(_DIMENSION_TEMPLATE)}"
        )

    records = _load_records(source_path)
    resolved = detect_format(records) if fmt == "auto" else fmt
    if resolved not in ("generic", "openai", "anthropic", "otel"):
        raise BootstrapError(
            f"unknown format {resolved!r}; expected generic, openai, anthropic, or otel"
        )

    interactions: list[dict] = []
    if resolved == "otel":
        for span in _iter_spans(records):
            got = _extract_otel(span) if isinstance(span, dict) else None
            if got:
                interactions.append(got)
    elif resolved == "openai":
        for rec in records:
            got = _extract_openai(rec) if isinstance(rec, dict) else None
            if got:
                interactions.append(got)
    elif resolved == "anthropic":
        for rec in records:
            got = _extract_anthropic(rec) if isinstance(rec, dict) else None
            if got:
                interactions.append(got)
    else:  # generic
        for rec in records:
            got = (
                _extract_generic(rec, input_field, output_field, context_field)
                if isinstance(rec, dict)
                else None
            )
            if got:
                interactions.append(got)

    if not interactions:
        raise BootstrapError(
            f"no interactions could be extracted from {source_path} as "
            f"format {resolved!r}. Check the format, or map fields explicitly "
            f"with --input-field / --output-field / --context-field."
        )

    if limit is not None:
        interactions = interactions[:limit]

    rows = [
        _draft_row(it, dimension, i, id_prefix)
        for i, it in enumerate(interactions, start=1)
    ]
    return rows, resolved


def write_dataset(rows: list[dict], out_path: str) -> None:
    with open(out_path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
