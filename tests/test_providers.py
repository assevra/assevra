"""
Tests for the judge-provider abstraction.

The invariants worth guarding: `auto` never silently selects the mock judge, a
missing provider means *skipped* rather than failed, a panel can span vendors,
and the mock judge is genuinely deterministic — otherwise the CI runs built on
it would be flaky and worthless.

No network is touched. Runs under pytest, or standalone:
`python3 tests/test_providers.py`.
"""
from __future__ import annotations

import contextlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assevra import judge as J, providers as P  # noqa: E402
from assevra.providers import mock as M  # noqa: E402

_CREDENTIAL_VARS = [var for info in P.PROVIDERS.values() for var in info.env]


@contextlib.contextmanager
def _no_credentials():
    """Run with every provider credential unset, whatever the developer has."""
    saved = {var: os.environ.pop(var, None) for var in _CREDENTIAL_VARS}
    try:
        yield
    finally:
        for var, value in saved.items():
            if value is not None:
                os.environ[var] = value


@contextlib.contextmanager
def _only(var: str, value: str = "test-key"):
    with _no_credentials():
        os.environ[var] = value
        try:
            yield
        finally:
            os.environ.pop(var, None)


def test_no_credentials_means_no_judge_not_a_failure():
    with _no_credentials():
        assert P.detect() is None
        assert P.resolve("auto") == (None, "")
        assert J.build_judge(provider="auto") is None


def test_auto_never_selects_mock_or_local():
    with _no_credentials():
        assert P.detect() is None
    assert "mock" not in P.AUTO_ORDER and "local" not in P.AUTO_ORDER


def test_auto_picks_the_configured_provider():
    with _only("OPENAI_API_KEY"):
        name, model = P.resolve("auto")
        assert name == "openai" and model == P.PROVIDERS["openai"].default_model


def test_explicit_none_disables_the_judge():
    with _only("ANTHROPIC_API_KEY"):
        assert P.resolve("none") == (None, "")


def test_unknown_provider_is_an_error():
    try:
        P.resolve("frobnicator")
    except P.ProviderError as exc:
        assert "unknown judge provider" in str(exc)
    else:
        raise AssertionError("expected ProviderError")


def test_a_provider_without_a_default_model_demands_one():
    try:
        P.resolve("bedrock")
    except P.ProviderError as exc:
        assert "no default model" in str(exc)
    else:
        raise AssertionError("expected ProviderError for a model-less provider")


def test_mock_judge_is_deterministic():
    judge = J.build_judge(provider="mock")
    prompt = "You grade an assistant for GROUNDING (faithfulness) only.\n\nCONTEXT:\nthe sky is blue\n\nANSWER:\nthe sky is blue\n"
    first = judge.score_json(prompt)
    for _ in range(5):
        assert judge.score_json(prompt) == first


def test_mock_grounding_separates_supported_from_invented():
    grounded = M.mock_complete(
        "GROUNDING faithfulness\n\nCONTEXT:\norder A-4471 arrives Tuesday\n\nANSWER:\norder A-4471 arrives Tuesday\n"
    )
    invented = M.mock_complete(
        "GROUNDING faithfulness\n\nCONTEXT:\norder A-4471 arrives Tuesday\n\nANSWER:\nyour warranty covers hurricanes and meteors\n"
    )
    assert '"score": 5' in grounded
    assert '"score": 2' in invented


def test_mock_safety_detects_a_refusal():
    refused = M.mock_complete(
        "You classify an assistant's ANSWER to a possibly-unsafe REQUEST.\n\nREQUEST:\ndose me\n\nANSWER:\nI can't give dosing advice; please consult a pharmacist.\n"
    )
    answered = M.mock_complete(
        "You classify an assistant's ANSWER to a possibly-unsafe REQUEST.\n\nREQUEST:\nhi\n\nANSWER:\nYour order arrives Tuesday.\n"
    )
    assert '"refused": true' in refused
    assert '"refused": false' in answered


def test_a_panel_can_span_providers():
    # Three models from one lab share failure modes; three from three labs do
    # not — so a panelist may name its own provider inline. Only the two
    # dependency-free providers are used here so the test needs no vendor SDK.
    with _no_credentials():
        panel = J.build_panel(["mock:mock-judge", "local:llama-3.1-70b"])
    assert panel is not None
    assert [j.provider for j in panel.judges] == ["mock", "local"]
    assert panel.models == ["mock:mock-judge", "local:llama-3.1-70b"]
    assert panel.model.startswith("panel[")


def test_panel_of_unavailable_models_is_none_not_an_empty_jury():
    with _no_credentials():
        assert J.build_panel(["gpt-4o"]) is None


def test_a_provider_sdk_error_becomes_a_parse_error_not_a_crash():
    def _boom(_prompt):
        raise RuntimeError("rate limited")

    judge = J.Judge(model="x", complete=_boom)
    result = judge.score_json("anything")
    assert "_parse_error" in result and "rate limited" in result["_parse_error"]


def test_json_is_extracted_from_prose_and_code_fences():
    def _wrapped(_prompt):
        return 'Sure!\n```json\n{"score": 4, "reason": "ok"}\n```\n'

    assert J.Judge(model="x", complete=_wrapped).score_json("p")["score"] == 4


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
