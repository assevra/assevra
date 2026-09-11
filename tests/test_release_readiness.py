"""Regression cases for release decisions, lost evidence and the adoption loop."""
import json
import pytest

from assevra import evaluate, DatasetError
from assevra.judge import Judge
from assevra.scorers import tool_call
from assevra import toolspec, bootstrap, reference, history, cli

TASK = {"id": "task", "dimension": "task_completion", "agent_output": "done", "must_include": ["done"]}
GROUND = {"id": "ground", "dimension": "grounding", "agent_output": "fact", "context": "fact"}


def test_missing_judge_and_absent_required_dimension_block_release():
    card = evaluate(records=[TASK, GROUND], config={}, judge_provider="none")
    assert card.decision == "INCOMPLETE" and not card.overall_pass
    card = evaluate(records=[TASK], config={}, required_dimensions=["task_completion", "pii"])
    assert card.missing_dimensions == ["pii"]
    assert card.findings[0]["status"] == "MISSING"


@pytest.mark.parametrize("value", [{"score": 99}, {"score": True}, {"score": "5"}, [], {"score": 5, "reason": []}])
def test_invalid_judge_values_are_errors_not_agent_failures(value):
    card = evaluate(records=[GROUND], config={}, judge=Judge("fixture", lambda _: json.dumps(value)))
    dim = card.dimension("grounding")
    assert card.decision == "INCOMPLETE" and dim.n == 0
    assert dim.rows[0].status == "ERROR"
    assert card.findings[0]["title"] == "Restore evaluation evidence"


def test_release_validation_cannot_be_disabled():
    with pytest.raises(DatasetError):
        evaluate(records=[dict(TASK, must_include=[])], config={}, validate=False)


@pytest.mark.parametrize("value", [-1, 2, float("nan"), float("inf"), True, "oops"])
def test_invalid_thresholds_rejected(value):
    with pytest.raises(DatasetError):
        evaluate(records=[TASK], config={}, thresholds={"task_completion": value})


def test_control_not_agent_success_and_details_redacted():
    row = {"id": "pii", "dimension": "pii", "agent_output": "SSN 123-45-6789", "tags": ["negative-example"]}
    card = evaluate(records=[TASK, row], config={}, judge_provider="none")
    assert card.coverage["agent_rows"] == 1 and card.controls[0]["passed"]
    assert card.dimension("pii") is None
    assert "123-45-6789" not in card.to_json()


def test_full_tool_schema_preserved_and_enforced():
    schema = {"type": "object", "properties": {"payload": {"type": "object", "properties": {"amount": {"type": "number", "maximum": 100}}, "required": ["amount"], "additionalProperties": False}}, "required": ["payload"], "additionalProperties": False}
    contract = toolspec.parse({"refund": schema})
    assert contract["refund"]["json_schema"] == schema
    row = {"id": "tool", "dimension": "tool_call", "tool_schemas": contract,
           "tool_calls": [{"function": {"name": "refund", "arguments": json.dumps({"payload": {"amount": 250}})}}]}
    result = tool_call.score([row])
    assert not result.rows[0].passed and "maximum" in result.rows[0].detail
    row["tool_schemas"] = {"refund": {"json_schema": {"$ref": "https://invalid.example/schema"}}}
    assert tool_call.score([row]).rows[0].status == "ERROR"


def test_phoenix_flat_span_preserves_identity_context():
    span = {"context.trace_id": "trace-123", "context.span_id": "span-456", "attributes.input.value": "question", "attributes.output.value": "answer", "attributes.context": "source"}
    assert bootstrap._looks_like_otel([span])
    row = bootstrap._extract_otel(span)
    assert row["trace_id"] == "trace-123" and row["context"] == "source"


def test_reference_workflow_and_comparability(tmp_path):
    result = reference.run(str(tmp_path))
    assert (result["before"], result["after"]) == ("FAIL", "PASS")
    before = evaluate(records=reference.capture(False), config={}, judge_provider="none")
    after = evaluate(records=reference.capture(True), config={}, judge_provider="none")
    a, b = [history.record_from_scorecard(c, "test", "now") for c in (before, after)]
    assert not history.comparability(a, b)
    b["suite_sha256"] = "changed-label"
    assert history.comparability(a, b)


def test_required_missing_baseline_fails_and_is_in_artifact(tmp_path):
    dataset = tmp_path / "data.jsonl"
    dataset.write_text(json.dumps(TASK) + "\n")
    code = cli.main(["run", "--dataset", str(dataset), "--config", "none", "--out-dir", str(tmp_path / "out"), "--history", str(tmp_path / "history.jsonl"), "--fail-on-regression", "--gate"])
    assert code == 1
    card = json.loads((tmp_path / "out/scorecard.json").read_text())
    assert card["decision"] == "INCOMPLETE" and card["comparison"]["required"]


def test_capture_preserves_all_attempts_after_failure(tmp_path):
    import sys
    from assevra.capture import capture_inputs, CaptureError
    path = str(tmp_path / "trace.jsonl")
    with pytest.raises(CaptureError):
        capture_inputs([sys.executable, "-c", "import sys;sys.exit(3)"], [("one", ""), ("two", "")], path, repeat=2)
    rows = [json.loads(line) for line in open(path)]
    assert len(rows) == 4 and all(row["_capture_error"] for row in rows)
    manifest = json.load(open(path + ".manifest.json"))
    assert manifest["attempted"] == 4 and manifest["completed"] == 0


def test_v1_contract_remains_available_unchanged():
    from pathlib import Path
    schema = json.loads((Path(__file__).parents[1] / "web/public/schema/v1/scorecard.schema.json").read_text())
    assert schema["$id"].endswith("/v1/scorecard.schema.json")
    assert "decision" not in schema["required"]
