"""Export the latest analysis for the MT5 chart overlay indicator."""
from __future__ import annotations

import csv
import os
from datetime import UTC, datetime
from pathlib import Path

from config import settings
from mt5.connector import MT5Connector


def export_overlay(connector: MT5Connector, symbol: str, timeframe: str, result: dict[str, object], execution: dict[str, object] | None = None) -> Path:
    common_path = connector.terminal_info().get("commondata_path")
    if not common_path:
        raise ConnectionError("MT5 common data path is unavailable")

    plan = result["plan"]
    levels = result["levels"]
    support, resistance = levels["nearest_support"], levels["nearest_resistance"]
    execution = execution or {}
    row = (
        2, symbol, timeframe, "AUTO" if settings.auto_trade else "MANUAL",
        int(datetime.now(UTC).timestamp()), plan.signal.value, plan.confidence,
        *plan.entry_zone, plan.stop_loss, plan.tp1, plan.tp2, plan.tp3,
        support.low if support else 0, support.high if support else 0,
        resistance.low if resistance else 0, resistance.high if resistance else 0,
        plan.risk_reward, execution.get("decision", ""), execution.get("reason", ""),
    )

    directory = Path(str(common_path)) / "Files" / "TradingBot"
    directory.mkdir(parents=True, exist_ok=True)
    target, temporary = directory / "signal.csv", directory / "signal.tmp"
    with temporary.open("w", newline="", encoding="ascii") as stream:
        csv.writer(stream, delimiter=";").writerow(row)
    os.replace(temporary, target)
    return target
