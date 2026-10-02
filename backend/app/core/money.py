"""Decimal-only money helpers. Floating point is forbidden (section 18)."""

from __future__ import annotations

from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_EVEN, ROUND_HALF_UP

MONEY_QUANT = Decimal("0.01")
RATE_QUANT = Decimal("0.0001")
HOURS_QUANT = Decimal("0.01")

_ROUNDING = {
    "HALF_UP": ROUND_HALF_UP,
    "HALF_EVEN": ROUND_HALF_EVEN,
    "FLOOR": ROUND_FLOOR,
}

ZERO = Decimal("0.00")


def to_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        raise TypeError("float is forbidden for money; use Decimal or str")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        return Decimal(value)
    raise TypeError(f"Cannot convert {type(value)!r} to Decimal")


def rounding_mode(name: str):
    return _ROUNDING.get((name or "HALF_UP").upper(), ROUND_HALF_UP)


def quantize_money(value: object, mode: str = "HALF_UP") -> Decimal:
    return to_decimal(value).quantize(MONEY_QUANT, rounding=rounding_mode(mode))


def quantize_rate(value: object) -> Decimal:
    return to_decimal(value).quantize(RATE_QUANT, rounding=ROUND_HALF_UP)


def quantize_hours(value: object) -> Decimal:
    return to_decimal(value).quantize(HOURS_QUANT, rounding=ROUND_HALF_UP)


def money_str(value: object, mode: str = "HALF_UP") -> str:
    return f"{quantize_money(value, mode):.2f}"


def hours_str(seconds: int) -> str:
    return f"{quantize_hours(Decimal(seconds) / Decimal(3600)):.2f}"


def percent_of(amount: object, percent: object, mode: str = "HALF_UP") -> Decimal:
    return quantize_money(to_decimal(amount) * to_decimal(percent) / Decimal(100), mode)