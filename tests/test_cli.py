"""
End-to-end tests for the command line.

These are the integration tests: they exercise the commands the way CI does,
including the exit codes CI depends on. The contract under test is stated in the
CLI docstring — **0** success, **1** the gate failed, **2** the command could not
run — and it is a contract because build pipelines branch on it.

Everything runs offline: the judged path uses the deterministic mock provider.

Runs under pytest, or standalone: `python3 tests/test_cli.py`.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assevra import cli, demo  # noqa: E402

PASSING = {
    "id": "t1",
    "dimension": "task_completion",
    "agent_output": "your code is 42",
    "must_include": ["42"],
}
FAILING = dict(PASSING, id="t2", must_include=["missing-token"])


def _dataset(directory: str, rows: list) -> str:
    path = os.path.join(directory, "d.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return path


def test_run_passes_and_writes_all_three_reports():
    with tempfile.TemporaryDirectory() as tmp:
        dataset = _dataset(tmp, [PASSING])
        code = cli.main(["run", "--dataset", dataset, "--out-dir", tmp, "--quiet", "--config", "none"])
        assert code == cli.EXIT_OK
        for name in ("scorecard.md", "scorecard.json", "scorecard.html"):
            assert os.path.getsize(os.path.join(tmp, name)) > 0


def test_gate_exit_code_is_one_when_a_dimension_fails():
    with tempfile.TemporaryDirectory() as tmp:
        dataset = _dataset(tmp, [PASSING, FAILING])
        assert cli.main(["run", "--dataset", dataset, "--out-dir", tmp, "--quiet", "--config", "none"]) == cli.EXIT_OK
        code = cli.main(["run", "--dataset", dataset, "--out-dir", tmp, "--quiet", "--gate", "--config", "none"])
        assert code == cli.EXIT_GATE_FAILED


def test_a_broken_dataset_exits_two_before_scoring():
    with tempfile.TemporaryDirectory() as tmp:
        dataset = _dataset(tmp, [{"id": "a", "dimension": "vibes", "agent_output": "x"}])
        code = cli.main(["run", "--dataset", dataset, "--out-dir", tmp, "--quiet", "--config", "none"])
        assert code == cli.EXIT_USAGE
        assert not os.path.exists(os.path.join(tmp, "scorecard.json"))


def test_threshold_override_from_the_command_line():
    with tempfile.TemporaryDirectory() as tmp:
        dataset = _dataset(tmp, [PASSING, FAILING])
        code = cli.main([
            "run", "--dataset", dataset, "--out-dir", tmp, "--quiet",
            "--gate", "--threshold", "task_completion=0.4", "--config", "none",
        ])
        assert code == cli.EXIT_OK


def test_validate_exit_codes():
    with tempfile.TemporaryDirectory() as tmp:
        good = _dataset(tmp, [PASSING])
        assert cli.main(["validate", good, "--config", "none"]) == cli.EXIT_OK

        unlabeled = os.path.join(tmp, "u.jsonl")
        with open(unlabeled, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(dict(PASSING, must_include=[])) + "\n")
        assert cli.main(["validate", unlabeled, "--config", "none"]) == cli.EXIT_OK
        assert cli.main(["validate", unlabeled, "--strict", "--config", "none"]) == cli.EXIT_GATE_FAILED


def test_validate_writes_a_machine_readable_report():
    with tempfile.TemporaryDirectory() as tmp:
        dataset = _dataset(tmp, [PASSING])
        out = os.path.join(tmp, "report.json")
        assert cli.main(["validate", dataset, "--out", out, "--config", "none"]) == cli.EXIT_OK
        payload = json.loads(open(out, encoding="utf-8").read())
        assert payload["ok"] is True and payload["counts"]["labeled"] == 1


def test_config_drives_run_with_no_flags():
    with tempfile.TemporaryDirectory() as tmp:
        dataset = _dataset(tmp, [PASSING, FAILING])
        config = os.path.join(tmp, ".assevra.yml")
        with open(config, "w", encoding="utf-8") as fh:
            fh.write(
                "version: 1\n"
                f"dataset: {dataset}\n"
                f"out_dir: {tmp}\n"
                "gate:\n  enabled: true\n"
                "judge:\n  provider: none\n"
            )
        assert cli.main(["run", "--config", config, "--quiet"]) == cli.EXIT_GATE_FAILED


def test_demo_writes_a_full_artifact_set_offline():
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "demo")
        assert cli.main(["demo", "--out-dir", out, "--provider", "mock"]) == cli.EXIT_OK
        for name in (
            "scorecard.html", "scorecard.json", "scorecard.md",
            "agent-card.md", "agent-card.json", "demo.jsonl", ".assevra.yml",
        ):
            assert os.path.getsize(os.path.join(out, name)) > 0
        payload = json.loads(open(os.path.join(out, "scorecard.json"), encoding="utf-8").read())
        assert payload["overall_pass"] is True
        assert payload["judge_model"] == "mock-judge"


def test_demo_without_a_judge_skips_rather_than_passes():
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "demo")
        assert cli.main(["demo", "--out-dir", out, "--provider", "none"]) == cli.EXIT_OK
        payload = json.loads(open(os.path.join(out, "scorecard.json"), encoding="utf-8").read())
        grounding = [d for d in payload["dimensions"] if d["name"] == "grounding"][0]
        assert grounding["skipped"] is True and grounding["passed"] is None


def test_schema_command_exports_every_contract():
    with tempfile.TemporaryDirectory() as tmp:
        assert cli.main(["schema", "--out-dir", tmp]) == cli.EXIT_OK
        written = sorted(os.listdir(tmp))
        assert "scorecard.schema.json" in written and len(written) == 5


def test_init_scaffolds_a_project_from_traces():
    with tempfile.TemporaryDirectory() as tmp:
        traces = os.path.join(tmp, "traces.jsonl")
        with open(traces, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"prompt": "hi", "response": "hello"}) + "\n")
        code = cli.main(["init", "--root", tmp, "--from", traces,
                         "--dataset", os.path.join(tmp, "evals", "agent.jsonl")])
        assert code == cli.EXIT_OK
        assert os.path.exists(os.path.join(tmp, ".assevra.yml"))
        assert os.path.exists(os.path.join(tmp, "EVALUATION.md"))
        assert os.path.exists(os.path.join(tmp, ".github", "workflows", "assevra.yml"))
        drafted = open(os.path.join(tmp, "evals", "agent.jsonl"), encoding="utf-8").read()
        assert "needs-review" in drafted


def test_init_does_not_clobber_without_force():
    with tempfile.TemporaryDirectory() as tmp:
        config = os.path.join(tmp, ".assevra.yml")
        with open(config, "w", encoding="utf-8") as fh:
            fh.write("version: 1\ndataset: mine.jsonl\n")
        cli.main(["init", "--root", tmp, "--no-workflow", "--no-docs"])
        assert "mine.jsonl" in open(config, encoding="utf-8").read()


def test_integrate_prints_a_wiring_guide():
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "guide.md")
        assert cli.main(["integrate", "langgraph", "--out", out]) == cli.EXIT_OK
        text = open(out, encoding="utf-8").read()
        assert "assevra bootstrap" in text and "LangGraph" in text


def test_sign_and_verify_round_trip():
    try:
        import cryptography  # noqa: F401
    except ImportError:
        return  # the signing extra is not installed in this environment
    with tempfile.TemporaryDirectory() as tmp:
        dataset = _dataset(tmp, [PASSING])
        private = os.path.join(tmp, "k.pem")
        public = os.path.join(tmp, "k.txt")
        assert cli.main(["keygen", "--out-private", private, "--out-public", public]) == 0
        assert cli.main(["run", "--dataset", dataset, "--out-dir", tmp, "--quiet",
                         "--sign", private, "--config", "none"]) == cli.EXIT_OK
        code = cli.main([
            "verify",
            "--scorecard", os.path.join(tmp, "scorecard.json"),
            "--signature", os.path.join(tmp, "scorecard.sig.json"),
            "--public-key", public,
        ])
        assert code == cli.EXIT_OK

        # Tampering must break verification — that is the whole point.
        path = os.path.join(tmp, "scorecard.json")
        payload = json.loads(open(path, encoding="utf-8").read())
        payload["overall_pass"] = not payload["overall_pass"]
        open(path, "w", encoding="utf-8").write(json.dumps(payload))
        assert cli.main([
            "verify", "--scorecard", path,
            "--signature", os.path.join(tmp, "scorecard.sig.json"),
        ]) == cli.EXIT_GATE_FAILED


def test_history_records_and_compares_runs():
    with tempfile.TemporaryDirectory() as tmp:
        dataset = _dataset(tmp, [PASSING])
        history = os.path.join(tmp, "history.jsonl")
        for label in ("v1", "v2"):
            assert cli.main(["run", "--dataset", dataset, "--out-dir", tmp, "--quiet",
                             "--history", history, "--label", label, "--config", "none"]) == cli.EXIT_OK
        assert cli.main(["history", "--history", history, "--config", "none"]) == cli.EXIT_OK
        assert len(open(history, encoding="utf-8").read().strip().splitlines()) == 2


def test_dogfood_the_repository_dataset_if_present():
    """The repo's own golden dataset must stay valid and passing."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dataset = os.path.join(root, "datasets", "golden.jsonl")
    if not os.path.exists(dataset):
        return
    with tempfile.TemporaryDirectory() as tmp:
        assert cli.main(["validate", dataset, "--config", "none"]) == cli.EXIT_OK
        assert cli.main(["run", "--dataset", dataset, "--out-dir", tmp, "--quiet",
                         "--gate", "--judge-provider", "mock", "--config", "none"]) == cli.EXIT_OK


def test_demo_dataset_ships_inside_the_package():
    assert demo.DEMO_DATASET.exists()
    assert len(demo.dataset_rows()) >= 20


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
