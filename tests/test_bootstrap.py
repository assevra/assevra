"""
Tests for `assevra bootstrap` -- drafting a dataset from captured traces.

Runs under pytest, or standalone: `python3 tests/test_bootstrap.py`.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assevra import bootstrap as bs  # noqa: E402


def _write(tmp: str, name: str, text: str) -> str:
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def test_generic_alias_detection():
    with tempfile.TemporaryDirectory() as tmp:
        src = _write(
            tmp,
            "g.jsonl",
            '{"prompt":"hi","response":"hello","reference":"ctx"}\n'
            '{"question":"q2","answer":"a2"}\n',
        )
        rows, fmt = bs.bootstrap(src)
        assert fmt == "generic"
        assert len(rows) == 2
        assert rows[0]["input"] == "hi"
        assert rows[0]["agent_output"] == "hello"
        assert rows[0]["context"] == "ctx"
        # Default dimension + answer-key placeholder + review hint present.
        assert rows[0]["dimension"] == "task_completion"
        assert rows[0]["must_include"] == []
        assert "needs-review" in rows[0]["tags"]
        assert rows[0]["_review"]


def test_explicit_field_mapping_overrides_aliases():
    with tempfile.TemporaryDirectory() as tmp:
        src = _write(tmp, "g.jsonl", '{"q":"question text","a":"answer text"}\n')
        rows, _ = bs.bootstrap(src, input_field="q", output_field="a")
        assert rows[0]["input"] == "question text"
        assert rows[0]["agent_output"] == "answer text"


def test_openai_chat_format():
    with tempfile.TemporaryDirectory() as tmp:
        src = _write(
            tmp,
            "o.jsonl",
            json.dumps(
                {
                    "request": {
                        "messages": [
                            {"role": "system", "content": "sys ctx"},
                            {"role": "user", "content": "u msg"},
                        ]
                    },
                    "response": {"choices": [{"message": {"role": "assistant", "content": "a msg"}}]},
                }
            )
            + "\n"
            + json.dumps(
                {"messages": [{"role": "user", "content": "u2"}, {"role": "assistant", "content": "a2"}]}
            )
            + "\n",
        )
        rows, fmt = bs.bootstrap(src, dimension="safety")
        assert fmt == "openai"
        assert len(rows) == 2
        assert rows[0]["input"] == "u msg"
        assert rows[0]["agent_output"] == "a msg"
        assert rows[0]["context"] == "sys ctx"  # system -> context
        assert rows[0]["should_refuse"] is None  # safety answer-key placeholder
        assert rows[1]["input"] == "u2" and rows[1]["agent_output"] == "a2"


def test_otel_openinference_and_openllmetry():
    with tempfile.TemporaryDirectory() as tmp:
        otlp = {
            "resourceSpans": [
                {
                    "scopeSpans": [
                        {
                            "spans": [
                                {
                                    "name": "openinference",
                                    "attributes": [
                                        {"key": "input.value", "value": {"stringValue": "in-oi"}},
                                        {"key": "output.value", "value": {"stringValue": "out-oi"}},
                                    ],
                                },
                                {
                                    "name": "openllmetry",
                                    "attributes": [
                                        {"key": "gen_ai.prompt.0.content", "value": {"stringValue": "in-ol"}},
                                        {"key": "gen_ai.completion.0.content", "value": {"stringValue": "out-ol"}},
                                    ],
                                },
                            ]
                        }
                    ]
                }
            ]
        }
        src = _write(tmp, "t.json", json.dumps(otlp))
        rows, fmt = bs.bootstrap(src, dimension="grounding")
        assert fmt == "otel"
        assert len(rows) == 2
        assert rows[0]["input"] == "in-oi" and rows[0]["agent_output"] == "out-oi"
        assert rows[1]["input"] == "in-ol" and rows[1]["agent_output"] == "out-ol"
        # grounding adds no extra answer-key field (context carries the truth).
        assert "must_include" not in rows[0] and "should_refuse" not in rows[0]


def test_limit_and_id_prefix():
    with tempfile.TemporaryDirectory() as tmp:
        src = _write(tmp, "g.jsonl", "".join(f'{{"input":"i{i}","output":"o{i}"}}\n' for i in range(5)))
        rows, _ = bs.bootstrap(src, limit=2, id_prefix="pre")
        assert len(rows) == 2
        assert rows[0]["id"] == "pre-0001"
        assert rows[1]["id"] == "pre-0002"


def test_bad_dimension_and_empty_input_raise():
    with tempfile.TemporaryDirectory() as tmp:
        src = _write(tmp, "g.jsonl", '{"input":"i","output":"o"}\n')
        try:
            bs.bootstrap(src, dimension="nope")
        except bs.BootstrapError:
            pass
        else:
            raise AssertionError("expected BootstrapError for bad dimension")

        empty = _write(tmp, "empty.jsonl", '{"unrelated":"x"}\n')
        try:
            bs.bootstrap(empty)
        except bs.BootstrapError:
            pass
        else:
            raise AssertionError("expected BootstrapError when nothing extractable")


def test_drafted_dataset_is_runnable():
    """A drafted, unlabeled dataset must load and score without error (unknown
    `_review` keys ignored; empty must_include surfaces as 'nothing to verify')."""
    from assevra.cli import build_scorecard

    with tempfile.TemporaryDirectory() as tmp:
        src = _write(tmp, "g.jsonl", '{"input":"i","output":"o with token"}\n')
        rows, _ = bs.bootstrap(src)
        rows[0]["must_include"] = ["token"]  # label the one row
        out = os.path.join(tmp, "draft.jsonl")
        bs.write_dataset(rows, out)
        card = build_scorecard(out, judge_model="")
        assert card.overall_pass is True


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
