"""EMA, ADX, and market-structure trend classification."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from utils.helpers import clamp


def market_structure(frame: pd.DataFrame, distance: int = 3) -> str:
    """Describe the two most recent paired swing highs/lows."""
    highs, _ = find_peaks(frame.high.to_numpy(), distance=distance)
    lows, _ = find_peaks(-frame.low.to_numpy(), distance=distance)
    if len(highs) < 2 or len(lows) < 2:
        return "insufficient"
    hh = frame.high.iloc[highs[-1]] > frame.high.iloc[highs[-2]]
    hl = frame.low.iloc[lows[-1]] > frame.low.iloc[lows[-2]]
    if hh and hl:
        return "higher_high_higher_low"
    if not hh and not hl:
        return "lower_high_lower_low"
    return "mixed"


def analyze_trend(frame: pd.DataFrame) -> dict[str, float | str]:
    """Classify direction and return a 0..100 trend strength."""
    if frame.empty or not {"ema20", "ema50", "ema200", "adx"} <= set(frame.columns):
        raise ValueError("Indicator-enriched candles are required")
    row, structure = frame.iloc[-1], market_structure(frame)
    bullish = row.ema20 > row.ema50 > row.ema200
    bearish = row.ema20 < row.ema50 < row.ema200
    alignment = "bullish" if bullish else "bearish" if bearish else "mixed"
    structure_vote = 1 if structure.startswith("higher") else -1 if structure.startswith("lower") else 0
    direction = 1 if bullish else -1 if bearish else structure_vote
    trend = "bullish" if direction > 0 else "bearish" if direction < 0 else "sideway"
    separation = abs(row.ema20 - row.ema200) / max(abs(row.close), 1e-12) * 1000
    strength = clamp(float(row.adx) * .7 + min(separation, 30) + (10 if structure_vote == direction and direction else 0))
    return {"trend": trend, "strength": round(strength, 2), "ema_alignment": alignment, "adx": round(float(row.adx), 2), "market_structure": structure}
