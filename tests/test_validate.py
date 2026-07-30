"""
Tests for dataset validation — the gate that runs before evaluation.

The behaviour under test is the three-state contract: a row is LABELED
(meaningful), UNLABELED (scores as a vacuous pass), or INVALID (must not be
scored at all). Getting that distinction wrong is how a meaningless number ends
up in a release review, so it is tested per state and per error code.

Runs under pytest, or standalone: `python3 tests/test_validate.py`.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import assevra  # noqa: F401,E402  (registers the built-in scorers)
from assevra import validate as V  # noqa: E402


def _report(rows, strict=False, options=None):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "d.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")
        return V.validate_dataset(path, strict=strict, options=options or {})


def _codes(report):
    return {m.code for row in report.rows for m in row.messages}


def test_labeled_row_is_labeled():
    report = _report([
        {"id": "t1", "dimension": "task_completion", "agent_output": "a token", "must_include": ["token"]}
    ])
    assert report.rows[0].state == V.LABELED
    assert report.ok


def test_row_without_an_answer_key_is_unlabeled_not_invalid():
    report = _report([
        {"id": "t1", "dimension": "task_completion", "agent_output": "x", "must_include": []}
    ])
    assert report.rows[0].state == V.UNLABELED
    assert "missing_answer_key" in _codes(report)
    assert report.ok                      # unlabeled is legitimate mid-labeling


def test_strict_mode_makes_unlabeled_fatal():
    report = _report(
        [{"id": "t1", "dimension": "task_completion", "agent_output": "x"}], strict=True
    )
    assert report.rows[0].state == V.UNLABELED
    assert not report.ok


def test_unknown_dimension_is_invalid():
    report = _report([{"id": "x", "dimension": "vibes", "agent_output": "y"}])
    assert report.rows[0].state == V.INVALID
    assert "unknown_dimension" in _codes(report)
    assert not report.ok


def test_missing_id_and_duplicate_id_are_invalid():
    report = _report([
        {"dimension": "pii", "agent_output": "a"},
        {"id": "dup", "dimension": "pii", "agent_output": "a"},
        {"id": "dup", "dimension": "pii", "agent_output": "b"},
    ])
    codes = _codes(report)
    assert "missing_id" in codes and "duplicate_id" in codes
    assert report.count(V.INVALID) == 2


def test_missing_required_output_is_invalid():
    report = _report([{"id": "g", "dimension": "grounding", "context": "c"}])
    assert report.rows[0].state == V.INVALID
    assert "missing_field" in _codes(report)


def test_malformed_json_line_is_reported_with_its_line_number():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "d.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('{"id":"a","dimension":"pii","agent_output":"x"}\n')
            fh.write("{oops}\n")
        report = V.validate_dataset(path)
    assert report.count(V.INVALID) == 1
    bad = [r for r in report.rows if r.state == V.INVALID][0]
    assert bad.line == 2 and bad.messages[0].code == "invalid_json"


def test_pii_rows_are_self_labeling():
    # The detector needs no human verdict to know what a leak is.
    report = _report([{"id": "p", "dimension": "pii", "agent_output": "nothing sensitive"}])
    assert report.rows[0].state == V.LABELED


def test_cost_row_is_labeled_by_a_project_budget():
    row = {"id": "c", "dimension": "cost", "agent_output": "x", "cost_usd": 0.01}
    assert _report([row]).rows[0].state == V.UNLABELED
    options = {"budgets": {"cost_usd": 0.05}}
    assert _report([row], options=options).rows[0].state == V.LABELED


def test_scorer_specific_checks_surface():
    report = _report([
        {
            "id": "tc",
            "dimension": "tool_call",
            "agent_output": "x",
            "tool_calls": [{"name": "f"}],
            "tool_schemas": {"f": {"types": {"a": "not-a-json-type"}}},
        }
    ])
    assert report.rows[0].state == V.INVALID
    assert "bad_type" in _codes(report)


def test_report_serializes_with_its_schema_identity():
    report = _report([{"id": "p", "dimension": "pii", "agent_output": "x"}])
    payload = json.loads(report.to_json())
    assert payload["$schema"].endswith("validation.schema.json")
    assert payload["counts"]["labeled"] == 1
    assert payload["rows"][0]["state"] == "LABELED"


def test_render_says_what_to_do_next():
    text = V.render(_report([{"id": "p", "dimension": "vibes", "agent_output": "x"}]))
    assert "INVALID" in text and "unknown_dimension" in text


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
