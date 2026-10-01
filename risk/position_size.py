"""Broker-specification-aware position sizing."""
from __future__ import annotations

from decimal import Decimal, ROUND_DOWN


def calculate_position_size(balance: float, risk_percent: float, entry: float, stop_loss: float, tick_size: float, tick_value: float, volume_step: float, volume_min: float, volume_max: float) -> float:
    """Calculate lots so stop distance loses no more than the risk budget."""
    values = (balance, risk_percent, entry, stop_loss, tick_size, tick_value, volume_step, volume_min, volume_max)
    if any(value <= 0 for value in values) or entry == stop_loss or volume_min > volume_max:
        raise ValueError("Positive broker values and non-zero stop distance are required")
    loss_per_lot = abs(entry - stop_loss) / tick_size * tick_value
    raw = balance * risk_percent / loss_per_lot
    steps = (Decimal(str(raw)) / Decimal(str(volume_step))).to_integral_value(rounding=ROUND_DOWN)
    size = float(steps * Decimal(str(volume_step)))
    return round(min(volume_max, max(volume_min, size)), 8) if raw >= volume_min else 0.0
