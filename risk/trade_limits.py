"""Daily and portfolio exposure limits."""
from __future__ import annotations

from dataclasses import dataclass

from config import settings


@dataclass(frozen=True)
class TradeState:
    balance: float
    daily_pnl: float
    trades_today: int
    open_positions: int
    has_symbol_position: bool = False


def check_trade_limits(state: TradeState) -> list[str]:
    reasons: list[str] = []
    if state.balance <= 0: reasons.append("invalid account balance")
    if state.daily_pnl <= -state.balance * settings.max_daily_loss: reasons.append("maximum daily loss reached")
    if state.trades_today >= settings.max_trades_per_day: reasons.append("maximum trades reached")
    if state.open_positions >= settings.max_positions: reasons.append("maximum open positions reached")
    if state.has_symbol_position: reasons.append("symbol already has a position")
    return reasons
