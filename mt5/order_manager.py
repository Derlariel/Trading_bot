"""Guarded live execution and local paper execution."""
from __future__ import annotations

from typing import Any

from config import settings
from database.database import Database
from mt5.connector import MT5Connector, native_mt5
from risk.risk_manager import RiskDecision
from utils.logger import get_logger

logger = get_logger(__name__)


class OrderManager:
    """Send an order only after explicit live configuration and risk approval."""

    def __init__(self, connector: MT5Connector, database: Database) -> None:
        self.connector, self.database = connector, database

    def market_order(self, symbol: str, side: str, volume: float, stop_loss: float, take_profit: float, risk_decision: RiskDecision) -> dict[str, Any]:
        side = side.upper()
        if side not in {"BUY", "SELL"} or volume <= 0 or stop_loss <= 0 or take_profit <= 0:
            raise ValueError("Invalid order parameters")
        if not risk_decision.approved:
            raise PermissionError(f"Risk manager rejected order: {', '.join(risk_decision.reasons)}")
        tick = self.connector.is_connected() and native_mt5.symbol_info_tick(symbol) if native_mt5 else None
        price = float((tick.ask if side == "BUY" else tick.bid) if tick else 0)
        if settings.demo_mode or not settings.live_trading:
            trade_id = self.database.save_trade(symbol, side, volume, price, stop_loss, take_profit)
            logger.info("Paper order %s %s %.2f", side, symbol, volume)
            return {"ok": True, "paper": True, "trade_id": trade_id, "price": price}
        if not self.connector.is_connected() or native_mt5 is None:
            raise ConnectionError("Live trading requested but MT5 is disconnected")
        request = {
            "action": native_mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": volume,
            "type": native_mt5.ORDER_TYPE_BUY if side == "BUY" else native_mt5.ORDER_TYPE_SELL,
            "price": price, "sl": stop_loss, "tp": take_profit, "deviation": settings.deviation,
            "magic": settings.magic_number, "comment": "AI-assisted rule bot",
            "type_time": native_mt5.ORDER_TIME_GTC, "type_filling": native_mt5.ORDER_FILLING_IOC,
        }
        result = native_mt5.order_send(request)
        ok = bool(result and result.retcode == native_mt5.TRADE_RETCODE_DONE)
        if not ok:
            logger.error("Order failed: %s", result)
        return {"ok": ok, "paper": False, "result": result._asdict() if result else None}
