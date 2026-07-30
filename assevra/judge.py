"""
The LLM-as-judge layer: one judge, or a jury.

Two things sit here, and everything vendor-specific sits one level down in
:mod:`assevra.providers`:

:class:`Judge`   a single model behind a pinned rubric. It sends a prompt, gets
                 text back, and extracts the compact JSON verdict — tolerating
                 the code fences and preambles models wrap around JSON, and
                 surfacing genuinely unparseable output as a *finding* rather
                 than swallowing it.

:class:`Panel`   several models voting as a jury. A panel agrees with humans more
                 often than any single judge, and — the part that matters more —
                 its *disagreement is itself the signal*. A split vote means the
                 row is genuinely ambiguous, which is exactly the row a human
                 should look at. Assevra reports that split instead of hiding it
                 behind a median.

Two invariants hold no matter which provider answers:

* **No judge means skipped, never failed.** A fork with no API key still gets a
  scorecard from the deterministic dimensions. A judged dimension that could not
  run is reported as SKIPPED and does not gate — because a missing measurement is
  not a passing one.
* **A judge score is not evidence until it is calibrated.** Agreement with humans
  on a labeled hold-out (Cohen's κ, bar 0.85) is what makes a judged number
  citable; ``assevra calibrate`` measures it, and METHODOLOGY.md §4 explains why
  the bar is there.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Optional

from . import providers

DEFAULT_JUDGE_MODEL = "claude-opus-4-8"
VOLUME_JUDGE_MODEL = "claude-sonnet-5"
JUDGE_MAX_TOKENS = 512


def _extract_json(raw: str) -> dict:
    """Pull the verdict object out of whatever the model wrapped it in."""
    text = raw.strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {"_parse_error": raw[:200]}


@dataclass
class Judge:
    """A single judge model behind a pinned rubric."""

    model: str
    complete: Callable[[str], str]
    provider: str = ""

    def score_json(self, prompt: str) -> dict:
        """Send a prompt, expect compact JSON back, and parse it.

        Unparseable output is a failure signal for the caller to handle, not a
        silent pass — it comes back as a dict carrying ``_parse_error``.
        """
        try:
            raw = self.complete(prompt)
        except providers.ProviderError:
            raise
        except Exception as exc:  # provider SDKs raise their own error types
            return {"_parse_error": f"judge call failed: {type(exc).__name__}: {exc}"[:200]}
        return _extract_json(raw or "")


def build_judge(
    provider: str = "auto",
    model: str = "",
    panel: Optional[list] = None,
    **opts,
):
    """Build a :class:`Judge`, a :class:`Panel`, or None.

    None means "no judge is available" — the caller skips its judged dimensions
    rather than failing them. That is the difference between a fork without
    secrets getting a partial, honest scorecard and getting a red build.
    """
    if panel:
        return build_panel(panel, provider=provider, **opts)
    name, chosen = providers.resolve(provider, model)
    if name is None:
        return None
    complete = providers.build(name, chosen, **opts)
    return Judge(model=chosen, complete=complete, provider=name)


def get_judge(model: str = "", provider: str = "auto", **opts) -> Optional[Judge]:
    """Backwards-compatible entry point: a single judge, or None."""
    return build_judge(provider=provider, model=model, **opts)


def _median_int(values: list) -> int:
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else round((s[mid - 1] + s[mid]) / 2)


@dataclass
class Panel:
    """A jury of judges.

    Exposes the same ``score_json`` interface as a single :class:`Judge`, so
    scorers use it unchanged. It aggregates whichever verdict field the panelists
    return — a 1–5 ``score`` by median, a boolean ``refused``/``followed`` by
    majority — and attaches the raw panelist votes so disagreement can be
    surfaced in the report rather than averaged away.
    """

    models: list
    judges: list
    provider: str = ""

    @property
    def model(self) -> str:
        return "panel[" + ",".join(self.models) + "]"

    @staticmethod
    def _majority(results: list, key: str, out: dict, reasons: list) -> None:
        votes = [bool(r[key]) for r in results if key in r]
        if not votes:
            return
        yes = sum(votes)
        out[key] = yes * 2 > len(votes)  # ties resolve to False
        out[f"panel_{key}"] = votes
        out.setdefault("reason", reasons[0] if reasons else "")

    def score_json(self, prompt: str) -> dict:
        results = [j.score_json(prompt) for j in self.judges]
        valid = [r for r in results if "_parse_error" not in r]
        if not valid:
            return {"_parse_error": "no panelist returned usable output"}

        out: dict = {"panel_models": self.models}
        reasons = [str(r.get("reason", "")) for r in valid]

        scores = []
        for r in valid:
            try:
                scores.append(int(r["score"]))
            except (KeyError, ValueError, TypeError):
                pass
        if scores:
            agg = _median_int(scores)
            out["score"] = agg
            out["panel_scores"] = scores
            # Prefer a reason from a panelist that landed on the aggregate.
            out["reason"] = next(
                (rs for sc, rs in zip(scores, reasons) if sc == agg), reasons[0]
            )

        self._majority(valid, "refused", out, reasons)
        self._majority(valid, "followed", out, reasons)

        if not ({"score", "refused", "followed"} & set(out)):
            return {"_parse_error": "panelists returned no usable verdict field"}
        return out


def build_panel(models: list, provider: str = "auto", **opts) -> Optional[Panel]:
    """Build a Panel over several judge models, or None when none is available.

    Panelists may name their provider inline as ``provider:model`` — so a jury
    can span vendors, which is the strongest form of the idea: three models from
    one lab share failure modes; three models from three labs do not.
    """
    judges, names, resolved_provider = [], [], ""
    for entry in models:
        spec = str(entry).strip()
        if not spec:
            continue
        if ":" in spec and spec.split(":", 1)[0] in providers.PROVIDERS:
            this_provider, model = spec.split(":", 1)
        else:
            this_provider, model = provider, spec
        name, chosen = providers.resolve(this_provider, model)
        if name is None:
            continue
        judges.append(
            Judge(model=chosen, complete=providers.build(name, chosen, **opts), provider=name)
        )
        names.append(spec if ":" in spec else chosen)
        resolved_provider = resolved_provider or name
    if not judges:
        return None
    return Panel(models=names, judges=judges, provider=resolved_provider)


def get_panel(models: list, provider: str = "auto", **opts) -> Optional[Panel]:
    """Backwards-compatible entry point for building a jury."""
    return build_panel(models, provider=provider, **opts)


def panel_note(parsed: dict) -> str:
    """A short annotation of the panelists' raw votes for a row's detail line,
    flagging disagreement. Empty for a single-judge result."""
    parts = []
    if "panel_scores" in parsed:
        s = parsed["panel_scores"]
        spread = max(s) - min(s)
        parts.append(f"panel {s}" + (f" DISAGREE(spread={spread})" if spread >= 2 else ""))
    for key in ("refused", "followed"):
        votes = parsed.get(f"panel_{key}")
        if votes:
            unanimous = all(votes) or not any(votes)
            parts.append(f"panel {key} {votes}" + ("" if unanimous else " DISAGREE"))
    return (" · " + "; ".join(parts)) if parts else ""
