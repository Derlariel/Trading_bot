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
    symbol_positions: int = 0
    same_direction_position: bool = False
    opposite_position: bool = False
    cooldown_remaining: float = 0


def check_trade_limits(state: TradeState) -> list[str]:
    reasons: list[str] = []
    if state.balance <= 0: reasons.append("INVALID_ACCOUNT_BALANCE")
    if state.daily_pnl <= -state.balance * settings.max_daily_loss: reasons.append("MAX_DAILY_LOSS_REACHED")
    if state.trades_today >= settings.max_trades_per_day: reasons.append("MAX_TRADES_PER_DAY_REACHED")
    if state.open_positions >= settings.max_positions: reasons.append("MAX_SIMULTANEOUS_POSITIONS_REACHED")
    if state.same_direction_position: reasons.append("SKIP_DUPLICATE_POSITION")
    if state.opposite_position and not settings.allow_hedging: reasons.append("OPPOSITE_POSITION_EXISTS")
    if state.symbol_positions >= settings.max_positions_per_symbol: reasons.append("MAX_POSITIONS_PER_SYMBOL_REACHED")
    if state.cooldown_remaining > 0: reasons.append("TRADE_COOLDOWN_ACTIVE")
    return reasons
