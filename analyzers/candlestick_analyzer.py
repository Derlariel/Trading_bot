"""Practical candlestick pattern detection."""
from __future__ import annotations

import pandas as pd


def detect_pattern(frame: pd.DataFrame) -> dict[str, str | float]:
    if len(frame) < 3:
        return {"pattern": "none", "direction": "neutral", "strength": 0.0}
    a, b, c = frame.iloc[-3], frame.iloc[-2], frame.iloc[-1]
    body, span = abs(c.close - c.open), max(c.high - c.low, 1e-12)
    upper, lower = c.high - max(c.open, c.close), min(c.open, c.close) - c.low
    candidates: list[tuple[str, str, float]] = []
    if body / span <= .1: candidates.append(("doji", "neutral", 45))
    if lower >= body * 2 and upper <= max(body, span * .1): candidates.append(("hammer", "bullish", 70))
    if upper >= body * 2 and lower <= max(body, span * .1): candidates.append(("shooting_star" if c.close < c.open else "inverted_hammer", "bearish" if c.close < c.open else "bullish", 65))
    if c.close > c.open and b.close < b.open and c.open <= b.close and c.close >= b.open: candidates.append(("bullish_engulfing", "bullish", 85))
    if c.close < c.open and b.close > b.open and c.open >= b.close and c.close <= b.open: candidates.append(("bearish_engulfing", "bearish", 85))
    if c.high < b.high and c.low > b.low: candidates.append(("inside_bar", "neutral", 50))
    if lower > span * .6 or upper > span * .6: candidates.append(("pin_bar", "bullish" if lower > upper else "bearish", 60))
    if all(x.close > x.open for x in (a, b, c)) and a.close < b.close < c.close: candidates.append(("three_white_soldiers", "bullish", 90))
    if all(x.close < x.open for x in (a, b, c)) and a.close > b.close > c.close: candidates.append(("three_black_crows", "bearish", 90))
    if a.close < a.open and abs(b.close - b.open) < abs(a.close - a.open) * .4 and c.close > c.open and c.close > (a.open + a.close) / 2: candidates.append(("morning_star", "bullish", 88))
    if a.close > a.open and abs(b.close - b.open) < abs(a.close - a.open) * .4 and c.close < c.open and c.close < (a.open + a.close) / 2: candidates.append(("evening_star", "bearish", 88))
    pattern = max(candidates, key=lambda item: item[2], default=("none", "neutral", 0))
    return {"pattern": pattern[0], "direction": pattern[1], "strength": pattern[2]}
