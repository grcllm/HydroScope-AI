import os
import re
from pathlib import Path
import subprocess
import pandas as pd
from tenacity import retry, wait_exponential, stop_after_attempt

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Load Kaggle values from .env
KAGGLE_FILE = os.environ.get("KAGGLE_FILE", "dpwh_flood_control_projects.csv")
DEFAULT_OUT = DATA_DIR / KAGGLE_FILE

def normalize_column(col: str) -> str:
    """
    Convert column names to snake_case (handles CamelCase + spaces).
    Example: "ApprovedBudgetForContract" -> "approved_budget_for_contract"
    """
    col = re.sub(r'(?<!^)(?=[A-Z])', '_', col).lower()
    return col.strip().replace(" ", "_")

@retry(wait=wait_exponential(min=1, max=30), stop=stop_after_attempt(4))
def fetch_from_kaggle(dataset_slug: str, file_name: str = None) -> Path:
    """
    Uses the Kaggle CLI to download a dataset CSV.
    """
    file_name = file_name or KAGGLE_FILE
    out_path = DATA_DIR / file_name

    cmd = [
        "kaggle", "datasets", "download", "-d", dataset_slug,
        "-f", file_name, "-p", str(DATA_DIR), "--unzip", "--force"
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)

    if not out_path.exists():
        raise FileNotFoundError(f"Downloaded file not found: {out_path}")

    return out_path

def agent1_run(dataset_slug: str = None, file_name: str = None):
    """
    Fetch fresh data from Kaggle and return local filepath.
    """
    dataset_slug = dataset_slug or os.environ["KAGGLE_SLUG"]
    file_name = file_name or KAGGLE_FILE

    path = fetch_from_kaggle(dataset_slug, file_name)

    # Load dataset
    df = pd.read_csv(path, nrows=5)

    # Normalize column names
    df.columns = [normalize_column(c) for c in df.columns]

    # Required schema (mapped to Kaggle’s actual column names)
    required_cols = {
        "region",
        "province",
        "legislative_district",
        "municipality",
        "project_id",
        "type_of_work",                  # Kaggle uses this
        "funding_year",
        "approved_budget_for_contract",  # Kaggle uses this
        "start_date",
        "actual_completion_date"         # Kaggle uses this
    }

    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Dataset is missing required columns: {missing}")

    return path
