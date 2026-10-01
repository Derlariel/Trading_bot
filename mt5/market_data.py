"""Validated MT5 market-data access."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import pandas as pd

from mt5.connector import MT5Connector, native_mt5

COLUMNS = ["time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"]


class MarketData:
    """Return normalized candles and ticks from an active connector."""

    def __init__(self, connector: MT5Connector) -> None:
        self.connector = connector

    @staticmethod
    @lru_cache(maxsize=16)
    def timeframe_value(timeframe: str) -> int:
        if native_mt5 is None:
            raise RuntimeError("MetaTrader5 is not installed")
        mapping = {name: getattr(native_mt5, f"TIMEFRAME_{name}") for name in ("M1", "M5", "M15", "M30", "H1", "H4", "D1")}
        try:
            return mapping[timeframe.upper()]
        except KeyError as error:
            raise ValueError(f"Unsupported timeframe: {timeframe}") from error

    def get_candles(self, symbol: str, timeframe: str, count: int = 500) -> pd.DataFrame:
        if count < 2:
            raise ValueError("count must be at least 2")
        if not self.connector.is_connected() or native_mt5 is None:
            raise ConnectionError("MT5 is disconnected")
        rates = native_mt5.copy_rates_from_pos(symbol, self.timeframe_value(timeframe), 0, count)
        if rates is None or not len(rates):
            raise ValueError(f"No candle data for {symbol} {timeframe}: {native_mt5.last_error()}")
        frame = pd.DataFrame(rates)
        frame["time"] = pd.to_datetime(frame["time"], unit="s", utc=True)
        for column in COLUMNS:
            if column not in frame:
                frame[column] = 0
        return frame[COLUMNS]

    def get_tick(self, symbol: str) -> dict[str, Any]:
        if not self.connector.is_connected() or native_mt5 is None:
            raise ConnectionError("MT5 is disconnected")
        tick = native_mt5.symbol_info_tick(symbol)
        if tick is None:
            raise ValueError(f"No tick for {symbol}")
        data = tick._asdict()
        data["time"] = pd.to_datetime(data["time"], unit="s", utc=True)
        data["spread"] = float(data.get("ask", 0) - data.get("bid", 0))
        return data
