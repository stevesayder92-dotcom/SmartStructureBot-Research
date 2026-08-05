"""Deterministic historical paper-execution subsystem.

This package consumes canonical Director actions.  It has no authority to
create or modify strategy signals and contains no live broker functions.
"""

from simulator.execution.paper_broker import PaperBroker
from simulator.execution.intrabar_resolver import IntrabarResolver
from simulator.execution.swap_engine import SwapEngine

__all__ = ["PaperBroker", "IntrabarResolver", "SwapEngine"]
