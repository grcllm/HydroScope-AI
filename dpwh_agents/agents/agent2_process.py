import pandas as pd
from pathlib import Path

def parse_currency(x):
    if pd.isna(x): 
        return None
    s = str(x).replace(",", "").replace("₱", "").replace("$","").strip()
    try:
        return float(s)
    except:
        return None

def agent2_run(filepath: Path):
    df = pd.read_csv(filepath, dtype=str)

    # Normalize column names
    df.columns = df.columns.str.strip().str.lower()

    # Region cleaning
    if "region" in df.columns:
        df["region"] = df["region"].str.strip().str.title()

    # Map Kaggle schema → expected names
    rename_map = {
        "approvedbudgetforcontract": "approved_budget",
        "startdate": "start_date",
        "actualcompletiondate": "completion_date",
        "projectid": "project_id",
        "typeofwork": "type_of_construction",
        "legislativedistrict": "legislative_district",
    }
    df.rename(columns={k:v for k,v in rename_map.items() if k in df.columns}, inplace=True)

    # Parse numeric budget
    if "approved_budget" in df.columns:
        df["approved_budget_num"] = df["approved_budget"].apply(parse_currency)

    # Parse dates
    for col in ["start_date", "completion_date"]:
        if col in df.columns:
            df[col + "_parsed"] = pd.to_datetime(df[col], errors="coerce")

    # Drop duplicates by project_id if exists
    if "project_id" in df.columns:
        df = df.drop_duplicates(subset=["project_id"])

    return df
