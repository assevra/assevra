"""
Tests for pass^k and run-to-run consistency (assevra.reliability).

Runs under pytest, or standalone: `python3 tests/test_reliability.py`.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assevra import reliability as rel  # noqa: E402


class _Row:
    def __init__(self, row_id, passed):
        self.row_id, self.passed = row_id, passed


def test_pass_hat_k_values():
    assert rel.pass_hat_k(3, 3, 2) == 1.0              # all trials pass -> always
    assert abs(rel.pass_hat_k(2, 3, 2) - 1 / 3) < 1e-9  # C(2,2)/C(3,2) = 1/3
    assert rel.pass_hat_k(1, 3, 2) == 0.0              # fewer passes than k
    assert rel.pass_hat_k(3, 3, 4) is None             # fewer trials than k
    assert rel.pass_hat_k(5, 10, 1) == 0.5             # k=1 reduces to the pass rate
    assert rel.pass_hat_k(4, 4, 4) == 1.0


def test_group_passed_by_case_uses_case_id():
    rows = [_Row("a1", True), _Row("a2", False), _Row("b1", True)]
    id_to_case = {"a1": "A", "a2": "A", "b1": "B"}
    groups = rel.group_passed_by_case(rows, id_to_case)
    assert groups == {"A": [True, False], "B": [True]}


def test_ungrouped_rows_are_their_own_cases():
    rows = [_Row("x", True), _Row("y", False)]
    groups = rel.group_passed_by_case(rows, {})  # no mapping -> id is the case
    assert groups == {"x": [True], "y": [False]}


def test_compute_dimension_consistency_and_passk():
    # case A: 3/3 pass (unanimous); case B: 2/3 pass (flaky)
    passed_by_case = {"A": [True, True, True], "B": [True, True, False]}
    cr = rel.compute_dimension("task_completion", passed_by_case, k=2)
    assert cr is not None
    assert cr.n_cases == 2 and cr.n_repeated == 2 and cr.total_trials == 6
    assert cr.consistency == 0.5              # 1 unanimous of 2 repeated cases
    assert cr.flaky_cases == ["B"]
    # pass^2: A -> 1.0, B -> 1/3; mean = 2/3
    assert abs(cr.passk - 2 / 3) < 1e-9
    assert cr.passk_cases == 2


def test_no_repeated_case_returns_none():
    # every case single-trial -> nothing to assess
    assert rel.compute_dimension("g", {"a": [True], "b": [False]}, k=2) is None


def test_case_with_too_few_trials_excluded_from_passk():
    # A has 3 trials (counts for k=2), B has 2 trials (counts), C single (excluded)
    passed_by_case = {"A": [True, True, True], "B": [True, False], "C": [True]}
    cr = rel.compute_dimension("g", passed_by_case, k=2)
    assert cr.n_cases == 3 and cr.n_repeated == 2
    assert cr.passk_cases == 2  # only A and B have n >= 2


def test_to_dict_and_markdown_render():
    cr = rel.compute_dimension("g", {"A": [True, True], "B": [True, False]}, k=2)
    d = cr.to_dict()
    assert d["dimension"] == "g" and d["k"] == 2 and d["flaky_cases"] == ["B"]
    assert "pass_hat_k" in d
    md = rel.render_markdown_section([cr])
    assert "Reliability across repeated trials" in md and "pass^k" in md
    assert rel.render_markdown_section([]) == ""


def test_html_render_smoke():
    cr = rel.compute_dimension("g", {"A": [True, True], "B": [True, False]}, k=2)
    html = rel.render_html_section([cr], esc=lambda s: s)
    assert "Reliability across repeated trials" in html and "<table>" in html
    assert rel.render_html_section([], esc=lambda s: s) == ""


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
