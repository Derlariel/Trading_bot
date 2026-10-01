"""Broker-specification-aware position sizing."""
from __future__ import annotations

from decimal import Decimal, ROUND_DOWN


def normalize_volume(volume: float, step: float, minimum: float, maximum: float) -> float:
    if volume <= 0 or step <= 0 or minimum <= 0 or minimum > maximum:
        raise ValueError("Invalid volume specification")
    steps = (Decimal(str(min(volume, maximum))) / Decimal(str(step))).to_integral_value(rounding=ROUND_DOWN)
    normalized = float(steps * Decimal(str(step)))
    return round(normalized, 8) if normalized >= minimum else 0.0


def calculate_position_size(balance: float, risk_percent: float, entry: float, stop_loss: float, tick_size: float, tick_value: float, volume_step: float, volume_min: float, volume_max: float) -> float:
    """Calculate lots so stop distance loses no more than the risk budget."""
    values = (balance, risk_percent, entry, stop_loss, tick_size, tick_value, volume_step, volume_min, volume_max)
    if any(value <= 0 for value in values) or entry == stop_loss or volume_min > volume_max:
        raise ValueError("Positive broker values and non-zero stop distance are required")
    loss_per_lot = abs(entry - stop_loss) / tick_size * tick_value
    raw = balance * risk_percent / loss_per_lot
    return normalize_volume(raw, volume_step, volume_min, volume_max) if raw >= volume_min else 0.0
