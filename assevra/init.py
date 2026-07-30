"""
``assevra init`` — from an unfamiliar repo to a working evaluation in one command.

Adoption dies in the gap between "this looks useful" and "this is wired into our
build". Closing that gap is mostly not a technical problem: it is knowing which
of your files are traces, which agent framework you are on, which provider has
credentials, and what the CI job should look like. Assevra can work all four out
by looking.

``assevra init`` detects, then generates — and generates nothing it did not tell
you it was going to write:

* **detects traces** — likely trace files in the repo, ranked by how confidently
  the bootstrap adapters can read them, and reports the format it inferred.
* **detects your framework** — LangGraph, LangChain, the OpenAI Agents SDK,
  Langfuse, Phoenix, OpenTelemetry, or the raw provider SDKs — from imports and
  dependency files, and points at the matching integration guide.
* **detects providers** — which judge credentials are present in the environment,
  so the config it writes is one you can actually run.

and then writes ``.assevra.yml``, a drafted dataset (via ``bootstrap`` when
traces were found), a ready-to-commit GitHub Actions workflow, and a short
``EVALUATION.md`` describing what is now measured and what is not.

Nothing is overwritten without ``--force``. A wizard that clobbers a config
someone tuned is a wizard nobody runs twice.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import bootstrap as bootstrap_mod
from . import config as config_mod
from . import providers

# Directories never worth walking when looking for traces.
_SKIP_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache",
    ".pytest_cache", "dist", "build", ".tox", ".next", "target", ".idea",
    "site-packages", ".assevra",
}

_TRACE_HINTS = ("trace", "span", "log", "eval", "run", "capture", "session", "transcript")
_TRACE_SUFFIXES = (".jsonl", ".json", ".csv")

# Import / dependency markers -> the integration that fits.
_FRAMEWORK_MARKERS = {
    "langgraph": (r"\blanggraph\b",),
    "langfuse": (r"\blangfuse\b",),
    "phoenix": (r"\bphoenix\b", r"\barize\b", r"\bopeninference\b"),
    "openai-agents": (r"from agents import", r"\bopenai-agents\b", r"\bopenai_agents\b"),
    "otel": (r"\bopentelemetry\b", r"\btraceloop\b", r"\bopenllmetry\b"),
    "anthropic": (r"\banthropic\b",),
}

_SOURCE_GLOBS = ("*.py", "*.toml", "*.txt", "*.cfg", "*.json", "*.yaml", "*.yml")


@dataclass
class Detection:
    traces: list[tuple[Path, str, int]] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    providers: list[str] = field(default_factory=list)

    @property
    def best_trace(self) -> Optional[tuple[Path, str, int]]:
        return self.traces[0] if self.traces else None


# --------------------------------------------------------------------------- #
# Detection                                                                    #
# --------------------------------------------------------------------------- #
def _walk(root: Path, max_files: int = 4000):
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            seen += 1
            if seen > max_files:
                return
            yield Path(dirpath) / name


def detect_traces(root: Path, limit: int = 6) -> list[tuple[Path, str, int]]:
    """Candidate trace files as (path, inferred format, rows readable).

    Ranking is by *how much Assevra could actually extract*, not by filename —
    a file called ``traces.jsonl`` that yields nothing is worse than an
    unhelpfully named one that yields two hundred interactions.
    """
    candidates = []
    for path in _walk(root):
        if path.suffix.lower() not in _TRACE_SUFFIXES:
            continue
        if path.name.startswith(".") or path.stat().st_size == 0:
            continue
        if path.stat().st_size > 200 * 1024 * 1024:
            continue
        name = path.name.lower()
        hinted = any(hint in name or hint in str(path.parent).lower() for hint in _TRACE_HINTS)
        try:
            rows, fmt = bootstrap_mod.bootstrap(str(path), limit=200)
        except Exception:
            continue
        if not rows:
            continue
        # Prefer files that both parse and look like traces by name.
        candidates.append((path, fmt, len(rows), 1 if hinted else 0))
    candidates.sort(key=lambda c: (c[3], c[2]), reverse=True)
    return [(p, f, n) for p, f, n, _ in candidates[:limit]]


def detect_frameworks(root: Path) -> list[str]:
    found: set[str] = set()
    checked = 0
    for path in _walk(root, max_files=2000):
        if not any(path.match(glob) for glob in _SOURCE_GLOBS):
            continue
        if path.stat().st_size > 2 * 1024 * 1024:
            continue
        checked += 1
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for name, patterns in _FRAMEWORK_MARKERS.items():
            if name in found:
                continue
            if any(re.search(p, text, re.IGNORECASE) for p in patterns):
                found.add(name)
        if len(found) == len(_FRAMEWORK_MARKERS) or checked > 1500:
            break
    return sorted(found)


def detect_providers() -> list[str]:
    return [name for name, info in providers.PROVIDERS.items() if info.env and info.configured]


def detect(root: str = ".") -> Detection:
    base = Path(root)
    return Detection(
        traces=detect_traces(base),
        frameworks=detect_frameworks(base),
        providers=detect_providers(),
    )


# --------------------------------------------------------------------------- #
# Generation                                                                   #
# --------------------------------------------------------------------------- #
WORKFLOW = """\
name: assevra

# Assevra gates this repository's agent on every pull request.
# The deterministic dimensions run with no API key, so forks get a real gate
# instead of a red build. Judged dimensions run only when a key is configured
# and are reported as SKIPPED — never as passing — when it is not.

on:
  pull_request:
  push:
    branches: [main]

jobs:
  reliability:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4

      - name: Score the agent and gate the build
        uses: assevra/assevra@v1
        with:
          dataset: {dataset}
          gate: true
          attest: true
          comment: true
        env:
          # Optional: unlocks the judged dimensions. Empty on forks by design.
          ANTHROPIC_API_KEY: ${{{{ secrets.ANTHROPIC_API_KEY }}}}
"""

EVALUATION_MD = """\
# Evaluating this agent

This project measures agent reliability with [Assevra](https://assevra.ai) — the
scorecard is a committed artifact, not a dashboard.

## Run it

```bash
pip install assevra
assevra validate {dataset}    # every row structurally valid and labeled?
assevra run                   # reads .assevra.yml, writes the scorecard
```

`assevra run --gate` exits non-zero when any scored dimension falls below its
threshold, which is how CI gates a release.

## What is measured

{dimension_table}

Every dimension reports a pass rate **with a 95% Wilson confidence interval and
its sample size**, so a small-sample move is never mistaken for a real one. The
overall verdict is a conjunction: one failing dimension fails the run.

## What is not measured

- Anything the dataset does not contain. A scorecard characterizes the rows it
  was given, not the agent in general.
- A judged dimension is only trustworthy once `assevra calibrate` shows the judge
  agrees with humans on a labeled hold-out (Cohen's κ ≥ 0.85).
- A dimension shown as SKIPPED contributed no evidence. It is not a pass.

## Keeping it honest

- Grow the dataset toward the failures you actually fear, not the ones that are
  easy to write.
- Record repeated trials of the same case with a shared `case_id` — pass^k and
  the flaky-case list are where run-to-run instability shows up.
- Commit `.assevra/history.jsonl` so regressions are detected against a real
  baseline rather than a vibe.
"""


def _dimension_table(dimensions: list[str]) -> str:
    from . import registry

    lines = ["| Dimension | Scoring | Threshold | Question |", "|---|---|---|---|"]
    for name in dimensions:
        spec = registry.get_scorer(name)
        lines.append(
            f"| `{name}` | {spec.mode} | {spec.threshold:.2f} | {spec.summary} |"
        )
    return "\n".join(lines)


@dataclass
class InitPlan:
    """What init is about to write. Printed before anything is created."""

    config_path: Path
    dataset_path: Optional[Path]
    workflow_path: Optional[Path]
    doc_path: Optional[Path]
    source_trace: Optional[Path]
    trace_format: str
    drafted_rows: int
    provider: str
    frameworks: list[str]
    skipped: list[str] = field(default_factory=list)


def plan(
    root: str = ".",
    dataset: Optional[str] = None,
    from_traces: Optional[str] = None,
    dimension: str = bootstrap_mod.DEFAULT_DIMENSION,
    workflow: bool = True,
    docs: bool = True,
) -> tuple[InitPlan, Detection]:
    base = Path(root)
    found = detect(root)

    source: Optional[Path] = None
    fmt = ""
    if from_traces:
        source = Path(from_traces)
        if not source.is_file():
            raise FileNotFoundError(f"traces not found: {from_traces}")
    elif found.best_trace:
        source, fmt, _ = found.best_trace

    dataset_path = Path(dataset) if dataset else base / "evals" / "agent.jsonl"
    provider = found.providers[0] if found.providers else "auto"

    return (
        InitPlan(
            config_path=base / ".assevra.yml",
            dataset_path=dataset_path if source else None,
            workflow_path=(base / ".github" / "workflows" / "assevra.yml") if workflow else None,
            doc_path=(base / "EVALUATION.md") if docs else None,
            source_trace=source,
            trace_format=fmt,
            drafted_rows=0,
            provider=provider,
            frameworks=found.frameworks,
        ),
        found,
    )


def apply(
    plan_: InitPlan,
    dimension: str = bootstrap_mod.DEFAULT_DIMENSION,
    limit: Optional[int] = None,
    force: bool = False,
) -> InitPlan:
    """Write the planned files. Existing files are skipped unless `force`."""

    def _write(path: Optional[Path], text: str) -> bool:
        if path is None:
            return False
        if path.exists() and not force:
            plan_.skipped.append(str(path))
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return True

    dataset_rel = "evals/agent.jsonl"
    if plan_.dataset_path is not None and plan_.source_trace is not None:
        rows, fmt = bootstrap_mod.bootstrap(
            str(plan_.source_trace), dimension=dimension, limit=limit
        )
        plan_.trace_format = fmt
        plan_.drafted_rows = len(rows)
        if plan_.dataset_path.exists() and not force:
            plan_.skipped.append(str(plan_.dataset_path))
        else:
            plan_.dataset_path.parent.mkdir(parents=True, exist_ok=True)
            with open(plan_.dataset_path, "w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        dataset_rel = os.path.relpath(plan_.dataset_path, plan_.config_path.parent)

    _write(
        plan_.config_path,
        config_mod.render_template(
            dataset=dataset_rel,
            out_dir=".assevra/out",
            provider=plan_.provider,
            history=".assevra/history.jsonl",
        ),
    )
    _write(plan_.workflow_path, WORKFLOW.format(dataset=dataset_rel))

    from . import registry

    _write(
        plan_.doc_path,
        EVALUATION_MD.format(
            dataset=dataset_rel,
            dimension_table=_dimension_table(registry.dimensions()[:4]),
        ),
    )
    return plan_


def render_detection(found: Detection) -> str:
    lines = ["[assevra] looking around this project…"]
    if found.traces:
        lines.append(f"[assevra]   traces: {len(found.traces)} candidate file(s)")
        for path, fmt, count in found.traces[:3]:
            lines.append(f"[assevra]     {path}  (format: {fmt}, {count} readable interactions)")
    else:
        lines.append("[assevra]   traces: none found — pass --from <file> if you have some")
    if found.frameworks:
        lines.append(f"[assevra]   framework: {', '.join(found.frameworks)}")
        lines.append(
            f"[assevra]     integration guide: assevra integrate {found.frameworks[0]}"
        )
    else:
        lines.append("[assevra]   framework: not detected")
    if found.providers:
        lines.append(f"[assevra]   judge providers with credentials: {', '.join(found.providers)}")
    else:
        lines.append(
            "[assevra]   judge providers: none configured — judged dimensions will be "
            "SKIPPED (not failed)"
        )
    return "\n".join(lines)
