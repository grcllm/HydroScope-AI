"""Callable tools exposed to the Gemini SDK.

Design goals:
- Keep a single source of truth for analytics by delegating to Agent 3
- Provide both a generic question-answer tool and a few structured helpers
- Be scalable: adding granular tools later won't break existing ones
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import threading

import pandas as pd

from dpwh_web_agent.dpwh_agent.agents.agent3_answer import (
    agent3_run,
    find_project_id_column,
)
from dpwh_web_agent.dpwh_agent.agents.agent3_answer import _set_pagination, _PAGINATION_STATE
from dpwh_web_agent.dpwh_agent.utils.schema import find_column


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


# Alias: top contractors by total budget
def top_contractors(top_n: int = 10, municipality: Optional[str] = None,
                    province: Optional[str] = None, region: Optional[str] = None) -> str:
    return top_contractors_by_budget(top_n, municipality, province, region)


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


def budget_trend_by_year(municipality: Optional[str] = None,
                         province: Optional[str] = None,
                         region: Optional[str] = None) -> str:
    """Return total approved budget per year (trend) with optional location filter.

    This makes the model more reliably call a concrete tool for trend questions
    instead of relying on generic QA routing.
    """
    _require_df()
    where = []
    if municipality:
        where.append(municipality)
    if province:
        where.append(province)
    if region:
        where.append(_fmt_place_token(region))
    place = f" in {' ,'.join(where)}" if where else ""
    q = f"budget trend by year{place}"
    return _agent_answer(q)


# ----------------------- Contractor totals and rankings -----------------------

def contractor_max_total_budget(municipality: Optional[str] = None,
                                province: Optional[str] = None,
                                region: Optional[str] = None) -> str:
    """Which contractor has the highest total approved budget (optionally in a place)."""
    _require_df()
    where = []
    if municipality:
        where.append(municipality)
    if province:
        where.append(province)
    if region:
        where.append(_fmt_place_token(region))
    place = f" in {' ,'.join(where)}" if where else ""
    q = f"which contractor has the highest approved budget{place}"
    return _agent_answer(q)


def contractor_max_count(municipality: Optional[str] = None,
                         province: Optional[str] = None,
                         region: Optional[str] = None) -> str:
    """Which contractor has the most projects (optionally in a place)."""
    _require_df()
    where = []
    if municipality:
        where.append(municipality)
    if province:
        where.append(province)
    if region:
        where.append(_fmt_place_token(region))
    place = f" in {' ,'.join(where)}" if where else ""
    q = f"which contractor has the most projects{place}"
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


# --- New contractor-focused helpers ---------------------------------------------------------

def top_projects_for_contractor(contractor: str, top_n: int = 5) -> str:
    """Return the top-N projects by approved budget for a contractor.

    Output format per row: "<Project ID> — <Contractor> — <Approved Budget>".

    Args:
        contractor: Contractor name or fragment (case-insensitive; fuzzy contains).
        top_n: Number of projects to return. Defaults to 5 and will be capped at 5 to
               follow product requirements.

    Returns:
        A bullet list with at most 5 lines. If no rows match, a helpful message.
    """
    df = _require_df()
    if not contractor or not str(contractor).strip():
        return "Please provide a contractor name."

    contractor_col = find_column(df, [
        "contractor",
        "contractor_name",
        "winning_contractor",
    ])
    budget_col = find_column(df, [
        "approved_budget_num",
        "approved_budget_for_contract",
        "approvedbudgetforcontract",
        "approved_budget",
        "budget",
        "contractcost",
        "approved budget for contract",
    ])
    if contractor_col is None or budget_col is None:
        return "I couldn't find the required columns (contractor/budget)."

    # Filter to the contractor (case-insensitive contains; prefer exact match if available)
    series = df[contractor_col].astype(str)
    target = str(contractor).strip()
    exact_mask = series.str.strip().str.casefold() == target.casefold()
    mask = exact_mask | series.str.casefold().str.contains(target.casefold(), na=False)
    sub = df[mask].copy()
    if sub.empty:
        return f"I couldn't find any projects for contractor {target}."

    # Coerce budget and sort
    sub[budget_col] = pd.to_numeric(sub[budget_col], errors="coerce")
    sub = sub.dropna(subset=[budget_col])
    if sub.empty:
        return f"No projects with a valid approved budget for contractor {target}."

    # Respect requested top_n but prepare the full sorted list for pagination
    n_req = int(top_n or 5)
    tmp_sorted = sub.sort_values(by=budget_col, ascending=False)

    pid_col = find_project_id_column(tmp_sorted)
    lines: List[str] = []
    for _, r in tmp_sorted.iterrows():
        pid = r.get(pid_col, "N/A")
        contr_val = r.get(contractor_col, target)
        amt = float(r[budget_col]) if pd.notna(r[budget_col]) else None
        if amt is not None:
            lines.append(f"- {pid} — {contr_val} — ₱{amt:,.2f}")
        else:
            lines.append(f"- {pid} — {contr_val}")

    # Prepare pagination state so follow-ups like 'more' work
    prepared: List[Tuple[str, str]] = []
    for line in lines:
        # line format: '- PID — ...' -> extract pid and rest
        l = line.lstrip('- ').strip()
        parts = l.split(' — ', 1)
        pid = parts[0]
        rest = parts[1] if len(parts) > 1 else ''
        prepared.append((pid, rest))

    # Store pagination and return first page
    header = f"Top {min(n_req, len(lines))} projects by approved budget for {target}:"
    _set_pagination("contractor", {"contractor": target}, prepared, f"for {target}")
    page_n = min(n_req, 5)
    _PAGINATION_STATE['offset'] = page_n
    first_chunk = prepared[:page_n]
    first_lines = [f"- {pid} — {rest}" for pid, rest in first_chunk]
    tail = "" if len(prepared) <= page_n else "\n\nWould you like 5 more projects?"
    return header + "\n" + ("\n".join(first_lines) if first_lines else "No projects found.") + tail


def top_projects_by_contractor_budget(contractor: str, top_n: int = 5) -> str:
    """NL-triggered version: ask for top-N projects by budget for a contractor.

    Uses phrasing that routes through agent3's parser path for
    top_projects_by_contractor_budget.
    """
    _require_df()
    n = int(top_n or 5)
    q = f"list the top {n} with the highest approved budget for {contractor}"
    return _agent_answer(q)


def highest_budget_for_contractor(contractor: str) -> str:
    """Return the highest approved budget for a given contractor with project ID.

    Output format: "<Project ID> — <Approved Budget>". Scope is only the specified
    contractor. If multiple share the same max value, the first encountered is shown.
    """
    df = _require_df()
    if not contractor or not str(contractor).strip():
        return "Please provide a contractor name."

    contractor_col = find_column(df, [
        "contractor",
        "contractor_name",
        "winning_contractor",
    ])
    budget_col = find_column(df, [
        "approved_budget_num",
        "approved_budget_for_contract",
        "approvedbudgetforcontract",
        "approved_budget",
        "budget",
        "contractcost",
        "approved budget for contract",
    ])
    if contractor_col is None or budget_col is None:
        return "I couldn't find the required columns (contractor/budget)."

    series = df[contractor_col].astype(str)
    target = str(contractor).strip()
    exact_mask = series.str.strip().str.casefold() == target.casefold()
    mask = exact_mask | series.str.casefold().str.contains(target.casefold(), na=False)
    sub = df[mask].copy()
    if sub.empty:
        return f"I couldn't find any projects for contractor {target}."

    sub[budget_col] = pd.to_numeric(sub[budget_col], errors="coerce")
    sub = sub.dropna(subset=[budget_col])
    if sub.empty:
        return f"No projects with a valid approved budget for contractor {target}."

    row = sub.loc[sub[budget_col].idxmax()]
    pid_col = find_project_id_column(sub)
    pid = row.get(pid_col, "N/A")
    amt = float(row[budget_col]) if pd.notna(row[budget_col]) else None
    if amt is None:
        return f"{pid} — Amount not available"
    return f"{pid} — ₱{amt:,.2f}"


# ----------------------- Municipality comparison -----------------------------

def municipality_max_total(municipality: Optional[str] = None,
                           province: Optional[str] = None,
                           region: Optional[str] = None) -> str:
    """Which municipality (in a region/area) has the highest total budget."""
    _require_df()
    where = []
    if municipality:
        where.append(municipality)
    if province:
        where.append(province)
    if region:
        where.append(_fmt_place_token(region))
    place = f" in {' ,'.join(where)}" if where else ""
    q = f"which municipality has highest total budget{place}"
    return _agent_answer(q)


# ----------------------- Location-based listing ------------------------------

def top_projects_by_location_budget(municipality: Optional[str] = None,
                                    province: Optional[str] = None,
                                    region: Optional[str] = None,
                                    top_n: Optional[int] = None) -> str:
    """List top projects by approved budget in a place.

    If top_n is None or <=5, returns the default top 5 (and asks for more).
    If top_n > 5, uses phrasing that requests all N.
    """
    _require_df()
    where = []
    if municipality:
        where.append(municipality)
    if province:
        where.append(province)
    if region:
        where.append(_fmt_place_token(region))
    place = ' ,'.join(where)
    if not place:
        return "Please provide a municipality, province, or region."
    if not top_n or int(top_n) <= 5:
        q = f"list all of the projects in {place}"
    else:
        q = f"give me all {int(top_n)} projects in {place}"
    return _agent_answer(q)


def more_projects(count: Optional[int] = None) -> str:
    """Return the next batch of projects from the last location listing.

    If count is None, behaves like the user said 'yes'. Otherwise phrases as
    'N more projects'.
    """
    _require_df()
    if count is None:
        return _agent_answer("yes")
    return _agent_answer(f"{int(count)} more projects")


# ----------------------- Project ID field helpers ----------------------------

def project_contractor(project_id: str) -> str:
    _require_df()
    return _agent_answer(f"who is the contractor of {project_id}")


def project_budget(project_id: str) -> str:
    _require_df()
    return _agent_answer(f"what is the budget of {project_id}")


def project_start_date(project_id: str) -> str:
    _require_df()
    return _agent_answer(f"when did {project_id} start")


def project_completion_date(project_id: str) -> str:
    _require_df()
    return _agent_answer(f"when was {project_id} completed")


def project_location(project_id: str) -> str:
    _require_df()
    return _agent_answer(f"what is the location of {project_id}")


def tools_list() -> List[Any]:
    """Return the list of callable tools to register with Gemini.

    These are simple wrappers around Agent 3 and are intentionally conservative.
    """
    return [
        answer_dpwh_question,
        lookup_project,
        # Totals and counts
        count_projects,
        total_approved_budget,
        budget_trend_by_year,
        municipality_max_total,
        # Budget extrema
        highest_budget,
        lowest_budget,
        # Contractor rankings and lists
        contractor_max_total_budget,
        contractor_max_count,
        top_projects_for_contractor,
        top_projects_by_contractor_budget,
        highest_budget_for_contractor,
        top_contractors_by_count,
        top_contractors_by_budget,
        top_contractors,
        # Location listings & pagination
        top_projects_by_location_budget,
        more_projects,
        # Project field helpers
        project_contractor,
        project_budget,
        project_start_date,
        project_completion_date,
        project_location,
    ]
