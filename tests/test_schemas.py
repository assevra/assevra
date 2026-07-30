"""
Tests for the published artifact contracts.

The scorecard JSON is arguably a more important deliverable than the CLI: it is
what a reviewer parses, what another tool consumes, and what has to still make
sense in a year. So these tests treat the schemas as the product they are —
every artifact Assevra emits is validated against its published schema, and the
identity keys (`$schema`, `schema_version`) must be present so a consumer never
has to guess what it is holding.

`jsonschema` is a CI-only dependency; without it the structural assertions still
run, so the suite never silently skips everything.

Runs under pytest, or standalone: `python3 tests/test_schemas.py`.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assevra import attest, calibration, demo, evaluate, schemas, validate_dataset  # noqa: E402

try:
    import jsonschema  # type: ignore
except ImportError:  # pragma: no cover - exercised in the CI matrix
    jsonschema = None


def _check(payload: dict, name: str) -> None:
    assert payload["$schema"] == schemas.schema_url(name)
    assert payload["schema_version"] == schemas.SCHEMA_VERSION
    if jsonschema is not None:
        jsonschema.validate(payload, schemas.load(name))


def _demo_scorecard():
    return evaluate(records=demo.dataset_rows(), config=dict(demo.DEMO_CONFIG))


def test_every_bundled_schema_is_valid_json_schema():
    for name in schemas.NAMES:
        schema = schemas.load(name)
        assert schema["$id"] == schemas.schema_url(name)
        assert schema["$schema"].startswith("https://json-schema.org/")
        if jsonschema is not None:
            jsonschema.Draft202012Validator.check_schema(schema)


def test_scorecard_conforms_to_its_schema():
    payload = _demo_scorecard().to_dict()
    _check(payload, "scorecard")
    assert payload["overall_pass"] is True
    names = [d["name"] for d in payload["dimensions"]]
    assert "grounding" in names and "injection" in names


def test_scorecard_records_provenance():
    payload = evaluate(records=demo.dataset_rows(), config=dict(demo.DEMO_CONFIG)).to_dict()
    assert payload["generated_at"]
    assert payload["assevra_version"]
    # Every dimension states its sample size and interval, always.
    for dimension in payload["dimensions"]:
        assert "sample_size" in dimension and len(dimension["ci_95"]) == 2


def test_agent_card_conforms_to_its_schema():
    card = attest.build_card_dict(_demo_scorecard().to_dict(), generated_at="2026-07-29T00:00:00Z")
    _check(card, "agent-card")
    assert "not a certification" in card["disclaimer"].lower() or "NOT" in card["disclaimer"]


def test_validation_report_conforms_to_its_schema():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "d.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            for row in demo.dataset_rows():
                fh.write(json.dumps(row) + "\n")
        report = validate_dataset(path, config=dict(demo.DEMO_CONFIG))
    _check(report.to_dict(), "validation")


def test_calibration_artifact_conforms_to_its_schema():
    overall = calibration.compute([True, True, False], [True, True, False])
    payload = calibration.to_artifact(
        overall,
        {"grounding": overall},
        judge_model="mock-judge",
        dataset="holdout.jsonl",
        assevra_version="0.4",
        generated_at="2026-07-29T00:00:00Z",
    )
    _check(payload, "calibration")
    assert payload["overall"]["trustworthy"] is True


def test_schema_urls_are_stable_and_versioned():
    assert schemas.SCHEMA_BASE_URL.endswith("/v1")
    assert schemas.schema_url("scorecard") == (
        "https://assevra.ai/schema/v1/scorecard.schema.json"
    )


def test_a_skipped_dimension_serializes_as_null_not_true():
    """The contract that matters most: skipped is not passed."""
    rows = [r for r in demo.dataset_rows() if r["dimension"] == "grounding"]
    payload = evaluate(records=rows, config={"judge": {"provider": "none"}}).to_dict()
    grounding = payload["dimensions"][0]
    assert grounding["skipped"] is True
    assert grounding["passed"] is None
    assert payload["overall_pass"] is False


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
