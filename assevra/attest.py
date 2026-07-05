"""
The Assevra Agent Card: map measured reliability evidence to AI-governance
control families.

Two stacks exist today and neither ships the bridge: governance/GRC tools map
frameworks but do not run evals, and eval tools produce numbers but do not speak
the language of an auditor or a procurement reviewer. `assevra attest` fills that
gap. It takes a scorecard and emits an **Agent Card** that says, for each measured
dimension, which control families of the major AI-governance frameworks the
evidence speaks to — the artifact a regulated-vertical buyer's security review is
actually looking for.

Scope discipline (this is load-bearing):
  * An Agent Card is **evidence and due-care documentation, not a certification,
    a compliance determination, or legal advice.** Every framework requires far
    more than these four measurements — governance, documentation, human
    oversight, data provenance — and conformity is decided by auditors and
    authorities, not by a tool.
  * The mappings are **indicative** and point at control *families*; verify them
    against the current text of each framework and your auditor's requirements.
  * Evidence is only ever as strong as the dataset it was measured on.

The frameworks referenced: the EU AI Act, the NIST AI Risk Management Framework
(incl. the Generative AI Profile), ISO/IEC 42001, and the OWASP Top 10 for LLM
Applications.
"""
from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class Mapping:
    framework: str
    reference: str
    rationale: str


# Indicative evidence mappings: which control families each Assevra dimension
# provides *evidence toward*. References are to control families / articles, not
# a claim of conformity.
DIMENSION_MAPPINGS = {
    "grounding": [
        Mapping("EU AI Act", "Art. 15 (accuracy) · Annex IV (metrics & test procedures)",
                "A grounding pass rate with a fixed threshold and interval is an accuracy metric and a documented test procedure."),
        Mapping("NIST AI RMF", "MEASURE (TEVV) · Generative AI Profile (confabulation)",
                "Faithfulness testing is test/evaluation evidence and addresses the confabulation/hallucination risk."),
        Mapping("OWASP Top 10 for LLM Apps (2025)", "LLM09 Misinformation",
                "Grounding checks whether the agent asserts facts not supported by its context."),
        Mapping("ISO/IEC 42001", "Clause 9.1 (performance evaluation)",
                "A repeatable measured metric supports the AI management system's performance-evaluation requirement."),
    ],
    "safety": [
        Mapping("EU AI Act", "Art. 15 (robustness) · Art. 9 (risk management)",
                "Correct refusal / safe-routing under adversarial prompts is robustness evidence and addresses identified harm risks."),
        Mapping("NIST AI RMF", "MEASURE (safety) · Generative AI Profile (red-teaming)",
                "Refusal testing is safety TEVV and a form of adversarial testing."),
        Mapping("OWASP Top 10 for LLM Apps (2025)", "LLM01 Prompt Injection · LLM05 Improper Output Handling",
                "Refusal of unsafe or injected requests tests resistance to these risks."),
        Mapping("ISO/IEC 42001", "Clause 9.1 · Annex A operational controls",
                "A measured safe-behavior rate supports operational-control evidence."),
    ],
    "pii": [
        Mapping("EU AI Act", "Art. 10 (data governance) · Art. 15 (cybersecurity)",
                "Zero-tolerance leak detection is evidence of data protection and resistance to sensitive-data disclosure."),
        Mapping("NIST AI RMF", "MEASURE (privacy) · Generative AI Profile (data leakage)",
                "PII-leak testing is privacy test/evaluation evidence."),
        Mapping("OWASP Top 10 for LLM Apps (2025)", "LLM02 Sensitive Information Disclosure",
                "Detecting leaked personal data in outputs directly tests this risk."),
        Mapping("ISO/IEC 42001 · ISO/IEC 27001", "privacy & information-security controls",
                "Leak testing supports these control objectives."),
    ],
    "task_completion": [
        Mapping("EU AI Act", "Art. 15 (accuracy) · Annex IV (effectiveness)",
                "Required-fact completion is functional-accuracy evidence."),
        Mapping("NIST AI RMF", "MEASURE (validity & reliability)",
                "Task-completion testing is validity test/evaluation evidence."),
        Mapping("ISO/IEC 42001", "Clause 9.1 (performance evaluation)",
                "A measured completion rate supports performance evaluation."),
    ],
}

# Reliability metrics (pass^k / consistency), when present, add robustness evidence.
RELIABILITY_MAPPINGS = [
    Mapping("EU AI Act", "Art. 15 (robustness / consistent performance)",
            "pass^k and run-to-run consistency evidence that the agent performs reliably across repeated invocations."),
    Mapping("NIST AI RMF", "MEASURE (reliability)",
            "Repeated-trial reliability is a direct reliability measurement."),
]

DISCLAIMER = (
    "This Agent Card maps measured evidence to control families of common AI "
    "governance frameworks to help a reviewer locate relevant evidence. It is NOT "
    "a certification, a conformity or compliance determination, or legal advice. "
    "Each framework requires substantially more than these measurements — "
    "governance, documentation, human oversight, data provenance — and conformity "
    "is decided by auditors and competent authorities, not by this tool. Mappings "
    "are indicative; verify them against the current text of each framework and "
    "your auditor's requirements. The evidence is only as strong as the dataset it "
    "was measured on."
)

FRAMEWORKS = [
    "EU AI Act",
    "NIST AI Risk Management Framework (incl. Generative AI Profile)",
    "ISO/IEC 42001",
    "OWASP Top 10 for LLM Applications",
]


def _dim_display(name: str) -> str:
    return {"pii": "PII-leak"}.get(name, name.replace("_", " "))


def _measured_line(dim: dict) -> str:
    if dim.get("skipped"):
        return "not measured (dimension skipped — no evidence)"
    lo, hi = dim.get("ci_95", [0, 0])
    verdict = "PASS" if dim.get("passed") else "FAIL"
    return (
        f"score {dim.get('score')} (95% CI {lo}–{hi}, n={dim.get('sample_size')}, "
        f"threshold {dim.get('threshold')}) — {verdict}"
    )


def build_card_dict(scorecard: dict, signature: dict = None, generated_at: str = "") -> dict:
    dims_out = []
    for dim in scorecard.get("dimensions", []):
        name = dim["name"]
        mappings = DIMENSION_MAPPINGS.get(name, [])
        dims_out.append(
            {
                "dimension": name,
                "measured": _measured_line(dim),
                "skipped": bool(dim.get("skipped")),
                "mappings": [m.__dict__ for m in mappings],
            }
        )
    reliability_out = []
    if scorecard.get("reliability"):
        reliability_out = [m.__dict__ for m in RELIABILITY_MAPPINGS]

    card = {
        "agent_card_version": "1",
        "generated_at": generated_at,
        "assevra_version": scorecard.get("assevra_version"),
        "dataset": scorecard.get("dataset"),
        "overall_pass": scorecard.get("overall_pass"),
        "frameworks": FRAMEWORKS,
        "dimensions": dims_out,
        "reliability_mappings": reliability_out,
        "disclaimer": DISCLAIMER,
    }
    if signature:
        card["signature"] = {
            "algorithm": signature.get("algorithm"),
            "public_key": signature.get("public_key"),
            "content_sha256": signature.get("content_sha256"),
            "signed_at": signature.get("signed_at"),
        }
    return card


def render_json(card: dict) -> str:
    return json.dumps(card, indent=2, ensure_ascii=False)


def render_markdown(card: dict) -> str:
    lines = ["# Assevra Agent Card", ""]
    lines.append("**Measured agent-reliability evidence, mapped to AI-governance control families.**")
    lines.append("")
    meta = [f"Assevra v{card.get('assevra_version')}"]
    if card.get("generated_at"):
        meta.append(f"generated {card['generated_at']}")
    meta.append(f"dataset `{card.get('dataset') or 'n/a'}`")
    lines.append(" · ".join(meta))
    lines.append("")
    lines.append(f"**Overall scorecard verdict: {'PASS' if card.get('overall_pass') else 'FAIL'}**")
    if card.get("signature"):
        sig = card["signature"]
        sha = (sig.get("content_sha256") or "")[:12]
        lines.append(
            f"  \n_Cryptographically signed ({sig.get('algorithm')}, content "
            f"sha256 `{sha}…`); verify with `assevra verify`._"
        )
    lines.append("")
    lines.append(f"> **Not a certification.** {card['disclaimer']}")
    lines.append("")
    lines.append("Frameworks referenced: " + "; ".join(card["frameworks"]) + ".")
    lines.append("")
    lines.append("## Evidence by dimension")
    lines.append("")
    for d in card["dimensions"]:
        lines.append(f"### {_dim_display(d['dimension'])} — {d['measured']}")
        lines.append("")
        if d["skipped"] or not d["mappings"]:
            lines.append("_No evidence to map for this dimension in this run._")
            lines.append("")
            continue
        lines.append("| Framework | Control family | How this evidence applies |")
        lines.append("|---|---|---|")
        for m in d["mappings"]:
            lines.append(f"| {m['framework']} | {m['reference']} | {m['rationale']} |")
        lines.append("")
    if card.get("reliability_mappings"):
        lines.append("### Reliability across repeated trials (pass^k / consistency)")
        lines.append("")
        lines.append("| Framework | Control family | How this evidence applies |")
        lines.append("|---|---|---|")
        for m in card["reliability_mappings"]:
            lines.append(f"| {m['framework']} | {m['reference']} | {m['rationale']} |")
        lines.append("")
    lines.append("## Evidence gaps and scope")
    lines.append("")
    lines.append(
        "- These four dimensions are **test/evaluation evidence only**. The "
        "frameworks above also require governance, risk-management, technical "
        "documentation, human-oversight, and data-provenance evidence that this "
        "card does not provide."
    )
    lines.append(
        "- Any dimension marked *skipped* contributes no evidence; a judge "
        "dimension is only trustworthy once calibrated (`assevra calibrate`)."
    )
    lines.append(
        "- Evidence strength depends entirely on the dataset: a small or "
        "illustrative dataset does not characterize a production agent."
    )
    lines.append("")
    lines.append(
        "_Generated with the Assevra Reliability Scorecard methodology. "
        "This card is evidence toward a review, not a compliance determination._"
    )
    lines.append("")
    return "\n".join(lines)
