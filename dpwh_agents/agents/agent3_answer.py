from typing import Dict
import pandas as pd
import re

# Mapping digits → roman numerals for regions
ROMAN_MAP = {
    "1": "i", "2": "ii", "3": "iii", "4": "iv", "5": "v",
    "6": "vi", "7": "vii", "8": "viii", "9": "ix", "10": "x",
    "11": "xi", "12": "xii", "13": "xiii", "14": "xiv", "15": "xv",
    "16": "xvi", "17": "xvii", "18": "xviii"
}

def detect_filters(prompt: str, df: pd.DataFrame) -> Dict[str, str]:
    """Detect filters (region/province/municipality/island/project_location) from user prompt."""
    p = prompt.lower()
    filters = {}

    # Region pattern
    m = re.search(r"region\s*([0-9ivx]+)", p)
    if m:
        filters["region"] = m.group(1)
        return filters

    # Island keywords
    for island in ["luzon", "visayas", "mindanao"]:
        if island in p and "mainisland" in df.columns:
            filters["mainisland"] = island
            return filters

    # Municipality + province
    if "municipality" in df.columns:
        for muni in df["municipality"].dropna().unique():
            if isinstance(muni, str) and muni.lower() in p:
                filters["municipality"] = muni
                if "province" in df.columns:
                    for prov in df["province"].dropna().unique():
                        if isinstance(prov, str) and prov.lower() in p:
                            filters["province"] = prov
                return filters

    # Province (only if no municipality found)
    if not filters and "province" in df.columns:
        for prov in df["province"].dropna().unique():
            if isinstance(prov, str) and prov.lower() in p:
                filters["province"] = prov
                return filters

    # Fallback: project_location catch-all
    if "project_location" in df.columns:
        for loc in df["project_location"].dropna().unique():
            if isinstance(loc, str) and loc.lower() in p:
                filters["project_location"] = loc
                return filters

    return filters


def simple_parse(prompt: str, df: pd.DataFrame) -> dict:
    p = prompt.lower()

    # 🔎 PRIORITY ORDER: Check statistical queries FIRST before project ID detection

    # Highest budget pattern - CHECK FIRST
    if "highest approved budget" in p or "max approved budget" in p or "highest budget" in p:
        filters = detect_filters(prompt, df)
        return {"action": "max", "column": "approved_budget_num", "filters": filters}

    # Total budget pattern - CHECK SECOND  
    if "total budget" in p or "sum" in p or "overall budget" in p:
        filters = detect_filters(prompt, df)
        return {"action": "sum", "column": "approved_budget_num", "filters": filters}

    # Count pattern - CHECK THIRD
    if "how many" in p or p.startswith("how many"):
        filters = detect_filters(prompt, df)

        # 🔥 Always capture "in X" as filter (even if detect_filters misses it)
        if not filters:
            m2 = re.search(r"in\s+([a-z\s\-]+)$", p)
            if m2:
                place = m2.group(1).strip()
                filters = {"project_location": place}

        return {"action": "count", "filters": filters, "column": None}

    # NOW check for project ID patterns (after statistical queries)
    
    # First check for explicit "project id" pattern
    m = re.search(r"(project\s*id|projectid)\s*([a-z0-9\-]+)", p)
    if m:
        return {"action": "lookup", "filters": {"project_id": m.group(2)}, "column": None}
    
    # Check for questions about specific project details (e.g., "who is the contractor of P00740613LZ")
    detail_match = re.search(r"(who is the contractor|what is the budget|what is the cost|who is the consultant|what is the location|when did.*start|when.*complet|what is the status).*?([a-z][a-z0-9\-]{5,19})(?:\s|$)", p)
    if detail_match:
        return {"action": "lookup", "filters": {"project_id": detail_match.group(2)}, "column": None}
    
    # Check if the entire prompt looks like a project ID (common patterns)
    project_id_pattern = re.match(r"^([a-z0-9\-]{6,20})$", p.strip())
    if project_id_pattern:
        return {"action": "lookup", "filters": {"project_id": project_id_pattern.group(1)}, "column": None}

    return {"action": "unknown", "filters": {}}


def apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    out = df
    if not filters:
        return out

    for k, v in filters.items():
        if v is None:
            continue

        if k == "region" and "region" in out.columns:
            pat = v.lower()
            patterns = [pat]
            if pat.isdigit() and pat in ROMAN_MAP:
                patterns.append(ROMAN_MAP[pat])
            mask = False
            for p in patterns:
                mask = mask | out["region"].astype(str).str.lower().str.contains(p, na=False)
            out = out[mask]

        elif k in out.columns and pd.api.types.is_string_dtype(out[k]):
            # ✅ exact match instead of substring
            out = out[out[k].astype(str).str.strip().str.lower() == v.lower()]

    return out


def find_project_id_column(df: pd.DataFrame) -> str:
    """Find the correct project ID column name in the DataFrame."""
    possible_names = [
        'projectid', 'project_id', 'ProjectID', 'Project_ID', 
        'project_number', 'projectnumber', 'id', 'ID'
    ]
    
    for name in possible_names:
        if name in df.columns:
            return name
    
    # If none found, return the first column that might contain project IDs
    for col in df.columns:
        if 'project' in col.lower() and 'id' in col.lower():
            return col
    
    # Last resort: return first column
    return df.columns[0] if len(df.columns) > 0 else None


def agent3_run(question: str, df: pd.DataFrame) -> str:
    parsed = simple_parse(question, df)
    action = parsed["action"]
    filters = parsed["filters"]

    sub = apply_filters(df, filters)

    if action == "lookup" and "project_id" in filters:
        pid = filters["project_id"].lower()
        
        # Find the correct project ID column
        project_id_col = find_project_id_column(df)
        
        if project_id_col is None:
            return "I couldn't find a project ID column in the dataset."
        
        # Search for the project
        project = df[df[project_id_col].astype(str).str.lower() == pid]

        if project.empty:
            return f"I couldn't find any project with ID {pid.upper()}."

        row = project.iloc[0]

        # Create a comprehensive project information display
        result = [f"=== PROJECT INFORMATION ==="]
        result.append(f"Project ID: {pid.upper()}")
        
        # Define field mappings with multiple possible column names
        field_mappings = {
            "Project Title": ['project_title', 'title', 'project_name', 'name', 'projecttitle'],
            "Description": ['description', 'project_description', 'scope', 'project_scope'],
            "Approved Budget": ['approvedbudgetforcontract', 'approved_budget', 'budget', 'approved_budget_num'],
            "Contract Amount": ['contract_amount', 'contractamount', 'contract_cost'],
            "Location": ['legislativedistrict', 'location', 'project_location', 'district'],
            "Municipality": ['municipality', 'city', 'municipal'],
            "Province": ['province', 'provincial'],
            "Region": ['region', 'regions'],
            "Contractor": ['contractor', 'contractor_name', 'contractorname', 'winning_contractor'],
            "Consultant": ['consultant', 'consultant_name', 'consultantname'],
            "Start Date": ['startdate', 'start_date', 'datestarted', 'commencement_date', 'contract_start'],
            "Target Completion": ['targetcompletiondate', 'target_completion', 'planned_completion', 'contract_end'],
            "Actual Completion": ['actualcompletiondate', 'actual_completion', 'datecompleted', 'completion_date'],
            "Project Status": ['status', 'project_status', 'current_status'],
            "Progress": ['progress', 'percent_complete', 'completion_percentage'],
            "Fund Source": ['fund_source', 'funding_source', 'source_of_fund'],
            "Implementing Office": ['implementing_office', 'office', 'implementing_unit'],
            "Project Type": ['project_type', 'type', 'category']
        }
        
        # Process each field
        for display_name, possible_columns in field_mappings.items():
            value = None
            
            # Find the first matching column
            for col in possible_columns:
                if col in df.columns:
                    value = row.get(col)
                    break
            
            # Format and clean the value
            if value is not None and pd.notna(value) and str(value).strip():
                # Special formatting for budget/monetary values
                if display_name in ["Approved Budget", "Contract Amount"] and isinstance(value, (int, float)):
                    formatted_value = f"₱{value:,.2f}"
                else:
                    formatted_value = str(value).strip()
                
                result.append(f"{display_name}: {formatted_value}")
        
        # Add any additional columns that might contain useful information
        result.append("\n=== ADDITIONAL INFORMATION ===")
        
        # Get columns that weren't covered by the main mappings
        covered_columns = set()
        for cols in field_mappings.values():
            covered_columns.update(cols)
        covered_columns.add(project_id_col)  # Also exclude the project ID column
        
        additional_info_added = False
        for col in df.columns:
            if col.lower() not in covered_columns and pd.notna(row.get(col)) and str(row.get(col)).strip():
                # Clean up column name for display
                display_col = col.replace('_', ' ').title()
                value = str(row.get(col)).strip()
                result.append(f"{display_col}: {value}")
                additional_info_added = True
        
        if not additional_info_added:
            result.append("No additional information available")
        
        return "\n".join(result)

    # If filters exist but no results → not found
    if filters and sub.empty:
        place = list(filters.values())[0]
        return f"I couldn't find any flood control projects in {place.title()}."

    # Count
    if action == "count":
        n = len(sub)
        if filters:
            place = list(filters.values())[0]
            return f"There are {n} flood control projects in {place.title()}."
        return f"There are {n} flood control projects in the dataset."

    # Sum budget
    if action == "sum" and parsed["column"]:
        # Find the correct budget column
        budget_cols = ['approved_budget_num', 'approvedbudgetforcontract', 'approved_budget', 'budget']
        budget_col = None
        for col in budget_cols:
            if col in sub.columns:
                budget_col = col
                break
        
        if budget_col is None:
            return "I couldn't find a budget column in the dataset."
        
        total = sub[budget_col].sum()
        if filters:
            place = list(filters.values())[0]
            return f"The total approved budget in {place.title()} is ₱{total:,.2f}."
        return f"The total approved budget for all projects is ₱{total:,.2f}."

    # Max budget
    if action == "max" and parsed["column"]:
        # Find the correct budget column
        budget_cols = ['approved_budget_num', 'approvedbudgetforcontract', 'approved_budget', 'budget']
        budget_col = None
        for col in budget_cols:
            if col in sub.columns:
                budget_col = col
                break
        
        if budget_col is None:
            return "I couldn't find a budget column in the dataset."
        
        if sub.empty:
            return "I couldn't find any projects matching that filter."

        row = sub.loc[sub[budget_col].idxmax()]

        # ✅ Use project_id if available
        project_id_col = find_project_id_column(sub)
        project_id = row[project_id_col] if project_id_col else "N/A"
        
        # Find location
        location_cols = ['project_location', 'location', 'municipality', 'province', 'legislativedistrict']
        location = "Unknown Location"
        for col in location_cols:
            if col in sub.columns and pd.notna(row.get(col)):
                location = row[col]
                break

        return (
            f"The project with the highest budget is Project ID {project_id} "
            f"in {location} with ₱{row[budget_col]:,.2f}."
        )

    return "Sorry — I couldn't understand the question."