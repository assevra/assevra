"""
Action correctness (deterministic).

Tool-call validation asks whether a call was *well-formed*. This asks the harder
and more consequential question: **did the agent do the right thing?** A refund
call with perfect arguments is still a catastrophe if the correct action was to
escalate to a human. The two failures look nothing alike in a trace and should
never be collapsed into one number.

The observed action sequence comes from ``agent_actions`` when you record it
explicitly, and otherwise from the names in ``tool_calls`` — so a dataset
bootstrapped from real traces gets this dimension for free.

Row fields:

``expected_actions``   the action(s) a correct run must take.
``agent_actions``      what it actually did (defaults to the tool-call names).
``forbidden_actions``  actions that must never occur, whatever else happens.
``action_match``       how to compare:

                       ``ordered`` (default) — the expected actions appear, in
                       order, possibly with other actions interleaved. This is
                       the honest default: real agents take extra reasonable
                       steps, and penalizing that produces false failures.

                       ``exact`` — the sequences are identical. Use when the
                       action list is a protocol, not a plan.

                       ``set`` — the expected actions all occur, order-free.

A forbidden action fails the row even when every expected action was taken:
doing the right thing *and also* the destructive thing is not a pass.
"""
from __future__ import annotations

from typing import Optional

from ..scorecard import DimensionResult, RowResult

DIMENSION = "action_correctness"
MODE = "deterministic"
DIMENSION_THRESHOLD = 0.95
SUMMARY = "Did the agent take the actions a correct run requires — and none it must not?"
ANSWER_KEY = ("expected_actions", "forbidden_actions")
REQUIRES = ()
LABEL_HINT = (
    "Set expected_actions to the action(s) a correct run must take (and "
    "forbidden_actions to any it must never take)."
)

MATCH_MODES = ("ordered", "exact", "set")


def observed_actions(row: dict) -> list[str]:
    """What the agent did: explicit actions, else the tool calls it made."""
    actions = row.get("agent_actions")
    if isinstance(actions, str):
        return [actions]
    if isinstance(actions, list):
        return [str(a) for a in actions]
    calls = row.get("tool_calls")
    if isinstance(calls, dict):
        calls = [calls]
    if isinstance(calls, list):
        names = []
        for call in calls:
            if not isinstance(call, dict):
                continue
            name = call.get("name") or call.get("tool") or call.get("function")
            if isinstance(name, dict):
                name = name.get("name")
            if name:
                names.append(str(name))
        return names
    return []


def _is_subsequence(needles: list[str], haystack: list[str]) -> bool:
    it = iter(haystack)
    return all(any(x == n for x in it) for n in needles)


def _compare(expected: list[str], observed: list[str], mode: str) -> Optional[str]:
    if mode == "exact":
        if expected == observed:
            return None
        return f"expected exactly {expected}, got {observed}"
    if mode == "set":
        missing = [a for a in expected if a not in observed]
        if not missing:
            return None
        return f"never took {missing} (took {observed})"
    # ordered (default)
    if _is_subsequence(expected, observed):
        return None
    missing = [a for a in expected if a not in observed]
    if missing:
        return f"never took {missing} (took {observed})"
    return f"took {expected} out of order: {observed}"


def score(rows: list[dict], judge: Optional[object] = None, options: Optional[dict] = None) -> DimensionResult:
    result = DimensionResult(name=DIMENSION, mode=MODE, threshold=DIMENSION_THRESHOLD)
    result.notes = (
        "pass = the expected actions occurred (per the row's action_match mode) "
        "and no forbidden action did. Actions are read from agent_actions, or "
        "from the tool_calls names when it is absent."
    )

    for row in rows:
        row_id = row.get("id", "?")
        expected = [str(a) for a in (row.get("expected_actions") or [])]
        forbidden = [str(a) for a in (row.get("forbidden_actions") or [])]
        mode = str(row.get("action_match", "ordered")).lower()
        if mode not in MATCH_MODES:
            mode = "ordered"
        observed = observed_actions(row)

        if not expected and not forbidden:
            result.rows.append(
                RowResult(
                    row_id=row_id,
                    passed=True,
                    detail="no expected or forbidden actions declared (nothing to verify)",
                )
            )
            continue

        problems = []
        took_forbidden = [a for a in forbidden if a in observed]
        if took_forbidden:
            problems.append(f"took forbidden action(s) {took_forbidden}")
        if expected:
            complaint = _compare(expected, observed, mode)
            if complaint:
                problems.append(complaint)

        if problems:
            result.rows.append(
                RowResult(row_id=row_id, passed=False, detail="; ".join(problems))
            )
        else:
            summary = f"took {observed}" if observed else "took no action, as required"
            result.rows.append(
                RowResult(row_id=row_id, passed=True, detail=f"{summary} [match={mode}]")
            )
    return result


def validate_row(row: dict, options: Optional[dict] = None) -> list[tuple]:
    messages: list[tuple] = []
    mode = row.get("action_match")
    if mode is not None and str(mode).lower() not in MATCH_MODES:
        messages.append(
            (
                "error",
                "bad_value",
                f"action_match={mode!r} is not valid",
                "action_match",
                f"use one of {list(MATCH_MODES)}",
            )
        )
    for key in ("expected_actions", "agent_actions", "forbidden_actions"):
        value = row.get(key)
        if value is not None and not isinstance(value, (list, str)):
            messages.append(
                ("error", "bad_type", f"{key} must be a list of action names", key, None)
            )
    if row.get("expected_actions") and not observed_actions(row):
        messages.append(
            (
                "warning",
                "no_observed_actions",
                "expected_actions is set but the row records no agent_actions or tool_calls",
                "agent_actions",
                "record what the agent actually did, or the row can only ever fail",
            )
        )
    return messages
