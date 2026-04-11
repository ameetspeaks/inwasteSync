import re
from datetime import datetime

def parse_iso(dt_str):
    """Robust ISO 8601 parser that handles varying fractional second precision."""
    if not dt_str: return None
    dt_str = dt_str.replace('Z', '+00:00')
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
