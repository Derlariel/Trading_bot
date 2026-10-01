"""Weighted confluence scoring."""
from __future__ import annotations

from config import settings
from utils.helpers import clamp


def weighted_score(components: dict[str, float]) -> float:
    """Convert named -1..1 components to a directional -100..100 score."""
    return round(clamp(sum(max(-1, min(1, components.get(name, 0))) * weight for name, weight in settings.signal_weights.items()) * 100, -100, 100), 2)
