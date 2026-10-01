"""Guarded live execution and local paper execution."""
from __future__ import annotations

from datetime import UTC, datetime
import time
from typing import Any

from config import settings
from database.database import Database, WORKER_LEASE_SECONDS
from database.models import SignalType, TradePlan
from mt5.connector import MT5Connector, native_mt5
from risk.position_size import calculate_position_size
from risk.risk_manager import RiskDecision, validate_trade
from risk.trade_limits import TradeState, check_trade_limits
from utils.logger import get_logger

logger = get_logger(__name__)


class OrderManager:
    """Run every safety check immediately before the single order-send path."""

    def __init__(self, connector: MT5Connector, database: Database, worker_id: str | None = None) -> None:
        self.connector, self.database = connector, database
        self.worker_id = worker_id

    def _runtime_guard(self, *, automatic: bool = True) -> tuple[str | None, str | None]:
        try:
            state = self.database.runtime_state()
            mode = state.get("mode")
            if state.get("stop_requested") or mode == "PAUSED":
                return mode, "SYSTEM_PAUSED"
            if mode == "MANUAL" or (automatic and mode is None and not settings.auto_trade):
                return mode, "MANUAL_MODE"
            if self.worker_id and (state.get("worker_id") != self.worker_id or time.time() - (state.get("heartbeat") or 0) >= WORKER_LEASE_SECONDS):
                return mode, "WORKER_LEASE_LOST"
            if (mode == "AUTO_DEMO" or getattr(settings, "demo_mode", False)) and self.connector.account_info().get("trade_mode") != getattr(native_mt5, "ACCOUNT_TRADE_MODE_DEMO", 0):
                return mode, "DEMO_ACCOUNT_REQUIRED"
            return mode, None
        except Exception:
            logger.exception("Runtime control unavailable; execution blocked")
            return None, "RUNTIME_CONTROL_UNAVAILABLE"

    def _skip(self, plan: TradePlan, timeframe: str, reason: str, **details: Any) -> dict[str, Any]:
        event = {"decision": "SKIP", "reason": reason, "symbol": plan.symbol, "timeframe": timeframe, "signal": plan.signal.value, "confidence": plan.confidence, "rr": plan.risk_reward, **details}
        try:
            self.database.save_bot_log("INFO", event)
        except Exception:
            logger.exception("Could not persist blocked execution")
        logger.info("decision=SKIP reason=%s symbol=%s timeframe=%s signal=%s confidence=%.2f rr=%.2f", reason, plan.symbol, timeframe, plan.signal.value, plan.confidence, plan.risk_reward)
        return {"ok": False, **event}

    def _trade_state(self, symbol: str, side: str, now: datetime, account: dict[str, Any], broker_orders: bool) -> TradeState:
        positions = [row for row in self.connector.positions() if int(row.get("magic", 0)) == settings.magic_number]
        symbol_positions = [row for row in positions if row.get("symbol") == symbol]
        side_type = native_mt5.POSITION_TYPE_BUY if side == "BUY" else native_mt5.POSITION_TYPE_SELL
        history = [row for row in self.connector.trade_history(now.replace(hour=0, minute=0, second=0, microsecond=0), now) if int(row.get("magic", 0)) == settings.magic_number]
        paper = self.database.rows("trades") if not broker_orders else []
        paper_today = [row for row in paper if datetime.fromisoformat(row["created_at"]).date() == now.date()]
        local_open = [row for row in paper if row["status"] in {"PAPER", "OPEN"}]
        last = self.database.last_executed_signal(symbol)
        elapsed = (now - datetime.fromisoformat(last["executed_at"])).total_seconds() / 60 if last and last.get("executed_at") else float("inf")
        daily_pnl = sum(float(row.get(key, 0)) for row in history for key in ("profit", "commission", "swap", "fee"))
        daily_pnl += sum(float(row.get("profit", 0)) for row in positions) + sum(float(row.get("pnl", 0)) for row in paper_today)
        return TradeState(
            balance=float(account.get("balance", 0)), daily_pnl=daily_pnl,
            trades_today=sum(row.get("entry") == native_mt5.DEAL_ENTRY_IN for row in history) + len(paper_today),
            open_positions=len(positions) + len(local_open),
            symbol_positions=len(symbol_positions) + sum(row.get("symbol") == symbol for row in local_open),
            same_direction_position=any(row.get("type") == side_type for row in symbol_positions) or any(row.get("symbol") == symbol and row.get("side") == side for row in local_open),
            opposite_position=any(row.get("type") != side_type for row in symbol_positions) or any(row.get("symbol") == symbol and row.get("side") != side for row in local_open),
            cooldown_remaining=max(0.0, settings.trade_cooldown_minutes - elapsed),
        )

    def auto_order(self, plan: TradePlan, timeframe: str, candle_time: Any) -> dict[str, Any]:
        candle = candle_time.isoformat() if hasattr(candle_time, "isoformat") else str(candle_time)
        mode, blocked = self._runtime_guard()
        if blocked:
            return self._skip(plan, timeframe, blocked)
        if plan.signal is SignalType.WAIT:
            self.database.update_signal_state(plan.symbol, timeframe, "WAIT", candle)
            return self._skip(plan, timeframe, "NO_TRADE_SIGNAL")

        side = "BUY" if "BUY" in plan.signal.value else "SELL"
        setup_id = f"{plan.symbol}|{timeframe}|{side}|{candle}"
        previous_signal = self.database.update_signal_state(plan.symbol, timeframe, side, candle)
        if self.database.signal_exists(setup_id):
            return self._skip(plan, timeframe, "SIGNAL_ALREADY_EXECUTED", setup_id=setup_id)

        account, spec = self.connector.account_info(), self.connector.symbol_info(plan.symbol)
        tick = self.connector.is_connected() and native_mt5.symbol_info_tick(plan.symbol) if native_mt5 else None
        if not account or not spec or tick is None:
            return self._skip(plan, timeframe, "MARKET_DATA_UNAVAILABLE", setup_id=setup_id)
        price = float(tick.ask if side == "BUY" else tick.bid)
        now = datetime.now(UTC)
        broker_orders = mode == "AUTO_DEMO" or settings.demo_mode or settings.live_trading
        state = self._trade_state(plan.symbol, side, now, account, broker_orders)
        limit_reasons = check_trade_limits(state)
        if limit_reasons:
            return self._skip(plan, timeframe, limit_reasons[0], setup_id=setup_id, all_reasons=tuple(limit_reasons), cooldown_remaining=state.cooldown_remaining)
        if plan.confidence < settings.min_confidence:
            return self._skip(plan, timeframe, "CONFIDENCE_TOO_LOW", setup_id=setup_id, previous_signal=previous_signal)
        if len({price, plan.stop_loss, plan.tp1}) < 3 or (side == "BUY" and not plan.stop_loss < price < plan.tp1) or (side == "SELL" and not plan.tp1 < price < plan.stop_loss):
            return self._skip(plan, timeframe, "INVALID_PROTECTIVE_LEVELS", setup_id=setup_id)
        if not plan.entry_zone[0] <= price <= plan.entry_zone[1]:
            return self._skip(plan, timeframe, "PRICE_OUTSIDE_ENTRY_ZONE", setup_id=setup_id)

        rr = abs(plan.tp1 - price) / abs(price - plan.stop_loss)
        if rr < settings.min_rr:
            return self._skip(plan, timeframe, "RISK_REWARD_TOO_LOW", setup_id=setup_id, actual_rr=rr)
        point = float(spec.get("point", 0))
        spread_points = float(tick.ask - tick.bid) / point if point > 0 else float("inf")
        market_open = bool(account.get("trade_allowed") and (not broker_orders or account.get("trade_expert")) and spec.get("trade_mode") != native_mt5.SYMBOL_TRADE_MODE_DISABLED and now.timestamp() - float(tick.time) < 120)
        decision = validate_trade(state, plan.confidence, rr, spread_points, market_open)
        if not decision.approved:
            return self._skip(plan, timeframe, decision.reasons[0], setup_id=setup_id, all_reasons=decision.reasons, cooldown_remaining=state.cooldown_remaining)

        try:
            volume = calculate_position_size(
                state.balance, settings.risk_per_trade, price, plan.stop_loss,
                float(spec["trade_tick_size"]), float(spec["trade_tick_value"]),
                float(spec["volume_step"]), float(spec["volume_min"]), float(spec["volume_max"]),
            )
        except (KeyError, ValueError):
            return self._skip(plan, timeframe, "INVALID_BROKER_VOLUME_SPEC", setup_id=setup_id)
        if volume <= 0:
            return self._skip(plan, timeframe, "VOLUME_BELOW_BROKER_MINIMUM", setup_id=setup_id)
        expected_loss = abs(price - plan.stop_loss) / float(spec["trade_tick_size"]) * float(spec["trade_tick_value"]) * volume
        if expected_loss > state.balance * settings.max_risk_per_trade:
            return self._skip(plan, timeframe, "MAX_RISK_PER_TRADE_EXCEEDED", setup_id=setup_id)
        if not self.database.reserve_signal(setup_id, plan.symbol, timeframe, side, candle):
            return self._skip(plan, timeframe, "SIGNAL_ALREADY_EXECUTED", setup_id=setup_id)

        digits = int(spec.get("digits", 2))
        result = self.market_order(plan.symbol, side, volume, round(plan.stop_loss, digits), round(plan.tp1, digits), decision)
        if not result.get("ok"):
            self.database.release_signal(setup_id)
            return self._skip(plan, timeframe, "ORDER_REJECTED", setup_id=setup_id, order_result=result)
        ticket = result.get("trade_id") if result.get("paper") else (result.get("result") or {}).get("order")
        self.database.complete_signal(setup_id, ticket)
        event = {"decision": "EXECUTE", "reason": "ORDER_EXECUTED", "symbol": plan.symbol, "timeframe": timeframe, "signal": side, "confidence": plan.confidence, "rr": rr, "setup_id": setup_id, "volume": volume, "entry": result.get("price", price), "sl": plan.stop_loss, "tp": plan.tp1, "ticket": ticket}
        self.database.save_bot_log("INFO", event)
        logger.info("decision=EXECUTE symbol=%s timeframe=%s signal=%s volume=%s entry=%s sl=%s tp=%s", plan.symbol, timeframe, side, volume, event["entry"], plan.stop_loss, plan.tp1)
        return {"ok": True, **event, "paper": result.get("paper", False)}

    def market_order(self, symbol: str, side: str, volume: float, stop_loss: float, take_profit: float, risk_decision: RiskDecision) -> dict[str, Any]:
        side = side.upper()
        if side not in {"BUY", "SELL"} or volume <= 0 or stop_loss <= 0 or take_profit <= 0:
            raise ValueError("Invalid order parameters")
        if not risk_decision.approved:
            raise PermissionError(f"Risk manager rejected order: {', '.join(risk_decision.reasons)}")
        mode, blocked = self._runtime_guard(automatic=False)
        if blocked:
            return {"ok": False, "reason": blocked}
        tick = self.connector.is_connected() and native_mt5.symbol_info_tick(symbol) if native_mt5 else None
        price = float((tick.ask if side == "BUY" else tick.bid) if tick else 0)
        if mode != "AUTO_DEMO" and not settings.demo_mode and not settings.live_trading:
            trade_id = self.database.save_trade(symbol, side, volume, price, stop_loss, take_profit)
            return {"ok": True, "paper": True, "trade_id": trade_id, "price": price}
        if not self.connector.is_connected() or native_mt5 is None:
            raise ConnectionError("Live trading requested but MT5 is disconnected")
        account = self.connector.account_info()
        is_demo_account = account.get("trade_mode") == native_mt5.ACCOUNT_TRADE_MODE_DEMO
        if (mode == "AUTO_DEMO" or settings.demo_mode) and not is_demo_account:
            return {"ok": False, "paper": False, "reason": "DEMO_ACCOUNT_REQUIRED"}
        if mode != "AUTO_DEMO" and settings.live_trading and is_demo_account:
            return {"ok": False, "paper": False, "reason": "LIVE_ACCOUNT_REQUIRED"}
        symbol_info = native_mt5.symbol_info(symbol)
        if symbol_info is None:
            raise ValueError(f"Unknown symbol: {symbol}")
        filling = native_mt5.ORDER_FILLING_IOC if symbol_info.filling_mode & 2 else native_mt5.ORDER_FILLING_FOK if symbol_info.filling_mode & 1 else native_mt5.ORDER_FILLING_RETURN
        request = {
            "action": native_mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": volume,
            "type": native_mt5.ORDER_TYPE_BUY if side == "BUY" else native_mt5.ORDER_TYPE_SELL,
            "price": price, "sl": stop_loss, "tp": take_profit, "deviation": settings.deviation,
            "magic": settings.magic_number, "comment": f"AI_TRADING_BOT_{symbol}_{settings.timeframe}"[:31],
            "type_time": native_mt5.ORDER_TIME_GTC, "type_filling": filling,
        }
        check = native_mt5.order_check(request)
        if not check or check.retcode != 0:
            return {"ok": False, "paper": False, "check": check._asdict() if check else None}
        _, blocked = self._runtime_guard(automatic=False)
        if blocked:
            return {"ok": False, "paper": False, "reason": blocked}
        result = native_mt5.order_send(request)
        ok = bool(result and result.retcode == native_mt5.TRADE_RETCODE_DONE)
        if not ok:
            logger.error("Order failed: %s", result)
        data = result._asdict() if result else None
        return {"ok": ok, "paper": False, "price": float(getattr(result, "price", price)), "result": data}
