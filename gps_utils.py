import re
from datetime import datetime

def ensure_ist(dt_str):
    """Ensures the timestamp string has an IST offset (+05:30) if it lacks one, 
    or replaces Z/UTC with IST if user specifies it's essentially IST."""
    if not dt_str: return dt_str
    
    # If it ends with Z or has no offset, and we KNOW the device sends IST but labels it wrongly or not at all
    if dt_str.endswith('Z'):
        return dt_str.replace('Z', '+05:30')
    if '+' not in dt_str and '-' not in dt_str[10:]: # Look for offset after the date part
        return f"{dt_str}+05:30"
    return dt_str

def parse_iso(dt_str):
    """Robust ISO 8601 parser that handles varying fractional second precision."""
    if not dt_str: return None
    
    dt_str = ensure_ist(dt_str)
    
    # If there's a fractional part, Python 3.7-3.10 fromisoformat is picky (expects 3 or 6 digits)
    if '.' in dt_str:
        prefix, rest = dt_str.split('.', 1)
        # Find where the timezone/offset starts
        tz_match = re.search(r'[Z+-]', rest)
        if tz_match:
            frac = rest[:tz_match.start()]
            suffix = rest[tz_match.start():]
            # Pad or truncate fractional part to 6 digits
            frac = frac.ljust(6, '0')[:6]
            dt_str = f"{prefix}.{frac}{suffix}"
        else:
            # No timezone
            frac = rest.ljust(6, '0')[:6]
            dt_str = f"{prefix}.{frac}"
    return datetime.fromisoformat(dt_str)
