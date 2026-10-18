"""Wave-gated unit placement scheduling, shared by future runtime deployment workers.

This module does not perform Roblox clicks or detect waves. A placement worker must
supply the *observed* current wave and mark an index completed after a successful
placement. Deferred indexes remain pending while later eligible indexes proceed.
"""


def requested_wave(raw):
    """Blank => no restriction; otherwise require wave 1 through 9999."""
    value = str(raw or "").strip()
    if not value:
        return None
    if not value.isascii() or not value.isdecimal() or not 1 <= int(value) <= 9999:
        raise ValueError("Place at wave must be blank or a whole number from 1 to 9999.")
    return int(value)


def eligible_unit_indexes(entries, current_wave, placed_indexes=()):
    """Return ready, unplaced *zero-based* indexes without blocking on later waves.

    Unit 0/None and rows without placement coordinates are incomplete and ignored.
    Re-check each wave using the index IDs returned; only mark an index placed
    after its actual placement succeeds.
    """
    if not isinstance(current_wave, int) or current_wave < 1:
        raise ValueError("Current wave must be an integer of at least 1.")
    placed = set(placed_indexes)
    ready = []
    for index, entry in enumerate(entries):
        if index in placed:
            continue
        unit = str(entry.get("unit", "0")).removeprefix("Unit ")
        if unit not in {"1", "2", "3", "4", "5", "6"}:
            continue
        x, y = str(entry.get("x", "")).strip(), str(entry.get("y", "")).strip()
        if not x.isdecimal() or not y.isdecimal():
            continue
        required = requested_wave(entry.get("place_at_wave", ""))
        if required is None or current_wave >= required:
            ready.append(index)
    return ready
