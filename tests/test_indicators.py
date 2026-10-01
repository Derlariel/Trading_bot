import numpy as np

from analyzers.indicator_analyzer import calculate_indicators, indicator_score


def test_indicator_calculation(candles):
    result = calculate_indicators(candles)
    assert {"rsi", "macd", "ema200", "atr", "adx", "bb_upper", "stoch_k", "obv"} <= set(result)
    assert 0 <= result.rsi.iloc[-1] <= 100
    assert result.atr.iloc[-1] > 0
    assert np.isfinite(indicator_score(result))
