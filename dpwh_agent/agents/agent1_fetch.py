import os
import re
from pathlib import Path
import pandas as pd

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Use cleaned file from local data directory
KAGGLE_FILE = os.environ.get("KAGGLE_FILE", "cleaned_dpwh_flood_control_projects.csv")
DEFAULT_OUT = DATA_DIR / KAGGLE_FILE

def normalize_column(col: str) -> str:
    """
    Convert column names to snake_case (handles CamelCase + spaces).
    Example: "ApprovedBudgetForContract" -> "approved_budget_for_contract"
    """
    col = re.sub(r'(?<!^)(?=[A-Z])', '_', col).lower()
    return col.strip().replace(" ", "_")

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
    file_name = file_name or KAGGLE_FILE
    path = DATA_DIR / file_name

    # Check if file exists
    if not path.exists():
        raise FileNotFoundError(
            f"Dataset file not found: {path}\n"
            f"Please ensure '{file_name}' exists in the '{DATA_DIR}' directory."
        )

    # Load dataset
    df = pd.read_csv(path)

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
            df.to_csv(path, index=False)

    return path


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