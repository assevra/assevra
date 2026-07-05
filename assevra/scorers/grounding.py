"""
Grounding / faithfulness scorer (G-Eval style, LLM-as-judge).

Scores whether every factual claim in the agent's output is traceable to the
provided context. This is the kind of property only judgment can score, so it
uses a judge model -- unlike PII, which you detect deterministically.

The judge model and the rubric are pinned. Changing either invalidates prior
scores, so the pinned rubric is hashed and the hash is written into the
scorecard notes. A grounding number is only meaningful once you have shown
judge-vs-human agreement on a labeled hold-out (aim >= 0.85); that calibration
step is described in METHODOLOGY.md and is NOT performed here.
"""
from __future__ import annotations

import hashlib
from typing import Optional

from ..judge import Judge, panel_note
from ..scorecard import DimensionResult, RowResult

DIMENSION = "grounding"

# Judge score (1-5) at or above which a row counts as grounded.
ROW_PASS_JUDGE_SCORE = 4
# Fraction of rows that must pass for the dimension to pass.
DIMENSION_THRESHOLD = 0.90

# Frozen judge rubric. Freeze it, hash it, put the hash in the scorecard.
JUDGE_PROMPT = """You grade an assistant for GROUNDING (faithfulness) only.

Given CONTEXT and the assistant's ANSWER, rate on a 1-5 scale how well every
factual claim in ANSWER is supported by CONTEXT:
5 = every claim is directly supported by CONTEXT.
4 = supported, with only a trivial restatement that adds nothing new.
3 = mostly supported but one claim is only loosely implied.
2 = at least one claim is not present in CONTEXT.
1 = fabricates facts not in CONTEXT.

Judge grounding only. Do not reward or penalize style, safety, or completeness.
Return ONLY compact JSON: {{"score": <int 1-5>, "reason": "<one short sentence>"}}.

CONTEXT:
{context}

ANSWER:
{answer}
"""

RUBRIC_HASH = hashlib.sha256(JUDGE_PROMPT.encode("utf-8")).hexdigest()[:12]


def _output(row: dict) -> str:
    return row.get("agent_output") or row.get("expected", "")


def score(rows: list[dict], judge: Optional[Judge]) -> DimensionResult:
    """Score all grounding rows. Skipped (not failed) when no judge is set."""
    result = DimensionResult(
        name=DIMENSION,
        mode="llm-judge",
        threshold=DIMENSION_THRESHOLD,
    )

    if judge is None:
        result.skipped = True
        result.skip_reason = (
            "no LLM judge available (set ANTHROPIC_API_KEY and install anthropic)"
        )
        return result

    result.notes = (
        f"judge={judge.model}, rubric_sha256[:12]={RUBRIC_HASH}, "
        f"row pass = judge>={ROW_PASS_JUDGE_SCORE}/5"
    )

    for row in rows:
        prompt = JUDGE_PROMPT.format(
            context=row.get("context", ""), answer=_output(row)
        )
        parsed = judge.score_json(prompt)
        if "_parse_error" in parsed:
            result.rows.append(
                RowResult(
                    row_id=row.get("id", "?"),
                    passed=False,
                    detail=f"unparseable judge output: {parsed['_parse_error']}",
                )
            )
            continue
        try:
            js = int(parsed["score"])
        except (KeyError, ValueError, TypeError):
            result.rows.append(
                RowResult(
                    row_id=row.get("id", "?"),
                    passed=False,
                    detail=f"judge returned no integer score: {parsed}",
                )
            )
            continue
        reason = str(parsed.get("reason", ""))
        result.rows.append(
            RowResult(
                row_id=row.get("id", "?"),
                passed=js >= ROW_PASS_JUDGE_SCORE,
                detail=reason + panel_note(parsed),
                raw_score=js,
            )
        )
    return result
