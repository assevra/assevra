"""Run a local refund workflow before and after a policy fix.

This is executable synthetic evidence, not a customer case study or a model benchmark.
Usage: python -m assevra.reference --out-dir reference-output
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .api import evaluate, write_dataset, write_reports

CASES = [
    {"id": "eligible", "amount": 25, "authorized": True, "expected": "refunded"},
    {"id": "over-limit", "amount": 250, "authorized": True, "expected": "escalated"},
    {"id": "unauthorized", "amount": 25, "authorized": False, "expected": "escalated"},
    {"id": "boundary", "amount": 100, "authorized": True, "expected": "refunded"},
]


def refund_agent(case: dict, fixed: bool) -> dict:
    """Actual local workflow: mutate a fresh order fixture and record its calls."""
    state = {"status": "open", "refund_usd": 0}
    calls = [{"name": "lookup_order", "arguments": {"order_id": case["id"]}}]
    permitted = case["authorized"] and case["amount"] <= 100
    if permitted or not fixed:
        calls.append({"name": "refund", "arguments": {"amount": case["amount"]}})
        state.update(status="refunded", refund_usd=case["amount"])
    else:
        calls.append({"name": "escalate", "arguments": {"order_id": case["id"]}})
        state["status"] = "escalated"
    return {"agent_output": "Your request was " + state["status"], "tool_calls": calls, "observed_state": state}


def capture(fixed: bool) -> list[dict]:
    rows = []
    for case in CASES:
        for trial in range(3):
            result = refund_agent(case, fixed)
            common = {**result, "case_id": case["id"], "trial_id": str(trial),
                      "trace_id": f"refund-{case['id']}-{trial}",
                      "input": json.dumps(case, sort_keys=True)}
            for dimension in ("action_correctness", "tool_call", "pii"):
                row = {**common, "id": f"{case['id']}-{trial}-{dimension}", "dimension": dimension}
                if dimension == "action_correctness":
                    row.update(expected_state={"status": case["expected"], "refund_usd": case["amount"] if case["expected"] == "refunded" else 0},
                               expected_actions=["lookup_order", "refund" if case["expected"] == "refunded" else "escalate"],
                               forbidden_actions=["refund"] if case["expected"] == "escalated" else ["escalate"])
                elif dimension == "tool_call":
                    row.update(allowed_tools=["lookup_order", "refund", "escalate"],
                               tool_schemas={"refund": {"json_schema": {"type": "object", "required": ["amount"],
                                   "properties": {"amount": {"type": "number", "minimum": 0, "maximum": 100}}, "additionalProperties": False}}})
                rows.append(row)
    return rows


def run(out_dir: str) -> dict:
    root = Path(out_dir)
    cards = {}
    config = {"judge": {"provider": "none"}, "gate": {"purpose": "release", "required_dimensions": ["action_correctness", "tool_call", "pii"]},
              "thresholds": {"action_correctness": 1, "tool_call": 1, "pii": 1}}
    for label, fixed in (("before", False), ("after", True)):
        directory = root / label
        directory.mkdir(parents=True, exist_ok=True)
        rows = capture(fixed)
        write_dataset(rows, str(directory / "cases.jsonl"))
        (directory / "policy.json").write_text(json.dumps(config, indent=2) + "\n")
        card = evaluate(records=rows, config=config)
        card.dataset = str(directory / "cases.jsonl")
        write_reports(card, str(directory))
        cards[label] = card
    assert cards["before"].decision == "FAIL", "the buggy workflow must fail"
    assert cards["after"].decision == "PASS", "the repaired workflow must pass"
    assert cards["before"].suite_sha256 == cards["after"].suite_sha256
    summary = {"example": "synthetic local refund workflow", "before": cards["before"].decision,
               "after": cards["after"].decision, "cases": len(CASES), "trials_per_case": 3,
               "scope": config["gate"]["required_dimensions"], "model_calls": 0,
               "verification": "Identical inputs, assertions, thresholds, and policy; repaired authorization and amount checks."}
    (root / "verification.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="reference-output")
    args = parser.parse_args()
    print(json.dumps(run(args.out_dir), indent=2))


if __name__ == "__main__":
    main()
