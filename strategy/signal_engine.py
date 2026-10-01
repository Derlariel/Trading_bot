"""Build a trade plan from technical and optional news confluence."""
from __future__ import annotations

from database.models import PriceZone, SignalType, TradePlan
from risk.risk_manager import stop_loss, take_profits
from strategy.scoring import weighted_score


def classify(score: float) -> SignalType:
    if score >= 75: return SignalType.STRONG_BUY
    if score >= 35: return SignalType.BUY
    if score <= -75: return SignalType.STRONG_SELL
    if score <= -35: return SignalType.SELL
    return SignalType.WAIT


def build_zone(zone: PriceZone | None, components: dict[str, float]) -> dict[str, object] | None:
    if zone is None:
        return None
    confidence = sum(max(0, value) for value in components.values()) / max(len(components), 1) * 100
    return {"low": zone.low, "high": zone.high, "confidence": round(min(100, confidence), 2)}


def create_trade_plan(symbol: str, price: float, atr: float, support: PriceZone | None, resistance: PriceZone | None, components: dict[str, float]) -> TradePlan:
    """Produce a safe WAIT plan when a directional setup lacks its protecting level."""
    score = weighted_score(components)
    signal = classify(score)
    side = "BUY" if score > 0 else "SELL"
    protective = support if side == "BUY" else resistance
    opposing = resistance if side == "BUY" else support
    if signal == SignalType.WAIT or protective is None:
        return TradePlan(symbol, SignalType.WAIT, abs(score), (price, price), price, price, price, price, 0, ("insufficient directional confluence or protective level",))
    entry_zone = (protective.low, protective.high)
    entry = min(max(price, protective.low), protective.high)
    stop = stop_loss(side, protective, atr)
    targets = take_profits(side, entry, stop, [opposing.low if side == "BUY" else opposing.high] if opposing else [])
    rr = abs(targets[0] - entry) / abs(entry - stop)
    reasons = tuple(name for name, value in components.items() if value * (1 if side == "BUY" else -1) > .2)
    return TradePlan(symbol, signal, abs(score), entry_zone, stop, *targets, rr, reasons)
