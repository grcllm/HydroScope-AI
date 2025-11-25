"""Callable tools exposed to the Gemini SDK.

Design goals:
- Keep a single source of truth for analytics by delegating to Agent 3
- Provide both a generic question-answer tool and a few structured helpers
- Be scalable: adding granular tools later won't break existing ones
- Support conversation context for follow-up questions
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import threading
import re

import pandas as pd

from ..core.agents.analytics_engine import (
    agent3_run,
    find_project_id_column,
    simple_parse,
)
from ..core.agents.analytics_engine import _set_pagination, _PAGINATION_STATE
from ..core.utils.schema import find_column
from ..core.utils.context_db import (
    get_or_create_session,
    log_conversation,
    update_context,
    get_context,
    clear_context,
)
from ..core.utils.context_extractor import (
    extract_context_from_question,
    apply_context_to_question,
    should_clear_context,
    get_contextual_summary,
)


_DF_LOCK = threading.Lock()
_CURRENT_DF: Optional[pd.DataFrame] = None
_CURRENT_SESSION: Optional[str] = None


def set_dataframe(df: pd.DataFrame) -> None:
    """Set the current dataframe used by tool functions."""
    global _CURRENT_DF
    with _DF_LOCK:
        _CURRENT_DF = df


def set_session(session_id: str) -> None:
    """Set the current session ID for context tracking."""
    global _CURRENT_SESSION
    _CURRENT_SESSION = get_or_create_session(session_id)


def get_session() -> str:
    """Get or create the current session ID."""
    global _CURRENT_SESSION
    if _CURRENT_SESSION is None:
        _CURRENT_SESSION = get_or_create_session()
    return _CURRENT_SESSION


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


def _parse_years_input(year_str: str) -> Optional[List[int]]:
    """Parse a year or a small range/list string into a list of years.

    Examples supported:
    - "2020" -> [2020]
    - "2020-2022" or "2020 to 2022" -> [2020,2021,2022]
    - "2020,2021,2022" -> [2020,2021,2022]
    - "20-22" -> [2020,2021,2022]
    Returns None if no parseable numbers found.
    """
    if not year_str:
        return None
    s = str(year_str).strip()
    if not s:
        return None

    s_clean = s.replace('\u2013', '-').replace('\u2014', '-')  # normalize dashes

    # Range like 2020-2022 or 20-22 or "2020 to 2022"
    m = re.search(r"(\d{2,4})\s*(?:-|–|—|to)\s*(\d{2,4})", s_clean, flags=re.IGNORECASE)
    if m:
        a = int(m.group(1))
        b = int(m.group(2))
        # Normalize two-digit years to 2000s
        if a < 100:
            a += 2000
        if b < 100:
            # keep same century as a
            b += (a // 100) * 100
        start, end = min(a, b), max(a, b)
        return list(range(start, end + 1))

    # Otherwise collect any 2-4 digit numbers (comma separated or space separated)
    nums = re.findall(r"\d{2,4}", s_clean)
    years: List[int] = []
    for n in nums:
        y = int(n)
        if y < 100:
            y += 2000
        years.append(y)
    if years:
        return sorted(list(dict.fromkeys(years)))
    return None


def answer_dpwh_question(question: str, session_id: Optional[str] = None) -> str:
    """Answer a natural language question about DPWH flood control projects.
    
    Supports conversation context - remembers previous questions about locations,
    contractors, etc., so users can ask follow-up questions naturally.

    Args:
        question: The user's question in natural language.
        session_id: Optional session ID for context tracking. If None, uses/creates default session.

    Returns:
        A concise, factual answer computed from the dataset. Use pesos (₱) for money.
    """
    # Get or create session
    if session_id:
        set_session(session_id)
    sid = get_session()
    
    # Handle greetings
    q_lower = question.lower().strip()
    greetings = ['hello', 'hi', 'hey', 'greetings', 'good morning', 'good afternoon', 'good evening']
    if any(q_lower.startswith(g) for g in greetings) or q_lower in greetings:
        response = (
            "👋 Hi! I'm your DPWH Flood Control Analytics Agent.\n\n"
            "I can help you analyze data about Department of Public Works and Highways (DPWH) flood control projects across the Philippines.\n\n"
            "Ask me about:\n"
            "• Project counts and locations\n"
            "• Budget totals and trends\n"
            "• Top contractors\n"
            "• Specific project details\n\n"
            "Type 'what questions can you answer?' to see examples!"
        )
        log_conversation(sid, question, response)
        return response
    
    # Handle help/capability requests
    help_patterns = [
        'what questions can you answer',
        'what can you do',
        'what can i ask',
        'help',
        'capabilities',
        'what are you capable of',
        'show me examples',
        'sample questions'
    ]
    if any(pattern in q_lower for pattern in help_patterns):
        response = (
            "📊 Here are some questions I can answer:\n\n"
            "PROJECT COUNTS:\n"
            "• How many flood control projects are there?\n"
            "• How many projects are in Region III?\n"
            "• Count projects in Quezon City\n\n"
            "BUDGET ANALYTICS:\n"
            "• What is the total budget for all projects?\n"
            "• Show budget trend by year\n"
            "• What's the average project budget?\n\n"
            "CONTRACTOR RANKINGS:\n"
            "• Which contractor has the highest total budget?\n"
            "• List top 10 contractors by project count\n"
            "• Find projects by contractor name [NAME]\n\n"
            "PROJECT DETAILS:\n"
            "• Show me the top 5 projects by budget\n"
            "• Find projects in Metro Manila\n"
            "• What are the largest projects?\n\n"
            "💡 TIP: I remember context! Ask about a city, then follow up with 'What's the total budget?' "
            "and I'll know you mean that city.\n\n"
            "Just ask naturally - I'll understand!"
        )
        log_conversation(sid, question, response)
        return response
    
    # Check if we should clear context (new topic)
    if should_clear_context(question):
        clear_context(sid)
    
    # Get stored context
    context = get_context(sid)
    
    # Apply context to question if needed
    original_question = question
    if context:
        question = apply_context_to_question(question, context)
        # If question was enhanced, add a note about using context
        if question != original_question:
            context_summary = get_contextual_summary(context)
            # We'll add this to the response later
    
    # Get the answer
    df = _require_df()
    response = _agent_answer(question)
    
    # Extract and store context from this question
    try:
        parsed = simple_parse(question, df)
        extracted_context = extract_context_from_question(question, parsed, df)
        
        # Special handling for project lookups - extract contractor from response
        if parsed.get('action') in ['lookup', 'contractor_lookup'] and 'contractor' not in extracted_context:
            # Try to extract contractor name from the response
            contractor_match = re.search(r'contractor.*?is\s+([A-Z][A-Z\s/\-&.,()]+?)(?:\.|$)', response, re.IGNORECASE | re.MULTILINE)
            if contractor_match:
                contractor_name = contractor_match.group(1).strip()
                # Clean up common trailing patterns
                contractor_name = re.sub(r'\s*\(FORMERLY:.*?\)\s*$', '', contractor_name, flags=re.IGNORECASE).strip()
                extracted_context['contractor'] = contractor_name
        
        # Extract project ID from responses (for follow-up questions like "who is the contractor")
        if 'project_id' not in extracted_context:
            # Look for patterns like "Project ID P00620087LZ" or "project with the highest budget is Project ID P00620087LZ"
            project_id_match = re.search(r'[Pp]roject\s+(?:ID\s+)?([A-Z0-9]{6,20})\b', response)
            if project_id_match:
                extracted_context['last_project_id'] = project_id_match.group(1)
        
        if extracted_context:
            update_context(sid, extracted_context)
            # Log conversation with extracted context
            log_conversation(sid, original_question, response, extracted_context)
        else:
            log_conversation(sid, original_question, response)
    except Exception:
        # If context extraction fails, still log the conversation
        log_conversation(sid, original_question, response)
    
    return response


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


def count_projects_in_year(year: Optional[str] = None) -> str:
    """Return the number of projects for a specific funding year.

    Args:
        year: Year as a string (e.g. "2020"). If omitted, asks for a year.

    Returns:
        A short human-readable string with the project count for that year.
    """
    df = _require_df()
    if year is None or str(year).strip() == "":
        return "Please provide a funding year (e.g., 2020)."

    # Find a likely year column — try several common variants for robustness
    year_col = find_column(df, [
        "funding_year",
        "funding year",
        "fundingyear",
        "year",
        "fy",
        "funding_years",
    ])
    if year_col is None:
        # Fall back to agent parsing which may understand date-like columns
        return _agent_answer(f"how many projects in the year {year}")

    # Parse the input which may be a single year, a list, or a range
    years = _parse_years_input(str(year))
    if not years:
        return "Please provide a funding year (e.g., 2020) or a range like 2020-2022."

    # Coerce year column to numeric once
    series = pd.to_numeric(df[year_col], errors="coerce")

    if len(years) == 1:
        y = years[0]
        count = int((series == y).sum())
        if count == 0:
            return _agent_answer(f"how many projects in the year {y}")
        return f"There {'is' if count==1 else 'are'} {count} project{'' if count==1 else 's'} in the year {y}."

    # Multiple years requested — compute per-year counts and total
    per_year: Dict[int, int] = {}
    total = 0
    for y in years:
        c = int((series == y).sum())
        per_year[y] = c
        total += c

    # If everything is zero, allow the agent a chance to answer more flexibly
    if total == 0:
        return _agent_answer(f"how many projects in the years {str(year)}")

    # Build a compact human-readable response
    years_sorted = sorted(per_year.keys())
    # compact range display if contiguous
    if years_sorted == list(range(years_sorted[0], years_sorted[-1] + 1)) and len(years_sorted) > 1:
        range_label = f"{years_sorted[0]}–{years_sorted[-1]}"
    else:
        range_label = ", ".join(str(y) for y in years_sorted)

    details = ", ".join(f"{y}: {per_year[y]}" for y in years_sorted)
    plural = 'are' if total != 1 else 'is'
    proj_word = 'projects' if total != 1 else 'project'
    return f"There {plural} {total} {proj_word} in {range_label} ({details})."


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
        count_projects_in_year,
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
