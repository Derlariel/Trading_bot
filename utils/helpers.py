"""Small numerical helpers."""
from __future__ import annotations


def clamp(value: float, low: float = 0, high: float = 100) -> float:
    """Clamp value to an inclusive range."""
    return max(low, min(high, value))


def safe_float(value: object, default: float = 0.0) -> float:
    """Convert nullable numeric values safely."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
