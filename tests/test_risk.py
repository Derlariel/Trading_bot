import pytest

from database.models import PriceZone
from risk.position_size import calculate_position_size
from risk.risk_manager import stop_loss, take_profits, validate_trade
from risk.trade_limits import TradeState


def test_position_size_uses_broker_specification():
    assert calculate_position_size(10_000, .01, 100, 98, .01, 1, .01, .01, 100) == .5
    assert calculate_position_size(100, .01, 100, 50, .01, 1, .01, .01, 100) == 0


def test_dynamic_stop_and_take_profit():
    support = PriceZone("support", 98, 99, 80, 4)
    stop = stop_loss("BUY", support, 1, 1.5)
    assert stop == 96.5
    targets = take_profits("BUY", 99, stop)
    assert targets == pytest.approx((104, 106.5, 109))
    assert (targets[0] - 99) / (99 - stop) >= 2


def test_risk_rejects_limits_and_accepts_clean_state():
    good = TradeState(10_000, 0, 0, 0)
    assert validate_trade(good, 80, 2.2, 10, True).approved
    bad = TradeState(10_000, -400, 5, 3, True)
    decision = validate_trade(bad, 40, 1, 100, False, .9)
    assert not decision.approved and len(decision.reasons) >= 7
