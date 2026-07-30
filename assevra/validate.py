"""
Dataset validation — the gate that runs *before* evaluation.

The most expensive failure in an evaluation pipeline is not a low score. It is a
high one that means nothing. A row whose ``must_include`` list is empty passes
every time; a row whose ``dimension`` is misspelled is silently dropped; a row
that never got its answer key contributes a vacuous pass to a number someone will
put in a release review. All three look identical in a scorecard, and all three
are detectable in milliseconds before a single judge call is made.

So every row lands in exactly one of three states:

``LABELED``     the row has an answer key and can produce a meaningful verdict.
``UNLABELED``   the row parses and will score — but there is nothing to verify,
                so its "pass" is vacuous. Legitimate mid-labeling (that is what
                ``assevra bootstrap`` emits); dangerous once you believe the
                number. ``--strict`` promotes it to a failure.
``INVALID``     the row is structurally unusable: no id, unknown dimension, a
                field of the wrong type, a duplicate id. Evaluation must not
                proceed on it.

``assevra validate`` exits non-zero when anything is INVALID, and ``assevra run``
calls the same check first, so a broken dataset fails in a second instead of
producing a confident, meaningless report.

The per-dimension rules are not hard-coded here. Each scorer declares its own
``ANSWER_KEY``/``REQUIRES``/``LABEL_HINT`` and may add a ``validate_row`` hook, so
a scorer you register brings its validation with it.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from . import registry, schemas

LABELED = "LABELED"
UNLABELED = "UNLABELED"
INVALID = "INVALID"


@dataclass
class Message:
    level: str  # "error" | "warning"
    code: str
    message: str
    field_name: Optional[str] = None
    fix: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "field": self.field_name,
            "fix": self.fix,
        }


@dataclass
class RowReport:
    line: int
    row_id: str
    dimension: Optional[str]
    state: str
    messages: list[Message] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "line": self.line,
            "id": self.row_id,
            "dimension": self.dimension,
            "state": self.state,
            "messages": [m.to_dict() for m in self.messages],
        }


@dataclass
class Report:
    dataset: str
    rows: list[RowReport]
    strict: bool = False
    dataset_sha256: Optional[str] = None
    assevra_version: str = ""
    generated_at: Optional[str] = None

    def count(self, state: str) -> int:
        return sum(1 for r in self.rows if r.state == state)

    @property
    def ok(self) -> bool:
        if self.count(INVALID):
            return False
        if self.strict and self.count(UNLABELED):
            return False
        return True

    def by_dimension(self) -> dict:
        out: dict[str, dict[str, int]] = {}
        for row in self.rows:
            key = row.dimension or "(none)"
            bucket = out.setdefault(key, {LABELED: 0, UNLABELED: 0, INVALID: 0})
            bucket[row.state] += 1
        return out

    def to_dict(self) -> dict:
        return schemas.stamp(
            {
                "assevra_version": self.assevra_version,
                "generated_at": self.generated_at,
                "dataset": self.dataset,
                "dataset_sha256": self.dataset_sha256,
                "strict": self.strict,
                "ok": self.ok,
                "counts": {
                    "total": len(self.rows),
                    "labeled": self.count(LABELED),
                    "unlabeled": self.count(UNLABELED),
                    "invalid": self.count(INVALID),
                },
                "by_dimension": self.by_dimension(),
                "rows": [r.to_dict() for r in self.rows],
            },
            "validation",
        )

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


# --------------------------------------------------------------------------- #
# Loading                                                                      #
# --------------------------------------------------------------------------- #
def dataset_sha256(path: str) -> Optional[str]:
    """Hash of the dataset file, stamped into the scorecard so a reader can
    confirm which rows produced a score."""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def load_rows(path: str) -> tuple[list[tuple[int, Any]], list[RowReport]]:
    """Read a JSONL dataset. Returns (rows as (lineno, value), unparseable rows).

    A malformed line does not abort the read: reporting *every* bad line at once
    is the difference between one fix-and-rerun cycle and ten.
    """
    rows: list[tuple[int, Any]] = []
    broken: list[RowReport] = []
    with open(path, encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                rows.append((lineno, json.loads(text)))
            except json.JSONDecodeError as exc:
                broken.append(
                    RowReport(
                        line=lineno,
                        row_id=f"(line {lineno})",
                        dimension=None,
                        state=INVALID,
                        messages=[
                            Message(
                                "error",
                                "invalid_json",
                                f"line is not valid JSON: {exc.msg} (column {exc.colno})",
                                fix="one JSON object per line, no trailing commas",
                            )
                        ],
                    )
                )
    return rows, broken


# --------------------------------------------------------------------------- #
# Validation                                                                   #
# --------------------------------------------------------------------------- #
def _non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (str, list, dict, tuple, set)):
        return len(value) > 0
    return True


def validate_row(
    row: Any,
    lineno: int,
    seen_ids: set,
    options: Optional[dict] = None,
) -> RowReport:
    """Classify one row as LABELED / UNLABELED / INVALID."""
    if not isinstance(row, dict):
        return RowReport(
            line=lineno,
            row_id=f"(line {lineno})",
            dimension=None,
            state=INVALID,
            messages=[
                Message(
                    "error",
                    "not_an_object",
                    f"row is a {type(row).__name__}, expected a JSON object",
                )
            ],
        )

    messages: list[Message] = []
    row_id = row.get("id")
    dimension = row.get("dimension")

    if not isinstance(row_id, str) or not row_id.strip():
        messages.append(
            Message(
                "error",
                "missing_id",
                "row has no non-empty string `id`",
                "id",
                "give every row a unique id so failures are traceable",
            )
        )
        row_id = f"(line {lineno})"
    elif row_id in seen_ids:
        messages.append(
            Message(
                "error",
                "duplicate_id",
                f"id {row_id!r} already appears earlier in this dataset",
                "id",
                "ids must be unique; use case_id to group repeated trials instead",
            )
        )
    else:
        seen_ids.add(row_id)

    if not isinstance(dimension, str) or not dimension.strip():
        messages.append(
            Message(
                "error",
                "missing_dimension",
                "row has no `dimension`",
                "dimension",
                f"one of: {', '.join(registry.dimensions())}",
            )
        )
        return RowReport(lineno, row_id, None, INVALID, messages)

    if not registry.has_scorer(dimension):
        messages.append(
            Message(
                "error",
                "unknown_dimension",
                f"unknown dimension {dimension!r}",
                "dimension",
                f"one of: {', '.join(registry.dimensions())}",
            )
        )
        return RowReport(lineno, row_id, dimension, INVALID, messages)

    spec = registry.get_scorer(dimension)

    for required in spec.requires:
        if not _non_empty(row.get(required)):
            messages.append(
                Message(
                    "error",
                    "missing_field",
                    f"`{required}` is required for dimension {dimension!r} and is empty or absent",
                    required,
                    "Assevra scores outputs you already captured — record what the agent produced",
                )
            )

    if "case_id" in row and not isinstance(row["case_id"], str):
        messages.append(
            Message("error", "bad_type", "`case_id` must be a string", "case_id")
        )
    if "tags" in row and not isinstance(row["tags"], list):
        messages.append(Message("error", "bad_type", "`tags` must be a list", "tags"))

    # Scorer-specific structural checks.
    if spec.validate_row is not None:
        for raw in spec.validate_row(row, options) or []:
            level, code, text, field_name, fix = (list(raw) + [None, None])[:5]
            messages.append(Message(level, code, text, field_name, fix))

    if any(m.level == "error" for m in messages):
        return RowReport(lineno, row_id, dimension, INVALID, messages)

    # Labeled? Any one answer-key field is enough; a scorer may also decide with
    # full knowledge of the config (cost and latency are labeled by a project
    # budget as readily as by a per-row one).
    if spec.is_labeled is not None:
        labeled = bool(spec.is_labeled(row, options))
    elif not spec.answer_key:
        labeled = True
    else:
        labeled = any(_non_empty(row.get(k)) for k in spec.answer_key)

    if labeled:
        return RowReport(lineno, row_id, dimension, LABELED, messages)

    messages.append(
        Message(
            "warning",
            "missing_answer_key",
            (
                f"no answer key for dimension {dimension!r} — this row will score as a "
                "vacuous pass"
            ),
            spec.answer_key[0] if spec.answer_key else None,
            spec.label_hint or None,
        )
    )
    return RowReport(lineno, row_id, dimension, UNLABELED, messages)


def validate_dataset(
    path: str,
    strict: bool = False,
    options: Optional[dict] = None,
    assevra_version: str = "",
    generated_at: Optional[str] = None,
) -> Report:
    rows, broken = load_rows(path)
    reports = list(broken)
    seen_ids: set = set()
    for lineno, row in rows:
        reports.append(validate_row(row, lineno, seen_ids, options))
    reports.sort(key=lambda r: r.line)
    return Report(
        dataset=path,
        rows=reports,
        strict=strict,
        dataset_sha256=dataset_sha256(path),
        assevra_version=assevra_version,
        generated_at=generated_at,
    )


# --------------------------------------------------------------------------- #
# Rendering                                                                    #
# --------------------------------------------------------------------------- #
_STATE_GLYPH = {LABELED: "ok  ", UNLABELED: "todo", INVALID: "FAIL"}


def render(report: Report, show: str = "problems", limit: int = 40) -> str:
    """A terminal report. `show` is 'problems' (default) or 'all'."""
    lines: list[str] = []
    total = len(report.rows)
    labeled = report.count(LABELED)
    unlabeled = report.count(UNLABELED)
    invalid = report.count(INVALID)

    lines.append(f"Dataset: {report.dataset}")
    lines.append(
        f"  {total} rows — {labeled} labeled, {unlabeled} unlabeled, {invalid} invalid"
    )

    by_dim = report.by_dimension()
    if by_dim:
        lines.append("")
        lines.append("  dimension            labeled  unlabeled  invalid")
        for name in sorted(by_dim):
            counts = by_dim[name]
            lines.append(
                f"  {name:<20} {counts[LABELED]:>7}  {counts[UNLABELED]:>9}  {counts[INVALID]:>7}"
            )

    interesting = [
        r for r in report.rows if show == "all" or r.state != LABELED or r.messages
    ]
    if interesting:
        lines.append("")
        for row in interesting[:limit]:
            lines.append(f"  [{_STATE_GLYPH[row.state]}] {row.row_id}  ({row.dimension or '?'})")
            for msg in row.messages:
                mark = "!" if msg.level == "error" else "-"
                lines.append(f"        {mark} {msg.code}: {msg.message}")
                if msg.fix:
                    lines.append(f"          fix: {msg.fix}")
        if len(interesting) > limit:
            lines.append(f"  … and {len(interesting) - limit} more rows not shown")

    lines.append("")
    if invalid:
        lines.append(
            f"INVALID: {invalid} row(s) are structurally unusable. Fix them before scoring — "
            "a scorecard built on them would be meaningless."
        )
    elif unlabeled and report.strict:
        lines.append(
            f"STRICT: {unlabeled} row(s) carry no answer key. In strict mode that is a failure "
            "(an unlabeled row scores as a vacuous pass)."
        )
    elif unlabeled:
        lines.append(
            f"OK, with {unlabeled} row(s) still unlabeled. They will score as vacuous passes "
            "until you fill the answer key — run with --strict once labeling is done."
        )
    else:
        lines.append("OK — every row is labeled and structurally valid.")
    return "\n".join(lines)
