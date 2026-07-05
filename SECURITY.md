# Security & verifying Assevra scorecards

Assevra is a personal open-source research project. This document covers two
things: how to **verify a signed Assevra scorecard**, and how to **report a
vulnerability**.

## Verifying a signed scorecard

An Assevra scorecard can be cryptographically signed (`assevra sign`) so that a
third party — an auditor, a reviewer, a customer — can confirm it was produced by
a specific signer and has not been altered since. The scheme is **Ed25519
detached signatures** over a canonical serialization of the scorecard's content
(see [`assevra/signing.py`](assevra/signing.py) and
[METHODOLOGY.md](METHODOLOGY.md)).

To verify a scorecard you were given (`scorecard.json`) against its signature
(`scorecard.sig.json`):

```bash
pip install "assevra[sign]"

# Integrity only (trust-on-first-use): confirms the scorecard was not modified
# after signing, using the public key embedded in the signature.
python -m assevra verify --scorecard scorecard.json --signature scorecard.sig.json

# Authorship: pin the signer's published public key. Verification then fails if
# the scorecard was signed by any other key.
python -m assevra verify --scorecard scorecard.json --signature scorecard.sig.json \
    --public-key <path-or-base64-of-the-signer's-public-key>
```

Verification fails if a single byte of the scorecard's content changed, or — when
you pin a key — if it was signed by anyone other than the pinned signer. The
signature is detached: the scorecard file itself is never modified.

**Always pin the signer's public key** obtained through a channel you trust. The
embedded key alone proves only internal consistency, not who signed it.

## Official signing key

Scorecards published by the maintainer are signed with a long-lived Ed25519 key.
The public half is published here and on <https://assevra.ai> so anyone can pin
it:

```
# Assevra maintainer signing key (Ed25519, base64)
# status: to be published — see "Publishing your own key" below
```

> Until a key is published above, treat any "official" signed scorecard with
> caution and request the public key directly.

## Publishing your own key

If you sign scorecards you distribute, publish your public key so recipients can
pin it:

```bash
# Generates assevra_ed25519_private.pem (keep secret) and
# assevra_ed25519_public.txt (publish this).
python -m assevra keygen
```

Keep the **private** key secret and never commit it (Assevra's `.gitignore`
already excludes `*.pem` and the default key filenames). Publish the **public**
key wherever recipients can find it durably — a repository file like this one, a
project website, a release note.

## Reporting a vulnerability

Please report security vulnerabilities **privately**, not as a public issue. Use
GitHub's private vulnerability reporting on this repository
(**Security → Advisories → Report a vulnerability**). Include a description, steps
to reproduce, and the affected version. You will get an acknowledgement, and a
fix or mitigation will be coordinated before any public disclosure.

Assevra scores *already-captured* agent outputs offline; it does not execute your
agent or your data. The most security-relevant surfaces are the signing/
verification code and the dataset/trace parsers — reports touching those are
especially welcome.
