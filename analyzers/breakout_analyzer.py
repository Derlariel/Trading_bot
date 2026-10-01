"""Breakout, false-breakout, and retest detection."""
from __future__ import annotations

import pandas as pd

from utils.helpers import clamp


def analyze_breakout(frame: pd.DataFrame, level: float, direction: str = "up", confirmations: int = 2) -> dict[str, object]:
    if len(frame) < max(22, confirmations + 1):
        return {"status": "NONE", "confidence": 0.0}
    recent, row = frame.tail(confirmations), frame.iloc[-1]
    above = recent.close.gt(level) if direction == "up" else recent.close.lt(level)
    crossed_intraday = row.high > level if direction == "up" else row.low < level
    wick_rejection = row.close < level if direction == "up" else row.close > level
    volume_ratio = float(row.volume / max(frame.volume.iloc[-21:-1].mean(), 1))
    body_ratio = abs(row.close - row.open) / max(row.high - row.low, 1e-12)
    atr_expansion = (row.high - row.low) / max(row.atr, 1e-12)
    if crossed_intraday and wick_rejection and (volume_ratio < 1 or body_ratio < .4):
        return {"status": "FALSE_BREAKOUT", "confidence": round(clamp((1 - min(volume_ratio, 1)) * 35 + (1 - body_ratio) * 45 + 20), 2)}
    if bool(above.all()):
        confidence = clamp(35 + min(volume_ratio, 2) * 20 + body_ratio * 25 + min(atr_expansion, 2) * 10)
        return {"status": "TRUE_BREAKOUT", "confidence": round(confidence, 2)}
    return {"status": "NONE", "confidence": 0.0}


def detect_retest(frame: pd.DataFrame, level: float, direction: str = "up", tolerance: float | None = None) -> dict[str, object]:
    if len(frame) < 4:
        return {"status": "NONE"}
    tolerance = tolerance or float(frame.atr.iloc[-1]) * .4
    row = frame.iloc[-1]
    touched = row.low <= level + tolerance if direction == "up" else row.high >= level - tolerance
    bounced = row.close > level and row.close > row.open if direction == "up" else row.close < level and row.close < row.open
    return {"status": "RETEST_CONFIRMED" if touched and bounced else "NONE", "entry_zone": (level - tolerance, level + tolerance) if touched and bounced else None}
