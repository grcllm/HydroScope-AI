from __future__ import annotations

from typing import Optional
import pandas as pd

from dpwh_web_agent.dpwh_agent.utils.schema import find_column


def find_project_id_column(df: pd.DataFrame) -> Optional[str]:
    """Find the most likely project ID column name in a DataFrame.

    Keeps the same heuristic used previously in agent3_answer.py so callers
    can rely on consistent behavior.
    """
    if df is None:
        return None

    possible_names = [
        'projectid', 'project_id', 'ProjectID', 'Project_ID',
        'project_number', 'projectnumber', 'id', 'ID'
    ]

    for name in possible_names:
        if name in df.columns:
            return name

    # Fallback: pick a column containing both 'project' and 'id'
    for col in df.columns:
        if 'project' in col.lower() and 'id' in col.lower():
            return col

    # Last resort: first column
    return df.columns[0] if len(df.columns) > 0 else None


def resolve_budget_column(df: pd.DataFrame) -> Optional[str]:
    """Return a best-effort budget column name or None."""
    return find_column(df, [
        'approved_budget_num', 'approved_budget_for_contract', 'approvedbudgetforcontract',
        'approved_budget', 'budget', 'contractcost', 'approved budget for contract'
    ])


def resolve_contractor_column(df: pd.DataFrame) -> Optional[str]:
    return find_column(df, ['contractor', 'contractor_name', 'winning_contractor'])


def format_money(value: float) -> str:
    try:
        return f"₱{float(value):,.2f}"
    except Exception:
        return str(value)
