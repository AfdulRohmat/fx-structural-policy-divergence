"""Deterministic month-end helpers."""

from __future__ import annotations

import calendar
from datetime import date


def month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def add_months(value: date, months: int) -> date:
    index = value.year * 12 + value.month - 1 + months
    year, zero_based = divmod(index, 12)
    return month_end(year, zero_based + 1)


def month_ends(start: date, end: date) -> tuple[date, ...]:
    if end < start:
        raise ValueError("month-end range is reversed")
    cursor = month_end(start.year, start.month)
    final = month_end(end.year, end.month)
    result: list[date] = []
    while cursor <= final:
        result.append(cursor)
        cursor = add_months(cursor, 1)
    return tuple(result)
