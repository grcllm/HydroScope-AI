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

    # Enhanced Municipality detection with better matching
    if "municipality" in df.columns:
        municipalities = df["municipality"].dropna().unique()
        municipalities = [str(m).strip() for m in municipalities if pd.notna(m) and str(m).strip()]
        
        # Sort by length (longest first) to match more specific names first
        municipalities = sorted(municipalities, key=len, reverse=True)
        
        for muni in municipalities:
            muni_lower = muni.lower()
            # Check if municipality name appears in the prompt
            # Try exact word match first, then contains
            if (f" {muni_lower} " in f" {p} " or 
                p.startswith(muni_lower + " ") or 
                p.endswith(" " + muni_lower) or
                p == muni_lower or
                muni_lower in p):
                
                filters["municipality"] = muni
                
                # Also try to find province if mentioned
                if "province" in df.columns:
                    provinces = df["province"].dropna().unique()
                    provinces = [str(prov).strip() for prov in provinces if pd.notna(prov) and str(prov).strip()]
                    
                    for prov in provinces:
                        prov_lower = prov.lower()
                        if (f" {prov_lower} " in f" {p} " or 
                            p.startswith(prov_lower + " ") or 
                            p.endswith(" " + prov_lower) or
                            p == prov_lower or
                            prov_lower in p):
                            filters["province"] = prov
                            break
                return filters

    # Province (only if no municipality found)
    if not filters and "province" in df.columns:
        provinces = df["province"].dropna().unique()
        provinces = [str(p).strip() for p in provinces if pd.notna(p) and str(p).strip()]
        provinces = sorted(provinces, key=len, reverse=True)
        
        for prov in provinces:
            prov_lower = prov.lower()
            if (f" {prov_lower} " in f" {p} " or 
                p.startswith(prov_lower + " ") or 
                p.endswith(" " + prov_lower) or
                p == prov_lower or
                prov_lower in p):
                filters["province"] = prov
                return filters

    # Enhanced fallback: project_location catch-all with better matching
    if "project_location" in df.columns:
        locations = df["project_location"].dropna().unique()
        locations = [str(l).strip() for l in locations if pd.notna(l) and str(l).strip()]
        locations = sorted(locations, key=len, reverse=True)
        
        for loc in locations:
            loc_lower = loc.lower()
            if (f" {loc_lower} " in f" {p} " or 
                p.startswith(loc_lower + " ") or 
                p.endswith(" " + loc_lower) or
                p == loc_lower or
                loc_lower in p):
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

    # Count pattern - CHECK THIRD (Enhanced with contractor-specific logic)
    if "how many" in p or p.startswith("how many"):
        filters = detect_filters(prompt, df)

        # Special handling for contractor queries
        if "contractor" in p and not filters:
            # Try to extract contractor name from patterns like:
            # "how many projects contractor have [name]" or "how many projects does [name] have"
            contractor_patterns = [
                r"how many projects.*contractor.*have\s+(.+)$",
                r"how many projects.*does\s+(.+?)\s+have",
                r"how many projects.*by\s+(.+)$",
                r"how many projects.*from\s+(.+)$"
            ]
            
            for pattern in contractor_patterns:
                match = re.search(pattern, p)
                if match:
                    contractor_name = match.group(1).strip()
                    # Clean up the contractor name (remove common words)
                    contractor_name = re.sub(r'\b(contractor|company|corp|inc|ltd)\b', '', contractor_name, flags=re.IGNORECASE).strip()
                    
                    # Find matching contractor in the dataset
                    if "contractor" in df.columns:
                        contractors = df["contractor"].dropna().unique()
                        for contractor in contractors:
                            if pd.notna(contractor) and contractor_name.lower() in str(contractor).lower():
                                filters = {"contractor": contractor}
                                break
                    break

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
    
    # Check for specific field queries about projects (NEW FEATURE)
    # Who is the contractor of [project_id]
    contractor_match = re.search(r"who is the contractor.*?([a-z][a-z0-9\-]{5,19})(?:\s|$)", p)
    if contractor_match:
        return {"action": "contractor_lookup", "filters": {"project_id": contractor_match.group(1)}, "column": None}
    
    # What is the budget of [project_id] 
    budget_match = re.search(r"what is the budget.*?([a-z][a-z0-9\-]{5,19})(?:\s|$)", p)
    if budget_match:
        return {"action": "budget_lookup", "filters": {"project_id": budget_match.group(1)}, "column": None}
    
    # When did [project_id] start
    start_match = re.search(r"when did.*?([a-z][a-z0-9\-]{5,19}).*start", p)
    if start_match:
        return {"action": "start_date_lookup", "filters": {"project_id": start_match.group(1)}, "column": None}
    
    # When was [project_id] completed
    completion_match = re.search(r"when.*?([a-z][a-z0-9\-]{5,19}).*(complet|finish)", p)
    if completion_match:
        return {"action": "completion_lookup", "filters": {"project_id": completion_match.group(1)}, "column": None}
    
    # Where is [project_id] / What is the location of [project_id]
    location_match = re.search(r"(where is|what is the location).*?([a-z][a-z0-9\-]{5,19})(?:\s|$)", p)
    if location_match:
        return {"action": "location_lookup", "filters": {"project_id": location_match.group(2)}, "column": None}
    
    # Check for questions about specific project details (FALLBACK - full info)
    detail_match = re.search(r"(what is the cost|who is the consultant|what is the status).*?([a-z][a-z0-9\-]{5,19})(?:\s|$)", p)
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

        elif k in out.columns:
            if pd.api.types.is_string_dtype(out[k]):
                # Enhanced matching for string columns
                # First try exact match (case-insensitive)
                mask = out[k].astype(str).str.strip().str.lower() == v.lower()
                
                # If no exact matches, try contains match for partial matches
                if not mask.any():
                    mask = out[k].astype(str).str.lower().str.contains(v.lower(), na=False)
                
                out = out[mask]
            else:
                # For non-string columns, use exact match
                out = out[out[k] == v]

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

    # Handle specific field lookups (NEW FEATURE)
    if action in ["contractor_lookup", "budget_lookup", "start_date_lookup", "completion_lookup", "location_lookup"] and "project_id" in filters:
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

        # Return specific field information
        if action == "contractor_lookup":
            contractor_cols = ['contractor', 'contractor_name', 'contractorname', 'winning_contractor']
            for col in contractor_cols:
                if col in df.columns and pd.notna(row.get(col)) and str(row.get(col)).strip():
                    return f"The contractor for Project ID {pid.upper()} is {row[col]}."
            return f"Contractor information is not available for Project ID {pid.upper()}."
        
        elif action == "budget_lookup":
            budget_cols = ['approvedbudgetforcontract', 'approved_budget', 'budget', 'contractcost']
            for col in budget_cols:
                if col in df.columns and pd.notna(row.get(col)):
                    value = row[col]
                    if isinstance(value, (int, float)):
                        return f"The approved budget for Project ID {pid.upper()} is ₱{value:,.2f}."
                    else:
                        return f"The approved budget for Project ID {pid.upper()} is {value}."
            return f"Budget information is not available for Project ID {pid.upper()}."
        
        elif action == "start_date_lookup":
            start_cols = ['startdate', 'start_date', 'datestarted', 'commencement_date']
            for col in start_cols:
                if col in df.columns and pd.notna(row.get(col)) and str(row.get(col)).strip():
                    return f"Project ID {pid.upper()} started on {row[col]}."
            return f"Start date information is not available for Project ID {pid.upper()}."
        
        elif action == "completion_lookup":
            completion_cols = ['actualcompletiondate', 'actual_completion', 'datecompleted', 'completion_date']
            for col in completion_cols:
                if col in df.columns and pd.notna(row.get(col)) and str(row.get(col)).strip():
                    return f"Project ID {pid.upper()} was completed on {row[col]}."
            return f"Completion date information is not available for Project ID {pid.upper()}."
        
        elif action == "location_lookup":
            location_cols = ['legislativedistrict', 'location', 'project_location', 'municipality', 'province']
            location_info = []
            
            # Gather all available location information
            if 'municipality' in df.columns and pd.notna(row.get('municipality')) and str(row.get('municipality')).strip():
                location_info.append(f"Municipality: {row['municipality']}")
            if 'province' in df.columns and pd.notna(row.get('province')) and str(row.get('province')).strip():
                location_info.append(f"Province: {row['province']}")
            if 'legislativedistrict' in df.columns and pd.notna(row.get('legislativedistrict')) and str(row.get('legislativedistrict')).strip():
                location_info.append(f"Legislative District: {row['legislativedistrict']}")
            
            # If no specific location fields, try general location columns
            if not location_info:
                for col in location_cols:
                    if col in df.columns and pd.notna(row.get(col)) and str(row.get(col)).strip():
                        location_info.append(str(row[col]))
                        break
            
            if location_info:
                return f"Project ID {pid.upper()} is located in {', '.join(location_info)}."
            else:
                return f"Location information is not available for Project ID {pid.upper()}."

    # Handle full project information lookup
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
        # Create a more descriptive place name
        place_parts = []
        if "contractor" in filters:
            return f"I couldn't find any flood control projects for contractor {filters['contractor']}."
        if "municipality" in filters:
            place_parts.append(f"municipality of {filters['municipality']}")
        if "province" in filters:
            place_parts.append(f"province of {filters['province']}")
        if "region" in filters:
            place_parts.append(f"Region {filters['region']}")
        if "mainisland" in filters:
            place_parts.append(filters['mainisland'])
        if "project_location" in filters:
            place_parts.append(filters['project_location'])
        
        place_description = ", ".join(place_parts) if place_parts else list(filters.values())[0]
        return f"I couldn't find any flood control projects in {place_description.title()}."

    # Count
    if action == "count":
        n = len(sub)
        if filters:
            # Create a more descriptive place name
            place_parts = []
            if "contractor" in filters:
                place_parts.append(f"contractor {filters['contractor']}")
            if "municipality" in filters:
                place_parts.append(f"municipality of {filters['municipality']}")
            if "province" in filters:
                place_parts.append(f"province of {filters['province']}")
            if "region" in filters:
                place_parts.append(f"Region {filters['region']}")
            if "mainisland" in filters:
                place_parts.append(filters['mainisland'])
            if "project_location" in filters:
                place_parts.append(filters['project_location'])
            
            place_description = ", ".join(place_parts) if place_parts else list(filters.values())[0]
            
            # Special formatting for contractor queries
            if "contractor" in filters:
                return f"{filters['contractor']} has {n} flood control projects."
            else:
                return f"There are {n} flood control projects in {place_description.title()}."
        return f"There are {n} flood control projects in the dataset."

    # Sum budget
    if action == "sum" and parsed["column"]:
        # Find the correct budget column
        budget_cols = ['approved_budget_num', 'approvedbudgetforcontract', 'approved_budget', 'budget', 'contractcost']
        budget_col = None
        for col in budget_cols:
            if col in sub.columns:
                budget_col = col
                break
        
        if budget_col is None:
            return "I couldn't find a budget column in the dataset."
        
        total = sub[budget_col].sum()
        if filters:
            # Create a more descriptive place name
            place_parts = []
            if "municipality" in filters:
                place_parts.append(f"municipality of {filters['municipality']}")
            if "province" in filters:
                place_parts.append(f"province of {filters['province']}")
            if "region" in filters:
                place_parts.append(f"Region {filters['region']}")
            if "mainisland" in filters:
                place_parts.append(filters['mainisland'])
            if "project_location" in filters:
                place_parts.append(filters['project_location'])
            
            place_description = ", ".join(place_parts) if place_parts else list(filters.values())[0]
            return f"The total approved budget in {place_description.title()} is ₱{total:,.2f}."
        return f"The total approved budget for all projects is ₱{total:,.2f}."

    # Max budget
    if action == "max" and parsed["column"]:
        # Find the correct budget column
        budget_cols = ['approved_budget_num', 'approvedbudgetforcontract', 'approved_budget', 'budget', 'contractcost']
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
        
        # Find location with more detail
        location_parts = []
        location_cols = ['municipality', 'province', 'legislativedistrict', 'project_location', 'location']
        for col in location_cols:
            if col in sub.columns and pd.notna(row.get(col)) and str(row.get(col)).strip():
                location_parts.append(str(row[col]).strip())
                break  # Take the first meaningful location found
        
        location = ", ".join(location_parts) if location_parts else "Unknown Location"

        result = f"The project with the highest budget is Project ID {project_id} in {location} with ₱{row[budget_col]:,.2f}."
        
        # If we have filters, add context about the search area
        if filters:
            filter_parts = []
            if "municipality" in filters:
                filter_parts.append(f"municipality of {filters['municipality']}")
            if "province" in filters:
                filter_parts.append(f"province of {filters['province']}")
            if "region" in filters:
                filter_parts.append(f"Region {filters['region']}")
            if "mainisland" in filters:
                filter_parts.append(filters['mainisland'])
            if "project_location" in filters:
                filter_parts.append(filters['project_location'])
            
            if filter_parts:
                search_area = ", ".join(filter_parts)
                result = f"In {search_area.title()}: {result}"
        
        return result

    return "Sorry — I couldn't understand the question."