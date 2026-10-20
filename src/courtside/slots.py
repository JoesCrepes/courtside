"""ESPN basketball lineup slot IDs.

These match espn-api's basketball POSITION_MAP. Leagues can differ, so check
them against a request captured from your own league (see docs/CAPTURE.md).
"""

SLOT_NAMES: dict[int, str] = {
    0: "PG",
    1: "SG",
    2: "SF",
    3: "PF",
    4: "C",
    5: "G",
    6: "F",
    7: "SG/SF",
    8: "G/F",
    9: "PF/C",
    10: "F/C",
    11: "UTIL",
    12: "BE",
    13: "IR",
}

SLOT_IDS: dict[str, int] = {name: sid for sid, name in SLOT_NAMES.items()}

BENCH = SLOT_IDS["BE"]
IR = SLOT_IDS["IR"]

# Slots that never count as "starting".
NON_STARTING = {BENCH, IR}


def slot_id(value: str | int) -> int:
    """Accept a slot name ("PG", "util") or numeric id."""
    if isinstance(value, int):
        return value
    if value.isdigit():
        return int(value)
    try:
        return SLOT_IDS[value.upper()]
    except KeyError:
        raise ValueError(f"unknown slot {value!r}; known: {', '.join(SLOT_IDS)}") from None


def slot_name(sid: int) -> str:
    return SLOT_NAMES.get(sid, str(sid))
