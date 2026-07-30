#!/usr/bin/env python3
"""
Golden snapshot: the numbers must not move silently.

Assevra's whole promise is that a score means something specific. Which means a
change to a regex, a rubric, a threshold, or a scorer's tie-breaking must never
land as an invisible drift in a reported number — it has to be a visible diff
that a human approved.

So this records the exact verdict of every row of the golden dataset, plus each
dimension's score, sample size, interval, and threshold, into a committed file.
CI re-runs it and fails on any difference. When a change *should* move a number:

    python tests/snapshot.py --update

and the diff shows up in the pull request, where a reviewer can agree with it.
That is the same discipline the project asks of its users — freeze what affects a
score, and say so when it changes.

The judged dimensions run against the deterministic mock provider, so the
snapshot is reproducible on any machine, in any fork, with no API key.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assevra import evaluate  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "datasets" / "golden.jsonl"
SNAPSHOT = Path(__file__).parent / "snapshots" / "golden.json"

# The judge is pinned to the mock provider and the config to an explicit literal,
# so the snapshot depends on the code under test and nothing else.
CONFIG = {
    "judge": {"provider": "mock"},
    "budgets": {"price": {"input_per_mtok": 3.0, "output_per_mtok": 15.0}},
    "reliability": {"pass_k": 2},
}


def digest() -> dict:
    """Everything that is a *number someone might quote*, and nothing else.

    Timestamps, file paths, and content hashes are deliberately excluded: they
    change every run and would make the snapshot noise rather than signal.
    """
    card = evaluate(dataset=str(DATASET), config=dict(CONFIG))
    return {
        "assevra_version": card.version,
        "overall_pass": card.overall_pass,
        "judge_model": card.judge_model,
        "dimensions": [
            {
                "name": d.name,
                "mode": d.mode,
                "skipped": d.skipped,
                "threshold": d.threshold,
                "n": d.n,
                "passes": d.passes,
                "score": round(d.score, 6),
                "ci_95": [round(x, 6) for x in d.ci],
                "passed": d.passed,
                "rows": {r.row_id: r.passed for r in d.rows},
            }
            for d in card.dimensions
        ],
        "reliability": [r.to_dict() for r in card.reliability],
    }


def _diff(expected: dict, actual: dict, path: str = "") -> list[str]:
    problems: list[str] = []
    if type(expected) is not type(actual):
        return [f"{path or '<root>'}: type changed {type(expected).__name__} -> {type(actual).__name__}"]
    if isinstance(expected, dict):
        for key in sorted(set(expected) | set(actual)):
            where = f"{path}.{key}" if path else key
            if key not in actual:
                problems.append(f"{where}: removed (was {expected[key]!r})")
            elif key not in expected:
                problems.append(f"{where}: added ({actual[key]!r})")
            else:
                problems.extend(_diff(expected[key], actual[key], where))
    elif isinstance(expected, list):
        if len(expected) != len(actual):
            problems.append(f"{path}: length {len(expected)} -> {len(actual)}")
        for index, (a, b) in enumerate(zip(expected, actual)):
            problems.extend(_diff(a, b, f"{path}[{index}]"))
    elif expected != actual:
        problems.append(f"{path}: {expected!r} -> {actual!r}")
    return problems


def check() -> int:
    if not SNAPSHOT.exists():
        print(f"no snapshot at {SNAPSHOT}. Create it with: python tests/snapshot.py --update")
        return 1
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    actual = digest()
    problems = _diff(expected, actual)
    if not problems:
        print(f"golden snapshot matches ({len(actual['dimensions'])} dimensions).")
        return 0
    print("The golden snapshot changed:\n")
    for problem in problems:
        print(f"  {problem}")
    print(
        "\nIf this change is intended, run `python tests/snapshot.py --update` and commit "
        "the result, so the diff is reviewed rather than absorbed."
    )
    return 1


def update() -> int:
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(digest(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {SNAPSHOT}")
    return 0


def test_golden_snapshot_is_unchanged():
    """Also runs under pytest, so `pytest tests/` covers it."""
    assert check() == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="fail if the numbers moved (default)")
    group.add_argument("--update", action="store_true", help="rewrite the snapshot")
    args = parser.parse_args()
    return update() if args.update else check()


if __name__ == "__main__":
    sys.exit(main())
