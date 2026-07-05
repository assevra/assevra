"""
Tests for the Agent Card (assevra.attest) — mapping evidence to control families.

Runs under pytest, or standalone: `python3 tests/test_attest.py`.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assevra import attest  # noqa: E402


def _scorecard(dims, reliability=None, overall=True):
    sc = {
        "assevra_version": "0.3",
        "dataset": "d.jsonl",
        "overall_pass": overall,
        "dimensions": dims,
    }
    if reliability:
        sc["reliability"] = reliability
    return sc


def _dim(name, skipped=False, passed=True):
    if skipped:
        return {"name": name, "skipped": True}
    return {
        "name": name,
        "skipped": False,
        "score": 0.95,
        "ci_95": [0.8, 0.99],
        "sample_size": 20,
        "threshold": 0.9,
        "passed": passed,
    }


def test_card_maps_each_known_dimension_to_frameworks():
    sc = _scorecard([_dim("grounding"), _dim("safety"), _dim("pii"), _dim("task_completion")])
    card = attest.build_card_dict(sc, generated_at="T")
    assert card["agent_card_version"] == "1"
    assert card["overall_pass"] is True
    by_name = {d["dimension"]: d for d in card["dimensions"]}
    for name in ("grounding", "safety", "pii", "task_completion"):
        assert by_name[name]["mappings"], f"{name} should map to at least one control"
    # each mapping has the three fields
    m = by_name["pii"]["mappings"][0]
    assert set(m) == {"framework", "reference", "rationale"}


def test_skipped_dimension_has_no_evidence():
    sc = _scorecard([_dim("grounding", skipped=True)])
    card = attest.build_card_dict(sc, generated_at="T")
    d = card["dimensions"][0]
    assert d["skipped"] is True
    assert "not measured" in d["measured"]


def test_unknown_dimension_maps_to_nothing_gracefully():
    sc = _scorecard([_dim("some_custom_dim")])
    card = attest.build_card_dict(sc, generated_at="T")
    assert card["dimensions"][0]["mappings"] == []


def test_reliability_mappings_present_only_when_scorecard_has_reliability():
    without = attest.build_card_dict(_scorecard([_dim("pii")]), generated_at="T")
    assert without["reliability_mappings"] == []
    with_rel = attest.build_card_dict(
        _scorecard([_dim("pii")], reliability=[{"dimension": "pii", "pass_hat_k": 0.9}]),
        generated_at="T",
    )
    assert with_rel["reliability_mappings"]


def test_signature_note_included_when_provided():
    sig = {
        "algorithm": "ed25519",
        "public_key": "PUB",
        "content_sha256": "abc123",
        "signed_at": "T",
    }
    card = attest.build_card_dict(_scorecard([_dim("pii")]), signature=sig, generated_at="T")
    assert card["signature"]["content_sha256"] == "abc123"
    md = attest.render_markdown(card)
    assert "signed" in md.lower() and "abc123"[:12] in md


def test_markdown_and_json_render():
    card = attest.build_card_dict(_scorecard([_dim("pii"), _dim("grounding", skipped=True)]), generated_at="T")
    md = attest.render_markdown(card)
    # The disclaimer and its scope discipline must be present and prominent.
    assert "Not a certification" in md
    assert "not legal advice" in md.lower() or "legal advice" in md.lower()
    assert "Evidence by dimension" in md
    assert "OWASP" in md and "EU AI Act" in md
    # JSON round-trips.
    parsed = json.loads(attest.render_json(card))
    assert parsed["dimensions"][0]["dimension"] == "pii"
    assert "disclaimer" in parsed


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
