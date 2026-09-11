# Assevra

**Find agent failures before your users do.**

Assevra is an MIT-licensed Python framework for evaluating captured agent runs. It produces actionable findings, an explicit release decision, and portable HTML and JSON evidence.

- **Connect existing runs.** Evaluate Python records, import exported traces, or capture a command you provide.
- **Know what to fix next.** Findings include case identity, available trace references, suggested actions, and verification steps.
- **Block incomplete releases.** Missing required dimensions, invalid evaluator results, and incompatible required comparisons cannot produce PASS.
- **Keep the evidence.** Export versioned scorecards and optionally sign their canonical JSON with Ed25519.

[Website](https://assevra.ai) · [Documentation](https://assevra.ai/docs) · [PyPI](https://pypi.org/project/assevra/) · [Methodology](METHODOLOGY.md) · [Changelog](CHANGELOG.md)

## Run a failure-to-fix example

Requires Python 3.10+. Installation downloads dependencies; the example itself runs locally without API keys.

```bash
pip install assevra==0.6.0
python -m assevra.reference --out-dir reference-output
```

Open `reference-output/before/scorecard.html`, then `reference-output/after/scorecard.html`.

The example executes a local refund workflow against four synthetic cases, three times each. The buggy branch refunds unauthorized and over-limit requests. The repaired branch checks authorization and the amount before issuing a refund. Assertions verify tool contracts, action order, forbidden actions, final order state, and the PII detector's supported patterns.

The first report is **FAIL**; the second is **PASS** for the three declared dimensions. Both use the same cases, assertions, and policy. This is an executable fixture, not evidence about a production model or a customer deployment. [Read the complete example](assevra/reference.py).

Rerun the repaired dataset through the actual release gate:

```bash
assevra run --dataset reference-output/after/cases.jsonl \
  --config reference-output/after/policy.json \
  --out-dir release-evidence --gate
```

## Evaluate your agent

```python
from assevra import evaluate, write_reports

card = evaluate(
    records=[{
        "id": "refund-unauthorized-1",
        "case_id": "refund-unauthorized",
        "trace_id": "your-trace-id",
        "dimension": "action_correctness",
        "expected_actions": ["escalate"],
        "forbidden_actions": ["refund"],
        "agent_actions": ["escalate"],
        "expected_state": {"status": "escalated", "refund_usd": 0},
        "observed_state": {"status": "escalated", "refund_usd": 0},
    }],
    config={"judge": {"provider": "none"}},
    required_dimensions=["action_correctness"],
)
write_reports(card, "evidence")
assert card.decision == "PASS"
```

A release-purpose evaluation always validates rows strictly. `validate=False` cannot bypass that requirement. Declare the release dimensions explicitly; otherwise the recorded scope is the dimensions included in the dataset. No tool can infer your missing business requirements from a trace.

## What happens after a finding?

1. Inspect `findings` in `scorecard.json` or the suggested-fixes section of the HTML report.
2. Locate the case and trace, then check its evidence and acceptance criteria.
3. Review the suggested action and change the agent, tool boundary, retrieval, or assertion as appropriate. Suggestions are deterministic guidance, not a root-cause diagnosis or an automatic code change.
4. Execute the agent again and rerun the **complete declared suite**. Re-scoring old outputs cannot verify a changed agent.
5. Compare only compatible runs. Keep the cases, labels, thresholds, scorer version, and judge configuration fixed when attributing a difference to an agent change.

## Decisions and scope

| Decision | Meaning | Release gate |
| --- | --- | --- |
| PASS | Complete release-purpose evidence meets every included and required threshold | Succeeds |
| FAIL | Complete measured evidence fails a threshold or a required compatible regression check | Blocks |
| INCOMPLETE | Required evidence, validation, evaluator output, or comparison is incomplete | Blocks |
| TRIAGE | Partial scan or exploratory evaluation | Blocks |
| SELF_TEST | Evaluator demonstration, including mock judging | Blocks |

A dimension can be SKIPPED; a row can be ERROR or ABSTAIN. These are missing evaluation evidence, not passing agent measurements. Errors are excluded from pass-rate denominators. Known-bad PII detector controls live in `controls`, outside agent pass rates.

## Nine dimensions

| Dimension | Checks |
| --- | --- |
| `grounding` | Judge rubric comparing the answer with captured supporting context |
| `safety` | Refusal behavior against explicit labels; inspect whether the judge or fallback rule ran |
| `pii` | Supported sensitive-data patterns; optional Presidio expands detector coverage |
| `task_completion` | Required strings in the output; does not establish business outcome by itself |
| `tool_call` | Allowed/forbidden calls, expected arguments, and tool schemas |
| `action_correctness` | Required/forbidden action sequences and optional observed final-state assertions |
| `injection` | Explicit canaries or judged resistance against labeled cases |
| `cost` | Captured cost or usage with your explicit price table against a budget |
| `latency` | Recorded elapsed time against a budget |

Dimension rates carry sample sizes and 95% Wilson intervals. Repeated trials sharing `case_id` also produce consistency and pass^k summaries. Repeated observations can be correlated: these summaries do not certify general reliability. Calibrate model judges against representative human labels before relying on them. [Scope, assumptions, and thresholds](METHODOLOGY.md).

Full tool definitions are retained as JSON Schema rather than flattened into a few constraints. Assevra validates nested properties, numeric limits, combinations, and local references. Unresolvable references yield evaluator errors; schema validation does not fetch remote URLs. Supply Draft 2020-12 compatible schemas with local references.

## Integrate with your pipeline

```bash
assevra integrate --list
assevra integrate langgraph
assevra integrate langfuse --out INTEGRATION.md
assevra scan --from traces.jsonl --tools tools.json --out-dir triage
assevra init --from traces.jsonl
```

`scan` is explicitly TRIAGE. It embeds measured and missing coverage in downloaded scorecards. To reach a release gate, review the drafted dataset and add the business labels that traces cannot supply.

| Stack | Integration maturity |
| --- | --- |
| Python / CLI | SDK, recorder, and explicit subprocess capture |
| OpenTelemetry / Phoenix | Supported OTLP/OpenInference export adapter, including flat Phoenix attributes and identity |
| LangGraph | Capture recipe retaining calls across message history |
| OpenAI Agents SDK | Capture recipe retaining run items and function-call results |
| Langfuse | Paginated observation-export recipe; confirm API compatibility with your deployment |
| MCP / OpenAI / Anthropic tool definitions | Contract import for recorded tool calls; not an MCP server connection |

Recipes and serialized formats are tested locally. Live hosted-service integration requires your own smoke test; there are no implied partnerships. [Integration guide](https://assevra.ai/docs/integrations).

## Configure and gate CI

```yaml
version: 1
dataset: evals/agent.jsonl
out_dir: .assevra/out
judge:
  provider: none
gate:
  enabled: true
  purpose: release
  required_dimensions: [action_correctness, tool_call, pii]
  fail_on_regression: false
validate:
  strict: true
thresholds:
  action_correctness: 1.0
  tool_call: 1.0
  pii: 1.0
```

```yaml
- uses: actions/checkout@v4
- uses: assevra/assevra@v0.6.0
  with:
    dataset: evals/agent.jsonl
    config: .assevra.yml
    version: 0.6.0
    gate: true
```

For cloud judging, install the corresponding extra (for example `extras: anthropic`) and provide the provider credentials. Missing required judges block the gate, including on forks. Run mock self-tests separately from release checks.

History is optional. First record and review a baseline with regression blocking disabled; then enable `fail_on_regression` and select that baseline. A missing or incompatible baseline blocks a required comparison. Do not use a mutable cache as your only source of approved baseline evidence.

## Privacy, signatures, and dependencies

Core evaluation uses `jsonschema`; provider SDKs, Presidio, and signing are optional extras. Deterministic checks run locally after installation. Cloud judges receive the input/context/output fields in their rubric prompts. The `local` provider can target your configured local model endpoint.

PII findings redact matched values, but reports can still contain sensitive row identifiers, judge reasons, and other diagnostic text. Review artifacts before sharing. `capture` executes only the command you explicitly provide and records every attempted trial, including errors, plus a completion manifest.

```bash
pip install 'assevra[sign]==0.6.0'
assevra keygen --out private.pem
assevra sign --scorecard evidence/scorecard.json --key private.pem
assevra verify --scorecard evidence/scorecard.json --signature evidence/scorecard.sig.json
```

Signatures cover canonical scorecard JSON, not HTML bytes. Integrity verification against the embedded key does not independently prove identity; pin a trusted public key for that. Agent Cards map evidence to governance control families, not legal compliance or certification.

## Upgrade from 0.5

Version 0.6 emits schema v2 artifacts. Existing `/schema/v1/` contracts remain available unchanged. Consumers should branch on `schema_version` and use `decision`; `overall_pass` is true only for a complete release PASS. Mock runs, missing judges, evaluator errors, and detector controls now have explicit semantics. See [migration notes](docs/MIGRATING-0.6.md).

## Development and citation

```bash
pip install -e '.[dev,sign]'
python -m pytest tests/ -q
python -m build
```

The repository golden dataset is an evaluator self-test. CI also runs the executable refund workflow and gates its repaired output through the composite GitHub Action.

MIT license. If you use the methodology or report scores, cite [Assevra on Zenodo](https://doi.org/10.5281/zenodo.21200852); version details are in [CITATION.cff](CITATION.cff). Contributions and reproducible issue reports are welcome through GitHub. Historical case-study datasets are synthetic illustrations.
