"""
Tests for the Python SDK — `assevra.evaluate` and the extension registries.

Two things are load-bearing here and are tested as such: that `evaluate` refuses
to score a dataset it could not understand (rather than returning a confident
number built on typos), and that a third-party scorer registered at runtime
becomes a first-class dimension — appearing in the scorecard, the validator, and
the gate without any change to Assevra.

Runs under pytest, or standalone: `python3 tests/test_api.py`.
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import assevra  # noqa: E402
from assevra import DatasetError, demo, evaluate, registry  # noqa: E402
from assevra.scorecard import DimensionResult, RowResult  # noqa: E402

TASK_ROW = {
    "id": "t1",
    "dimension": "task_completion",
    "agent_output": "your code is 42",
    "must_include": ["42"],
}


def test_evaluate_from_records():
    card = evaluate(records=[TASK_ROW], config={})
    assert card.overall_pass is True
    assert card.dimension("task_completion").score == 1.0
    assert card.dataset == "(in-memory records)"


def test_evaluate_requires_exactly_one_input():
    for kwargs in ({}, {"records": [TASK_ROW], "dataset": "x.jsonl"}):
        try:
            evaluate(config={}, **kwargs)
        except DatasetError:
            pass
        else:
            raise AssertionError("expected DatasetError")


def test_evaluate_refuses_an_invalid_dataset():
    try:
        evaluate(records=[{"id": "a", "dimension": "vibes", "agent_output": "x"}], config={})
    except DatasetError as exc:
        assert exc.report is not None and exc.report.count(assevra.INVALID) == 1
    else:
        raise AssertionError("expected DatasetError for an unknown dimension")


def test_validation_can_be_turned_off_deliberately():
    card = evaluate(records=[dict(TASK_ROW, must_include=[])], config={}, strict=True, validate=False)
    assert card.overall_pass is True


def test_thresholds_can_be_overridden_per_call_and_by_config():
    failing = dict(TASK_ROW, must_include=["nope"])
    card = evaluate(records=[failing], config={})
    assert card.dimension("task_completion").passed is False

    lenient = evaluate(records=[failing], config={"thresholds": {"task_completion": 0.0}})
    assert lenient.dimension("task_completion").passed is True

    explicit = evaluate(records=[failing], config={}, thresholds={"task_completion": 0.0})
    assert explicit.dimension("task_completion").passed is True


def test_failures_lists_every_failing_row():
    card = evaluate(records=[dict(TASK_ROW, must_include=["nope"])], config={})
    failures = card.failures()
    assert len(failures) == 1 and failures[0][0] == "task_completion"


def test_pass_k_appears_only_with_repeated_trials():
    single = evaluate(records=[TASK_ROW], config={})
    assert single.reliability == []

    trials = [dict(TASK_ROW, id=f"t{i}", case_id="shared") for i in range(3)]
    repeated = evaluate(records=trials, config={})
    assert repeated.reliability and repeated.reliability[0].n_repeated == 1


def test_write_reports_emits_every_requested_format():
    card = evaluate(records=[TASK_ROW], config={})
    with tempfile.TemporaryDirectory() as tmp:
        written = assevra.write_reports(card, tmp, ("md", "json", "html"))
        names = sorted(p.name for p in written)
        assert names == ["scorecard.html", "scorecard.json", "scorecard.md"]
        html = (written[2]).read_text(encoding="utf-8")
        assert "<!doctype html>" in html.lower() and "95% CI" in html


def test_a_registered_scorer_becomes_a_first_class_dimension():
    """The extension contract: a domain metric without forking Assevra."""

    class _Module:
        DIMENSION = "policy_citation"
        MODE = "deterministic"
        DIMENSION_THRESHOLD = 1.0
        SUMMARY = "Did the answer cite the governing policy id?"
        ANSWER_KEY = ("expected_policy_id",)
        REQUIRES = ("agent_output",)
        LABEL_HINT = "Set expected_policy_id to the id the answer must cite."

        @staticmethod
        def score(rows, judge=None, options=None):
            result = DimensionResult(name="policy_citation", mode="deterministic", threshold=1.0)
            for row in rows:
                wanted = row.get("expected_policy_id", "")
                result.rows.append(
                    RowResult(
                        row_id=row["id"],
                        passed=wanted in row.get("agent_output", ""),
                        detail=f"expected citation {wanted!r}",
                    )
                )
            return result

    assevra.register_scorer_module(_Module, replace=True)
    try:
        assert "policy_citation" in registry.dimensions()
        rows = [
            {"id": "p1", "dimension": "policy_citation", "agent_output": "per POL-7", "expected_policy_id": "POL-7"},
            {"id": "p2", "dimension": "policy_citation", "agent_output": "just because", "expected_policy_id": "POL-9"},
        ]
        card = evaluate(records=rows, config={})
        dimension = card.dimension("policy_citation")
        assert dimension.n == 2 and dimension.score == 0.5
        assert card.overall_pass is False          # it gates like any other dimension

        # …and the validator learned its labeling rule from the same declaration.
        from assevra import validate as validate_mod

        unlabeled = validate_mod.validate_row(
            {"id": "p3", "dimension": "policy_citation", "agent_output": "x"}, 1, set(), {}
        )
        assert unlabeled.state == assevra.UNLABELED
        assert "expected_policy_id" in unlabeled.messages[0].fix
    finally:
        registry._SCORERS.pop("policy_citation", None)


def test_registering_a_duplicate_dimension_is_an_error():
    try:
        registry.register_scorer(registry.get_scorer("pii"))
    except registry.RegistryError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("expected RegistryError")


def test_demo_dataset_covers_every_builtin_dimension():
    covered = {row["dimension"] for row in demo.dataset_rows()}
    builtin = set(registry.dimensions())
    assert builtin <= covered | {"policy_citation"}, f"uncovered: {builtin - covered}"


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
