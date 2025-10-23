from __future__ import annotations

import re
from functools import lru_cache
from typing import Iterable, Optional

import pandas as pd


def normalize_column(col: str) -> str:
    """
    Convert column names to snake_case (handles CamelCase + spaces and symbols).
    Example: "ApprovedBudgetForContract" -> "approved_budget_for_contract".
    """
    if not isinstance(col, str):
        return str(col)
    # Insert underscores before capitals, lowercase, replace non-word with underscore, collapse repeats
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", col).lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


def _norm_key(name: str) -> str:
    """Normalize a column or candidate name for case/format-insensitive matching."""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


@lru_cache(maxsize=1024)
def _norm_cols_tuple(cols_tuple: tuple[str, ...]) -> tuple[str, ...]:
    # trivial cache helper for column name tuples
    return cols_tuple


def find_column(df: pd.DataFrame, candidates: Iterable[str]) -> Optional[str]:
    """
    Return the first DataFrame column matching any candidate (case/format-insensitive),
    with fallbacks:
      1) exact normalized match
      2) substring match on normalized names
      3) fuzzy match via RapidFuzz if installed (score_cutoff 85)
    """
    if df is None or not hasattr(df, "columns") or len(df.columns) == 0:
        return None

    cols = list(df.columns)
    norm_map = {_norm_key(c): c for c in cols}

    # 1) exact normalized match
    for cand in candidates:
        key = _norm_key(cand)
        if key in norm_map:
            return norm_map[key]

    # 2) substring partial match
    for cand in candidates:
        key = _norm_key(cand)
        for col in cols:
            if key and key in _norm_key(col):
                return col

    # 3) fuzzy matching with RapidFuzz (optional)
    try:
        from rapidfuzz import process, fuzz  # type: ignore

        choices = {c: _norm_key(c) for c in cols}
        for cand in candidates:
            query = _norm_key(cand)
            if not query:
                continue
            match = process.extractOne(
                query,
                choices,
                scorer=fuzz.ratio,
                score_cutoff=85,
            )
            if match:
                # match is a tuple like (best_key, score, original_key_or_index)
                best_col = match[2] if len(match) > 2 else match[0]
                # best_col may be the original column name if provided as mapping
                return best_col
    except Exception:
        # RapidFuzz not installed or failed; ignore
        pass

    return None
