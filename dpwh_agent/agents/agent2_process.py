import os
from pathlib import Path
import pandas as pd
from dpwh_agent.utils.schema import normalize_column

def parse_currency(x):
    """Parse currency strings like '₱1,234,567.89', '(1,000.00)', 'PHP 2,000' to float.
    Returns None if not parseable."""
    if pd.isna(x):
        return None
    s = str(x).strip()
    if not s:
        return None
    neg = False
    # Parentheses denote negative
    if s.startswith('(') and s.endswith(')'):
        neg = True
        s = s[1:-1]
    # Remove common currency tokens and separators
    s = s.replace(',', '')
    s = s.replace('₱', '').replace('PHP', '').replace('php', '').replace('$', '').strip()
    # Keep only digits and dot
    m = pd.Series([s]).str.extract(r'([-+]?\d*\.?\d+)')
    try:
        val = float(m.iloc[0, 0]) if pd.notna(m.iloc[0, 0]) else None
        if val is not None and neg:
            val = -val
        return val
    except Exception:
        return None

def agent2_run(filepath: Path):
    df = pd.read_csv(filepath, dtype=str, low_memory=False)

    # Columns are already normalized by agent1, so just strip/lowercase
    # Normalize column names robustly (idempotent)
    df.columns = [normalize_column(c) for c in df.columns]

    # Basic string cleanup: trim whitespace and stray quotes on all object columns
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip().str.strip('"').str.strip()

    # Region cleaning
    if "region" in df.columns:
        df["region"] = df["region"].str.strip().str.title()

    # Map normalized column names → expected names
    rename_map = {
        "approved_budget_for_contract": "approved_budget",
        "start_date": "start_date",
        "actual_completion_date": "completion_date",
        "project_id": "project_id",
        "type_of_work": "type_of_construction",
        "legislative_district": "legislative_district",
    }
    df.rename(columns={k:v for k,v in rename_map.items() if k in df.columns}, inplace=True)

    # Parse numeric budget
    if "approved_budget" in df.columns:
        df["approved_budget_num"] = df["approved_budget"].apply(parse_currency)

    # Fix misaligned rows where project_id content ended up in municipality (observed in NCR rows)
    if "project_id" in df.columns and "municipality" in df.columns:
        # Heuristic: project IDs are compact codes (letters/digits/hyphens), no spaces; municipalities usually contain spaces or commas
        id_like = df["project_id"].astype(str).str.match(r"^[A-Za-z][A-Za-z0-9\-]{5,}$", na=False)
        muni_looks_id = df["municipality"].astype(str).str.match(r"^[A-Za-z][A-Za-z0-9\-]{5,}$", na=False)
        swap_mask = (~id_like) & (muni_looks_id)
        if swap_mask.any():
            tmp = df.loc[swap_mask, "project_id"].copy()
            df.loc[swap_mask, "project_id"] = df.loc[swap_mask, "municipality"].values
            df.loc[swap_mask, "municipality"] = tmp.values

    # Parse dates
    for col in ["start_date", "completion_date"]:
        if col in df.columns:
            df[col + "_parsed"] = pd.to_datetime(df[col], errors="coerce")

    # Derived year fields
    if "start_date_parsed" in df.columns:
        df["year_start"] = pd.to_datetime(df["start_date_parsed"], errors="coerce").dt.year
    if "completion_date_parsed" in df.columns:
        df["year_completion"] = pd.to_datetime(df["completion_date_parsed"], errors="coerce").dt.year
    if "funding_year" in df.columns:
        df["funding_year_num"] = pd.to_numeric(df["funding_year"], errors="coerce")

    # Drop duplicates by project_id if exists
    if "project_id" in df.columns:
        df = df.drop_duplicates(subset=["project_id"])

    # Optional Parquet snapshot for faster re-loads
    try:
        data_dir = Path(os.environ.get("DATA_DIR", "./data"))
        data_dir.mkdir(parents=True, exist_ok=True)
        parquet_path = data_dir / "processed_dpwh_projects.parquet"
        # Write without index; requires pyarrow or fastparquet
        df.to_parquet(parquet_path, index=False)
    except Exception:
        # If pyarrow is not installed or any failure, skip silently
        pass

    return df