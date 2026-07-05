"""
Pluggable LLM-as-judge client for the grounding and safety dimensions.

The judge is deliberately thin and optional. If there is no API key, or the
Anthropic SDK is not installed, `get_judge()` returns None and the judge
dimensions are *skipped* (not failed) by the scorers -- so a fork with no
secret still produces a scorecard from the deterministic dimensions.

Default judge models (override on the CLI with --judge-model):
  - claude-opus-4-8   : primary judge (highest agreement)
  - claude-sonnet-5   : volume judge (cheaper, for larger datasets)

The API key is read from the ANTHROPIC_API_KEY environment variable by the SDK.
A judge score is only meaningful once you have shown judge-vs-human agreement on
a labeled hold-out; that calibration step is described in METHODOLOGY.md and is
deliberately NOT automated here.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

DEFAULT_JUDGE_MODEL = "claude-opus-4-8"
VOLUME_JUDGE_MODEL = "claude-sonnet-5"
JUDGE_MAX_TOKENS = 512


@dataclass
class Judge:
    """A minimal wrapper over the Anthropic Messages API for scoring."""

    model: str
    _client: object

    def score_json(self, prompt: str) -> dict:
        """Send a prompt, expect compact JSON back, and parse it.

        Unparseable judge output is a failure signal for the caller to handle,
        not a silent pass -- we surface it as a dict with a `_parse_error` key.
        """
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=JUDGE_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        # Judges sometimes wrap JSON in prose or a code fence; extract the object.
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            raw = raw[start : end + 1]
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return {"_parse_error": raw[:200]}


def get_judge(model: str = DEFAULT_JUDGE_MODEL) -> Optional[Judge]:
    """Build a Judge, or return None when no judge is available.

    None is returned (and the caller skips the dimension) when either:
      - ANTHROPIC_API_KEY is unset, or
      - the `anthropic` package is not installed.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        from anthropic import Anthropic
    except ImportError:
        return None
    return Judge(model=model, _client=Anthropic())


def _median_int(values: list) -> int:
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else round((s[mid - 1] + s[mid]) / 2)


@dataclass
class Panel:
    """A jury of judges. A panel of several models agrees with humans more often
    than any single judge and, crucially, its *disagreement* is itself a signal
    (a split vote flags a genuinely ambiguous row). The panel exposes the same
    ``score_json`` interface as a single Judge, so scorers use it unchanged; it
    aggregates whichever verdict field the panelists return (a 1-5 ``score`` by
    median, a boolean ``refused`` by majority) and attaches the raw panelist
    votes so disagreement can be surfaced."""

    models: list
    judges: list

    @property
    def model(self) -> str:
        return "panel[" + ",".join(self.models) + "]"

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

        refused = [bool(r["refused"]) for r in valid if "refused" in r]
        if refused:
            yes = sum(refused)
            out["refused"] = yes * 2 > len(refused)  # majority; ties -> not refused
            out["panel_refused"] = refused
            out.setdefault("reason", reasons[0] if reasons else "")

        if "score" not in out and "refused" not in out:
            return {"_parse_error": "panelists returned no usable verdict field"}
        return out


def get_panel(models: list) -> Optional[Panel]:
    """Build a Panel over several judge models sharing one client, or None when
    no judge is available (same conditions as get_judge)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        from anthropic import Anthropic
    except ImportError:
        return None
    client = Anthropic()
    judges = [Judge(model=m, _client=client) for m in models]
    return Panel(models=list(models), judges=judges)


def panel_note(parsed: dict) -> str:
    """A short annotation of the panelists' raw votes for a row's detail line,
    flagging disagreement. Empty for a single-judge result."""
    parts = []
    if "panel_scores" in parsed:
        s = parsed["panel_scores"]
        spread = max(s) - min(s)
        parts.append(f"panel {s}" + (f" DISAGREE(spread={spread})" if spread >= 2 else ""))
    if "panel_refused" in parsed:
        r = parsed["panel_refused"]
        unanimous = all(r) or not any(r)
        parts.append("panel refused " + str(r) + ("" if unanimous else " DISAGREE"))
    return (" · " + "; ".join(parts)) if parts else ""
