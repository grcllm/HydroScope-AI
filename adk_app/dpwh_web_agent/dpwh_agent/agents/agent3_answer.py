from typing import Dict, Optional, Any, List, Tuple
import os
import pandas as pd
import re
import unicodedata
from dpwh_web_agent.dpwh_agent.utils.schema import find_column
from dpwh_web_agent.dpwh_agent.utils.text import display_municipality as _display_municipality, normalize_lgu_text as _normalize_lgu_text

ROMAN_MAP = {
    "1": "i", "2": "ii", "3": "iii", "4": "iv", "5": "v",
    "6": "vi", "7": "vii", "8": "viii", "9": "ix", "10": "x",
    "11": "xi", "12": "xii", "13": "xiii", "14": "xiv", "15": "xv",
    "16": "xvi", "17": "xvii", "18": "xviii"
}

# ---------- Column resolution utilities are provided by utils.schema.find_column

# Simple in-process pagination memory for follow-ups like "yes" / "5 more".
# This lives for the lifetime of the process (single-user ADK session is fine).
_PAGINATION_STATE: Dict[str, Any] = {
    "mode": None,              # 'location' | 'contractor' | None
    "filters": None,           # filters dict used to build the list
    "rows": None,              # List[Tuple[str, str]] of (project_id, contractor) in display order
    "offset": 0,               # how many already shown
    "header_ctx": "",          # cached header context text
}

def _set_pagination(mode: str, filters: dict, rows: List[Tuple[str, str]], header_ctx: str) -> None:
    _PAGINATION_STATE.update({
        "mode": mode,
        "filters": filters,
        "rows": rows,
        "offset": 0,
        "header_ctx": header_ctx,
    })

def _consume_more(count: int = 5) -> Optional[str]:
    rows = _PAGINATION_STATE.get("rows") or []
    off = int(_PAGINATION_STATE.get("offset") or 0)
    if not rows or off >= len(rows):
        return None
    n = max(1, int(count))
    take = rows[off: off + n]
    _PAGINATION_STATE["offset"] = off + len(take)
    lines = [f"- {pid} — {contr}" for pid, contr in take]
    remaining = len(rows) - _PAGINATION_STATE["offset"]
    tail = f"\n\nWould you like 5 more projects?" if remaining > 0 else ""
    prefix = f"More projects{(' ' + _PAGINATION_STATE['header_ctx']) if _PAGINATION_STATE.get('header_ctx') else ''}:\n"
    return prefix + ("\n".join(lines)) + tail



def _today_year() -> int:
    try:
        return pd.Timestamp.today().year
    except Exception:
        return  pd.Timestamp.now().year

def detect_filters(prompt: str, df: pd.DataFrame) -> Dict[str, Any]:
    """Detect filters (region/province/municipality/island/project_location) from user prompt."""
    p = prompt.lower()
    
    def _normalize_text(s: str) -> str:
        """Lowercase, remove accents/diacritics, collapse spaces and drop generic prefixes like 'city of'."""
        if not isinstance(s, str):
            return ""
        # remove accents
        s_norm = unicodedata.normalize('NFKD', s)
        s_ascii = s_norm.encode('ascii', 'ignore').decode('ascii')
        s_ascii = s_ascii.lower()
        # remove common prefixes and stopwords around LGUs
        s_ascii = re.sub(r"\b(city of|municipality of|municipality|city)\b", " ", s_ascii)
        # keep letters, numbers and spaces
        s_ascii = re.sub(r"[^a-z0-9\s\-]", " ", s_ascii)
        s_ascii = re.sub(r"[\-]", " ", s_ascii)
        s_ascii = re.sub(r"\s+", " ", s_ascii).strip()
        return s_ascii

    p_norm = _normalize_text(prompt)
    filters: Dict[str, Any] = {}

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
    main_island_col = find_column(df, ["main_island", "mainisland", "main island"])
    for island in ["luzon", "visayas", "mindanao"]:
        if island in p and main_island_col is not None:
            filters["main_island"] = island
            return filters

    # Municipality detection (diacritic-insensitive; allow prompts like "paranaque" to match "CITY OF PARAÑAQUE")
    muni_col = find_column(df, ["municipality", "city"])
    if muni_col is not None:
        municipalities = df[muni_col].dropna().astype(str).unique()
        # Build normalized lookup: longest names first to avoid partial collisions
        norm_map = []  # list of tuples (norm_name, tokens, canonical)
        for muni in municipalities:
            canon = muni.strip()
            norm = _normalize_text(canon)
            if norm:
                tokens = [t for t in norm.split() if len(t) >= 5]
                norm_map.append((norm, tokens, canon))
        norm_map.sort(key=lambda x: len(x[0]), reverse=True)

        # 1) prefer full normalized phrase match
        for norm, tokens, canon in norm_map:
            if re.search(rf"\b{re.escape(norm)}\b", p_norm):
                filters["municipality"] = canon
                province_col = find_column(df, ["province"])
                if province_col is not None:
                    provinces = df[province_col].dropna().astype(str).unique()
                    prov_norm_map = sorted((( _normalize_text(prov), prov) for prov in provinces), key=lambda x: len(x[0]), reverse=True)
                    for prov_norm, prov_canon in prov_norm_map:
                        if prov_norm and re.search(rf"\b{re.escape(prov_norm)}\b", p_norm):
                            filters["province"] = prov_canon
                            break
                return filters

        # 2) token-based match (e.g., 'paranaque' within 'paranaque metropolitan manila')
        p_tokens = set(p_norm.split())
        for norm, tokens, canon in norm_map:
            if any(t in p_tokens for t in tokens):
                filters["municipality"] = canon
                province_col = find_column(df, ["province"])
                if province_col is not None:
                    provinces = df[province_col].dropna().astype(str).unique()
                    prov_norm_map = sorted((( _normalize_text(prov), prov) for prov in provinces), key=lambda x: len(x[0]), reverse=True)
                    for prov_norm, prov_canon in prov_norm_map:
                        if prov_norm and re.search(rf"\b{re.escape(prov_norm)}\b", p_norm):
                            filters["province"] = prov_canon
                            break
                return filters

    # Multi-location in municipality/province: "in Pasig or Quezon City" / "in Laguna and Cavite"
    # Capture tokens after 'in' split by 'or/and,/'
    m_multi = re.search(r"\bin\s+([a-z\s,\/]+)(?:\?|$)", p)
    if m_multi and (find_column(df, ["municipality"]) or find_column(df, ["province"])):
        raw = m_multi.group(1)
        items = [it.strip() for it in re.split(r"\s*(?:,|\/|\band\b|\bor\b)\s*", raw) if it.strip()]
        if items:
            filters["multi_locations"] = items

    # Province detection (if no municipality) – also diacritic-insensitive
    if not filters:
        province_col = find_column(df, ["province"])
        if province_col is not None:
            provinces = df[province_col].dropna().astype(str).unique()
            prov_norm_map = sorted((( _normalize_text(prov), prov) for prov in provinces), key=lambda x: len(x[0]), reverse=True)
            for prov_norm, prov_canon in prov_norm_map:
                if prov_norm and re.search(rf"\b{re.escape(prov_norm)}\b", p_norm):
                    filters["province"] = prov_canon
                    return filters

    # Fallback: project_location
    project_loc_col = find_column(df, ["project_location", "location", "site_location"])
    if project_loc_col is not None:
        locations = sorted(df[project_loc_col].dropna().astype(str).unique(), key=len, reverse=True)
        for loc in locations:
            if loc.lower() in p:
                filters["project_location"] = loc
                return filters

    return filters


def _parse_top_n(prompt: str) -> Optional[int]:
    m = re.search(r"\btop\s+(\d{1,3})\b", prompt.lower())
    if m:
        try:
            n = int(m.group(1))
            return n if n > 0 else None
        except Exception:
            return None
    return None

def _parse_time_filters(prompt: str) -> Dict[str, Any]:
    p = prompt.lower()
    t: Dict[str, Any] = {}
    # Year range: between 2021 and 2023
    m = re.search(r"between\s+(\d{4})\s+and\s+(\d{4})", p)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        t["year_range"] = (min(a,b), max(a,b))
        return t
    # Single year: in 2023 / for 2024
    m = re.search(r"\b(in|for)\s+(\d{4})\b", p)
    if m:
        t["year"] = int(m.group(2))
    # Completed in YEAR
    m = re.search(r"completed\s+in\s+(\d{4})", p)
    if m:
        t["completed_year"] = int(m.group(1))
    # Relative years
    if "last year" in p:
        t["year"] = _today_year() - 1
    if "this year" in p:
        t["year"] = _today_year()
    # Status keywords
    if re.search(r"\bongoing\b", p):
        t["status"] = "ongoing"
    if re.search(r"\bcompleted\b", p) and "completed_year" not in t:
        t["status"] = "completed"
    return t



def simple_parse(prompt: str, df: pd.DataFrame) -> dict:
    p = prompt.lower()

    # 🔎 PRIORITY ORDER: Check statistical queries FIRST before project ID detection

    # Top N projects with highest approved budget for a contractor
    m_contractor_top = (
        re.search(r"top\s+\d+\s+(?:with\s+the\s+)?(?:highest\s+)?(?:approved\s+)?budget\s+(?:of|for|by)\s+(.+)$", p)
        or re.search(r"list\s+the\s+top\s+(\d+)\s+(?:with\s+the\s+)?(?:highest\s+)?(?:approved\s+)?budget\s+(?:of|for|by)\s+(.+)$", p)
    )
    if m_contractor_top:
        # Extract top_n and contractor name
        top_n = _parse_top_n(prompt) or 5
        # Pick the last capture group that contains the name
        if isinstance(m_contractor_top, re.Match):
            contractor_query = m_contractor_top.group(m_contractor_top.lastindex).strip()
        else:
            contractor_query = ""
        contractor_query = contractor_query.rstrip('. ,;!?')
        # Try to resolve contractor name against dataset
        contractor_col = find_column(df, ['contractor', 'contractor_name', 'winning_contractor'])
        filters = {}
        if contractor_col:
            candidates = df[contractor_col].dropna().astype(str).unique()
            best = None
            cq = contractor_query.lower()
            for c in candidates:
                cs = str(c)
                cl = cs.lower()
                if cq and (cq in cl or cl in cq):
                    best = cs
                    break
            if best:
                filters['contractor'] = best
        time_filters = _parse_time_filters(prompt)
        return {"action": "top_projects_by_contractor_budget", "filters": filters, "column": "approved_budget_num", "top_n": top_n, "time": time_filters}

    # Contractor with highest total/approved budget (single winner) - CHECK BEFORE generic highest budget
    if (
        ("contractor" in p and re.search(r"highest\s+(?:total\s+)?(?:approved\s+)?budget", p))
        or re.search(r"who\s+(?:is\s+)?the\s+contractor\s+with\s+(?:the\s+)?highest\s+(?:total\s+)?(?:approved\s+)?budget", p)
        or re.search(r"which\s+contractor\s+(?:has|with)\s+(?:the\s+)?highest\s+(?:total\s+)?(?:approved\s+)?budget", p)
    ):
        filters = detect_filters(prompt, df)
        time_filters = _parse_time_filters(prompt)
        return {"action": "contractor_max_total_budget", "filters": filters, "column": "approved_budget_num", "time": time_filters}

    # Highest budget pattern - CHECK FIRST
    highest_keywords: list[str] = ["highest approved budget", "max approved budget", "highest budget", "max budget", "largest budget", "biggest budget"]
    if any(keyword in p for keyword in highest_keywords):
        filters = detect_filters(prompt, df)
        top_n = _parse_top_n(prompt) or 1
        time_filters = _parse_time_filters(prompt)
        return {"action": "max", "column": "approved_budget_num", "filters": filters, "top_n": top_n, "time": time_filters}
    
    # Lowest budget pattern
    lowest_keywords: list[str] = ["lowest approved budget", "min approved budget", "minimum approved budget", "lowest budget", "minimum budget", "least budget"]
    if any(keyword in p for keyword in lowest_keywords):
        filters = detect_filters(prompt, df)
        top_n = _parse_top_n(prompt) or 1
        time_filters = _parse_time_filters(prompt)
        return {"action": "min", "column": "approved_budget_num", "filters": filters, "top_n": top_n, "time": time_filters}

    # List projects by location – interpret as "top 5 by highest approved budget in <place>"
    # Also accept: "give me all <N> projects in <place>"
    if ("list" in p and "project" in p and "in" in p) or re.search(r"list all .*projects", p) or re.search(r"give me all\s+\d+\s+projects\s+in", p):
        filters = detect_filters(prompt, df)
        # trigger only if we found a location-like filter
        if any(k in filters for k in ("municipality", "province", "region", "project_location")):
            time_filters = _parse_time_filters(prompt)
            # Default top_n=5 and cap later in renderer unless explicit number appears after 'all'
            m_alln = re.search(r"give me all\s+(\d+)\s+projects", p)
            if m_alln:
                try:
                    return {"action": "top_projects_by_location_budget", "filters": filters, "column": "approved_budget_num", "top_n": int(m_alln.group(1)), "force_all": True, "time": time_filters}
                except Exception:
                    pass
            return {"action": "top_projects_by_location_budget", "filters": filters, "column": "approved_budget_num", "top_n": 5, "time": time_filters}

    # Follow-ups for pagination
    if re.fullmatch(r"\s*(yes|yeah|yep|sure|ok|okay|please)\s*", p):
        return {"action": "more_projects", "count": 5}
    m_more = re.search(r"(\d+)\s+more\s+projects?", p)
    if m_more:
        try:
            return {"action": "more_projects", "count": int(m_more.group(1))}
        except Exception:
            return {"action": "more_projects", "count": 5}
    # "give me all 9 projects" without restating location – use pagination state
    m_all_total = re.search(r"give me all\s+(\d+)\s+projects", p)
    if m_all_total and not any(kw in p for kw in ["in "]):
        try:
            return {"action": "more_projects", "count": int(m_all_total.group(1))}
        except Exception:
            return {"action": "more_projects", "count": 5}

    # Count pattern - CHECK THIRD (Enhanced with contractor-specific logic)
    if "how many" in p or p.startswith("how many"):
        filters = detect_filters(prompt, df)

        # Special handling for contractor queries
        if "contractor" in p and not filters:
            # Direct pattern: "how many projects contractor <NAME> have"
            direct_match = re.search(r"how many projects\s+contractor\s+(.+?)\s+have\b", p)
            if direct_match:
                contractor_name = direct_match.group(1).strip().rstrip('.,;:!?')
                contractor_col = find_column(df, ['contractor', 'contractor_name', 'winning_contractor'])
                if contractor_col:
                    contractors = df[contractor_col].dropna().unique()
                    for contractor in contractors:
                        if pd.notna(contractor) and contractor_name.lower() in str(contractor).lower():
                            filters = {"contractor": contractor}
                            break
            
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

        time_filters = _parse_time_filters(prompt)
        return {"action": "count", "filters": filters, "column": None, "time": time_filters}

    # Top contractors by total budget (prioritize before generic sum)
    if re.search(r"top\s+\d+\s+contractors\s+by\s+(?:total\s+)?budget", p):
        filters = detect_filters(prompt, df)
        time_filters = _parse_time_filters(prompt)
        top_n = _parse_top_n(prompt) or 5
        return {"action": "top_contractors", "filters": filters, "column": "approved_budget_num", "top_n": top_n, "time": time_filters}

    # Top contractors by number of projects
    if re.search(r"top\s+\d+\s+contractors\s+by\s+(?:number\s+of\s+projects|project\s+count|projects)", p):
        filters = detect_filters(prompt, df)
        time_filters = _parse_time_filters(prompt)
        top_n = _parse_top_n(prompt) or 10
        return {"action": "top_contractors_by_count", "filters": filters, "column": None, "top_n": top_n, "time": time_filters}

    # Contractor with highest number of projects (single winner)
    if (
        re.search(r"which\s+contractor\s+(?:has|with)\s+(?:the\s+)?(?:most|highest|largest)\s+(?:number\s+of\s+)?projects?", p)
        or re.search(r"who\s+is\s+the\s+contractor\s+with\s+(?:the\s+)?(?:most|highest|largest)\s+(?:number\s+of\s+)?projects?", p)
        or ("contractor" in p and re.search(r"highest\s+number\s+of\s+projects?", p))
    ):
        filters = detect_filters(prompt, df)
        time_filters = _parse_time_filters(prompt)
        return {"action": "contractor_max_count", "filters": filters, "column": None, "time": time_filters}

    # Total budget pattern - CHECK SECOND
    total_keywords: list[str] = ["total budget", "sum", "overall budget","cost","total cost","total approved budget"]
    if any(keyword in p for keyword in total_keywords):
        filters = detect_filters(prompt, df)
        time_filters = _parse_time_filters(prompt)
        return {"action": "sum", "column": "approved_budget_num", "filters": filters, "time": time_filters}

    # Trend by year
    if re.search(r"(trend|by year|per year)", p) and ("total" in p or "budget" in p):
        filters = detect_filters(prompt, df)
        return {"action": "trend_by_year", "filters": filters, "column": "approved_budget_num"}

    # Comparative queries: which municipality in X has highest total budget
    if re.search(r"which\s+municipality.*highest\s+total\s+budget", p):
        filters = detect_filters(prompt, df)
        time_filters = _parse_time_filters(prompt)
        return {"action": "municipality_max_total", "filters": filters, "column": "approved_budget_num", "time": time_filters}

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

    # Resolve common columns in a case-insensitive way
    region_col = find_column(out, ["region"])
    main_island_col = find_column(out, ["main_island", "mainisland", "main island"])
    municipality_col = find_column(out, ["municipality", "city"])
    province_col = find_column(out, ["province"])
    project_loc_col = find_column(out, ["project_location", "location", "site_location"])
    contractor_col = find_column(out, ["contractor", "contractor_name", "winning_contractor"])

    # Multi-location support (municipality/province lists)
    multi_locs = filters.get("multi_locations")
    if multi_locs:
        # Try matching municipalities first; fallback to provinces
        muni_col = municipality_col
        prov_col = province_col
        candidates_norm = [str(x).strip().lower() for x in multi_locs]
        if muni_col is not None:
            out = out[out[muni_col].astype(str).str.lower().apply(lambda x: any(c in x for c in candidates_norm))]
        elif prov_col is not None:
            out = out[out[prov_col].astype(str).str.lower().apply(lambda x: any(c in x for c in candidates_norm))]

    for k, v in filters.items():
        if v is None:
            continue

        if k == "region" and region_col is not None:
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
            # Start with an all-False boolean Series to avoid scalar-bool indexing errors when no patterns match
            mask = pd.Series(False, index=out.index)
            for p in patterns:
                # Use word boundary or exact space matching to prevent partial matches
                region_vals = out[region_col].astype(str).str.lower()
                if p.startswith('region '):
                    # Use startswith to allow suffixes like "(Cagayan Valley)" or extra descriptors
                    current_mask = region_vals.str.startswith(p)
                else:
                    current_mask = region_vals == p
                mask = mask | current_mask

            # NCR alias support: also match province and DEO text for Metro Manila synonyms
            ncr_aliases = {"national capital region", "ncr", "metro manila", "metropolitan manila"}
            if pat in ncr_aliases:
                # Province-based matching (common for Metro Manila rows)
                if province_col is not None:
                    prov_vals = out[province_col].astype(str).str.lower()
                    prov_mask = pd.Series(False, index=out.index)
                    for alias in ncr_aliases:
                        prov_mask = prov_mask | prov_vals.str.contains(alias, na=False)
                    mask = mask | prov_mask
                # District Engineering Office sometimes contains Metro Manila
                deo_col = find_column(out, ["district_engineering_office", "district engineering office"]) 
                if deo_col is not None:
                    deo_vals = out[deo_col].astype(str).str.lower()
                    deo_mask = pd.Series(False, index=out.index)
                    for alias in ncr_aliases:
                        deo_mask = deo_mask | deo_vals.str.contains(alias, na=False)
                    mask = mask | deo_mask

            out = out[mask]
            
        elif k == "main_island" and main_island_col is not None:
            mask = out[main_island_col].astype(str).str.lower() == v.lower()
            out = out[mask]

        elif k in out.columns or (k in ["municipality", "province", "project_location", "contractor"]):
            # map to actual column
            col = None
            if k == "municipality":
                col = municipality_col
            elif k == "province":
                col = province_col
            elif k == "project_location":
                col = project_loc_col
            elif k == "contractor":
                col = contractor_col
            if col is None and k in out.columns:
                col = k

            if col is None:
                continue

            if pd.api.types.is_string_dtype(out[col]):
                mask = out[col].astype(str).str.strip().str.lower() == v.lower()
                
                if not mask.any():
                    mask = out[col].astype(str).str.lower().str.contains(v.lower(), na=False)
                
                out = out[mask]
            else:
                out = out[out[col] == v]

    return out


def _apply_time_filters(df: pd.DataFrame, time_spec: Optional[Dict[str, Any]]) -> pd.DataFrame:
    if not time_spec:
        return df
    out = df
    # Prefer parsed dates where available
    start_col = find_column(out, ["start_date_parsed", "startdate_parsed"]) or find_column(out, ["start_date", "startdate"]) 
    comp_col  = find_column(out, ["completion_date_parsed", "actualcompletiondate_parsed"]) or find_column(out, ["completion_date", "actual_completion_date", "actualcompletiondate"]) 
    year_col  = find_column(out, ["funding_year", "year"])  # backup when dates missing

    # Completed in a specific year
    if "completed_year" in time_spec and comp_col is not None:
        year = int(time_spec["completed_year"])
        out = out[pd.to_datetime(out[comp_col], errors='coerce').dt.year == year]

    # Single year
    if "year" in time_spec:
        y = int(time_spec["year"])
        if start_col is not None:
            out = out[pd.to_datetime(out[start_col], errors='coerce').dt.year == y]
        elif year_col is not None:
            out = out[out[year_col].astype(str) == str(y)]

    # Year range
    if "year_range" in time_spec:
        a, b = time_spec["year_range"]
        if start_col is not None:
            ys = pd.to_datetime(out[start_col], errors='coerce').dt.year
            out = out[(ys >= a) & (ys <= b)]
        elif year_col is not None:
            ys = pd.to_numeric(out[year_col], errors='coerce')
            out = out[(ys >= a) & (ys <= b)]

    # Status filters
    if time_spec.get("status") == "ongoing" and comp_col is not None:
        comp = pd.to_datetime(out[comp_col], errors='coerce')
        out = out[comp.isna() | (comp > pd.Timestamp.today())]
    if time_spec.get("status") == "completed" and comp_col is not None:
        comp = pd.to_datetime(out[comp_col], errors='coerce')
        out = out[comp.notna() & (comp <= pd.Timestamp.today())]
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


REQUIRE_CONFIRM = str(os.environ.get("REQUIRE_CONFIRM", "0")).lower() in {"1", "true", "yes", "on"}

def _clarify_message(parsed: dict, df: pd.DataFrame) -> str:
    action = parsed.get("action")
    filters = parsed.get("filters", {})
    time_spec = parsed.get("time", {})
    top_n = parsed.get("top_n")
    parts = ["I plan to:"]
    if action == "max":
        parts.append(f"find the highest approved budget" + (f" (top {top_n})" if top_n and top_n>1 else ""))
    elif action == "min":
        parts.append(f"find the lowest approved budget" + (f" (top {top_n})" if top_n and top_n>1 else ""))
    elif action == "sum":
        parts.append("compute the total approved budget")
    elif action == "count":
        parts.append("count the number of projects")
    elif action == "top_contractors":
        parts.append(f"find top {top_n} contractors by total budget")
    elif action == "trend_by_year":
        parts.append("show total budget by year (trend)")
    elif action == "municipality_max_total":
        parts.append("identify the municipality with the highest total budget in the specified region/area")
    else:
        parts.append(f"perform action '{action}'")

    loc_bits = []
    if "municipality" in filters:
        loc_bits.append(_display_municipality(filters['municipality']))
    if "province" in filters:
        loc_bits.append(filters['province'].title() if isinstance(filters['province'], str) else str(filters['province']))
    if "region" in filters:
        loc_bits.append(f"Region {filters['region']}")
    if "multi_locations" in filters:
        loc_bits.append(" or ".join(filters['multi_locations']))
    where = (", in " + ", ".join(loc_bits)) if loc_bits else ""

    time_bits = []
    if "completed_year" in time_spec:
        time_bits.append(f"completed in {time_spec['completed_year']}")
    if "year" in time_spec:
        time_bits.append(f"in {time_spec['year']}")
    if "year_range" in time_spec:
        a,b = time_spec['year_range']
        time_bits.append(f"between {a} and {b}")
    if "status" in time_spec:
        time_bits.append(time_spec['status'])
    when = (" " + ", ".join(time_bits)) if time_bits else ""

    questions = [
        "- Do you want a specific year or range (e.g., 2023 or between 2021 and 2022)?",
        "- How many results should I return (e.g., top 3)?",
        "- Should I focus on approved budget or contract cost?",
        "- Is this limited to certain locations or contractors?",
    ]
    return "Clarification needed: " + " ".join(parts) + f"{where}{when}.\n" + "\n".join(questions)


def agent3_run(question: str, df: pd.DataFrame) -> str:
    parsed = simple_parse(question, df)
    action = parsed["action"]
    filters = parsed["filters"]
    time_spec = parsed.get("time")
    top_n = parsed.get("top_n") or 1

    if REQUIRE_CONFIRM:
        return _clarify_message(parsed, df)

    sub = apply_filters(df, filters)
    sub = _apply_time_filters(sub, time_spec)

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
        if "main_island" in filters:
            place_parts.append(filters['main_island'])
        if "project_location" in filters:
            place_parts.append(filters['project_location'])
        
        place_description = ", ".join(place_parts) if place_parts else list(filters.values())[0]
        # Try to suggest nearest municipality/province by simple token inclusion
        suggestions = []
        try:
            target = str(filters.get('municipality') or filters.get('province') or '').lower()
            if target:
                # search municipalities first
                muc = find_column(df, ['municipality','city'])
                if muc:
                    vals = df[muc].dropna().astype(str).unique().tolist()
                    matches = [v for v in vals if _normalize_lgu_text(target) in _normalize_lgu_text(v)]
                    suggestions = [ _display_municipality(m) for m in matches[:5] ]
        except Exception:
            pass
        if suggestions:
            return f"I couldn't find any flood control projects in {place_description.title()}. Did you mean: {', '.join(suggestions)}?"
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
            if "main_island" in filters:
                place_parts.append(filters['main_island'])
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
        budget_col = find_column(sub, ['approved_budget_num', 'approved_budget_for_contract', 'approvedbudgetforcontract', 'approved_budget', 'budget', 'contractcost', 'approved budget for contract'])
        
        if budget_col is None:
            return "I couldn't find a budget column in the dataset."

        # Coerce to numeric to safely sum even if stored as strings
        sub_num = sub.copy()
        sub_num[budget_col] = pd.to_numeric(sub_num[budget_col], errors='coerce')
        # If multi-location specified, show per-location totals (comparative)
        if filters.get('multi_locations'):
            muni_col = find_column(sub_num, ['municipality','city']) or find_column(sub_num, ['province'])
            if muni_col:
                comp = sub_num.groupby(muni_col)[budget_col].sum().sort_values(ascending=False)
                lines = [f"- {_display_municipality(str(k))}: ₱{float(v):,.2f}" for k,v in comp.items()]
                return "Total approved budget by location:\n" + ("\n".join(lines) if lines else "No matching locations.")
        total = sub_num[budget_col].sum()
        if filters:
            # Create a more descriptive place name
            place_parts = []
            if "municipality" in filters:
                place_parts.append(f"municipality of {filters['municipality']}")
            if "province" in filters:
                place_parts.append(f"province of {filters['province']}")
            if "region" in filters:
                place_parts.append(f"Region {filters['region']}")
            if "main_island" in filters:
                place_parts.append(filters['main_island'])
            if "project_location" in filters:
                place_parts.append(filters['project_location'])
            
            place_description = ", ".join(place_parts) if place_parts else list(filters.values())[0]
            return f"The total approved budget in {place_description.title()} is ₱{total:,.2f}."
        return f"The total approved budget for all projects is ₱{total:,.2f}."
    
    # Minimum budget
    if action == "min" and parsed["column"]:
        budget_col = find_column(sub, ['approved_budget_num', 'approved_budget_for_contract', 'approvedbudgetforcontract', 'approved_budget', 'budget', 'contractcost', 'approved budget for contract'])
        
        if budget_col is None:
            return "I couldn't find a budget column in the dataset."
        
        if sub.empty:
            return "I couldn't find any matching projects for your request."
        
        # Coerce to numeric for comparison and drop rows without a valid budget
        sub = sub.copy()
        sub[budget_col] = pd.to_numeric(sub[budget_col], errors='coerce')
        valid = sub.dropna(subset=[budget_col])
        if valid.empty:
            # All budgets are missing/invalid under this filter
            ctx = []
            if "municipality" in filters:
                ctx.append(_display_municipality(filters['municipality']))
            if "province" in filters:
                ctx.append(filters['province'])
            if "region" in filters:
                ctx.append(f"Region {filters['region']}")
            where = f" in {', '.join(ctx)}" if ctx else ""
            return f"I couldn't find any projects with a valid approved budget{where}."
        # If requesting top-N, return N smallest from valid rows
        if top_n and top_n > 1:
            rows = valid.nsmallest(top_n, budget_col)
            lines = []
            for _, r in rows.iterrows():
                pid_col = find_project_id_column(valid)
                pid = r.get(pid_col, 'N/A')
                lines.append(f"- {pid}: ₱{float(r[budget_col]):,.2f}")
            ctx = []
            if "municipality" in filters:
                ctx.append(_display_municipality(filters['municipality']))
            if "province" in filters:
                ctx.append(filters['province'])
            if "region" in filters:
                ctx.append(f"Region {filters['region']}")
            prefix = f"Top {top_n} lowest budgets" + (f" in {', '.join(ctx)}" if ctx else "")
            return prefix + ":\n" + "\n".join(lines)
        row = valid.loc[valid[budget_col].idxmin()]
        
        # Find project ID column
        project_id_col = find_project_id_column(valid)
        pid = row[project_id_col] if project_id_col in row else "Unknown ID"
        
        # Figure out what table / filter matched (Municipality, Province, etc.)
        place_parts = []
        if "municipality" in filters:
            place_parts.append(f"Municipality of {filters['municipality']}")
        if "province" in filters:
            place_parts.append(f"Province of {filters['province']}")
        if "region" in filters:
            place_parts.append(f"Region {filters['region']}")
        if "main_island" in filters:
            place_parts.append(filters['main_island'].title())
        if "project_location" in filters:
            place_parts.append(filters['project_location'])
        
        place_description = ", ".join(place_parts) if place_parts else "the dataset"
        
        return (f"In {place_description}: The project with the lowest approved budget "
                f"is Project ID {pid} with ₱{row[budget_col]:,.2f}.")

    # Max budget
    if action == "max" and parsed["column"]:
        # Find the correct budget column
        budget_col = find_column(sub, ['approved_budget_num', 'approved_budget_for_contract', 'approvedbudgetforcontract', 'approved_budget', 'budget', 'contractcost', 'approved budget for contract'])
        
        if budget_col is None:
            return "I couldn't find a budget column in the dataset."
        
        if sub.empty:
            return "I couldn't find any projects matching that filter."

        # Coerce to numeric for comparison and drop rows without a valid budget
        sub = sub.copy()
        sub[budget_col] = pd.to_numeric(sub[budget_col], errors='coerce')
        valid = sub.dropna(subset=[budget_col])
        if valid.empty:
            # All budgets are missing/invalid under this filter
            ctx = []
            if "municipality" in filters:
                ctx.append(_display_municipality(filters['municipality']))
            if "province" in filters:
                ctx.append(filters['province'])
            if "region" in filters:
                ctx.append(f"Region {filters['region']}")
            where = f" in {', '.join(ctx)}" if ctx else ""
            return f"I couldn't find any projects with a valid approved budget{where}."
        # If requesting top-N, return N largest from valid rows
        if top_n and top_n > 1:
            rows = valid.nlargest(top_n, budget_col)
            lines = []
            pid_col = find_project_id_column(valid)
            for _, r in rows.iterrows():
                pid = r.get(pid_col, 'N/A')
                # Find location
                location_parts = []
                for col in [find_column(valid, ['municipality','city']), find_column(valid, ['province'])]:
                    if col and pd.notna(r.get(col)):
                        location_parts.append(str(r.get(col)))
                loc = ", ".join(location_parts) if location_parts else "Unknown Location"
                lines.append(f"- {pid} in {_display_municipality(loc)}: ₱{float(r[budget_col]):,.2f}")
            ctx = []
            if "municipality" in filters:
                ctx.append(_display_municipality(filters['municipality']))
            if "province" in filters:
                ctx.append(filters['province'])
            if "region" in filters:
                ctx.append(f"Region {filters['region']}")
            prefix = f"Top {top_n} highest budgets" + (f" in {', '.join(ctx)}" if ctx else "")
            return prefix + ":\n" + "\n".join(lines)
        row = valid.loc[valid[budget_col].idxmax()]

        # ✅ Use project_id if available
        project_id_col = find_project_id_column(valid)
        project_id = row[project_id_col] if project_id_col else "N/A"
        
        # Find location with more detail
        location_parts = []
        # Resolve location columns case-insensitively
        loc_candidates = [
            find_column(valid, ['municipality', 'city']),
            find_column(valid, ['province']),
            find_column(valid, ['legislative_district', 'legislativedistrict']),
            find_column(valid, ['project_location', 'location'])
        ]
        for col in [c for c in loc_candidates if c]:
            if pd.notna(row.get(col)) and str(row.get(col)).strip():
                location_parts.append(str(row[col]).strip())
                break  # first meaningful
        
        location = ", ".join(location_parts) if location_parts else "Unknown Location"

        value = row[budget_col]
        if pd.notna(value):
            result = f"The project with the highest budget is Project ID {project_id} in {location} with ₱{float(value):,.2f}."
        else:
            result = f"The project with the highest budget is Project ID {project_id} in {location}."
        
        # If we have filters, add context about the search area
        if filters:
            filter_parts = []
            if "municipality" in filters:
                filter_parts.append(f"municipality of {filters['municipality']}")
            if "province" in filters:
                filter_parts.append(f"province of {filters['province']}")
            if "region" in filters:
                filter_parts.append(f"Region {filters['region']}")
            if "main_island" in filters:
                filter_parts.append(filters['main_island'])
            if "project_location" in filters:
                filter_parts.append(filters['project_location'])
            
            if filter_parts:
                search_area = ", ".join(filter_parts)
                result = f"In {search_area.title()}: {result}"
        
        return result

    # Top N projects with highest approved budget for a location (municipality/province/region)
    if action == "top_projects_by_location_budget":
        budget_col = find_column(sub, ['approved_budget_num', 'approved_budget_for_contract', 'approvedbudgetforcontract', 'approved_budget', 'budget', 'contractcost', 'approved budget for contract'])
        if budget_col is None:
            return "I couldn't find a budget column in the dataset."
        if sub.empty:
            return "I couldn't find any matching projects for that location."
        tmp = sub.copy()
        tmp[budget_col] = pd.to_numeric(tmp[budget_col], errors='coerce')
        tmp = tmp.dropna(subset=[budget_col])
        if tmp.empty:
            return "No projects with a valid approved budget were found for that location."
        # Build a full sorted list once for pagination
        tmp_sorted = tmp.sort_values(by=budget_col, ascending=False)
        force_all = bool(parsed.get("force_all"))
        n = int(top_n or 5)
        top_rows = tmp_sorted.head(n if force_all else min(n, 5))
        pid_col = find_project_id_column(tmp)
        contractor_col = find_column(tmp, ['contractor', 'contractor_name', 'winning_contractor'])
        lines = []
        prepared: List[Tuple[str, str]] = []
        for _, r in tmp_sorted.iterrows():
            pid = r.get(pid_col, 'N/A')
            contractor = r.get(contractor_col, 'Unknown Contractor') if contractor_col else 'Unknown Contractor'
            prepared.append((str(pid), str(contractor)))
        # Store pagination state then render the first chunk
        ctx = []
        if "municipality" in filters:
            ctx.append(_display_municipality(filters['municipality']))
        if "province" in filters:
            ctx.append(str(filters['province']))
        if "region" in filters:
            ctx.append(f"Region {filters['region']}")
        header_ctx = f"in {', '.join(ctx)}" if ctx else ""
        _set_pagination("location", filters, prepared, header_ctx)
        # consume first portion (min(5) unless force_all)
        _PAGINATION_STATE['offset'] = len(top_rows)
        lines = [f"- {pid} — {contr}" for pid, contr in prepared[:len(top_rows)]]
        header = (f"Top {len(top_rows)} projects by approved budget" + (f" {header_ctx}" if header_ctx else "") + ":\n")
        tail = "" if force_all or len(prepared) <= len(top_rows) else "\n\nWould you like 5 more projects?"
        return header + ("\n".join(lines) if lines else "No projects found.") + tail

    if action == "more_projects":
        cnt = int(parsed.get("count") or 5)
        out = _consume_more(cnt)
        if out is None:
            return "There are no more projects to show for the last location. You can ask for another place or specify a contractor."
        return out

    # Top contractors by total budget
    if action == "top_contractors":
        budget_col = find_column(sub, ['approved_budget_num', 'approvedbudgetforcontract', 'approved_budget', 'budget', 'contractcost'])
        contractor_col = find_column(sub, ['contractor', 'contractor_name', 'winning_contractor'])
        if not budget_col or not contractor_col:
            return "I couldn't find the required columns (contractor/budget)."
        grp = sub.copy()
        grp[budget_col] = pd.to_numeric(grp[budget_col], errors='coerce')
        top = grp.groupby(contractor_col, dropna=True)[budget_col].sum().sort_values(ascending=False).head(top_n)
        lines = [f"- {k}: ₱{float(v):,.2f}" for k, v in top.items()]
        return f"Top {top_n} contractors by total budget:\n" + "\n".join(lines)

    # Contractor with highest total/approved budget (single winner; tie-aware)
    if action == "contractor_max_total_budget":
        budget_col = find_column(sub, ['approved_budget_num', 'approvedbudgetforcontract', 'approved_budget', 'budget', 'contractcost'])
        contractor_col = find_column(sub, ['contractor', 'contractor_name', 'winning_contractor'])
        if not budget_col or not contractor_col:
            return "I couldn't find the required columns (contractor/budget)."
        if sub.empty:
            return "I couldn't find any matching projects for your request."
        tmp = sub.copy()
        tmp[budget_col] = pd.to_numeric(tmp[budget_col], errors='coerce')
        agg = tmp.groupby(contractor_col, dropna=True)[budget_col].sum().sort_values(ascending=False)
        if agg.empty:
            return "No contractor data found."
        max_total = float(agg.iloc[0]) if pd.notna(agg.iloc[0]) else 0.0
        top_contractors = [str(k) for k, v in agg.items() if float(v) == max_total]
        # Build context string
        ctx = []
        muni_disp = _display_municipality(filters['municipality']) if 'municipality' in filters else None
        prov_disp = str(filters['province']) if 'province' in filters else None
        if muni_disp:
            ctx.append(muni_disp)
        if prov_disp and not (muni_disp and prov_disp.lower() in (muni_disp or '').lower()):
            ctx.append(prov_disp)
        if "region" in filters:
            ctx.append(f"Region {filters['region']}")
        in_ctx = f" in {', '.join(ctx)}" if ctx else ""

        if len(top_contractors) == 1:
            return f"The contractor with the highest total approved budget{in_ctx} is {top_contractors[0]} with ₱{max_total:,.2f}."
        else:
            names = ", ".join(top_contractors)
            return f"There is a tie for the highest total approved budget{in_ctx}: {names} with ₱{max_total:,.2f} each."

    # Top N projects with highest approved budget for a contractor
    if action == "top_projects_by_contractor_budget":
        budget_col = find_column(sub, ['approved_budget_num', 'approved_budget_for_contract', 'approvedbudgetforcontract', 'approved_budget', 'budget', 'contractcost', 'approved budget for contract'])
        contractor_col = find_column(sub, ['contractor', 'contractor_name', 'winning_contractor'])
        if not contractor_col or not budget_col:
            return "I couldn't find the required columns (contractor/budget)."
        # If contractor not in filters, try to infer from question again
        contractor_value = filters.get('contractor')
        if not contractor_value:
            return "Please specify a contractor name to list their top projects by approved budget."
        # Ensure numeric budgets
        tmp = sub.copy()
        tmp[budget_col] = pd.to_numeric(tmp[budget_col], errors='coerce')
        # Filter to contractor explicitly to be safe
        mask = tmp[contractor_col].astype(str).str.strip().str.lower() == str(contractor_value).strip().lower()
        tmp = tmp[mask]
        if tmp.empty:
            return f"I couldn't find any projects for contractor {contractor_value}."
        # Sort and take top N
        N = top_n if 'top_n' in locals() else (parsed.get('top_n') or 5)
        rows = tmp.sort_values(by=budget_col, ascending=False).head(N)
        pid_col = find_project_id_column(tmp)
        title_col = find_column(tmp, ['project_title', 'project_name', 'name', 'projecttitle'])
        lines = []
        for _, r in rows.iterrows():
            pid = r.get(pid_col, 'N/A') if pid_col else 'N/A'
            title = r.get(title_col) if title_col else None
            amt = r.get(budget_col)
            if pd.notna(amt):
                if title and str(title).strip():
                    lines.append(f"- {pid}: {str(title).strip()} — ₱{float(amt):,.2f}")
                else:
                    lines.append(f"- {pid}: ₱{float(amt):,.2f}")
        # Context
        ctx = []
        if "region" in filters:
            ctx.append(f"Region {filters['region']}")
        if "municipality" in filters:
            ctx.append(_display_municipality(filters['municipality']))
        if "province" in filters:
            ctx.append(str(filters['province']))
        header_ctx = (" in " + ", ".join(ctx)) if ctx else ""
        return f"Top {len(rows)} projects with the highest approved budget for {contractor_value}{header_ctx}:\n" + ("\n".join(lines) if lines else "No projects found.")

    # Top contractors by number of projects
    if action == "top_contractors_by_count":
        contractor_col = find_column(sub, ['contractor', 'contractor_name', 'winning_contractor'])
        if not contractor_col:
            return "I couldn't find the contractor column in the dataset."
        # Count projects per contractor
        counts = (
            sub.copy()
              .dropna(subset=[contractor_col])
              .groupby(contractor_col, dropna=True)
              .size()
              .sort_values(ascending=False)
              .head(top_n)
        )
        # Build context string for location filters (avoid duplicate province in municipality display)
        ctx = []
        muni_disp = None
        prov_disp = None
        if "municipality" in filters:
            muni_disp = _display_municipality(filters['municipality'])
        if "province" in filters:
            prov_disp = str(filters['province'])
        if muni_disp:
            ctx.append(muni_disp)
        if prov_disp and not (muni_disp and prov_disp.lower() in muni_disp.lower()):
            ctx.append(prov_disp)
        if "region" in filters:
            ctx.append(f"Region {filters['region']}")
        prefix = f"Top {top_n} contractors by number of projects" + (f" in {', '.join(ctx)}" if ctx else "")
        lines = [f"- {k}: {int(v)} project(s)" for k, v in counts.items()]
        return prefix + ":\n" + ("\n".join(lines) if len(lines) > 0 else "No contractor data found.")

    # Contractor with highest number of projects (single winner; tie-aware)
    if action == "contractor_max_count":
        contractor_col = find_column(sub, ['contractor', 'contractor_name', 'winning_contractor'])
        if not contractor_col:
            return "I couldn't find the contractor column in the dataset."
        if sub.empty:
            return "I couldn't find any matching projects for your request."
        counts = (
            sub.copy()
              .dropna(subset=[contractor_col])
              .groupby(contractor_col, dropna=True)
              .size()
              .sort_values(ascending=False)
        )
        if counts.empty:
            return "No contractor data found."
        max_count = int(counts.iloc[0])
        top_contractors = [str(k) for k, v in counts.items() if int(v) == max_count]
        # Build context string
        ctx = []
        muni_disp = _display_municipality(filters['municipality']) if 'municipality' in filters else None
        prov_disp = str(filters['province']) if 'province' in filters else None
        if muni_disp:
            ctx.append(muni_disp)
        if prov_disp and not (muni_disp and prov_disp.lower() in (muni_disp or '').lower()):
            ctx.append(prov_disp)
        if "region" in filters:
            ctx.append(f"Region {filters['region']}")
        in_ctx = f" in {', '.join(ctx)}" if ctx else ""

        if len(top_contractors) == 1:
            return f"The contractor with the highest number of projects{in_ctx} is {top_contractors[0]} with {max_count} project(s)."
        else:
            names = ", ".join(top_contractors)
            return f"There is a tie for the highest number of projects{in_ctx}: {names} with {max_count} project(s) each."

    # Trend by year (total budget per year)
    if action == "trend_by_year":
        budget_col = find_column(sub, ['approved_budget_num', 'approvedbudgetforcontract', 'approved_budget', 'budget', 'contractcost'])
        year_source = find_column(sub, ['start_date_parsed','start_date','funding_year'])
        if not budget_col or not year_source:
            return "I couldn't find columns needed for trend (budget/year)."
        tmp = sub.copy()
        if 'year' not in tmp.columns:
            y = pd.to_datetime(tmp[year_source], errors='coerce').dt.year if 'date' in year_source else pd.to_numeric(tmp[year_source], errors='coerce')
            tmp['year'] = y
        tmp[budget_col] = pd.to_numeric(tmp[budget_col], errors='coerce')
        series = tmp.groupby('year')[budget_col].sum().sort_index()
        lines = [f"- {int(y)}: ₱{float(v):,.2f}" for y, v in series.items() if pd.notna(y)]
        return "Total approved budget by year:\n" + ("\n".join(lines) if lines else "No yearly data available")

    # Municipality with highest total budget in a region/area
    if action == "municipality_max_total":
        budget_col = find_column(sub, ['approved_budget_num', 'approvedbudgetforcontract', 'approved_budget', 'budget', 'contractcost'])
        muni_col = find_column(sub, ['municipality','city'])
        if not budget_col or not muni_col:
            return "I couldn't find columns needed (municipality/budget)."
        tmp = sub.copy()
        tmp[budget_col] = pd.to_numeric(tmp[budget_col], errors='coerce')
        agg = tmp.groupby(muni_col)[budget_col].sum().sort_values(ascending=False)
        if agg.empty:
            return "No municipalities found for that area."
        muni = agg.index[0]
        total = agg.iloc[0]
        return f"The municipality with the highest total approved budget is {_display_municipality(str(muni))} with ₱{float(total):,.2f}."

    return "Sorry — I couldn't understand the question."
