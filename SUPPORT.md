# Getting help

Start here, in this order — it is roughly fastest-first.

## 1. Try it against something known-good

Most "is it me or the tool?" questions are answered in ten seconds:

```bash
assevra demo --provider mock
```

That runs the full engine — including the judged dimensions, offline and
deterministically — on a bundled dataset. If the demo works and your dataset does
not, the problem is in the dataset, and the next step tells you exactly where.

## 2. Ask the validator

```bash
assevra validate your_dataset.jsonl
```

Every row comes back as **LABELED**, **UNLABELED**, or **INVALID**, with a
specific error code and a suggested fix. A surprising share of unexpected scores
are an unlabeled row scoring as a vacuous pass, and the validator says so by
name.

## 3. Read the docs

- [Getting started](https://assevra.ai/docs/getting-started)
- [Troubleshooting](https://assevra.ai/docs/troubleshooting) — the specific
  symptoms people actually hit
- [Configuration reference](https://assevra.ai/docs/configuration)
- [CLI reference](https://assevra.ai/docs/cli)
- [Methodology](https://github.com/assevra/assevra/blob/main/METHODOLOGY.md) —
  what each dimension means and, just as importantly, what it does not

## 4. Ask in Discussions

[GitHub Discussions](https://github.com/assevra/assevra/discussions) is the place
for:

- "How should I model *this* failure as a dimension?"
- "Is this threshold reasonable for my domain?"
- "What does this number actually let me claim?"
- Showing what you built. Real datasets and real failure modes are what sharpen
  the methodology, and they are genuinely welcome.

## 5. Open an issue

[Open an issue](https://github.com/assevra/assevra/issues/new/choose) for a bug
or a concrete feature request. What makes an issue fast to resolve:

- The command you ran and its full output.
- `assevra --version` and your Python version.
- A **minimal dataset** that reproduces it — two or three rows is usually plenty.
  Please synthesise them; never paste real personal data into a public issue.
- What you expected the score to be, and why.

## Security

Do **not** open a public issue for a vulnerability. Follow
[SECURITY.md](SECURITY.md).

## What to expect

Assevra is maintained by one person alongside other work. Issues are usually
looked at within a week. A methodology question may take longer, because getting
a definition right matters more than answering quickly — see
[GOVERNANCE.md](GOVERNANCE.md) for how those decisions are made.

If something is urgent for you and stalled here, say so on the issue. That is
useful information, not a nuisance.
