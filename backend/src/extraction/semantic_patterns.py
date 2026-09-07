import re
from typing import Dict, Any, List, Optional, Tuple

# ==============================================================================
# 1. SEMANTIC ONTOLOGIES & CONCEPT LABELS
# ==============================================================================

# Net Quantity semantic indicator patterns
NET_QUANTITY_LABELS = [
    r'\bNET\s*QTY\b', r'\bNET\s*QUANTITY\b', r'\bNET\s*WT\b', r'\bNET\s*WEIGHT\b',
    r'\bNET\s*VOL\b', r'\bNET\s*VOLUME\b', r'\bNET\s*CONTENTS?\b', r'\bNET\s*MASS\b',
    r'\bQUANTITY\b', r'\bCONTENTS?\b', r'\bNET\b', r'\bQTY\b', r'\bWEIGHT\b',
    r'\bVOL\b', r'\bVOLUME\b', r'\bPACK\s*SIZE\b', r'\bSTICK\s*COUNT\b'
]

# MRP semantic indicator patterns
MRP_LABELS = [
    r'\bM\.?R\.?P\.?\b', r'\bMAX(?:IMUM)?\s*RETAIL\s*PRICE\b', r'\bRETAIL\s*PRICE\b',
    r'\bPRICE\b', r'\bINCL(?:USIVE)?\s*OF\s*ALL\s*TAXES\b', r'\bMAX\s*PRICE\b',
    r'\bMRP\s*RS\.?\b', r'\bMRP\s*₹\b', r'\bMRP\s*INR\b',
    r'\bMRP\s*\(\s*INCL(?:USIVE)?\s*(?:OF\s*)?ALL\s*TAXES\s*\)\b'
]

# Batch / Lot semantic indicator patterns
BATCH_LABELS = [
    r'\bBATCH\s*NO\.?\b', r'\bBATCH\s*NUMBER\b', r'\bBATCH\s*CODE\b', r'\bBATCH\b',
    r'\bB\.?\s*NO\.?\b', r'\bLOT\s*NO\.?\b', r'\bLOT\s*NUMBER\b', r'\bLOT\s*CODE\b',
    r'\bLOT\b', r'\bL\.?\s*NO\.?\b', r'\bPRODUCTION\s*BATCH\b', r'\bBCODE\b',
    r'\bCONTROL\s*NO\.?\b', r'\bCHARG(?:E|EN)\b'
]

# Manufacturing / Packing Date semantic indicator patterns
MFG_DATE_LABELS = [
    r'\bMFG\.?\s*MONTH\s*(?:&|AND)?\s*YEAR\b', r'\bMONTH\s*(?:&|AND)?\s*YEAR\s*OF\s*(?:MFG|PKD|PACKING|MANUFACTURE)\b',
    r'\bMFG\s*DATE\b', r'\bMFD\s*DATE\b', r'\bMFG\b', r'\bMFD\b', r'\bMANUFACTURED\s*ON\b',
    r'\bDATE\s*OF\s*MANUFACTURE\b', r'\bMANUFACTURED\b', r'\bDOM\b', r'\bPKD\s*DATE\b',
    r'\bPKD\b', r'\bPACKED\s*ON\b', r'\bDATE\s*OF\s*PACKING\b', r'\bPACKING\s*DATE\b',
    r'\bPACKED\b', r'\bPKG\s*DATE\b', r'\bPKG\s*DT\b', r'\bMANUFACTURED\s*/\s*PACKED\b',
    r'\bMFG\.?\s*/\s*PKG\.?\s*DATE\b', r'\bMFG\s*ON\b', r'\bPKD\s*ON\b'
]

# Expiry / Best Before semantic indicator patterns
EXPIRY_DATE_LABELS = [
    r'\bEXPIRY\s*DATE\b', r'\bEXP\s*DATE\b', r'\bEXP\.?\s*DT\.?\b', r'\bEXPIRY\b',
    r'\bEXP\b', r'\bUSE\s*BY\s*DATE\b', r'\bUSE\s*BY\b', r'\bUSE\s*BEFORE\b',
    r'\bBEST\s*BEFORE\s*END\b', r'\bBEST\s*BEFORE\b', r'\bBBE\b', r'\bBB\b',
    r'\bVALID\s*TILL\b', r'\bEXPIRES\s*ON\b', r'\bEXPIRES\b', r'\bUSE\s*WITHIN\b',
    r'\bSHELF\s*LIFE\b', r'\bCONSUME\s*BEFORE\b'
]

# Manufacturer / Packer semantic indicators
MANUFACTURER_LABELS = [
    r'\bMFD\s*BY\b', r'\bMANUFACTURED\s*BY\b', r'\bPACKED\s*BY\b', r'\bPKD\s*BY\b',
    r'\bMARKETED\s*BY\b', r'\bMKT\s*BY\b', r'\bPRODUCED\s*BY\b', r'\bIMPORTED\s*BY\b',
    r'\bPROCESSED\s*BY\b', r'\bMFG\s*&\s*PKD\s*BY\b', r'\bMFG\s*IN\s*INDIA\s*BY\b'
]

# Consumer Care semantic indicators
CONSUMER_CARE_LABELS = [
    r'\bCONSUMER\s*CARE\b', r'\bCUSTOMER\s*CARE\b', r'\bFEEDBACK\b', r'\bQUERIES\b',
    r'\bCOMPLAINTS\b', r'\bTOLL\s*FREE\b', r'\bHELPLINE\b', r'\bCONTACT\s*US\b',
    r'\bCARE\s*CELL\b', r'\bEXECUTIVE\s*AT\b', r'\bCUSTOMER\s*SERVICE\b'
]

# Country of Origin semantic indicators
COUNTRY_ORIGIN_LABELS = [
    r'\bMADE\s*IN\b', r'\bCOUNTRY\s*OF\s*ORIGIN\b', r'\bPRODUCT\s*OF\b',
    r'\bORIGIN\b', r'\bMANUFACTURED\s*IN\b', r'\bPRODUCE\s*OF\b'
]


# ==============================================================================
# 2. VALUE PATTERNS & REGEX VALIDATORS
# ==============================================================================

# Net Quantity: Number + Unit
REGEX_QUANTITY_VALUE = re.compile(
    r'(?<!\d[xX*])(?<!\d\s[xX*])\b(\d+(?:\.\d+)?)\s*(g|gm|gms|gram|grams|kg|kgs|kilogram|kilograms|ml|millilitre|millilitres|l|ltr|ltrs|liter|liters|litre|litres|n|nos|pieces|pcs|pc|units|u|sticks|tablets|capsules|sheets|sachets|packs|pouches)\b(?!\s*[xX*]\s*\d)',
    re.IGNORECASE
)

# MRP Value: Currency + Price digits
REGEX_MRP_VALUE = re.compile(
    r'(?:(?:₹|RS\.?|INR)\s*)?([0-9]+(?:[.,][0-9]{2})?)\s*(?:/-)?(?:\s*(?:INCL\.?|INCLUSIVE)?\s*(?:OF\s*ALL\s*TAXES)?)?',
    re.IGNORECASE
)

# Date formats: standard and textual
REGEX_DATE_STANDARD = re.compile(
    r'\b(0[1-9]|1[0-2]|[1-9])[-/.](20\d{2}|\d{2})\b|\b(0[1-9]|[12]\d|3[01])[-/.](0[1-9]|1[0-2]|[1-9])[-/.](20\d{2}|\d{2})\b|\b(20\d{2})[-/.](0[1-9]|1[0-2]|[1-9])[-/.](0[1-9]|[12]\d|3[01])\b',
    re.IGNORECASE
)

REGEX_DATE_MONTH_YEAR = re.compile(
    r'\b(JAN(?:UARY)?|FEB(?:RUARY)?|MAR(?:CH)?|APR(?:IL)?|MAY|JUN(?:E)?|JUL(?:Y)?|AUG(?:UST)?|SEP(?:TEMBER)?|OCT(?:OBER)?|NOV(?:EMBER)?|DEC(?:EMBER)?)[-/\s]*(20\d{2}|\d{2})\b',
    re.IGNORECASE
)

# Relative Expiry / Best Before representation
REGEX_RELATIVE_EXPIRY = re.compile(
    r'\b(?:BEST\s*BEFORE|USE\s*WITHIN|VALID\s*FOR)?\s*(\d{1,2})\s*(MONTHS?|DAYS?|YEARS?|WEEKS?)\s*(?:FROM\s*(?:MFD|PKD|MANUFACTURE|PACKING|DATE\s*OF\s*PKD|DATE\s*OF\s*MFG))?',
    re.IGNORECASE
)

# Batch Number Pattern (alphanumeric code, avoids pure 10-digit phone or pincodes)
REGEX_BATCH_CODE = re.compile(
    r'\b([A-Z0-9]{1,4}[-/\s]?[A-Z0-9]{2,12}(?:[-/][A-Z0-9]{1,6})?)\b',
    re.IGNORECASE
)


# ==============================================================================
# 3. NORMALIZERS & SEMANTIC HELPERS
# ==============================================================================

def normalize_unit(unit_str: str) -> str:
    """Normalizes units to standard SI / Legal Metrology abbreviations."""
    u = unit_str.strip().lower()
    if u in ['g', 'gm', 'gms', 'gram', 'grams']:
        return 'g'
    if u in ['kg', 'kgs', 'kilogram', 'kilograms']:
        return 'kg'
    if u in ['ml', 'millilitre', 'millilitres']:
        return 'ml'
    if u in ['l', 'ltr', 'ltrs', 'liter', 'liters', 'litre', 'litres']:
        return 'L'
    if u in ['n', 'nos', 'number']:
        return 'N'
    if u in ['u', 'units', 'unit']:
        return 'U'
    if u in ['pcs', 'pc', 'pieces', 'piece']:
        return 'pcs'
    if u in ['sticks', 'stick']:
        return 'sticks'
    if u in ['packs', 'pack', 'pouches', 'pouch', 'sachets']:
        return 'packs'
    return u


def normalize_currency(curr_text: str) -> str:
    """Detects and normalizes currency symbol or text."""
    txt = curr_text.upper()
    if '₹' in txt or 'RS' in txt or 'INR' in txt:
        return 'INR'
    if '$' in txt or 'USD' in txt:
        return 'USD'
    if '€' in txt or 'EUR' in txt:
        return 'EUR'
    if '£' in txt or 'GBP' in txt:
        return 'GBP'
    return 'INR'


def parse_quantity_value(text: str) -> Optional[Tuple[float, str]]:
    """Extracts numeric quantity and canonical unit from text string."""
    # Guard against dimension strings like "20 x 15 cm" or "10 x 5 g"
    if re.search(r'\d+\s*[xX*]\s*\d+\s*(?:cm|mm|m|inch)', text):
        return None

    match = REGEX_QUANTITY_VALUE.search(text)
    if match:
        try:
            val_num = float(match.group(1))
            unit_norm = normalize_unit(match.group(2))
            return val_num, unit_norm
        except ValueError:
            pass
    return None


def parse_mrp_value(text: str) -> Optional[Tuple[float, str]]:
    """Extracts numeric price and currency from text string."""
    # Ensure it is not a phone number, pin code, or batch code
    clean_txt = re.sub(r'\b(?:1800|91\d{8,})\b', '', text)
    match = REGEX_MRP_VALUE.search(clean_txt)
    if match:
        raw_num = match.group(1).replace(',', '.')
        try:
            val = float(raw_num)
            if 0.1 <= val <= 100000.0:  # Reasonable packaged commodity MRP range
                curr = normalize_currency(text)
                return val, curr
        except ValueError:
            pass
    return None


def parse_date_value(text: str) -> Optional[Tuple[str, str]]:
    """Extracts date representation and identifies format."""
    # 1. Standard numeric date
    match_std = REGEX_DATE_STANDARD.search(text)
    if match_std:
        matched_str = match_std.group(0).strip()
        # Clean separator to /
        normalized = re.sub(r'[-.]', '/', matched_str)
        return normalized, "exact_date"

    # 2. Month-Year textual date (e.g. AUG 2026, JAN-26)
    match_my = REGEX_DATE_MONTH_YEAR.search(text)
    if match_my:
        month = match_my.group(1).upper()[:3]
        year = match_my.group(2)
        if len(year) == 2:
            year = f"20{year}"
        return f"{month} {year}", "month_year"

    # 3. Relative duration (e.g. Best Before 24 Months)
    match_rel = REGEX_RELATIVE_EXPIRY.search(text)
    if match_rel:
        num = match_rel.group(1)
        period = match_rel.group(2).lower()
        return f"{num} {period}", "relative_duration"

    return None
