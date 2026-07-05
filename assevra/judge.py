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
