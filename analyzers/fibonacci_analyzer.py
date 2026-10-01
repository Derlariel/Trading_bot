"""Automatic Fibonacci retracement analysis."""
from __future__ import annotations

import pandas as pd
from scipy.signal import find_peaks


def fibonacci_levels(frame: pd.DataFrame) -> dict[float, float]:
    """Calculate retracements over the latest meaningful swing range."""
    if len(frame) < 5:
        return {}
    highs, _ = find_peaks(frame.high.to_numpy(), distance=3)
    lows, _ = find_peaks(-frame.low.to_numpy(), distance=3)
    high = float(frame.high.iloc[highs[-1]] if len(highs) else frame.high.max())
    low = float(frame.low.iloc[lows[-1]] if len(lows) else frame.low.min())
    if high <= low:
        return {}
    bullish = frame.close.iloc[-1] >= frame.close.iloc[max(0, len(frame) - 20)]
    return {ratio: round((high - (high - low) * ratio) if bullish else (low + (high - low) * ratio), 8) for ratio in (0, .236, .382, .5, .618, .786, 1)}


def confluence(price: float, levels: dict[float, float], tolerance: float) -> bool:
    return any(abs(price - level) <= tolerance for level in levels.values())
