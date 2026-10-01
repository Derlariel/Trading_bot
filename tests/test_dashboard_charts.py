from dataclasses import replace

import pandas as pd

from config import settings
from dashboard.charts import pnl_chart, price_chart, signal_chart
from database.models import PriceZone, SignalType, TradePlan
from strategy.scoring import weighted_score


def test_price_chart_overlays_and_modes():
    candles = pd.DataFrame({
        "time": pd.date_range("2026-01-01", periods=3, freq="15min", tz="UTC"),
        "open": [101, 102, 103], "high": [103, 104, 105], "low": [100, 101, 102],
        "close": [102, 103, 104], "tick_volume": [20, 30, 40], "ema20": [101, 102, 103],
    })
    plan = TradePlan("XAUUSD", SignalType.BUY, 80, (100, 101), 98, 106, 108, 110, 2)
    result = {"candles": candles, "plan": plan, "levels": {
        "nearest_support": PriceZone("support", 99, 100, 60, 3),
        "nearest_resistance": PriceZone("resistance", 109, 110, 60, 3),
    }}
    figure = price_chart(result, timeframe="M15")
    assert figure.data[0].type == "candlestick"
    assert pd.Timestamp(figure.data[0].x[0]).hour == 7
    assert figure.layout.uirevision == "XAUUSD:M15"
    assert len(figure.layout.shapes) == 7  # Two zones, entry, SL and three targets.
    assert {annotation.text for annotation in figure.layout.annotations} >= {"Entry", "SL", "TP1", "TP2", "TP3"}
    assert all(shape.yref == "y" for shape in figure.layout.shapes)
    line = price_chart(result, "Line", show_ema=False, show_zones=False)
    assert [trace.type for trace in line.data] == ["scatter", "bar"]
    assert list(line.data[1].y) == [20, 30, 40]
    assert len(line.layout.shapes) == 5
    for invalid in (
        replace(plan, signal=SignalType.WAIT), replace(plan, stop_loss=float("nan")),
        replace(plan, tp2=float("inf")), replace(plan, stop_loss=102),
        replace(plan, entry_zone=(101, 100)), replace(plan, tp1=99), replace(plan, tp3=107),
    ):
        result["plan"] = invalid
        assert not price_chart(result, show_zones=False).layout.shapes
    result["plan"] = replace(plan, signal=SignalType.SELL, stop_loss=103, tp1=96, tp2=94, tp3=92)
    assert len(price_chart(result, show_zones=False).layout.shapes) == 5


def test_signal_contributions_match_scoring():
    components = {"trend": 8, "levels": -.8, "news": -9, "volume": .5, "unrecognized": 100}
    figure = signal_chart(components)
    assert round(sum(figure.data[0].x), 2) == weighted_score(components)
    assert len(figure.data[0].x) == len(settings.signal_weights)
    assert all("%" not in label for label in figure.data[0].text)


def test_realized_pnl_preserves_local_days_and_empty_data():
    frame = pd.DataFrame({"time": pd.date_range("2026-10-01", periods=2, tz="Asia/Bangkok"),
                          "realized_pnl": [-3.25, 7.5], "cumulative_pnl": [-3.25, 4.25]})
    figure = pnl_chart(frame)
    assert list(figure.data[0].y) == [-3.25, 4.25]
    assert list(figure.data[0].customdata) == [-3.25, 7.5]
    assert pd.Timestamp(figure.data[0].x[0]) == pd.Timestamp("2026-10-01")
    assert not pnl_chart(frame.iloc[:0]).data
