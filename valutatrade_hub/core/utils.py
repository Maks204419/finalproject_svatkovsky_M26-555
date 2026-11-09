"""Shared validators and rate conversion helpers."""

import math
from datetime import datetime, timezone

from .exceptions import ValidationError


def positive_amount(value: float) -> float:
    """Require a finite, strictly positive numeric amount."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError("'amount' должен быть положительным числом")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValidationError("'amount' должен быть положительным числом")
    return result


def currency_code(value: str) -> str:
    """Validate normalized 2–5-letter currency ticker."""
    if (
        not isinstance(value, str)
        or not (2 <= len(value) <= 5)
        or not value.isascii()
        or not value.isalpha()
        or value != value.upper()
    ):
        raise ValidationError("Код валюты: 2–5 латинских букв в верхнем регистре")
    return value


def utc_now() -> str:
    """Return a UTC ISO-8601 timestamp."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str) -> datetime:
    """Parse ISO-8601 timestamp as timezone-aware UTC."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
