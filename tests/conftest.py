from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def candles() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    count = 320
    close = 100 + np.linspace(0, 18, count) + np.sin(np.arange(count) / 6) * 2 + rng.normal(0, .18, count)
    open_ = close + rng.normal(0, .25, count)
    high = np.maximum(open_, close) + rng.uniform(.3, .8, count)
    low = np.minimum(open_, close) - rng.uniform(.3, .8, count)
    return pd.DataFrame({"time": pd.date_range("2025-01-01", periods=count, freq="15min", tz="UTC"), "open": open_, "high": high, "low": low, "close": close, "tick_volume": rng.integers(500, 1500, count), "spread": 10, "real_volume": 0})
