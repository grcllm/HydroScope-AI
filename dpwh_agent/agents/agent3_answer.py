from typing import Dict
import pandas as pd
import re

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

    # Region IV-A / IV-B pattern
    m = re.search(r"region\s*(?:iv-?|4)?\s*[–-]?\s*([ab])", p)
    if m:
        subregion = m.group(1).lower()
        filters["region"] = "iv-a" if subregion == 'a' else "iv-b"
        return filters

    # NCR pattern (check FIRST before other patterns)
    if re.search(r"\bncr\b|national capital region|metro manila|ncr", p):
        filters["region"] = "National Capital Region"
        return filters
    
    # Cordillera pattern (check FIRST before other patterns)  
    if re.search(r"\bcar\b|cordillera|cordillera administrative region|car", p):
        filters["region"] = "Cordillera Administrative Region"
        return filters

    # Standard region pattern (handles both roman and numeric)
    m = re.search(r"region\s*([0-9ivx]+)", p)
    if m:
        region_str = m.group(1).lower()
        filters["region"] = region_str  # Store what user typed - apply_filters handles matching
        return filters

    # Island keywords
    for island in ["luzon", "visayas", "mindanao"]:
        if island in p and "main_island" in df.columns:  # Changed from "mainisland"
            filters["main_island"] = island  # Changed from "mainisland"
            return filters

    # Municipality detection
    if "municipality" in df.columns:
        municipalities = sorted(df["municipality"].dropna().astype(str).unique(), key=len, reverse=True)
        for muni in municipalities:
            muni_lower = muni.lower()
            if muni_lower in p:
                filters["municipality"] = muni
                if "province" in df.columns:
                    provinces = sorted(df["province"].dropna().astype(str).unique(), key=len, reverse=True)
                    for prov in provinces:
                        if prov.lower() in p:
                            filters["province"] = prov
                            break
                return filters

    # Province detection (if no municipality)
    if not filters and "province" in df.columns:
        provinces = sorted(df["province"].dropna().astype(str).unique(), key=len, reverse=True)
        for prov in provinces:
            if prov.lower() in p:
                filters["province"] = prov
                return filters

    # Fallback: project_location
    if "project_location" in df.columns:
        locations = sorted(df["project_location"].dropna().astype(str).unique(), key=len, reverse=True)
        for loc in locations:
            if loc.lower() in p:
                filters["project_location"] = loc
                return filters

    return filters



def simple_parse(prompt: str, df: pd.DataFrame) -> dict:
    p = prompt.lower()

    # 🔎 PRIORITY ORDER: Check statistical queries FIRST before project ID detection

    # Highest budget pattern - CHECK FIRST
    highest_keywords: list[str] = ["highest approved budget", "max approved budget", "highest budget", "max budget", "largest budget", "biggest budget"]
    if any(keyword in p for keyword in highest_keywords):
        filters = detect_filters(prompt, df)
        return {"action": "max", "column": "approved_budget_num", "filters": filters}
    
    # Lowest budget pattern
    lowest_keywords: list[str] = ["lowest approved budget", "min approved budget", "minimum approved budget", "lowest budget", "minimum budget", "least budget"]
    if any(keyword in p for keyword in lowest_keywords):
        filters = detect_filters(prompt, df)
        return {"action": "min", "column": "approved_budget_num", "filters": filters}

    # Total budget pattern - CHECK SECOND
    total_keywords: list[str] = ["total budget", "sum", "overall budget"]
    if any(keyword in p for keyword in total_keywords):
        filters = detect_filters(prompt, df)
        return {"action": "sum", "column": "approved_budget_num", "filters": filters}

    # Count pattern - CHECK THIRD (Enhanced with contractor-specific logic)
    if "how many" in p or p.startswith("how many"):
        filters = detect_filters(prompt, df)

        # Special handling for contractor queries
        if "contractor" in p and not filters:
            # Enhanced patterns to catch more variations
            contractor_patterns = [
                r"how many projects.*contractor.*have\s+(.+)$",
                r"how many projects.*does\s+(.+?)\s+have",
                r"how many projects.*by\s+(.+)$",
                r"how many projects.*from\s+(.+)$",
                r"how many projects\s+(.+?)\s+(?:does|do)\s+have",  # ✅ NEW: "projects X does have"
                r"contractor\s+have\s+(.+?)(?:\?|$)",  # ✅ NEW: "contractor have X"
            ]
            
            for pattern in contractor_patterns:
                match = re.search(pattern, p)
                if match:
                    contractor_name = match.group(1).strip()
                    # Clean up the contractor name (remove common words and punctuation)
                    contractor_name = re.sub(r'\b(contractor|company|corp|inc|ltd|does|have)\b', '', contractor_name, flags=re.IGNORECASE).strip()
                    contractor_name = contractor_name.rstrip('.,;:!?')  # ✅ Remove trailing punctuation
                    
                    # Find matching contractor in the dataset
                    if "contractor" in df.columns:
                        contractors = df["contractor"].dropna().unique()
                        for contractor in contractors:
                            if pd.notna(contractor) and contractor_name.lower() in str(contractor).lower():
                                filters = {"contractor": contractor}
                                break
                    break
        
        # ✅ NEW: Fallback - if still no filters but contractor name appears in prompt
        if not filters and "contractor" in df.columns:
            # Try to extract any capitalized words that might be contractor name
            words = prompt.split()
            # Look for sequences of uppercase words (likely contractor names)
            for i, word in enumerate(words):
                if word.isupper() or (word[0].isupper() and len(word) > 2):
                    # Build potential contractor name from consecutive uppercase words
                    potential_name = []
                    for j in range(i, len(words)):
                        if words[j].isupper() or (words[j][0].isupper() and words[j].lower() not in ['have', 'does', 'do', 'the', 'of']):
                            potential_name.append(words[j].rstrip('.,;:!?'))
                        else:
                            break
                    
                    if potential_name:
                        contractor_name = ' '.join(potential_name)
                        # Search in dataset
                        contractors = df["contractor"].dropna().unique()
                        for contractor in contractors:
                            if pd.notna(contractor) and contractor_name.lower() in str(contractor).lower():
                                filters = {"contractor": contractor}
                                break
                        if filters:
                            break

        # Always capture "in X" as filter (even if detect_filters misses it)
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
            patterns = []
            
            # If input is a digit (e.g., "2" or "3"), convert to roman and add "region" prefix
            if pat.isdigit():
                roman = ROMAN_MAP.get(pat, pat)
                patterns.extend([
                    f"region {roman}",      # "region ii"
                    f"region {pat}",         # "region 2"
                ])
            # If input is already roman (e.g., "ii" or "iii")
            elif pat in ROMAN_MAP.values():
                patterns.extend([
                    f"region {pat}",         # "region ii"
                ])
            else:
                patterns.append(pat)
            
            # Special handling for Region 4/IV
            if pat in ['4', 'iv']:
                patterns.extend([
                    'region iv-a', 'region iv-b',
                    'region 4-a', 'region 4-b',
                    'calabarzon', 'mimaropa'
                ])
            
            if pat in ['4a', 'iv-a']:
                patterns.extend(['region iv-a', 'region 4-a', 'calabarzon'])
            if pat in ['4b', 'iv-b']:
                patterns.extend(['region iv-b', 'region 4-b', 'mimaropa'])
            
            # Build mask with EXACT matching after "region " prefix
            mask = False
            for p in patterns:
                # Use word boundary or exact space matching to prevent partial matches
                if p.startswith('region '):
                    # Match "Region II" but not "Region III"
                    current_mask = out["region"].astype(str).str.lower().str.match(f"^{re.escape(p)}$|^{re.escape(p)}\s")
                else:
                    current_mask = out["region"].astype(str).str.lower() == p
                mask = mask | current_mask
            
            out = out[mask]
            
        elif k == "main_island" and "main_island" in out.columns:
            mask = out["main_island"].astype(str).str.lower() == v.lower()
            out = out[mask]

        elif k in out.columns:
            if pd.api.types.is_string_dtype(out[k]):
                mask = out[k].astype(str).str.strip().str.lower() == v.lower()
                
                if not mask.any():
                    mask = out[k].astype(str).str.lower().str.contains(v.lower(), na=False)
                
                out = out[mask]
            else:
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
    
    # Minimum budget
    if action == "min" and parsed["column"]:
        budget_cols = ['approved_budget_num', 'approvedbudgetforcontract', 'approved_budget', 'budget', 'contractcost']
        budget_col = None
        for col in budget_cols:
            if col in sub.columns:
                budget_col = col
                break
        
        if budget_col is None:
            return "I couldn't find a budget column in the dataset."
        
        if sub.empty:
            return "I couldn't find any matching projects for your request."
        
        row = sub.loc[sub[budget_col].idxmin()]
        
        # Find project ID column
        project_id_col = find_project_id_column(df)
        pid = row[project_id_col] if project_id_col in row else "Unknown ID"
        
        # Figure out what table / filter matched (Municipality, Province, etc.)
        place_parts = []
        if "municipality" in filters:
            place_parts.append(f"Municipality of {filters['municipality']}")
        if "province" in filters:
            place_parts.append(f"Province of {filters['province']}")
        if "region" in filters:
            place_parts.append(f"Region {filters['region']}")
        if "mainisland" in filters:
            place_parts.append(filters['mainisland'].title())
        if "project_location" in filters:
            place_parts.append(filters['project_location'])
        
        place_description = ", ".join(place_parts) if place_parts else "the dataset"
        
        return (f"In {place_description}: The project with the lowest approved budget "
                f"is Project ID {pid} with ₱{row[budget_col]:,.2f}.")

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