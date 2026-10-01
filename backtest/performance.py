"""Performance metrics from a series of completed trade returns."""
from __future__ import annotations

import numpy as np
import pandas as pd


def metrics(returns: pd.Series, initial_cash: float = 10_000) -> dict[str, float]:
    clean = returns.dropna().astype(float)
    wins, losses = clean[clean > 0], clean[clean < 0]
    equity = initial_cash + clean.cumsum()
    drawdown = (equity - equity.cummax()) / equity.cummax()
    gross_profit, gross_loss = wins.sum(), abs(losses.sum())
    return {
        "total_return": float(clean.sum() / initial_cash * 100),
        "win_rate": float(len(wins) / len(clean) * 100) if len(clean) else 0,
        "loss_rate": float(len(losses) / len(clean) * 100) if len(clean) else 0,
        "profit_factor": float(gross_profit / gross_loss) if gross_loss else float("inf") if gross_profit else 0,
        "sharpe_ratio": float(clean.mean() / clean.std(ddof=1) * np.sqrt(252)) if len(clean) > 1 and clean.std(ddof=1) else 0,
        "max_drawdown": float(drawdown.min() * 100) if len(drawdown) else 0,
        "average_profit": float(wins.mean()) if len(wins) else 0,
        "average_loss": float(losses.mean()) if len(losses) else 0,
        "risk_reward": float(wins.mean() / abs(losses.mean())) if len(wins) and len(losses) else 0,
        "number_of_trades": float(len(clean)),
        "expectancy": float(clean.mean()) if len(clean) else 0,
        "total_profit": float(clean.sum()),
    }
