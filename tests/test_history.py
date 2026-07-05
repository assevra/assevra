"""
Tests for reliability trend tracking (assevra.history).

Runs under pytest, or standalone: `python3 tests/test_history.py`.
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assevra import history as h  # noqa: E402


def _dim(name, score, lo, hi, passed, threshold=0.9, skipped=False, n=10):
    return {
        "name": name,
        "skipped": skipped,
        "score": score,
        "ci_lo": lo,
        "ci_hi": hi,
        "n": n,
        "passes": round(score * n),
        "threshold": threshold,
        "passed": passed,
    }


def _rec(overall, dims, label="x"):
    return {"timestamp": "2026-07-05T00:00:00+00:00", "label": label,
            "dataset": "d", "judge_model": "", "overall_pass": overall, "dimensions": dims}


def test_stable_when_inside_previous_interval():
    prev = _rec(True, [_dim("g", 0.90, 0.80, 0.96, True, threshold=0.5)])
    curr = _rec(True, [_dim("g", 0.88, 0.78, 0.95, True, threshold=0.5)])  # dropped but inside prev CI
    d = h.compare(prev, curr)[0]
    assert d.status == "stable"
    assert not d.is_regression


def test_regressed_when_below_previous_interval():
    prev = _rec(True, [_dim("g", 0.95, 0.90, 0.99, True, threshold=0.5)])
    # below prev ci_lo (0.90) but still above its own threshold, so not a crossing:
    curr = _rec(True, [_dim("g", 0.85, 0.78, 0.91, True, threshold=0.5)])
    d = h.compare(prev, curr)[0]
    assert d.status == "regressed"
    assert d.is_regression


def test_improved_when_above_previous_interval():
    prev = _rec(True, [_dim("g", 0.70, 0.60, 0.80, True, threshold=0.5)])
    curr = _rec(True, [_dim("g", 0.90, 0.85, 0.95, True, threshold=0.5)])
    d = h.compare(prev, curr)[0]
    assert d.status == "improved"
    assert not d.is_regression


def test_threshold_crossing_dominates():
    # A pass -> fail is "now failing" even if the numeric move is small.
    prev = _rec(True, [_dim("t", 0.91, 0.70, 0.99, True, threshold=0.90)])
    curr = _rec(False, [_dim("t", 0.89, 0.68, 0.97, False, threshold=0.90)])
    d = h.compare(prev, curr)[0]
    assert d.status == "now failing"
    assert d.is_regression
    prev2 = _rec(False, [_dim("t", 0.80, 0.60, 0.92, False, threshold=0.90)])
    curr2 = _rec(True, [_dim("t", 0.95, 0.85, 0.99, True, threshold=0.90)])
    assert h.compare(prev2, curr2)[0].status == "now passing"


def test_new_and_skipped_dimensions():
    prev = _rec(True, [_dim("a", 1.0, 0.9, 1.0, True)])
    curr = _rec(True, [
        _dim("a", 1.0, 0.9, 1.0, True, skipped=True),  # became skipped
        _dim("b", 1.0, 0.9, 1.0, True),                # brand new
    ])
    deltas = {d.name: d for d in h.compare(prev, curr)}
    assert deltas["a"].status == "skipped"
    assert deltas["b"].status == "new"
    assert not deltas["a"].is_regression and not deltas["b"].is_regression


def test_overall_regression_from_verdict_flip():
    prev = _rec(True, [_dim("g", 0.95, 0.9, 0.99, True)])
    curr = _rec(False, [_dim("g", 0.95, 0.9, 0.99, True)])  # dims stable, overall flipped
    deltas = h.compare(prev, curr)
    assert h.is_overall_regression(prev, curr, deltas)


def test_append_load_and_baseline_selection():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "sub", "history.jsonl")  # nested dir must be created
        h.append_record(path, _rec(True, [_dim("g", 1.0, 0.9, 1.0, True)], label="v1"))
        h.append_record(path, _rec(True, [_dim("g", 1.0, 0.9, 1.0, True)], label="v2"))
        hist = h.load_history(path)
        assert len(hist) == 2
        # default baseline = most recent
        assert h.find_baseline(hist, None)["label"] == "v2"
        # labelled baseline
        assert h.find_baseline(hist, "v1")["label"] == "v1"
        # missing label -> None
        assert h.find_baseline(hist, "nope") is None
        assert h.find_baseline([], None) is None


def test_render_history_smoke():
    hist = [
        _rec(True, [_dim("g", 1.0, 0.9, 1.0, True)], label="v1"),
        _rec(False, [_dim("g", 0.5, 0.3, 0.7, False)], label="v2"),
    ]
    out = h.render_history(hist)
    assert "v1" in out and "v2" in out and "PASS" in out and "FAIL" in out
    assert h.render_history([]) == "No runs recorded yet."


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
