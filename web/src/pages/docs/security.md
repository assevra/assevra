---
layout: ../../layouts/DocsLayout.astro
title: Security & signing
description: A shared HTML file is convenient. A signed one is evidence.
eyebrow: The artifact
---

Anyone can edit an HTML file. If a scorecard is going to function as evidence —
attached to a release, sent to a customer, put in front of an auditor — a
reviewer needs to be able to confirm two things: that it has not been altered,
and that _you_ produced it.

## The scheme

Deliberately boring and standard: **Ed25519 detached signatures** over a
canonical serialization of the scorecard's content.

1. The signer holds an Ed25519 private key and publishes the matching public key
   somewhere durable.
2. `sign` canonicalizes the scorecard (sorted keys, no incidental whitespace),
   hashes it with SHA-256, wraps that hash together with the public key and a
   timestamp into a small **signing payload**, and signs the payload.
3. `verify` recomputes the content hash, checks it matches the hash the signature
   commits to — so any edit breaks verification — then verifies the Ed25519
   signature over the payload.

The signature is **detached**: the scorecard files are never modified, and the
signature travels as a small `scorecard.sig.json`.

Canonicalization matters in practice. Re-indenting or re-saving the JSON does not
break verification, because only the _content_ is hashed. Changing a single score
does.

## Sign

```bash
pip install "assevra[sign]"

# One-time: generate a keypair.
assevra keygen

# Sign while scoring:
assevra run --sign assevra_ed25519_private.pem

# …or sign an existing scorecard:
assevra sign --scorecard scorecard.json --key assevra_ed25519_private.pem
```

Or from `.assevra.yml`:

```yaml
signing:
  key: /run/secrets/assevra_signing_key.pem
```

Keep the private key secret and never commit it — Assevra's `.gitignore` already
excludes `*.pem` and the default key filenames. In CI, write it from a secret to
a file for the duration of the job.

## Verify

```bash
# Integrity only: trust-on-first-use, using the key embedded in the signature.
assevra verify --scorecard scorecard.json --signature scorecard.sig.json

# Authorship: pin the signer's published public key.
assevra verify --scorecard scorecard.json --signature scorecard.sig.json \
               --public-key assevra_official.txt
```

`verify` exits `1` on any mismatch.

> **Always pin the key.** The embedded public key proves only _internal
> consistency_ — a forger can substitute their own key along with their own
> signature. Pinning a key you obtained through a channel you trust is what turns
> "unaltered" into "unaltered, and signed by them".

## The maintainer's key

Scorecards published by the maintainer are signed with this long-lived Ed25519
key:

```
dEcTKT/9ThXewTjRdBm2qyGIH69Ghy08kVuB19AJnSg=
```

It is also published in
[SECURITY.md](https://github.com/assevra/assevra/blob/main/SECURITY.md). A
scorecard that verifies against any _other_ key was not signed by the maintainer.

## Publishing your own key

```bash
assevra keygen
# assevra_ed25519_private.pem  → keep secret, never commit
# assevra_ed25519_public.txt   → publish this
```

Put the public key wherever recipients will durably find it: a file in the
repository, a release note, your project's site, an email footer.

## Assevra's own security posture

**Execution is explicit.** `run` and `scan` score captured records. `capture` executes the command you provide, preserving failed attempts and a completion manifest. It does not replay tools from a trace automatically.

**Dependencies and data flow.** Core tool-contract checking uses JSON Schema. Deterministic checks run locally after installation; provider SDKs and signing are optional. Cloud judges receive the fields included in their evaluation prompts. Use the configured local provider when you need a local model endpoint.

**Report sharing.** Matched PII values are redacted from PII diagnostic details. Other fields, including case identifiers, tool diagnostics, and judge explanations, may contain sensitive information. Review reports before sharing them. HTML rendering escapes dynamic content; report HTML contains no scripts.

**Browser scan.** Runtime and package assets are downloaded when you start a scan. Input traces are processed in the tab, not uploaded by Assevra. The result remains TRIAGE and records unavailable coverage. Cost from token usage requires your explicit input/output price table.
