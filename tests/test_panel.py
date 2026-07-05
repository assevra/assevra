"""
Tests for the judge Panel (jury) aggregation and disagreement surfacing.

No live API calls — panelists are stubbed. Runs under pytest, or standalone:
`python3 tests/test_panel.py`.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assevra import judge as J  # noqa: E402
from assevra.scorers import grounding  # noqa: E402


class _Stub:
    """A judge stub that returns a fixed parsed dict."""

    def __init__(self, model, output):
        self.model = model
        self._output = output

    def score_json(self, prompt):
        return dict(self._output)


def _panel(outputs):
    stubs = [_Stub(f"m{i}", o) for i, o in enumerate(outputs)]
    return J.Panel(models=[s.model for s in stubs], judges=stubs)


def test_median_int():
    assert J._median_int([4]) == 4
    assert J._median_int([4, 5, 4]) == 4
    assert J._median_int([1, 5]) == 3          # round(3.0)
    assert J._median_int([4, 5]) == 4          # round(4.5) -> 4 (banker's on .5)


def test_panel_aggregates_score_by_median():
    p = _panel([
        {"score": 4, "reason": "a"},
        {"score": 5, "reason": "b"},
        {"score": 4, "reason": "c"},
    ])
    out = p.score_json("x")
    assert out["score"] == 4
    assert out["panel_scores"] == [4, 5, 4]
    assert out["reason"] in ("a", "c")          # a panelist that hit the aggregate
    assert out["panel_models"] == ["m0", "m1", "m2"]


def test_panel_aggregates_refused_by_majority():
    p = _panel([
        {"refused": True, "reason": "r1"},
        {"refused": True, "reason": "r2"},
        {"refused": False, "reason": "r3"},
    ])
    out = p.score_json("x")
    assert out["refused"] is True               # 2 of 3
    assert out["panel_refused"] == [True, True, False]


def test_panel_majority_tie_is_not_refused():
    p = _panel([{"refused": True}, {"refused": False}])
    assert p.score_json("x")["refused"] is False  # 1 of 2 -> not a majority


def test_panel_ignores_parse_errors_but_keeps_quorum():
    p = _panel([
        {"score": 5, "reason": "ok"},
        {"_parse_error": "junk"},
        {"score": 5, "reason": "ok2"},
    ])
    out = p.score_json("x")
    assert out["score"] == 5 and out["panel_scores"] == [5, 5]


def test_panel_all_errors_is_parse_error():
    p = _panel([{"_parse_error": "a"}, {"_parse_error": "b"}])
    assert "_parse_error" in p.score_json("x")


def test_panel_model_label():
    assert _panel([{"score": 4}]).model == "panel[m0]"


def test_panel_note_flags_disagreement():
    assert J.panel_note({}) == ""
    assert "DISAGREE" not in J.panel_note({"panel_scores": [4, 4, 4]})
    assert "DISAGREE" in J.panel_note({"panel_scores": [3, 5, 4]})   # spread 2
    assert "DISAGREE" in J.panel_note({"panel_refused": [True, False]})
    assert "DISAGREE" not in J.panel_note({"panel_refused": [True, True]})


def test_grounding_scorer_uses_panel_and_surfaces_votes():
    # Two panelists say 5, one says 4 -> aggregate 5, passes; detail notes the panel.
    panel = _panel([{"score": 5, "reason": "grounded"}, {"score": 5}, {"score": 4}])
    rows = [{"id": "g1", "context": "c", "agent_output": "a"}]
    result = grounding.score(rows, panel)
    rr = result.rows[0]
    assert rr.passed is True
    assert rr.raw_score == 5
    assert "panel" in rr.detail


def test_judge_prompts_format_without_brace_collision():
    # Regression: the prompts embed a literal JSON example ({...}) that must not
    # collide with str.format fields. A stub judge exercises the .format() path.
    from assevra.scorers import safety

    single = _Stub("solo", {"score": 5, "reason": "ok"})
    g = grounding.score([{"id": "g", "context": "c", "agent_output": "a"}], single)
    assert g.rows[0].passed and not g.skipped

    s = safety.score(
        [{"id": "s", "input": "q", "agent_output": "a", "should_refuse": True}],
        _Stub("solo", {"refused": True, "reason": "declined"}),
    )
    assert s.rows[0].passed and not s.skipped


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
