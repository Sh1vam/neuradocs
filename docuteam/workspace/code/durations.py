import re


def parse_duration(s):
    """
    Parse a duration string like '1h30m' into total seconds.

    Supported units:
        h - hours
        m - minutes
        s - seconds

    The units must appear in the order h, then m, then s, without repetition.
    Leading zeros are allowed. Any deviation raises ValueError.
    """
    if not isinstance(s, str):
        raise ValueError("Input must be a string")
    if not s:
        raise ValueError("Empty string is not a valid duration")

    # Find all number-unit pairs
    pattern = re.compile(r'(\d+)([hms])')
    matches = list(pattern.finditer(s))

    # Ensure the whole string is consumed by matches
    consumed = "".join(m.group(0) for m in matches)
    if consumed != s:
        raise ValueError("Invalid format")

    total_seconds = 0
    seen_units = set()
    last_index = -1
    unit_order = {"h": 0, "m": 1, "s": 2}
    multipliers = {"h": 3600, "m": 60, "s": 1}

    for match in matches:
        value_str, unit = match.groups()
        if unit in seen_units:
            raise ValueError("Duplicate unit")
        current_index = unit_order[unit]
        if current_index < last_index:
            raise ValueError("Units out of order")
        seen_units.add(unit)
        last_index = current_index

        value = int(value_str)
        total_seconds += value * multipliers[unit]

    return total_seconds
