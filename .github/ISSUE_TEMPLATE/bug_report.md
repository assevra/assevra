---
name: Bug report
about: Something scored wrong, crashed, or behaved unexpectedly
title: ""
labels: bug
---

<!--
Two commands answer a surprising share of these before you file, and their output
is exactly what makes an issue fast to resolve either way:

    assevra demo --provider mock     # does the engine work at all?
    assevra validate <your dataset>  # is the dataset the problem?

If the demo works and your dataset does not, the validator will usually name the
row and the reason.
-->

**What happened**

<!-- What did Assevra do, and what did you expect instead? If it is a scoring
     surprise, quote the row's `detail` line from the report — it usually says
     exactly why. -->

**How to reproduce**

- The command you ran, in full:
- A **minimal synthetic** dataset that triggers it (two or three rows is usually
  plenty — please never paste real personal data into a public issue):

```jsonl
{"id":"repro-1","dimension":"...","input":"...","agent_output":"...","...":"..."}
```

**Output**

<details>
<summary>Full command output</summary>

```
paste here
```

</details>

**Environment**

- `assevra --version`:
- Python version:
- OS:
- Extras installed (`pii`, `sign`, `anthropic`, `openai`, …):
- Judge provider, if the failure involves a judged dimension:
