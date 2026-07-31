"""
Tool-call validation (deterministic).

The single most common way a production agent fails is not a bad sentence — it
is a bad *call*. It invokes a tool that does not exist, omits a required
argument, passes a string where the API wants an integer, or reaches for a tool
it was never allowed to touch. None of that needs a model to detect: a tool call
is structured data with a contract, and a contract is checkable.

This scorer answers: **was every call the agent made well-formed and permitted?**
It deliberately does *not* ask whether the call was the right thing to do — that
is action correctness, a separate dimension, because the two fail for different
reasons and a team needs to know which one broke.

Row fields:

``tool_calls``        what the agent actually called: ``[{"name": ..., "arguments": {...}}]``.
                      ``arguments`` may be the raw JSON string a model emitted —
                      unparseable JSON is itself a failure, and a common one.
``allowed_tools``     an allow-list; calling anything outside it fails the row.
``forbidden_tools``   a deny-list, for cases where an allow-list is impractical.
``tool_schemas``      per-tool argument contract:
                      ``{"refund": {"required": ["order_id"], "types": {"amount": "number"},
                      "enum": {"reason": ["damaged", "late"]}}}``
``expected_tool_calls`` calls that must appear, with the argument values that must match.

A row with none of those declares no contract, so there is nothing to verify; it
is reported as such rather than counted as a silent pass.

The threshold is 0.95 rather than 1.00: a malformed call is usually recoverable
(the agent retries), unlike a leaked SSN. Tighten it in ``.assevra.yml`` if your
tools are destructive.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from ..scorecard import DimensionResult, RowResult

DIMENSION = "tool_call"
MODE = "deterministic"
DIMENSION_THRESHOLD = 0.95
SUMMARY = "Were the agent's tool calls well-formed, permitted, and complete?"
ANSWER_KEY = ("allowed_tools", "forbidden_tools", "tool_schemas", "expected_tool_calls")
REQUIRES = ("tool_calls",)
LABEL_HINT = (
    "Declare the contract: allowed_tools (the permitted tools), tool_schemas "
    "(required args and their types), and/or expected_tool_calls (the calls a "
    "correct run must make)."
)

# Zero-label, given the agent's own tool spec: `assevra.toolspec` turns an
# OpenAI/Anthropic/MCP tool definition into exactly the contract this dimension
# checks, and `scan` passes it in through options. Nothing about *intent* is
# derived — an allow-list and argument schemas say what the agent may do, never
# which call was the right one.
AUTOLABEL_NOTE = "contract derived from the agent's own tool spec (--tools)"


def autolabel(interaction: dict, options: Optional[dict] = None):
    contract = (options or {}).get("tool_contract") or {}
    if not contract:
        return None
    if not interaction.get("tool_calls"):
        return None
    from .. import toolspec

    return toolspec.as_row_fields(contract)


_TYPES = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _parse_arguments(raw: Any) -> tuple[Optional[dict], Optional[str]]:
    """Normalize a call's arguments to a dict, or explain why we cannot.

    Models emit arguments as a JSON *string* far more often than as an object,
    and truncated or unquoted JSON is one of the highest-frequency real failures
    in agent traces — so a parse error is a first-class finding, not a crash.
    """
    if raw is None:
        return {}, None
    if isinstance(raw, dict):
        return raw, None
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}, None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            return None, f"arguments are not valid JSON ({exc.msg} at char {exc.pos})"
        if not isinstance(parsed, dict):
            return None, "arguments JSON is not an object"
        return parsed, None
    return None, f"arguments have unusable type {type(raw).__name__}"


def _iter_calls(row: dict) -> list[dict]:
    calls = row.get("tool_calls")
    if isinstance(calls, dict):
        return [calls]
    if isinstance(calls, list):
        return [c for c in calls if isinstance(c, dict)]
    return []


def _check_schema(name: str, args: dict, contract: dict) -> list[str]:
    problems: list[str] = []
    for required in contract.get("required", []) or []:
        if required not in args:
            problems.append(f"{name}: missing required argument {required!r}")
    for arg, want in (contract.get("types", {}) or {}).items():
        if arg not in args:
            continue
        expected = _TYPES.get(want)
        if expected is None:
            continue
        value = args[arg]
        # bool is a subclass of int in Python; an API expecting a number does not
        # mean it accepts True.
        if want in ("number", "integer") and isinstance(value, bool):
            problems.append(f"{name}: argument {arg!r} is a boolean, expected {want}")
        elif not isinstance(value, expected):
            problems.append(
                f"{name}: argument {arg!r} is {type(value).__name__}, expected {want}"
            )
    for arg, choices in (contract.get("enum", {}) or {}).items():
        if arg in args and args[arg] not in choices:
            problems.append(
                f"{name}: argument {arg!r}={args[arg]!r} is not one of {choices!r}"
            )
    return problems


def _match_expected(expected: dict, observed: list[tuple[str, dict]]) -> Optional[str]:
    """Is there an observed call matching this expectation? Returns a complaint."""
    name = expected.get("name")
    want_args, err = _parse_arguments(expected.get("arguments"))
    if err or want_args is None:
        want_args = {}
    candidates = [args for (got_name, args) in observed if got_name == name]
    if not candidates:
        return f"expected a call to {name!r}, which never happened"
    if not want_args:
        return None
    for args in candidates:
        if all(args.get(k) == v for k, v in want_args.items()):
            return None
    wrong = ", ".join(
        f"{k}={want_args[k]!r}"
        for k in want_args
        if all(c.get(k) != want_args[k] for c in candidates)
    )
    return f"{name!r} was called, but never with {wrong}"


def score(rows: list[dict], judge: Optional[object] = None, options: Optional[dict] = None) -> DimensionResult:
    result = DimensionResult(name=DIMENSION, mode=MODE, threshold=DIMENSION_THRESHOLD)
    result.notes = (
        "pass = every call parses, targets a permitted tool, satisfies its "
        "argument contract, and every expected call happened. Structural only: "
        "this does not judge whether the call was the right decision."
    )

    for row in rows:
        row_id = row.get("id", "?")
        calls = _iter_calls(row)
        allowed = row.get("allowed_tools") or []
        forbidden = row.get("forbidden_tools") or []
        schemas = row.get("tool_schemas") or {}
        expected = row.get("expected_tool_calls") or []

        if not (allowed or forbidden or schemas or expected):
            result.rows.append(
                RowResult(
                    row_id=row_id,
                    passed=True,
                    detail="no tool contract declared (nothing to verify)",
                )
            )
            continue

        problems: list[str] = []
        observed: list[tuple[str, dict]] = []

        for index, call in enumerate(calls):
            name = call.get("name") or call.get("tool") or call.get("function")
            if isinstance(name, dict):  # OpenAI shape: {"function": {"name": ...}}
                name = name.get("name")
            if not name:
                problems.append(f"call #{index + 1} has no tool name")
                continue
            raw_args = call.get("arguments", call.get("args", call.get("input")))
            args, err = _parse_arguments(raw_args)
            if err:
                problems.append(f"{name}: {err}")
                continue
            observed.append((name, args))
            if allowed and name not in allowed:
                problems.append(f"called {name!r}, which is not in allowed_tools")
            if name in forbidden:
                problems.append(f"called forbidden tool {name!r}")
            if name in schemas:
                problems.extend(_check_schema(name, args, schemas[name]))

        for want in expected:
            if not isinstance(want, dict):
                continue
            complaint = _match_expected(want, observed)
            if complaint:
                problems.append(complaint)

        if problems:
            result.rows.append(
                RowResult(row_id=row_id, passed=False, detail="; ".join(problems))
            )
        else:
            made = ", ".join(name for name, _ in observed) or "none"
            result.rows.append(
                RowResult(
                    row_id=row_id,
                    passed=True,
                    detail=f"{len(observed)} call(s) valid ({made})",
                )
            )
    return result


def validate_row(row: dict, options: Optional[dict] = None) -> list[tuple]:
    """Extra structural checks surfaced by ``assevra validate``."""
    messages: list[tuple] = []
    calls = row.get("tool_calls")
    if calls is not None and not isinstance(calls, (list, dict)):
        messages.append(
            ("error", "bad_type", "tool_calls must be a list of call objects", "tool_calls", None)
        )
    for name, contract in (row.get("tool_schemas") or {}).items():
        if not isinstance(contract, dict):
            messages.append(
                (
                    "error",
                    "bad_type",
                    f"tool_schemas[{name!r}] must be an object with 'required'/'types'/'enum'",
                    "tool_schemas",
                    None,
                )
            )
            continue
        for arg, want in (contract.get("types", {}) or {}).items():
            if want not in _TYPES:
                messages.append(
                    (
                        "error",
                        "bad_type",
                        f"tool_schemas[{name!r}].types[{arg!r}]={want!r} is not a JSON type",
                        "tool_schemas",
                        f"use one of {sorted(_TYPES)}",
                    )
                )
    return messages
