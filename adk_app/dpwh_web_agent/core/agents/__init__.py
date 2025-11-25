"""Convenience re-exports for dpwh_agent.agents.

This module provides stable names for commonly used agent functions so
callers can import from `dpwh_web_agent.dpwh_agent.agents` without
depending on specific filenames which may be refactored.
"""
from typing import Any

# Attempt to import common agent entrypoints. Missing imports are left as
# None so callers can handle graceful degradation with clear error messages.
try:
    from .agent1_fetch import agent1_run  # type: ignore
except Exception:  # pragma: no cover - resilient import
    agent1_run = None  # type: ignore

try:
    from .agent2_process import agent2_run  # type: ignore
except Exception:
    agent2_run = None  # type: ignore

try:
    from .agent3_answer import agent3_run  # type: ignore
except Exception:
    agent3_run = None  # type: ignore

__all__ = [
    "agent1_run",
    "agent2_run",
    "agent3_run",
]
