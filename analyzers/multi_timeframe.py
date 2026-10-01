"""Aggregate trend evidence across configured timeframes."""
from __future__ import annotations


def aggregate_trends(trends: dict[str, dict[str, object]]) -> dict[str, object]:
    weights = {"H4": .4, "H1": .3, "M15": .2, "M5": .1}
    direction = {"bullish": 1, "sideway": 0, "bearish": -1}
    score = sum(direction.get(str(value.get("trend")), 0) * weights.get(timeframe, 0) for timeframe, value in trends.items())
    label = "STRONG BUY CONFIRMATION" if score >= .75 else "BUY CONFIRMATION" if score >= .3 else "STRONG SELL CONFIRMATION" if score <= -.75 else "SELL CONFIRMATION" if score <= -.3 else "MIXED"
    return {"score": round(score, 3), "label": label, "timeframes": {key: value.get("trend") for key, value in trends.items()}}
