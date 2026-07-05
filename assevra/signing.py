"""
Cryptographic signing for Assevra Reliability Scorecards.

A scorecard is only useful as *evidence* if a third party -- an auditor, a
procurement reviewer, a customer -- can confirm it was produced by whoever claims
to have produced it and has not been altered since. A styled HTML file is
shareable; it is not tamper-evident. This module makes the scorecard tamper-evident.

The scheme is deliberately boring and standard: **Ed25519** detached signatures
over a canonical serialization of the scorecard's content.

  * The signer holds an Ed25519 private key and publishes the matching public key
    (in a repo, on a site, in an email footer -- anywhere durable).
  * `sign` canonicalizes the scorecard's data (sorted keys, no incidental
    whitespace), hashes it with SHA-256, wraps that hash together with the public
    key and an optional timestamp into a small *signing payload*, and signs the
    payload. The result is a detached `scorecard.sig.json` -- the scorecard file
    itself is never modified.
  * `verify` recomputes the content hash from the scorecard, checks it matches the
    hash the signature commits to (so any edit to the scorecard breaks
    verification), then verifies the Ed25519 signature over the payload.

Because the signature embeds the public key, verification is self-contained; but
self-contained verification only proves *internal consistency* (trust-on-first-use).
To prove authorship, pin the expected public key with `--public-key` -- then a
forger cannot simply substitute their own key.

Signing needs the `cryptography` package, kept out of Assevra's dependency-free
core as the optional ``[sign]`` extra: ``pip install "assevra[sign]"``.
"""
from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Optional

SIGNATURE_VERSION = "1"
ALGORITHM = "ed25519"


class SigningError(Exception):
    """Raised for any signing/verification failure (missing dep, bad key, ...)."""


def _require_crypto():
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
            Ed25519PublicKey,
        )
    except ImportError as exc:  # pragma: no cover - exercised via the extra
        raise SigningError(
            "signing requires the 'cryptography' package. "
            'Install it with:  pip install "assevra[sign]"'
        ) from exc
    return Ed25519PrivateKey, Ed25519PublicKey, serialization


# --------------------------------------------------------------------------- #
# Canonicalization + hashing                                                   #
# --------------------------------------------------------------------------- #
def canonical_bytes(obj: Any) -> bytes:
    """Deterministic, formatting-independent serialization used for hashing.

    Sorting keys and stripping incidental whitespace means a scorecard hashes to
    the same value regardless of how its JSON file happened to be indented.
    """
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def content_hash(scorecard_dict: dict) -> str:
    """SHA-256 hex digest of a scorecard's canonical content."""
    return hashlib.sha256(canonical_bytes(scorecard_dict)).hexdigest()


def _signing_payload(sha256: str, public_key_b64: str, signed_at: Optional[str]) -> dict:
    """The exact object that is signed. Everything a verifier must trust lives
    here so nothing in the signature block is unauthenticated."""
    return {
        "algorithm": ALGORITHM,
        "assevra_signature_version": SIGNATURE_VERSION,
        "content_sha256": sha256,
        "public_key": public_key_b64,
        "signed_at": signed_at,
    }


# --------------------------------------------------------------------------- #
# Keys                                                                         #
# --------------------------------------------------------------------------- #
def generate_keypair() -> tuple[str, str]:
    """Return (private_key_PEM, public_key_base64). Keep the private key secret;
    publish the public key."""
    Ed25519PrivateKey, _pub, serialization = _require_crypto()
    priv = Ed25519PrivateKey.generate()
    priv_pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    return priv_pem, _public_b64(priv.public_key(), serialization)


def _public_b64(public_key, serialization) -> str:
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


def load_private_key(pem_text: str):
    Ed25519PrivateKey, _pub, serialization = _require_crypto()
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    try:
        key = load_pem_private_key(pem_text.encode("utf-8"), password=None)
    except Exception as exc:
        raise SigningError(f"could not load private key: {exc}") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise SigningError("private key is not an Ed25519 key")
    return key


def _load_public_key_b64(b64: str):
    _priv, Ed25519PublicKey, _ser = _require_crypto()
    try:
        raw = base64.b64decode(b64.strip(), validate=True)
        return Ed25519PublicKey.from_public_bytes(raw)
    except Exception as exc:
        raise SigningError(f"invalid public key: {exc}") from exc


# --------------------------------------------------------------------------- #
# Sign                                                                         #
# --------------------------------------------------------------------------- #
def sign_scorecard(
    scorecard_dict: dict, private_pem: str, signed_at: Optional[str] = None
) -> dict:
    """Produce a detached signature block for a scorecard dict.

    `signed_at` is an optional caller-supplied timestamp string (kept explicit so
    the operation is deterministic and testable); when present it is part of what
    is signed.
    """
    _priv, _pub, serialization = _require_crypto()
    key = load_private_key(private_pem)
    pub_b64 = _public_b64(key.public_key(), serialization)

    sha256 = content_hash(scorecard_dict)
    payload = _signing_payload(sha256, pub_b64, signed_at)
    signature = key.sign(canonical_bytes(payload))

    block = dict(payload)
    block["signature"] = base64.b64encode(signature).decode("ascii")
    return block


# --------------------------------------------------------------------------- #
# Verify                                                                       #
# --------------------------------------------------------------------------- #
@dataclass
class VerifyResult:
    ok: bool
    reason: str
    public_key: str = ""
    signed_at: Optional[str] = None
    content_matches: bool = False
    signature_valid: bool = False
    pinned: bool = False  # whether an expected public key was supplied and matched

    def __bool__(self) -> bool:
        return self.ok


def verify_scorecard(
    scorecard_dict: dict, signature_block: dict, expected_public_key_b64: Optional[str] = None
) -> VerifyResult:
    """Verify a detached signature against a scorecard dict.

    Checks, in order: the signature block is well-formed; the scorecard's content
    hash matches the one the signature commits to (tamper check); the Ed25519
    signature over the payload is valid; and, if `expected_public_key_b64` is
    given, that the signing key is the pinned key (authorship check).
    """
    required = {
        "algorithm",
        "assevra_signature_version",
        "content_sha256",
        "public_key",
        "signature",
    }
    missing = required - set(signature_block)
    if missing:
        return VerifyResult(False, f"signature block missing fields: {sorted(missing)}")
    if signature_block["algorithm"] != ALGORITHM:
        return VerifyResult(False, f"unsupported algorithm {signature_block['algorithm']!r}")

    pub_b64 = signature_block["public_key"]
    signed_at = signature_block.get("signed_at")

    # 1) tamper check: does the scorecard still hash to what was signed?
    recomputed = content_hash(scorecard_dict)
    content_matches = recomputed == signature_block["content_sha256"]
    if not content_matches:
        return VerifyResult(
            False,
            "content hash mismatch: the scorecard has been modified since signing",
            public_key=pub_b64,
            signed_at=signed_at,
            content_matches=False,
        )

    # 2) cryptographic check: is the signature valid over the payload?
    payload = _signing_payload(recomputed, pub_b64, signed_at)
    try:
        pub_key = _load_public_key_b64(pub_b64)
        sig = base64.b64decode(signature_block["signature"], validate=True)
        pub_key.verify(sig, canonical_bytes(payload))
        signature_valid = True
    except Exception:  # fail closed on any verification error
        return VerifyResult(
            False,
            "invalid signature",
            public_key=pub_b64,
            signed_at=signed_at,
            content_matches=True,
            signature_valid=False,
        )

    # 3) authorship check (only if a key was pinned).
    if expected_public_key_b64 is not None:
        if expected_public_key_b64.strip() != pub_b64.strip():
            return VerifyResult(
                False,
                "signature is valid but was made by a different key than the one pinned",
                public_key=pub_b64,
                signed_at=signed_at,
                content_matches=True,
                signature_valid=True,
                pinned=False,
            )
        return VerifyResult(
            True,
            "verified: content intact and signed by the pinned key",
            public_key=pub_b64,
            signed_at=signed_at,
            content_matches=True,
            signature_valid=True,
            pinned=True,
        )

    return VerifyResult(
        True,
        "verified: content intact and signature valid (public key not pinned — "
        "trust-on-first-use; pass --public-key to prove authorship)",
        public_key=pub_b64,
        signed_at=signed_at,
        content_matches=True,
        signature_valid=True,
        pinned=False,
    )
