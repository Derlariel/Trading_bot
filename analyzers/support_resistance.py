"""Swing-based support/resistance zones clustered with DBSCAN."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import find_peaks
from sklearn.cluster import DBSCAN

from database.models import PriceZone
from utils.helpers import clamp


def find_zones(frame: pd.DataFrame, timeframe_weight: float = 1.0, prominence: float | None = None) -> list[PriceZone]:
    """Cluster local extrema into scored price zones."""
    if len(frame) < 20:
        return []
    typical_range = float((frame.high - frame.low).rolling(14).mean().iloc[-1])
    epsilon = max(typical_range * .65, float(frame.close.iloc[-1]) * .0005)
    prominence = prominence or typical_range * .5
    hi_idx, _ = find_peaks(frame.high.to_numpy(), distance=3, prominence=prominence)
    lo_idx, _ = find_peaks(-frame.low.to_numpy(), distance=3, prominence=prominence)
    points = [(float(frame.high.iloc[i]), int(i), "resistance") for i in hi_idx]
    points += [(float(frame.low.iloc[i]), int(i), "support") for i in lo_idx]
    if not points:
        return []
    prices = np.array([point[0] for point in points]).reshape(-1, 1)
    labels = DBSCAN(eps=epsilon, min_samples=1).fit_predict(prices)
    zones: list[PriceZone] = []
    volume = frame.get("volume", frame.get("tick_volume", pd.Series(1, index=frame.index))).astype(float)
    volume_mean = max(float(volume.mean()), 1)
    swing_low, swing_high = float(frame.low.min()), float(frame.high.max())
    fib_prices = [swing_low + (swing_high - swing_low) * ratio for ratio in (.236, .382, .5, .618, .786)]
    for label in sorted(set(labels)):
        members = [point for point, cluster in zip(points, labels) if cluster == label]
        values, indexes = [m[0] for m in members], [m[1] for m in members]
        support_votes = sum(m[2] == "support" for m in members)
        zone_type = "support" if np.mean(values) <= frame.close.iloc[-1] and support_votes >= len(members) / 2 else "resistance"
        recency = 1 - (len(frame) - 1 - max(indexes)) / len(frame)
        relative_volume = min(float(volume.iloc[indexes].mean()) / volume_mean, 2) / 2
        ema_confirm = any(abs(np.mean(values) - float(frame[f"ema{n}"].iloc[-1])) <= epsilon for n in (20, 50, 200) if f"ema{n}" in frame)
        fib_confirm = any(abs(np.mean(values) - price) <= epsilon for price in fib_prices)
        reactions = [abs(float(frame.close.iloc[min(index + 5, len(frame) - 1)]) - values[offset]) / max(typical_range, 1e-12) for offset, index in enumerate(indexes)]
        historical_reaction = min(float(np.mean(reactions)), 2) / 2
        strength = clamp(len(members) * 10 + recency * 20 + relative_volume * 15 + timeframe_weight * 8 + ema_confirm * 8 + fib_confirm * 8 + historical_reaction * 12)
        zones.append(PriceZone(zone_type, min(values), max(values), round(strength, 2), len(members)))
    return sorted(zones, key=lambda zone: zone.low)


def select_levels(zones: list[PriceZone], price: float) -> dict[str, PriceZone | None]:
    supports = [zone for zone in zones if zone.high < price]
    resistances = [zone for zone in zones if zone.low > price]
    return {
        "nearest_support": max(supports, key=lambda z: z.high, default=None),
        "nearest_resistance": min(resistances, key=lambda z: z.low, default=None),
        "major_support": max(supports, key=lambda z: z.strength, default=None),
        "major_resistance": max(resistances, key=lambda z: z.strength, default=None),
    }
