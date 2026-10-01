"""MT5 terminal lifecycle and account queries."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from config import settings
from utils.logger import get_logger

try:
    import MetaTrader5 as native_mt5
except ImportError:  # MT5 officially supports Windows; analysis remains portable.
    native_mt5 = None

logger = get_logger(__name__)


def _dict(value: Any) -> dict[str, Any]:
    return value._asdict() if hasattr(value, "_asdict") else {}


class MT5Connector:
    """Own an MT5 connection without hiding terminal errors."""

    def __init__(self) -> None:
        self.connected = False

    def initialize(self) -> bool:
        if native_mt5 is None:
            logger.warning("MetaTrader5 package unavailable; analysis/demo features remain usable")
            return False
        if not native_mt5.initialize():
            logger.error("MT5 initialize failed: %s", native_mt5.last_error())
            return False
        if settings.mt5_login and not native_mt5.login(settings.mt5_login, settings.mt5_password, settings.mt5_server):
            logger.error("MT5 login failed: %s", native_mt5.last_error())
            native_mt5.shutdown()
            return False
        self.connected = native_mt5.terminal_info() is not None
        logger.info("MT5 connection: %s", self.connected)
        return self.connected

    def disconnect(self) -> None:
        if native_mt5:
            native_mt5.shutdown()
        self.connected = False

    def is_connected(self) -> bool:
        self.connected = bool(native_mt5 and native_mt5.terminal_info())
        return self.connected

    def account_info(self) -> dict[str, Any]:
        return _dict(native_mt5.account_info()) if self.is_connected() else {}

    def account_summary(self) -> dict[str, float]:
        info = self.account_info()
        summary = {key: float(info.get(key, 0)) for key in ("balance", "equity", "margin", "margin_free")}
        summary["free_margin"] = summary["margin_free"]
        return summary

    def positions(self, symbol: str | None = None) -> list[dict[str, Any]]:
        if not self.is_connected():
            return []
        rows = native_mt5.positions_get(symbol=symbol) if symbol else native_mt5.positions_get()
        return [_dict(row) for row in (rows or [])]

    def pending_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        if not self.is_connected():
            return []
        rows = native_mt5.orders_get(symbol=symbol) if symbol else native_mt5.orders_get()
        return [_dict(row) for row in (rows or [])]

    def trade_history(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        if not self.is_connected():
            return []
        return [_dict(row) for row in (native_mt5.history_deals_get(start, end) or [])]

    def symbol_info(self, symbol: str) -> dict[str, Any]:
        if not self.is_connected():
            return {}
        info = native_mt5.symbol_info(symbol)
        if info is None:
            logger.error("Invalid/unavailable MT5 symbol: %s", symbol)
        return _dict(info)
