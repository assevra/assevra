"""
``assevra capture`` — record what your agent did, without writing a capture script.

Assevra scores outputs you have already captured, and that boundary is
load-bearing: it is why the tool works with every framework, and why "it never
executes your code" survives a security review. But the boundary has always had
a cost — the user writes a small script to run their agent over some inputs and
write JSONL.

That script is the same script every time. So it ships here.

    # answer a generated probe suite
    assevra capture --from probes.jsonl --out answered.jsonl -- python agent.py

    # capture fresh traces from a list of inputs
    assevra capture --inputs questions.txt --out traces.jsonl -- python agent.py

The contract with your agent is the smallest one that could work, so that
anything can satisfy it: **the input arrives on stdin, the answer comes back on
stdout.** A three-line wrapper around any framework satisfies it. Anything your
agent writes to stderr is left alone, so logging still works.

Note what this does *not* change: Assevra still runs only the command **you**
typed, in your shell, with your environment. It is a stopwatch and a file writer,
not a runtime.

Two things come free because a wrapper is doing the timing:

* **``latency_ms`` on every row**, measured around the call — which turns the
  latency dimension on with no further work.
* **``case_id`` grouping with ``--repeat N``**, which runs each input N times
  under one case id and unlocks pass^k and the flaky-case report. Repeated trials
  are the single most informative thing you can capture and the least likely to
  be set up by hand.

For in-process capture, where a subprocess makes no sense, use the recorder:

    from assevra.capture import Recorder

    with Recorder("traces.jsonl") as rec:
        for question in questions:
            with rec.record(question, context=policy) as turn:
                turn.output = my_agent(question)
                turn.tool_calls = [{"name": c.name, "arguments": c.args} for c in ...]
"""
from __future__ import annotations

import json
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional


class CaptureError(Exception):
    """Raised when the agent command cannot be run or produced nothing."""


@dataclass
class Turn:
    """One recorded interaction, filled in by the caller."""

    input: str
    context: str = ""
    output: str = ""
    tool_calls: list = field(default_factory=list)
    usage: Optional[dict] = None
    cost_usd: Optional[float] = None
    case_id: Optional[str] = None
    tags: list = field(default_factory=list)
    latency_ms: Optional[float] = None
    row_id: Optional[str] = None

    def to_row(self) -> dict:
        row: dict = {
            "input": self.input,
            "context": self.context,
            "agent_output": self.output,
        }
        if self.row_id:
            row["id"] = self.row_id
        if self.case_id:
            row["case_id"] = self.case_id
        if self.tool_calls:
            row["tool_calls"] = self.tool_calls
        if self.usage:
            row["usage"] = self.usage
        if self.cost_usd is not None:
            row["cost_usd"] = self.cost_usd
        if self.latency_ms is not None:
            row["latency_ms"] = round(self.latency_ms, 3)
        if self.tags:
            row["tags"] = self.tags
        return row


class Recorder:
    """Append captured turns to a JSONL file, timing each one."""

    def __init__(self, path: str, id_prefix: str = "capture"):
        self.path = Path(path)
        self.id_prefix = id_prefix
        self._handle = None
        self._count = 0

    def __enter__(self) -> "Recorder":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("w", encoding="utf-8")
        return self

    def __exit__(self, *exc) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    @contextmanager
    def record(self, user_input: str, context: str = "", **kwargs):
        """Time one interaction and write it when the block exits."""
        self._count += 1
        turn = Turn(
            input=user_input,
            context=context,
            row_id=kwargs.pop("row_id", f"{self.id_prefix}-{self._count:04d}"),
            **kwargs,
        )
        started = time.perf_counter()
        try:
            yield turn
        finally:
            if turn.latency_ms is None:
                turn.latency_ms = (time.perf_counter() - started) * 1000.0
            self.write(turn)

    def write(self, turn: Turn) -> None:
        if self._handle is None:
            raise CaptureError("Recorder used outside its `with` block")
        self._handle.write(json.dumps(turn.to_row(), ensure_ascii=False) + "\n")
        self._handle.flush()


# --------------------------------------------------------------------------- #
# Subprocess capture                                                           #
# --------------------------------------------------------------------------- #
def run_command(
    command: list[str],
    user_input: str,
    context: str = "",
    timeout: float = 120.0,
    pass_context: bool = True,
) -> tuple[str, float]:
    """Run the agent once. Returns (stdout, latency_ms).

    The whole prompt goes in on stdin — the context first when there is one, so
    an agent that simply echoes its stdin still produces something meaningful to
    score.
    """
    payload = f"{context}\n\n{user_input}" if (context and pass_context) else user_input
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            input=payload,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise CaptureError(f"cannot run {command[0]!r}: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise CaptureError(
            f"the agent did not answer within {timeout:.0f}s. Raise --timeout, or "
            "check whether it is waiting for input it will never get."
        ) from exc
    latency_ms = (time.perf_counter() - started) * 1000.0

    if completed.returncode != 0:
        detail = (completed.stderr or "").strip().splitlines()
        tail = detail[-1] if detail else "no stderr"
        raise CaptureError(
            f"the agent exited {completed.returncode}: {tail}"
        )
    return completed.stdout.strip(), latency_ms


def capture_inputs(
    command: list[str],
    inputs: Iterable[tuple[str, str]],
    out_path: str,
    repeat: int = 1,
    timeout: float = 120.0,
    id_prefix: str = "capture",
    on_progress: Optional[Callable[[int, int, str], None]] = None,
) -> int:
    """Run `command` over (input, context) pairs and write a JSONL trace file.

    `repeat > 1` runs each input several times under a shared ``case_id``, which
    is what makes pass^k and the flaky-case report available.
    """
    pairs = list(inputs)
    total = len(pairs) * repeat
    written = 0

    with Recorder(out_path, id_prefix=id_prefix) as recorder:
        for index, (user_input, context) in enumerate(pairs, start=1):
            case_id = f"{id_prefix}-case-{index:04d}" if repeat > 1 else None
            for trial in range(1, repeat + 1):
                output, latency_ms = run_command(
                    command, user_input, context, timeout=timeout
                )
                turn = Turn(
                    input=user_input,
                    context=context,
                    output=output,
                    latency_ms=latency_ms,
                    case_id=case_id,
                    row_id=(
                        f"{id_prefix}-{index:04d}-t{trial}"
                        if repeat > 1
                        else f"{id_prefix}-{index:04d}"
                    ),
                    tags=["captured"],
                )
                recorder.write(turn)
                written += 1
                if on_progress:
                    on_progress(written, total, turn.row_id or "")
    return written


def answer_probes(
    command: list[str],
    probe_rows: list[dict],
    out_path: str,
    timeout: float = 120.0,
    on_progress: Optional[Callable[[int, int, str], None]] = None,
) -> tuple[int, list[str]]:
    """Run the agent over a probe suite and write the answered dataset.

    The probes keep every field they arrived with — crucially their answer key —
    and gain ``agent_output`` and ``latency_ms``. A probe the agent fails to
    answer is recorded with the error rather than dropped, because a suite that
    silently shrinks would inflate the score of the runs that did complete.
    """
    answered_rows: list[dict] = []
    failures: list[str] = []
    total = len(probe_rows)

    for index, row in enumerate(probe_rows, start=1):
        merged = dict(row)
        try:
            output, latency_ms = run_command(
                command, row.get("input", ""), row.get("context", ""), timeout=timeout
            )
            merged["agent_output"] = output
            merged["latency_ms"] = round(latency_ms, 3)
        except CaptureError as exc:
            merged["agent_output"] = ""
            merged["_capture_error"] = str(exc)
            failures.append(f"{row.get('id', '?')}: {exc}")
        merged.pop("_probe", None)
        answered_rows.append(merged)
        if on_progress:
            on_progress(index, total, str(row.get("id", "")))

    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in answered_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(answered_rows), failures


def read_inputs(path: str) -> list[tuple[str, str]]:
    """Read inputs from a plain text file (one per line) or a JSONL file."""
    file = Path(path)
    if not file.is_file():
        raise CaptureError(f"inputs file not found: {path}")
    text = file.read_text(encoding="utf-8")
    pairs: list[tuple[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("{"):
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                pairs.append((line, ""))
                continue
            pairs.append(
                (
                    str(record.get("input") or record.get("prompt") or record.get("question") or ""),
                    str(record.get("context") or ""),
                )
            )
        else:
            pairs.append((line, ""))
    if not pairs:
        raise CaptureError(f"{path}: no inputs found")
    return pairs
