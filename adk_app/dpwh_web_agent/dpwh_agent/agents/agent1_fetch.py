import os
import re
from pathlib import Path
import pandas as pd
from dpwh_web_agent.dpwh_agent.utils.schema import normalize_column

# Prefer robust, location-independent dataset discovery. Avoid creating directories at import time.
KAGGLE_FILE = os.environ.get("KAGGLE_FILE", "normalized_dpwh_flood_control_projects.csv")

def _project_root() -> Path:
    """Return the repository root irrespective of current working directory.

    Walk up until we find a README.md; fallback to top-most parent.
    """
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "README.md").exists():
            return parent
    return p.parents[-1]

def _candidate_data_dirs() -> list[Path]:
    """Candidate directories to search for dataset files, in priority order."""
    root = _project_root()
    env_dir = os.environ.get("DATA_DIR")
    candidates = []
    if env_dir:
        candidates.append(Path(env_dir))
    # Common in-repo locations
    candidates.append(root / "data")
    # candidates.append(root / "dpwh_agent" / "data")
    # candidates.append(root / "adk_app" / "dpwh_web_agent" / "dpwh_agent" / "data")
    # De-duplicate while preserving order
    out: list[Path] = []
    seen = set()
    for p in candidates:
        rp = p.resolve()
        if rp not in seen:
            out.append(rp)
            seen.add(rp)
    return out

def _resolve_dataset_path(file_name: str | None) -> Path:
    """Resolve the dataset path by searching likely locations.

    Preference:
    1) Explicit file_name if provided and exists in any candidate dir
    2) cleaned_dpwh_flood_control_projects.csv if present
    3) dpwh_flood_control_projects.csv if present
    """
    preferred_names: list[str] = []
    if file_name:
        preferred_names.append(file_name)
    # Prefer a known-good normalized file first, then cleaned, then raw
    # This avoids parsing issues observed in some "cleaned_*" exports where quoting breaks rows.
    if "normalized_dpwh_flood_control_projects.csv" not in preferred_names:
        preferred_names.append("normalized_dpwh_flood_control_projects.csv")
    if "cleaned_dpwh_flood_control_projects.csv" not in preferred_names:
        preferred_names.append("cleaned_dpwh_flood_control_projects.csv")
    if "dpwh_flood_control_projects.csv" not in preferred_names:
        preferred_names.append("dpwh_flood_control_projects.csv")

    checked: list[Path] = []
    for d in _candidate_data_dirs():
        for name in preferred_names:
            p = (d / name).resolve()
            checked.append(p)
            if p.exists():
                return p

    # Nothing found; craft a helpful error message
    msg = [
        "Dataset file not found. Looked for the following files in candidate directories:",
    ]
    msg += [f"  - {str(p)}" for p in checked]
    msg.append(
        "You can fix this by: \n"
        "  • Placing the CSV in one of the above directories, or\n"
        "  • Setting DATA_DIR to the folder that contains the CSV, or\n"
        "  • Providing a file_name to agent1_run(file_name=...)."
    )
    raise FileNotFoundError("\n".join(msg))

def _robust_read_csv(path: Path) -> pd.DataFrame:
    """Robust CSV ingestion with reasonable fallbacks for encoding/bad lines."""
    # Try utf-8 first
    try:
        return pd.read_csv(path, engine="python", on_bad_lines="skip", encoding="utf-8")
    except Exception:
        # Fallback to latin-1
        return pd.read_csv(path, engine="python", on_bad_lines="skip", encoding="latin-1")

def clean_municipality_value(value):
    """
    Clean municipality format from 'CONNER (APAYAO)' to 'CONNER, APAYAO'
    """
    if pd.isna(value) or not isinstance(value, str):
        return value
    
    # Convert parentheses to comma format
    cleaned = re.sub(r'\s*\(([^)]+)\)\s*$', r', \1', value)
    return cleaned.strip()

def agent1_run(file_name: str = None) -> Path:
    """
    Load data from local data directory.
    
    Args:
        file_name: Name of the CSV file to load (default: cleaned_dpwh_flood_control_projects.csv)
    
    Returns:
        Path: Path to the loaded CSV file
    """
    # Resolve dataset path from multiple likely locations
    file_name = file_name or KAGGLE_FILE
    path = _resolve_dataset_path(file_name)

    # Load dataset robustly
    df = _robust_read_csv(path)

    # Normalize column names
    df.columns = [normalize_column(c) for c in df.columns]

    # Required schema
    required_cols = {
        "region",
        "province",
        "legislative_district",
        "municipality",
        "project_id",
        "type_of_work",
        "funding_year",
        "approved_budget_for_contract",
        "start_date",
        "actual_completion_date"
    }

    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Dataset is missing required columns: {missing}")
    
    # Apply municipality cleaning if needed
    if 'municipality' in df.columns:
        has_parentheses = df['municipality'].astype(str).str.contains(r'\(', na=False).any()
        if has_parentheses:
            df['municipality'] = df['municipality'].apply(clean_municipality_value)

    # If the discovered path is already a normalized file, return it directly to avoid re-writing
    if path.name.startswith("normalized_"):
        return path

    # Otherwise, write a normalized CSV alongside the discovered dataset file
    normalized_path = path.parent / ("normalized_" + path.name)
    normalized_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(normalized_path, index=False)
    return normalized_path


# For testing
if __name__ == "__main__":
    try:
        # Test the normalization function
        test_cols = [
            "ProjectID",
            "ApprovedBudgetForContract",
            "LegislativeDistrict",
            "StartDate",
            "ActualCompletionDate",
            "TypeOfWork",
            "FundingYear"
        ]
        
        print("Testing column normalization:")
        for col in test_cols:
            normalized = normalize_column(col)
            print(f"  {col:30} -> {normalized}")
        
        print("\nLoading dataset...")
        path = agent1_run()
        print(f"\nSuccess! Dataset ready at: {path}")
        
    except Exception as e:
        print(f"Error: {e}")
