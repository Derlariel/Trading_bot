"""End-to-end rule-based market analysis."""
from __future__ import annotations

import pandas as pd

from analyzers.breakout_analyzer import analyze_breakout
from analyzers.candlestick_analyzer import detect_pattern
from analyzers.fibonacci_analyzer import confluence, fibonacci_levels
from analyzers.indicator_analyzer import calculate_indicators, indicator_score
from analyzers.support_resistance import find_zones, select_levels
from analyzers.trend_analyzer import analyze_trend
from analyzers.volume_analyzer import analyze_volume
from strategy.signal_engine import build_zone, create_trade_plan


def analyze(symbol: str, candles: pd.DataFrame, multi_timeframe_score: float = 0, news_score: float = 0) -> dict[str, object]:
    """Analyze candles; news can influence but cannot create a trade alone."""
    frame = calculate_indicators(candles)
    trend, zones = analyze_trend(frame), find_zones(frame)
    selected = select_levels(zones, float(frame.close.iloc[-1]))
    support, resistance = selected["nearest_support"], selected["nearest_resistance"]
    candle, volume = detect_pattern(frame), analyze_volume(frame)
    direction = 1 if candle["direction"] == "bullish" else -1 if candle["direction"] == "bearish" else 0
    breakout = analyze_breakout(frame, resistance.low, "up") if resistance else {"status": "NONE", "confidence": 0}
    fib = fibonacci_levels(frame)
    level_score = 0.0
    price, atr = float(frame.close.iloc[-1]), float(frame.atr.iloc[-1])
    if support and price - support.high <= atr: level_score += support.strength / 100
    if resistance and resistance.low - price <= atr: level_score -= resistance.strength / 100
    if support and confluence((support.low + support.high) / 2, fib, atr * .35): level_score += .15
    trend_sign = 1 if trend["trend"] == "bullish" else -1 if trend["trend"] == "bearish" else 0
    components = {
        "trend": trend_sign * float(trend["strength"]) / 100,
        "levels": max(-1, min(1, level_score)),
        "indicators": indicator_score(frame),
        "volume": (1 if volume["trend"] == "rising" else -1) * (.8 if volume["spike"] else .4),
        "candlestick": direction * float(candle["strength"]) / 100,
        "breakout": float(breakout["confidence"]) / 100 if breakout["status"] == "TRUE_BREAKOUT" else -.5 if breakout["status"] == "FALSE_BREAKOUT" else 0,
        "multi_timeframe": multi_timeframe_score,
    }
    # News may confirm at least two aligned technical factors, never originate a trade.
    confirmations = sum(value * news_score > 0 and abs(value) >= .25 for value in components.values())
    components["news"] = news_score if confirmations >= 2 else 0
    plan = create_trade_plan(symbol, price, atr, support, resistance, components)
    return {"plan": plan, "candles": frame, "trend": trend, "zones": zones, "levels": selected, "buy_zone": build_zone(support, components), "sell_zone": build_zone(resistance, {k: -v for k, v in components.items()}), "indicators": frame.iloc[-1].to_dict(), "volume": volume, "candlestick": candle, "breakout": breakout, "fibonacci": fib, "components": components}
