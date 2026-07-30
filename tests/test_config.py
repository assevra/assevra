"""
Tests for `.assevra.yml` loading: the dependency-free parser, merge precedence,
and the guarantee that a typo is reported rather than silently ignored.

Runs under pytest, or standalone: `python3 tests/test_config.py`.
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assevra import config as C  # noqa: E402

SAMPLE = """\
# a comment
version: 1
dataset: evals/agent.jsonl     # trailing comment
out_dir: .assevra/out

judge:
  provider: openai
  model: gpt-4o
  panel: [a, b, "c,d"]
  max_tokens: 1024

gate:
  enabled: true
  fail_on_regression: false

thresholds:
  grounding: 0.92
  custom_dimension: 0.5

budgets:
  cost_usd: 0.05
  price:
    input_per_mtok: 3.0

reports:
  formats:
    - md
    - html
"""


def _parse(text: str) -> dict:
    # Exercise the built-in parser specifically, even when PyYAML is installed.
    lines = C._tokenize(text)
    value, _ = C._parse_block(lines, 0, lines[0][1])
    return value


def test_parses_scalars_and_types():
    data = _parse(SAMPLE)
    assert data["version"] == 1
    assert data["dataset"] == "evals/agent.jsonl"      # trailing comment stripped
    assert data["gate"]["enabled"] is True
    assert data["gate"]["fail_on_regression"] is False
    assert data["judge"]["max_tokens"] == 1024
    assert data["thresholds"]["grounding"] == 0.92


def test_parses_inline_and_block_lists():
    data = _parse(SAMPLE)
    assert data["judge"]["panel"] == ["a", "b", "c,d"]  # quoted comma survives
    assert data["reports"]["formats"] == ["md", "html"]


def test_parses_nested_maps():
    data = _parse(SAMPLE)
    assert data["budgets"]["price"]["input_per_mtok"] == 3.0


def test_hash_inside_a_value_is_not_a_comment():
    data = _parse('key: "a # b"\nother: c#d\n')
    assert data["key"] == "a # b"
    assert data["other"] == "c#d"      # no space before '#', so not a comment


def test_tabs_are_rejected_with_a_line_number():
    try:
        _parse("a:\n\tb: 1\n")
    except C.ConfigError as exc:
        assert "line 2" in str(exc)
    else:
        raise AssertionError("expected ConfigError for tab indentation")


def test_load_merges_over_defaults_and_finds_the_file():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, ".assevra.yml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(SAMPLE)
        cfg = C.load(path)
        assert cfg.get("judge.provider") == "openai"
        # untouched defaults survive the merge
        assert cfg.get("reliability.pass_k") == 2
        assert cfg.get("calibration.label_field") == "human_label"


def test_find_config_walks_upward():
    with tempfile.TemporaryDirectory() as tmp:
        nested = os.path.join(tmp, "a", "b")
        os.makedirs(nested)
        with open(os.path.join(tmp, ".assevra.yml"), "w", encoding="utf-8") as fh:
            fh.write("version: 1\ndataset: x.jsonl\n")
        found = C.find_config(nested)
        assert found is not None and found.name == ".assevra.yml"


def test_cli_wins_over_config_which_wins_over_default():
    cfg = C.load(None)  # defaults only (no file in a temp cwd is not guaranteed)
    cfg.data["out_dir"] = "from-config"
    assert cfg.pick("from-cli", "out_dir", ".") == "from-cli"
    assert cfg.pick(None, "out_dir", ".") == "from-config"
    assert cfg.pick(None, "nope.missing", "fallback") == "fallback"
    # A store_true flag left at False must not veto a config that enabled it.
    cfg.data["gate"]["enabled"] = True
    assert cfg.pick(False, "gate.enabled", False) is True


def test_unknown_keys_are_reported_not_swallowed():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, ".assevra.yml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("version: 1\ntreshold: 0.9\njudge:\n  provdier: openai\n")
        cfg = C.load(path)
        assert "treshold" in cfg.unknown_keys
        assert "judge.provdier" in cfg.unknown_keys


def test_open_maps_allow_third_party_keys():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, ".assevra.yml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("version: 1\nthresholds:\n  my_custom_dimension: 0.8\n")
        cfg = C.load(path)
        assert cfg.unknown_keys == []
        assert cfg.threshold("my_custom_dimension") == 0.8


def test_unsupported_version_is_an_error():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, ".assevra.yml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("version: 99\n")
        try:
            C.load(path)
        except C.ConfigError as exc:
            assert "99" in str(exc)
        else:
            raise AssertionError("expected ConfigError for an unsupported version")


def test_rendered_template_parses_back():
    text = C.render_template(dataset="d.jsonl")
    data = C.parse_yaml(text)
    assert data["dataset"] == "d.jsonl"
    assert data["gate"]["enabled"] is True
    assert data["version"] == 1


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
