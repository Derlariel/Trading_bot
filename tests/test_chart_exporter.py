import csv

from config import settings
from mt5.chart_exporter import export_overlay
from strategy.strategy import analyze


class Connector:
    def __init__(self, path):
        self.path = path

    def terminal_info(self):
        return {"commondata_path": str(self.path)}


def test_export_overlay(tmp_path, candles):
    result = analyze("TEST", candles)
    target = export_overlay(Connector(tmp_path), "TEST", "M15", result)

    with target.open(newline="", encoding="ascii") as stream:
        row = next(csv.reader(stream, delimiter=";"))
    assert row[0:4] == ["2", "TEST", "M15", "AUTO" if settings.auto_trade else "MANUAL"]
    assert row[5] == result["plan"].signal.value
    assert len(row) == 20
