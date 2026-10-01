"""Stop/target construction and final pre-trade validation."""
from __future__ import annotations

from dataclasses import dataclass

from config import settings
from database.models import PriceZone
from risk.trade_limits import TradeState, check_trade_limits


def stop_loss(side: str, zone: PriceZone, atr: float, multiplier: float = settings.atr_multiplier) -> float:
    if atr <= 0 or multiplier <= 0:
        raise ValueError("ATR and multiplier must be positive")
    return float(zone.low - atr * multiplier if side.upper() == "BUY" else zone.high + atr * multiplier)


def take_profits(side: str, entry: float, stop: float, opposing_levels: list[float] | None = None, minimum_rr: float = settings.min_rr) -> tuple[float, float, float]:
    """Use valid opposing levels, falling back to 2R/3R/4R targets."""
    risk, direction = abs(entry - stop), 1 if side.upper() == "BUY" else -1
    if risk <= 0:
        raise ValueError("Entry and stop must differ")
    minimum = entry + direction * risk * minimum_rr
    candidates = sorted([value for value in (opposing_levels or []) if (value - minimum) * direction >= 0], reverse=direction < 0)
    targets = candidates[:3]
    for rr in (minimum_rr, minimum_rr + 1, minimum_rr + 2):
        target = entry + direction * risk * rr
        if len(targets) < 3 and all(abs(target - used) > risk * .2 for used in targets):
            targets.append(target)
    return tuple(sorted(targets[:3], reverse=direction < 0))  # type: ignore[return-value]


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reasons: tuple[str, ...]


def validate_trade(state: TradeState, confidence: float, risk_reward: float, spread_points: float, market_open: bool, news_risk: float = 0) -> RiskDecision:
    reasons = check_trade_limits(state)
    if confidence < settings.min_confidence: reasons.append("signal confidence below minimum")
    if risk_reward < settings.min_rr: reasons.append("risk/reward below minimum")
    if spread_points > settings.max_spread_points: reasons.append("spread too high")
    if not market_open: reasons.append("market closed")
    if news_risk >= .8: reasons.append("high-impact news risk")
    return RiskDecision(not reasons, tuple(reasons))
