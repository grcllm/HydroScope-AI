"""Callable tools exposed to the Gemini SDK.

Design goals:
- Keep a single source of truth for analytics by delegating to Agent 3
- Provide both a generic question-answer tool and a few structured helpers
- Be scalable: adding granular tools later won't break existing ones
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import threading

import pandas as pd

from dpwh_agent.agents.agent3_answer import agent3_run


_DF_LOCK = threading.Lock()
_CURRENT_DF: Optional[pd.DataFrame] = None


def set_dataframe(df: pd.DataFrame) -> None:
    """Set the current dataframe used by tool functions."""
    global _CURRENT_DF
    with _DF_LOCK:
        _CURRENT_DF = df


def _require_df() -> pd.DataFrame:
    with _DF_LOCK:
        if _CURRENT_DF is None:
            raise RuntimeError("Dataset not initialized. Call set_dataframe(df) first.")
        return _CURRENT_DF


def _agent_answer(question: str) -> str:
    """Run Agent 3 safely and return a string even if an internal error occurs."""
    df = _require_df()
    try:
        return agent3_run(question, df)
    except Exception as e:
        # Return a user-friendly error so the model doesn't surface a tool failure
        return (
            "I hit an internal error while computing that answer. "
            "Please try rephrasing the question or adding more specifics (e.g., municipality/province/year)."
        )


def _fmt_place_token(token: str) -> str:
    """Normalize location tokens for better intent parsing (e.g., 'Region 2' over plain '2')."""
    if not token:
        return token
    t = str(token).strip()
    low = t.lower()
    # Common region shorthands
    if low in {"ncr", "national capital region", "metro manila", "metropolitan manila"}:
        return "National Capital Region"
    if low in {"car", "cordillera", "cordillera administrative region"}:
        return "Cordillera Administrative Region"
    # Region IV variants
    if low in {"4a", "iv-a", "region 4a", "region iv-a"}:
        return "Region IV-A"
    if low in {"4b", "iv-b", "region 4b", "region iv-b"}:
        return "Region IV-B"
    # Pure digits – prefer explicit 'Region N'
    if low.isdigit():
        return f"Region {t}"
    # Already looks like 'Region X'
    if low.startswith("region "):
        return t
    return t


def answer_dpwh_question(question: str) -> str:
    """Answer a natural language question about DPWH flood control projects.

    Args:
        question: The user's question in natural language.

    Returns:
        A concise, factual answer computed from the dataset. Use pesos (₱) for money.
    """
    return _agent_answer(question)


def lookup_project(project_id: str) -> str:
    """Return details about a project by ID.

    Args:
        project_id: The project identifier string.

    Returns:
        A human-readable description of the project.
    """
    q = f"project id {project_id}"
    return _agent_answer(q)


def top_contractors_by_count(top_n: int = 10, municipality: Optional[str] = None,
                             province: Optional[str] = None, region: Optional[str] = None) -> str:
    """List top contractors by number of projects with optional location filter.

    Args:
        top_n: Number of contractors to return (default 10).
        municipality: Optional municipality/city filter.
        province: Optional province filter.
        region: Optional region (e.g., NCR, Region II, IV-A).

    Returns:
        A bullet list of contractors with project counts.
    """
    df = _require_df()
    where = []
    if municipality:
        where.append(municipality)
    if province:
        where.append(province)
    if region:
        where.append(_fmt_place_token(region))
    place = f" in {' ,'.join(where)}" if where else ""
    q = f"top {top_n} contractors by number of projects{place}"
    return _agent_answer(q)


def top_contractors_by_budget(top_n: int = 10, municipality: Optional[str] = None,
                              province: Optional[str] = None, region: Optional[str] = None) -> str:
    """List top contractors by total approved budget with optional location filter."""
    df = _require_df()
    where = []
    if municipality:
        where.append(municipality)
    if province:
        where.append(province)
    if region:
        where.append(_fmt_place_token(region))
    place = f" in {' ,'.join(where)}" if where else ""
    q = f"top {top_n} contractors by total budget{place}"
    return _agent_answer(q)


def total_approved_budget(municipality: Optional[str] = None,
                          province: Optional[str] = None,
                          region: Optional[str] = None) -> str:
    """Compute total approved budget optionally filtered by location."""
    df = _require_df()
    where = []
    if municipality:
        where.append(municipality)
    if province:
        where.append(province)
    if region:
        where.append(_fmt_place_token(region))
    place = f" in {' ,'.join(where)}" if where else ""
    q = f"total approved budget{place}"
    return _agent_answer(q)


def count_projects(municipality: Optional[str] = None,
                   province: Optional[str] = None,
                   region: Optional[str] = None,
                   contractor: Optional[str] = None) -> str:
    """Count projects with optional filters for location or contractor."""
    df = _require_df()
    parts = ["how many projects"]
    if contractor:
        parts.append(f"contractor {contractor} have")
    place = []
    if municipality:
        place.append(municipality)
    if province:
        place.append(province)
    if region:
        place.append(_fmt_place_token(region))
    q = " ".join(parts)
    if place:
        q += f" in {' ,'.join(place)}"
    return _agent_answer(q)


def highest_budget(top_n: int = 1, municipality: Optional[str] = None,
                   province: Optional[str] = None,
                   region: Optional[str] = None) -> str:
    """Get the project(s) with the highest approved budget, optionally filtered by location."""
    df = _require_df()
    where = []
    if municipality:
        where.append(municipality)
    if province:
        where.append(province)
    if region:
        where.append(_fmt_place_token(region))
    prefix = f"top {top_n} " if top_n and top_n > 1 else ""
    place = f" in {' ,'.join(where)}" if where else ""
    q = f"{prefix}highest approved budget{place}"
    # Use the safe wrapper to avoid propagating exceptions into the model's tool-calling path
    return _agent_answer(q)


def lowest_budget(top_n: int = 1, municipality: Optional[str] = None,
                  province: Optional[str] = None,
                  region: Optional[str] = None) -> str:
    """Get the project(s) with the lowest approved budget, optionally filtered by location."""
    df = _require_df()
    where = []
    if municipality:
        where.append(municipality)
    if province:
        where.append(province)
    if region:
        where.append(_fmt_place_token(region))
    prefix = f"top {top_n} " if top_n and top_n > 1 else ""
    place = f" in {' ,'.join(where)}" if where else ""
    q = f"{prefix}lowest approved budget{place}"
    # Use the safe wrapper to avoid propagating exceptions into the model's tool-calling path
    return _agent_answer(q)


def tools_list() -> List[Any]:
    """Return the list of callable tools to register with Gemini.

    These are simple wrappers around Agent 3 and are intentionally conservative.
    """
    return [
        answer_dpwh_question,
        lookup_project,
        count_projects,
        total_approved_budget,
        highest_budget,
        lowest_budget,
        top_contractors_by_count,
        top_contractors_by_budget,
    ]
