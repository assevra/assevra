"""
Published artifact contracts.

Assevra's most valuable output is not the CLI — it is the artifact. A scorecard
that a reviewer, an auditor, or another tool can parse six months from now is
what makes the evidence portable, so the JSON shapes are treated as a product in
their own right: versioned independently of the Python package, published at a
stable URL, and validated in CI on every commit.

The contract, in one sentence: **within schema major version 1, fields are only
added — never removed, renamed, or repurposed.** A scorecard produced by any
Assevra 1.x-schema release validates against ``scorecard.schema.json`` forever.
A breaking change means a new ``/schema/v2/`` path, not a silent mutation.

Five schemas ship with the package and are served from
``https://assevra.ai/schema/v1/``:

===========================  ==============================================
``scorecard``                the release-evidence artifact (`assevra run`)
``agent-card``               governance mapping (`assevra attest`)
``calibration``              judge-vs-human agreement (`assevra calibrate`)
``dataset``                  one JSONL row of an Assevra dataset
``validation``               dataset validation report (`assevra validate`)
===========================  ==============================================

Every emitted artifact carries ``$schema`` and ``schema_version`` so a consumer
can tell what it is holding without guessing.
"""
from __future__ import annotations

import json
from pathlib import Path

# Bump the minor when a field is ADDED. Bump the major (and the /vN/ URL) only
# for a breaking change -- which should essentially never happen.
SCHEMA_VERSION = "1.0"
SCHEMA_BASE_URL = "https://assevra.ai/schema/v1"

_DIR = Path(__file__).parent

NAMES = ("scorecard", "agent-card", "calibration", "dataset", "validation")


def schema_url(name: str) -> str:
    """The canonical public URL of a schema, as stamped into artifacts."""
    return f"{SCHEMA_BASE_URL}/{name}.schema.json"


def schema_path(name: str) -> Path:
    if name not in NAMES:
        raise KeyError(f"unknown schema {name!r}; expected one of {list(NAMES)}")
    return _DIR / f"{name}.schema.json"


def load(name: str) -> dict:
    """Load a bundled schema as a dict."""
    return json.loads(schema_path(name).read_text(encoding="utf-8"))


def stamp(payload: dict, name: str) -> dict:
    """Return `payload` with its contract identity in front.

    The two keys go first so that a human opening the file sees what it is on
    line one, and so a consumer can dispatch on ``$schema`` without a full parse
    of the body.
    """
    return {"$schema": schema_url(name), "schema_version": SCHEMA_VERSION, **payload}
