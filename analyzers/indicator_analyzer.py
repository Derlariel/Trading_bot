"""Vectorized technical indicators without hidden mutable state."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _wilder(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def calculate_indicators(data: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with the indicators required by the strategy."""
    required = {"open", "high", "low", "close"}
    if missing := required - set(data.columns):
        raise ValueError(f"Missing OHLC columns: {sorted(missing)}")
    frame = data.copy()
    close, high, low = frame["close"].astype(float), frame["high"].astype(float), frame["low"].astype(float)
    for period in (20, 50, 200):
        frame[f"ema{period}"] = close.ewm(span=period, adjust=False).mean()
    delta = close.diff()
    gain, loss = delta.clip(lower=0), -delta.clip(upper=0)
    rs = _wilder(gain, 14) / _wilder(loss, 14).replace(0, np.nan)
    frame["rsi"] = (100 - 100 / (1 + rs)).fillna(50)
    fast, slow = close.ewm(span=12, adjust=False).mean(), close.ewm(span=26, adjust=False).mean()
    frame["macd"], frame["macd_signal"] = fast - slow, (fast - slow).ewm(span=9, adjust=False).mean()
    previous = close.shift()
    tr = pd.concat([(high - low), (high - previous).abs(), (low - previous).abs()], axis=1).max(axis=1)
    frame["atr"] = _wilder(tr, 14).bfill()
    up, down = high.diff(), -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0), index=frame.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0), index=frame.index)
    plus_di, minus_di = 100 * _wilder(plus_dm, 14) / frame["atr"], 100 * _wilder(minus_dm, 14) / frame["atr"]
    frame["adx"] = _wilder(100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan), 14).fillna(0)
    mean, std = close.rolling(20).mean(), close.rolling(20).std()
    frame["bb_mid"], frame["bb_upper"], frame["bb_lower"] = mean, mean + 2 * std, mean - 2 * std
    lowest, highest = low.rolling(14).min(), high.rolling(14).max()
    frame["stoch_k"] = (100 * (close - lowest) / (highest - lowest).replace(0, np.nan)).fillna(50)
    frame["stoch_d"] = frame["stoch_k"].rolling(3).mean()
    volume = frame.get("real_volume", frame.get("tick_volume", pd.Series(0, index=frame.index))).astype(float)
    frame["volume"] = volume.where(volume > 0, frame.get("tick_volume", volume).astype(float))
    frame["volume_ma"] = frame["volume"].rolling(20).mean()
    frame["obv"] = (np.sign(close.diff()).fillna(0) * frame["volume"]).cumsum()
    return frame


def indicator_score(frame: pd.DataFrame) -> float:
    """Map latest indicator confluence to -1..1."""
    if frame.empty:
        return 0.0
    row = frame.iloc[-1]
    votes = [
        1 if row.rsi < 35 else -1 if row.rsi > 65 else 0,
        1 if row.macd > row.macd_signal else -1,
        1 if row.close > row.ema20 else -1,
        1 if row.stoch_k < 25 else -1 if row.stoch_k > 75 else 0,
        1 if frame.obv.iloc[-1] > frame.obv.iloc[max(0, len(frame) - 6)] else -1,
    ]
    return float(np.mean(votes))
