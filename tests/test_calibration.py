"""
Tests for judge calibration metrics (assevra.calibration).

Pure arithmetic — no judge calls. Runs under pytest, or standalone:
`python3 tests/test_calibration.py`.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assevra import calibration as c  # noqa: E402


def test_to_bool():
    assert c.to_bool(True) is True and c.to_bool(False) is False
    assert c.to_bool(1) is True and c.to_bool(0) is False
    assert c.to_bool("pass") is True and c.to_bool("FAIL") is False
    assert c.to_bool("yes") is True and c.to_bool("no") is False
    assert c.to_bool("maybe") is None


def test_confusion_counts():
    judge = [True, True, True, False, False]
    human = [True, True, False, False, False]
    conf = c.confusion(judge, human)
    assert conf == {"tp": 2, "fp": 1, "tn": 2, "fn": 0}


def test_cohens_kappa_perfect_and_zero():
    assert c.cohens_kappa([True, True, False, False], [True, True, False, False]) == 1.0
    # judge always True, human mixed -> chance-corrected agreement is 0
    assert c.cohens_kappa([True, True, True], [True, True, False]) == 0.0
    # degenerate: both raters all one class -> defined as 1.0
    assert c.cohens_kappa([True, True], [True, True]) == 1.0
    assert c.cohens_kappa([], []) is None


def test_cohens_kappa_known_value():
    judge = [True, True, True, False, False]
    human = [True, True, False, False, False]
    k = c.cohens_kappa(judge, human)
    assert abs(k - 0.6154) < 1e-3


def test_compute_metrics():
    judge = [True, True, True, False, False]
    human = [True, True, False, False, False]
    cal = c.compute(judge, human)
    assert cal.n == 5
    assert abs(cal.accuracy - 0.8) < 1e-9
    assert cal.sensitivity == 1.0            # tp/(tp+fn) = 2/2
    assert abs(cal.specificity - 2 / 3) < 1e-9  # tn/(tn+fp) = 2/3
    assert not cal.trustworthy               # kappa 0.615 < 0.85


def test_trustworthy_threshold():
    # 20 perfectly-agreeing rows -> kappa 1.0 -> trustworthy
    cal = c.compute([True, False] * 10, [True, False] * 10)
    assert cal.kappa == 1.0 and cal.trustworthy


def test_to_dict_and_render_smoke():
    cal = c.compute([True, True, False], [True, False, False])
    d = cal.to_dict()
    assert d["n"] == 3 and "cohens_kappa" in d and "confusion" in d
    out = c.render(cal, {"grounding": cal})
    assert "Judge calibration" in out and "Cohen" in out and "grounding" in out


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
