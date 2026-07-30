"""
The built-in Assevra reliability scorers.

Nine dimensions ship with the package. Four are the founding methodology
(grounding, safety, PII, task-completion); five extend it to the failure modes
that actually take agents down in production — bad tool calls, wrong actions,
prompt injection, and blown cost and latency budgets.

Every scorer module declares the same handful of module-level constants, which is
all :mod:`assevra.registry` needs to wire it into the scorecard, the validator,
the config, and the CLI:

  ``DIMENSION``            the name a dataset row routes on
  ``MODE``                 ``deterministic`` or ``llm-judge``
  ``DIMENSION_THRESHOLD``  the pass rate at which the dimension passes
  ``ANSWER_KEY``           fields, any one of which labels a row
  ``REQUIRES``             fields without which the row cannot be scored
  ``LABEL_HINT``           what to tell a human whose row is unlabeled
  ``score(rows, judge=None, options=None) -> DimensionResult``

Registering a scorer of your own is the same three lines — see
:func:`assevra.register_scorer_module`. Two rules keep a new dimension honest, and
they are not negotiable: **deterministic before judge** (if a rule can detect it,
do not ask a model), and **every dimension ships a threshold and a confidence
interval** (a number without a bar is not a gate).
"""
from .. import registry
from . import (
    action_correctness,
    cost,
    grounding,
    injection,
    latency,
    pii,
    safety,
    task_completion,
    tool_call,
)

BUILTIN_MODULES = (
    grounding,
    safety,
    pii,
    task_completion,
    tool_call,
    action_correctness,
    injection,
    cost,
    latency,
)

for _module in BUILTIN_MODULES:
    registry.register_scorer_module(_module, replace=True, builtin=True)

__all__ = [
    "action_correctness",
    "cost",
    "grounding",
    "injection",
    "latency",
    "pii",
    "safety",
    "task_completion",
    "tool_call",
    "BUILTIN_MODULES",
]
