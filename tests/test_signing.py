"""
Tests for scorecard signing/verification (assevra.signing).

Signing needs the optional `cryptography` extra; when it is absent these tests
skip cleanly rather than fail. Runs under pytest, or standalone:
`python3 tests/test_signing.py`.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assevra import signing as sg  # noqa: E402

# Detect whether the crypto backend is available; skip if not.
try:
    _PRIV, _PUB = sg.generate_keypair()
    HAVE_CRYPTO = True
except sg.SigningError:
    HAVE_CRYPTO = False

# A representative scorecard-shaped payload.
CARD = {
    "assevra_version": "0.1",
    "dataset": "d.jsonl",
    "judge_model": "",
    "overall_pass": True,
    "dimensions": [{"name": "pii", "score": 1.0, "passed": True}],
}

TS = "2026-07-05T00:00:00+00:00"  # fixed timestamp -> deterministic signatures


def test_canonical_hash_is_key_order_independent():
    a = {"x": 1, "y": [1, 2], "z": {"b": 2, "a": 1}}
    b = {"z": {"a": 1, "b": 2}, "y": [1, 2], "x": 1}
    assert sg.content_hash(a) == sg.content_hash(b)


def test_sign_verify_roundtrip_and_pinning():
    if not HAVE_CRYPTO:
        print("  (skipped: cryptography not installed)")
        return
    block = sg.sign_scorecard(CARD, _PRIV, signed_at=TS)
    assert block["algorithm"] == "ed25519"
    assert block["public_key"] == _PUB
    assert block["signed_at"] == TS

    # Trust-on-first-use: valid, but not pinned.
    r = sg.verify_scorecard(CARD, block)
    assert r.ok and r.content_matches and r.signature_valid and not r.pinned

    # Pinned to the correct key: verified authorship.
    r2 = sg.verify_scorecard(CARD, block, expected_public_key_b64=_PUB)
    assert r2.ok and r2.pinned


def test_deterministic_signature_for_fixed_timestamp():
    if not HAVE_CRYPTO:
        print("  (skipped: cryptography not installed)")
        return
    b1 = sg.sign_scorecard(CARD, _PRIV, signed_at=TS)
    b2 = sg.sign_scorecard(CARD, _PRIV, signed_at=TS)
    assert b1["signature"] == b2["signature"]  # Ed25519 is deterministic


def test_tamper_is_detected():
    if not HAVE_CRYPTO:
        print("  (skipped: cryptography not installed)")
        return
    block = sg.sign_scorecard(CARD, _PRIV, signed_at=TS)
    tampered = dict(CARD)
    tampered["overall_pass"] = False  # attacker flips the verdict
    r = sg.verify_scorecard(tampered, block)
    assert not r.ok
    assert not r.content_matches
    assert "modified" in r.reason


def test_wrong_pinned_key_is_rejected():
    if not HAVE_CRYPTO:
        print("  (skipped: cryptography not installed)")
        return
    block = sg.sign_scorecard(CARD, _PRIV, signed_at=TS)
    _other_priv, other_pub = sg.generate_keypair()
    r = sg.verify_scorecard(CARD, block, expected_public_key_b64=other_pub)
    assert not r.ok
    # Signature itself is valid; it is the authorship pin that fails.
    assert r.signature_valid and not r.pinned


def test_forgery_with_attacker_key_fails_against_pinned_real_key():
    if not HAVE_CRYPTO:
        print("  (skipped: cryptography not installed)")
        return
    # Attacker edits the card and signs it with their own key.
    forged_card = dict(CARD)
    forged_card["overall_pass"] = False
    attacker_priv, _attacker_pub = sg.generate_keypair()
    forged_block = sg.sign_scorecard(forged_card, attacker_priv, signed_at=TS)
    # Victim pins the REAL signer's public key -> forgery rejected.
    r = sg.verify_scorecard(forged_card, forged_block, expected_public_key_b64=_PUB)
    assert not r.ok


def test_malformed_signature_block_rejected():
    if not HAVE_CRYPTO:
        print("  (skipped: cryptography not installed)")
        return
    r = sg.verify_scorecard(CARD, {"algorithm": "ed25519"})  # missing fields
    assert not r.ok and "missing" in r.reason


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    tag = "" if HAVE_CRYPTO else " (crypto-dependent tests skipped)"
    print(f"\n{len(fns)} passed{tag}")


if __name__ == "__main__":
    _run_all()
