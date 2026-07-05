"""
Assevra -- a reference implementation and methodology for measuring the
reliability of LLM agents (the Assevra Reliability Scorecard).

A personal open-source research project by Veera Ravindra Divi. MIT licensed.
See METHODOLOGY.md for the four-dimension specification.
"""
from .scorecard import (
    ASSEVRA_VERSION,
    DimensionResult,
    RowResult,
    Scorecard,
    wilson_ci,
)

__all__ = [
    "ASSEVRA_VERSION",
    "DimensionResult",
    "RowResult",
    "Scorecard",
    "wilson_ci",
]

__version__ = ASSEVRA_VERSION
