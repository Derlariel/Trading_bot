from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

import mt5.order_manager as order_module
import risk.risk_manager as risk_module
import risk.trade_limits as limits_module
from database.database import Database
from database.models import SignalType, TradePlan
from mt5.order_manager import OrderManager
from risk.risk_manager import validate_trade
from risk.trade_limits import TradeState, check_trade_limits


@pytest.fixture
def safety_settings(monkeypatch):
    settings = SimpleNamespace(
        auto_trade=True, demo_mode=False, live_trading=False, magic_number=2601001,
        min_confidence=70, min_rr=2, max_spread_points=50, max_daily_loss=.03,
        max_trades_per_day=5, max_positions=3, max_positions_per_symbol=1,
        allow_hedging=False, trade_cooldown_minutes=15, risk_per_trade=.01,
        max_risk_per_trade=.02, timeframe="M15", deviation=20,
    )
    monkeypatch.setattr(order_module, "settings", settings)
    monkeypatch.setattr(risk_module, "settings", settings)
    monkeypatch.setattr(limits_module, "settings", settings)
    return settings


def state(**changes):
    values = dict(balance=10_000, daily_pnl=0, trades_today=0, open_positions=0)
    values.update(changes)
    return TradeState(**values)


def test_existing_same_direction_position_is_blocked(safety_settings):
    assert "SKIP_DUPLICATE_POSITION" in check_trade_limits(state(same_direction_position=True))


def test_position_per_symbol_limit_is_blocked(safety_settings):
    assert "MAX_POSITIONS_PER_SYMBOL_REACHED" in check_trade_limits(state(symbol_positions=1))


def test_total_position_limit_is_blocked(safety_settings):
    assert "MAX_SIMULTANEOUS_POSITIONS_REACHED" in check_trade_limits(state(open_positions=3))


def test_low_confidence_is_blocked(safety_settings):
    assert "CONFIDENCE_TOO_LOW" in validate_trade(state(), 69, 2, 1, True).reasons


def test_low_risk_reward_is_blocked(safety_settings):
    assert "RISK_REWARD_TOO_LOW" in validate_trade(state(), 70, 1.99, 1, True).reasons


def test_daily_loss_limit_includes_floating_state(safety_settings):
    assert "MAX_DAILY_LOSS_REACHED" in check_trade_limits(state(daily_pnl=-300))


def test_max_bot_trades_per_day_is_blocked(safety_settings):
    assert "MAX_TRADES_PER_DAY_REACHED" in check_trade_limits(state(trades_today=5))


def test_opposite_position_is_blocked_when_hedging_disabled(safety_settings):
    assert "OPPOSITE_POSITION_EXISTS" in check_trade_limits(state(opposite_position=True))


def test_cooldown_is_blocked(safety_settings):
    assert "TRADE_COOLDOWN_ACTIVE" in check_trade_limits(state(cooldown_remaining=1))


def test_same_candle_setup_is_reserved_once(tmp_path):
    database = Database(tmp_path / "signals.db")
    setup = "XAUUSD|M15|SELL|2026-10-01T11:45:00+00:00"
    assert database.reserve_signal(setup, "XAUUSD", "M15", "SELL", "2026-10-01T11:45:00+00:00")
    assert not Database(tmp_path / "signals.db").reserve_signal(setup, "XAUUSD", "M15", "SELL", "2026-10-01T11:45:00+00:00")


def test_new_candle_has_new_setup_identity(tmp_path):
    database = Database(tmp_path / "signals.db")
    first = "XAUUSD|M15|SELL|2026-10-01T11:45:00+00:00"
    second = "XAUUSD|M15|SELL|2026-10-01T12:00:00+00:00"
    assert database.reserve_signal(first, "XAUUSD", "M15", "SELL", "2026-10-01T11:45:00+00:00")
    assert database.reserve_signal(second, "XAUUSD", "M15", "SELL", "2026-10-01T12:00:00+00:00")


class Connector:
    def __init__(self, positions=()):
        self._positions = list(positions)

    def account_info(self):
        return {"balance": 10_000, "trade_allowed": True, "trade_expert": True, "trade_mode": 0}

    def symbol_info(self, symbol):
        return {"point": .01, "trade_mode": 1, "trade_tick_size": .01, "trade_tick_value": 1, "volume_step": .01, "volume_min": .01, "volume_max": 100, "digits": 2}

    def is_connected(self):
        return True

    def positions(self):
        return self._positions

    def trade_history(self, start, end):
        return []


def manager(tmp_path, monkeypatch, safety_settings, positions=()):
    native = SimpleNamespace(
        POSITION_TYPE_BUY=0, POSITION_TYPE_SELL=1, DEAL_ENTRY_IN=0,
        SYMBOL_TRADE_MODE_DISABLED=0,
        symbol_info_tick=lambda symbol: SimpleNamespace(ask=100.0, bid=99.9, time=datetime.now(UTC).timestamp()),
    )
    monkeypatch.setattr(order_module, "native_mt5", native)
    return OrderManager(Connector(positions), Database(tmp_path / "orders.db"))


def buy_plan(stop=98, target=104, confidence=80):
    return TradePlan("XAUUSD", SignalType.BUY, confidence, (99, 101), stop, target, 106, 108, 2)


def test_invalid_sl_tp_is_blocked(tmp_path, monkeypatch, safety_settings):
    result = manager(tmp_path, monkeypatch, safety_settings).auto_order(buy_plan(stop=101), "M15", "2026-10-01T12:00:00+00:00")
    assert result["reason"] == "INVALID_PROTECTIVE_LEVELS"


def test_valid_setup_executes_only_once_and_ignores_manual_position(tmp_path, monkeypatch, safety_settings):
    manual_position = {"symbol": "XAUUSD", "magic": 0, "type": 0, "profit": 0}
    orders = manager(tmp_path, monkeypatch, safety_settings, [manual_position])
    candle = "2026-10-01T12:00:00+00:00"
    first = orders.auto_order(buy_plan(), "M15", candle)
    second = orders.auto_order(buy_plan(), "M15", candle)
    assert first["decision"] == "EXECUTE"
    assert second["reason"] == "SIGNAL_ALREADY_EXECUTED"
    assert len(orders.database.rows("trades")) == 1


def test_demo_mode_sends_only_to_mt5_demo_account(tmp_path, monkeypatch, safety_settings):
    sent = []
    native = SimpleNamespace(
        ACCOUNT_TRADE_MODE_DEMO=0, TRADE_ACTION_DEAL=1, ORDER_TYPE_BUY=0, ORDER_TYPE_SELL=1,
        ORDER_TIME_GTC=0, ORDER_FILLING_IOC=1, ORDER_FILLING_FOK=0, ORDER_FILLING_RETURN=2,
        TRADE_RETCODE_DONE=10009, symbol_info_tick=lambda symbol: SimpleNamespace(ask=100.0, bid=99.9),
        symbol_info=lambda symbol: SimpleNamespace(filling_mode=2),
        order_check=lambda request: SimpleNamespace(retcode=0),
        order_send=lambda request: sent.append(request) or SimpleNamespace(retcode=10009, price=request["price"], _asdict=lambda: {"order": 7}),
    )
    monkeypatch.setattr(order_module, "native_mt5", native)
    safety_settings.demo_mode = True
    orders = OrderManager(Connector(), Database(tmp_path / "demo.db"))
    result = orders.market_order("XAUUSD", "BUY", .01, 98, 104, SimpleNamespace(approved=True, reasons=()))
    assert result["ok"] and not result["paper"] and len(sent) == 1

    connector = Connector()
    connector.account_info = lambda: {"trade_mode": 1}
    blocked = OrderManager(connector, Database(tmp_path / "real.db")).market_order("XAUUSD", "BUY", .01, 98, 104, SimpleNamespace(approved=True, reasons=()))
    assert blocked["reason"] == "DEMO_ACCOUNT_REQUIRED" and len(sent) == 1
