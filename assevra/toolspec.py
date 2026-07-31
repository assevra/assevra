"""
Derive a tool-call contract from the agent's own tool definitions.

The `tool_call` dimension needs to know which tools were permitted and what
arguments each one requires. Before 0.5, Assevra asked a human to write that
down — `allowed_tools`, `tool_schemas` — per row.

That was always redundant. **The agent already has this information**, in a
machine-readable form, because the model needs it to call anything at all: the
OpenAI `tools` array, the Anthropic `tools` list, an MCP server manifest, a
LangChain tool dump. Every one of them is a name plus a JSON Schema, which is
exactly what the dimension checks against.

So point Assevra at that file and the whole dimension becomes zero-label:

    assevra scan --from traces.jsonl --tools tools.json

Four shapes are understood, distinguished by structure rather than by filename:

``openai``     ``[{"type": "function", "function": {"name", "parameters"}}]``
``anthropic``  ``[{"name", "input_schema"}]``
``mcp``        ``{"tools": [{"name", "inputSchema"}]}``
``schema-map`` ``{"tool_name": {<JSON Schema>}}``

What is deliberately *not* derived: ``forbidden_tools`` and
``expected_tool_calls``. A tool spec says what the agent *can* do. Which tools
must never be reached for in a given case, and which calls a correct run must
make, are policy and intent — judgments a schema cannot contain and Assevra must
not invent.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

# JSON Schema type names Assevra's tool_call checker understands.
_TYPES = {"string", "number", "integer", "boolean", "array", "object"}

# Files worth looking at when nobody passed --tools.
_CANDIDATE_NAMES = (
    "tools.json", "tool_spec.json", "toolspec.json", "functions.json",
    "tool_schemas.json", "mcp.json", "mcp.config.json", ".mcp.json",
)
_SKIP_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build",
    ".mypy_cache", ".pytest_cache", ".tox", ".assevra",
}


class ToolSpecError(Exception):
    """Raised for a tool-spec file that cannot be understood."""


def detect_shape(doc: Any) -> Optional[str]:
    """Name the tool-spec dialect, or None if this is not one."""
    if isinstance(doc, dict):
        if isinstance(doc.get("tools"), list):
            return detect_shape(doc["tools"]) or "mcp"
        # A bare {name: schema} map: every value looks like a JSON Schema.
        if doc and all(
            isinstance(v, dict) and ("properties" in v or v.get("type") == "object")
            for v in doc.values()
        ):
            return "schema-map"
        return None
    if not isinstance(doc, list) or not doc:
        return None
    first = next((e for e in doc if isinstance(e, dict)), None)
    if first is None:
        return None
    if "function" in first or first.get("type") == "function":
        return "openai"
    if "input_schema" in first:
        return "anthropic"
    if "inputSchema" in first:
        return "mcp"
    if "name" in first and ("parameters" in first or "args_schema" in first):
        return "openai"  # LangChain dumps and bare function specs
    return None


def _schema_to_contract(schema: Any) -> dict:
    """Turn one tool's JSON Schema into Assevra's argument contract."""
    contract: dict[str, Any] = {}
    if not isinstance(schema, dict):
        return contract

    required = schema.get("required")
    if isinstance(required, list):
        names = [str(r) for r in required if isinstance(r, str)]
        if names:
            contract["required"] = names

    properties = schema.get("properties")
    if isinstance(properties, dict):
        types, enums = {}, {}
        for arg, spec in properties.items():
            if not isinstance(spec, dict):
                continue
            declared = spec.get("type")
            # A union type ("string" or null) cannot be enforced as one type, so
            # it is left unchecked rather than guessed at.
            if isinstance(declared, str) and declared in _TYPES:
                types[arg] = declared
            choices = spec.get("enum")
            if isinstance(choices, list) and choices:
                enums[arg] = list(choices)
        if types:
            contract["types"] = types
        if enums:
            contract["enum"] = enums
    return contract


def parse(doc: Any, shape: Optional[str] = None) -> dict[str, dict]:
    """Return {tool_name: contract} from any supported tool-spec document."""
    shape = shape or detect_shape(doc)
    if shape is None:
        raise ToolSpecError(
            "this does not look like a tool specification. Expected an OpenAI "
            "`tools` array, an Anthropic `tools` list, an MCP manifest, or a "
            "{tool_name: json-schema} map."
        )

    if isinstance(doc, dict) and isinstance(doc.get("tools"), list):
        doc = doc["tools"]

    out: dict[str, dict] = {}

    if shape == "schema-map" and isinstance(doc, dict):
        for name, schema in doc.items():
            out[str(name)] = _schema_to_contract(schema)
        return out

    for entry in doc if isinstance(doc, list) else []:
        if not isinstance(entry, dict):
            continue
        # OpenAI nests the real definition one level down.
        body = entry.get("function") if isinstance(entry.get("function"), dict) else entry
        name = body.get("name")
        if not name:
            continue
        schema = (
            body.get("parameters")
            or body.get("input_schema")
            or body.get("inputSchema")
            or body.get("args_schema")
        )
        out[str(name)] = _schema_to_contract(schema)
    if not out:
        raise ToolSpecError("the tool specification contained no named tools")
    return out


def load(path: str) -> tuple[dict[str, dict], str]:
    """Load a tool spec from a file. Returns ({name: contract}, shape)."""
    file = Path(path)
    if not file.is_file():
        raise ToolSpecError(f"tool spec not found: {path}")
    try:
        doc = json.loads(file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ToolSpecError(f"{path}: invalid JSON: {exc}") from exc
    shape = detect_shape(doc)
    if shape is None:
        raise ToolSpecError(
            f"{path} is valid JSON but not a recognized tool specification "
            "(OpenAI tools, Anthropic tools, MCP manifest, or a name→schema map)."
        )
    return parse(doc, shape), shape


def discover(root: str = ".", limit: int = 3) -> list[tuple[Path, dict, str]]:
    """Find tool-spec files in a project. Returns [(path, contracts, shape)].

    Structure decides, not the filename: a file called ``tools.json`` that turns
    out to be something else is skipped rather than misread.
    """
    import os

    found: list[tuple[Path, dict, str]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            if not name.endswith(".json"):
                continue
            lowered = name.lower()
            if lowered not in _CANDIDATE_NAMES and "tool" not in lowered:
                continue
            path = Path(dirpath) / name
            try:
                if path.stat().st_size > 4 * 1024 * 1024:
                    continue
                contracts, shape = load(str(path))
            except (ToolSpecError, OSError):
                continue
            found.append((path, contracts, shape))
            if len(found) >= limit:
                return found
    return found


def as_row_fields(contracts: dict[str, dict], allow_list: bool = True) -> dict:
    """The row fields a derived contract contributes to a dataset row.

    Only tools that actually declare something checkable get a schema entry —
    an empty contract would assert nothing while looking like a check.
    """
    fields: dict[str, Any] = {}
    if allow_list and contracts:
        fields["allowed_tools"] = sorted(contracts)
    schemas = {name: c for name, c in contracts.items() if c}
    if schemas:
        fields["tool_schemas"] = schemas
    return fields


def describe(contracts: dict[str, dict]) -> str:
    """A one-line summary for the console."""
    checkable = sum(1 for c in contracts.values() if c)
    return (
        f"{len(contracts)} tool(s), {checkable} with a checkable argument contract"
        if contracts
        else "no tools"
    )
