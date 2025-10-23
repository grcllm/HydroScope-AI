import re
import unicodedata


def normalize_lgu_text(s: str) -> str:
    """
    Normalize LGU text for tolerant matching:
    - remove accents/diacritics
    - lowercase
    - drop generic prefixes (city/municipality of)
    - keep letters/numbers/spaces, collapse whitespace
    """
    if not isinstance(s, str):
        return ""
    s_norm = unicodedata.normalize('NFKD', s)
    s_ascii = s_norm.encode('ascii', 'ignore').decode('ascii').lower()
    s_ascii = re.sub(r"\b(city of|municipality of|municipality|city)\b", " ", s_ascii)
    s_ascii = re.sub(r"[^a-z0-9\s\-]", " ", s_ascii)
    s_ascii = re.sub(r"[\-]", " ", s_ascii)
    s_ascii = re.sub(r"\s+", " ", s_ascii).strip()
    return s_ascii


def display_municipality(name: str) -> str:
    """
    Render municipality nicely:
    - "CITY OF PARAÑAQUE, METROPOLITAN MANILA" -> "Parañaque City, Metro Manila"
    """
    if not isinstance(name, str):
        return str(name)
    s = name.strip()
    parts = [p.strip() for p in s.split(',')]
    city = parts[0]
    rest = ", ".join(parts[1:]) if len(parts) > 1 else ""
    city_norm = re.sub(r"^CITY OF\s+", "", city, flags=re.IGNORECASE).title()
    if re.match(r"^CITY OF\s+", city, flags=re.IGNORECASE):
        city_norm = f"{city_norm} City"
    rest = re.sub(r"\bMETROPOLITAN MANILA\b", "Metro Manila", rest, flags=re.IGNORECASE)
    return f"{city_norm}, {rest}".strip(', ')
