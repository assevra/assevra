"""
``assevra demo`` — a complete, honest worked example in under a minute.

The single biggest adoption cost in an evaluation tool is not installation. It is
the distance between installing it and *seeing what it produces*. Cloning a repo,
finding a dataset, guessing at flags, and discovering an API key is required
before anything renders — that gap is where most evaluations of an eval tool
quietly end.

So the demo dataset ships **inside the package**. After ``pip install assevra``:

    assevra demo

writes a full set of artifacts — the styled HTML report, the JSON scorecard, the
Markdown summary, the Agent Card, the dataset it scored, and the ``.assevra.yml``
that produced it — with **no clone, no API key, and no network**. Everything is
real output from the real engine on a real dataset, not a screenshot.

What it covers, deliberately: all nine dimensions, a sanctioned-echo PII row and
a known-bad leak row that proves the detector fires, three prompt-injection cases
with canaries, tool-call and action checks, cost and latency budgets, and three
repeated trials sharing a ``case_id`` so the pass^k and consistency section
appears too.

Without a judge, the judged dimensions are reported as **SKIPPED, not passed** —
which is the point. The first artifact a new user sees demonstrates the project's
central discipline rather than hiding it: ``assevra demo --provider mock`` runs
the judged path offline with the deterministic mock judge, and the scorecard says
so on its face.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import api, attest, config as config_mod

DEMO_DATASET = Path(__file__).parent / "data" / "demo.jsonl"

# The demo's own configuration. The price table matters: one cost row is priced
# from token usage rather than a reported dollar figure, which is the shape most
# real traces arrive in.
DEMO_CONFIG = {
    "dataset": "demo.jsonl",
    "out_dir": ".",
    "gate": {"enabled": True},
    "budgets": {
        "cost_usd": 0.02,
        "latency_ms": 4000,
        "price": {"input_per_mtok": 3.0, "output_per_mtok": 15.0},
    },
    "reliability": {"pass_k": 2},
    "attest": {"enabled": True},
}

_DEMO_YML = """\
# The configuration that produced the scorecard in this directory.
# Copy it to your own project as .assevra.yml and point `dataset` at your rows.
version: 1
dataset: demo.jsonl
out_dir: .

judge:
  # 'auto' uses whichever provider has credentials; 'mock' is the offline
  # deterministic judge used for tests and CI; 'none' skips judged dimensions.
  provider: {provider}

gate:
  enabled: true
  fail_on_regression: true

budgets:
  cost_usd: 0.02
  latency_ms: 4000
  price:
    input_per_mtok: 3.0
    output_per_mtok: 15.0

reliability:
  pass_k: 2

attest:
  enabled: true
"""


def run(
    out_dir: str = "assevra-demo",
    provider: str = "auto",
    judge_model: str = "",
) -> tuple[object, list[Path]]:
    """Score the bundled dataset and write a full artifact set into `out_dir`.

    Returns (scorecard, written paths).
    """
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)

    # Copy the dataset next to the artifacts: the evidence should never point at
    # a file the reader cannot open.
    dataset_copy = directory / "demo.jsonl"
    dataset_copy.write_text(DEMO_DATASET.read_text(encoding="utf-8"), encoding="utf-8")

    cfg = api.resolve_config(dict(DEMO_CONFIG))
    scorecard = api.evaluate(
        dataset=str(dataset_copy),
        config=cfg,
        judge_provider=provider,
        judge_model=judge_model or None,
    )

    written = api.write_reports(scorecard, str(directory), ("md", "json", "html"))

    card = attest.build_card_dict(scorecard.to_dict(), generated_at=scorecard.generated_at)
    card_md = directory / "agent-card.md"
    card_json = directory / "agent-card.json"
    card_md.write_text(attest.render_markdown(card), encoding="utf-8")
    card_json.write_text(attest.render_json(card), encoding="utf-8")

    config_path = directory / ".assevra.yml"
    config_path.write_text(_DEMO_YML.format(provider=provider), encoding="utf-8")

    written += [dataset_copy, card_md, card_json, config_path]
    return scorecard, written


def summary(scorecard, directory: str) -> str:
    """The short console note that follows a demo run."""
    skipped = [d.name for d in scorecard.dimensions if d.skipped]
    lines = [
        "",
        f"[assevra] demo artifacts written to {directory}/",
        "[assevra]   scorecard.html   ← open this one first",
        "[assevra]   scorecard.json   ← the machine-readable contract",
        "[assevra]   scorecard.md     ← paste into a PR",
        "[assevra]   agent-card.md    ← the governance mapping",
        "[assevra]   demo.jsonl       ← the dataset that was scored",
        "[assevra]   .assevra.yml     ← the config that produced all of it",
    ]
    if skipped:
        lines += [
            "",
            f"[assevra] {len(skipped)} judged dimension(s) were SKIPPED, not passed: "
            + ", ".join(skipped) + ".",
            "[assevra] That is the methodology working: a measurement that could not run "
            "is never a passing one.",
            "[assevra] Try `assevra demo --provider mock` to run the judged path offline, "
            "or set a provider key for a real judge.",
        ]
    lines += [
        "",
        "[assevra] Next: `assevra init --from your_traces.jsonl` to draft a dataset "
        "from traces you already have.",
    ]
    return "\n".join(lines)


def dataset_rows() -> list[dict]:
    """The demo rows, for tests and for the SDK docs."""
    return [
        json.loads(line)
        for line in DEMO_DATASET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def config() -> config_mod.Config:
    return api.resolve_config(dict(DEMO_CONFIG))
