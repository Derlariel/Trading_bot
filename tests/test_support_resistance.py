from analyzers.indicator_analyzer import calculate_indicators
from analyzers.support_resistance import find_zones, select_levels


def test_swing_zones_are_clustered(candles):
    frame = calculate_indicators(candles)
    zones = find_zones(frame)
    assert zones
    assert all(zone.low <= zone.high and 0 <= zone.strength <= 100 and zone.touches >= 1 for zone in zones)
    selected = select_levels(zones, float(frame.close.iloc[-1]))
    assert set(selected) == {"nearest_support", "nearest_resistance", "major_support", "major_resistance"}
