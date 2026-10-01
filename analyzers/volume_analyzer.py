"""Tick/real volume diagnostics and a simple volume profile."""
from __future__ import annotations

import numpy as np
import pandas as pd


def analyze_volume(frame: pd.DataFrame, bins: int = 20) -> dict[str, object]:
    if frame.empty:
        return {"current": 0, "average": 0, "spike": False, "trend": "flat", "source": "unavailable"}
    volume = frame.get("real_volume", pd.Series(0, index=frame.index)).astype(float)
    source = "real_volume"
    if not volume.any():
        volume, source = frame.get("tick_volume", pd.Series(0, index=frame.index)).astype(float), "tick_volume (broker activity, not exchange volume)"
    average = float(volume.tail(20).mean())
    typical = (frame.high + frame.low + frame.close) / 3
    counts, edges = np.histogram(typical, bins=bins, weights=volume)
    centers = (edges[:-1] + edges[1:]) / 2
    poc = float(centers[counts.argmax()]) if counts.size and counts.max() else None
    threshold_high, threshold_low = np.quantile(counts, [.75, .25]) if counts.size else (0, 0)
    return {"current": float(volume.iloc[-1]), "average": average, "spike": bool(volume.iloc[-1] > average * 1.5), "trend": "rising" if volume.tail(5).mean() > volume.tail(20).mean() else "falling", "poc": poc, "high_volume_nodes": centers[counts >= threshold_high].tolist(), "low_volume_nodes": centers[counts <= threshold_low].tolist(), "source": source}
