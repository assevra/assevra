"""Deterministic remediation guidance; suggestions are never automatic fixes."""
from __future__ import annotations

GUIDANCE = {
    "pii": ("Restrict sensitive output", "Redact sensitive fields before returning agent output; allow only explicitly sanctioned fields.", "Repeat this case with synthetic sensitive values and check permitted fields separately."),
    "grounding": ("Repair unsupported claims", "Inspect retrieved context and citations; require abstention when the source does not support an answer.", "Rerun this case with the same sources and a human-reviewed grounding label."),
    "safety": ("Repair the policy boundary", "Review the policy and refusal path for this request; add a human escalation where needed.", "Rerun the failing request and a permitted neighboring request to check over-refusal."),
    "injection": ("Separate instructions from untrusted content", "Restrict tool permissions and treat retrieved documents and tool outputs as untrusted data.", "Repeat the injection and a benign control; verify both tool actions and final state."),
    "tool_call": ("Repair the tool contract", "Compare recorded arguments with the full tool schema and validate them before execution.", "Rerun with boundary values, nested fields, and unexpected arguments."),
    "action_correctness": ("Repair the action or outcome", "Inspect the complete action sequence and observed final state; enforce authorization before side effects.", "Repeat against an isolated fixture and assert final state, including forbidden side effects."),
    "task_completion": ("Repair the completion criteria", "Turn the missing business requirement into an explicit assertion and update the agent workflow.", "Rerun the same case and check its acceptance criteria, not just its wording."),
    "cost": ("Reduce measured cost", "Inspect repeated model calls and token usage; consider caching, shorter context, or a smaller model.", "Rerun with an explicit price table and confirm quality thresholds still pass."),
    "latency": ("Reduce measured latency", "Inspect slow spans, retries, and sequential calls; remove redundant work.", "Repeat under representative load and compare latency alongside correctness."),
}


def build(scorecard) -> list[dict]:
    findings = []
    for dimension in scorecard.dimensions:
        title, action, verify = GUIDANCE.get(dimension.name, (
            "Review the failed assertion", "Inspect this scorer's acceptance criteria.", "Rerun the same case after a reviewed change."))
        for row in dimension.rows:
            if row.passed and row.status == "PASS":
                continue
            error = row.status in ("ERROR", "ABSTAIN")
            findings.append({
                "id": f"{dimension.name}:{row.row_id}",
                "dimension": dimension.name,
                "case_id": row.case_id or row.row_id,
                "row_id": row.row_id,
                "trace_id": row.trace_id,
                "status": row.status,
                "severity": "blocker" if error or dimension.name in ("pii", "safety", "injection") else "high",
                "title": "Restore evaluation evidence" if error else title,
                "evidence": row.detail,
                "suggested_action": "Repair the evaluator or contract, then rerun; no agent verdict is available." if error else action,
                "verification": verify,
                "automation": "human_review_required",
            })
    for name in scorecard.missing_dimensions:
        findings.append({"id": f"coverage:{name}", "dimension": name,
                         "status": "MISSING", "severity": "blocker",
                         "title": "Collect missing evidence", "evidence": "Required dimension has no completed measurements.",
                         "suggested_action": "Supply labeled cases and the required evaluator configuration.",
                         "verification": "Rerun the declared release suite.", "automation": "human_review_required"})
    return findings
