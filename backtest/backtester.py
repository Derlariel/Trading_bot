"""Small event-driven backtester for this project's trade-plan contract."""
from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from backtest.performance import metrics
from database.models import SignalType, TradePlan


def run_backtest(candles: pd.DataFrame, strategy: Callable[[pd.DataFrame], TradePlan], warmup: int = 220, cash: float = 10_000, risk_fraction: float = .01) -> dict[str, object]:
    """Open one trade at a time and resolve SL/TP1 conservatively per candle."""
    trades: list[dict[str, object]] = []
    position: dict[str, object] | None = None
    for i in range(warmup, len(candles)):
        row = candles.iloc[i]
        if position:
            side, stop, target = position["side"], float(position["stop"]), float(position["target"])
            stop_hit = row.low <= stop if side == "BUY" else row.high >= stop
            target_hit = row.high >= target if side == "BUY" else row.low <= target
            if stop_hit or target_hit:
                exit_price = stop if stop_hit else target  # conservative if both touched
                pnl = (exit_price - float(position["entry"])) * (1 if side == "BUY" else -1) * float(position["size"])
                trades.append({**position, "exit": exit_price, "pnl": pnl, "exit_time": row.get("time", i)})
                cash += pnl
                position = None
            continue
        plan = strategy(candles.iloc[: i + 1])
        if plan.signal == SignalType.WAIT:
            continue
        side = "BUY" if plan.signal in {SignalType.BUY, SignalType.STRONG_BUY} else "SELL"
        entry, risk = float(row.close), abs(float(row.close) - plan.stop_loss)
        if risk > 0:
            position = {"side": side, "entry": entry, "stop": plan.stop_loss, "target": plan.tp1, "size": cash * risk_fraction / risk, "entry_time": row.get("time", i)}
    result = metrics(pd.Series([float(trade["pnl"]) for trade in trades]), cash if not trades else cash - sum(float(t["pnl"]) for t in trades))
    return {"metrics": result, "trades": trades}
