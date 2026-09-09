"""Field parsing shared by the entry form and the inline table editor.

Entry time is typed freely to the minute and normalised on save. Storage is
zero-padded 'HH:MM' so the column sorts lexicographically and the bucket
arithmetic in v_trade works; display is unpadded because that is what reads
naturally. Nothing here rounds or snaps to an interval -- the buckets in
v_trade are an analytical grouping only.
"""

from __future__ import annotations

import re
from datetime import datetime

_TIME_PATTERNS = (
    re.compile(r"^(?P<h>\d{1,2}):(?P<m>\d{2})$"),
    re.compile(r"^(?P<h>\d{1,2})(?P<m>\d{2})$"),
    re.compile(r"^(?P<h>\d{1,2}):(?P<m>\d{2})\s*(?P<ap>[ap])\.?m\.?$", re.I),
    re.compile(r"^(?P<h>\d{1,2})\s*(?P<ap>[ap])\.?m\.?$", re.I),
)


class FieldError(ValueError):
    """Raised when a typed value cannot be interpreted."""


def normalize_time(raw: str) -> str:
    """'934' | '9:34' | '9:34am' | '09:34' -> '09:34'. Minute precision kept."""
    text = (raw or "").strip()
    if not text:
        raise FieldError("time is required")

    for pattern in _TIME_PATTERNS:
        match = pattern.match(text)
        if not match:
            continue
        hour = int(match.group("h"))
        minute = int(match.groupdict().get("m") or 0)
        meridiem = (match.groupdict().get("ap") or "").lower()

        if meridiem:
            if not 1 <= hour <= 12:
                raise FieldError(f"{raw!r}: hour must be 1-12 with am/pm")
            hour = hour % 12 + (12 if meridiem == "p" else 0)
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise FieldError(f"{raw!r}: not a valid time of day")
        return f"{hour:02d}:{minute:02d}"

    raise FieldError(f"{raw!r}: expected a time like 9:34, 934 or 9:34am")


def display_time(stored: str) -> str:
    """'09:34' -> '9:34'. Purely cosmetic; storage is untouched."""
    if not stored:
        return ""
    hour, _, minute = stored.partition(":")
    return f"{int(hour)}:{minute}"


def display_date(stored: str) -> str:
    """'2026-07-09' -> '07/09/2026'. Purely cosmetic; storage stays ISO.

    Storage has to remain ISO -- it is what sorts correctly, what strftime in
    v_trade reads, and what every query compares against. This is only for
    text the user reads, so the app shows one date format throughout.
    """
    if not stored:
        return ""
    try:
        return datetime.strptime(str(stored), "%Y-%m-%d").strftime("%m/%d/%Y")
    except ValueError:
        return str(stored)


def parse_rr(raw: str) -> float:
    text = (raw or "").strip()
    if not text:
        raise FieldError("RR is required")
    try:
        value = float(text)
    except ValueError as exc:
        raise FieldError(f"{raw!r}: not a number") from exc
    if value <= 0:
        raise FieldError(f"{raw!r}: RR must be greater than 0")
    return value
