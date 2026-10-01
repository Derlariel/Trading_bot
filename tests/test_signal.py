from database.models import PriceZone, SignalType
from strategy.scoring import weighted_score
from strategy.signal_engine import create_trade_plan


def test_signal_score_and_plan():
    bullish = {name: 1 for name in ("trend", "levels", "indicators", "volume", "candlestick", "breakout", "multi_timeframe", "news")}
    assert weighted_score(bullish) == 100
    support = PriceZone("support", 99, 100, 90, 5)
    resistance = PriceZone("resistance", 108, 109, 80, 4)
    plan = create_trade_plan("TEST", 100.2, 1, support, resistance, bullish)
    assert plan.signal is SignalType.STRONG_BUY
    assert plan.stop_loss < support.low < plan.tp1
    assert plan.risk_reward >= 2


def test_news_alone_cannot_create_plan(candles):
    from strategy.strategy import analyze
    result = analyze("TEST", candles, news_score=1)
    assert result["components"]["news"] == 0 or any(abs(value) >= .25 for key, value in result["components"].items() if key != "news")
