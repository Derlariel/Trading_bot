"""Offline console checks: account boundaries, partial fills and failed reads."""
from datetime import UTC, datetime
from types import SimpleNamespace

import pandas as pd

import dashboard.data as data

NOW = datetime(2026, 10, 1, 18, 0, tzinfo=UTC)  # October 2, 01:00 in Bangkok.


def connector(connected=True):
    return SimpleNamespace(
        is_connected=lambda: connected,
        terminal_info=lambda: {"connected": connected},
        account_info=lambda: {"balance": 10_000, "equity": 10_001, "margin_free": 9_000, "currency": "USD", "trade_mode": 0, "leverage": 10, "login": 123456, "password": "secret"},
    )


def ledger(rows=None):
    def read(table, limit):
        assert limit == 5000
        return (rows or {}).get(table, [])
    return SimpleNamespace(rows=read)


def deal(ticket, order, timestamp, **fields):
    return {"ticket": ticket, "order": order, "position_id": 99, "time": datetime.fromisoformat(timestamp).timestamp(), "magic": data.settings.magic_number, "symbol": "XAUUSD", "type": 0, "entry": 0, "volume": .01, "price": 2000, "profit": 0, "commission": -1, "swap": 0, "fee": 0, **fields}


def test_bangkok_bot_pnl_partial_fills_reversals_and_manual_separation(monkeypatch):
    history = [
        deal(1, 11, "2026-10-01T16:59:00+00:00", profit=10),  # Previous Bangkok day.
        deal(2, 12, "2026-10-01T17:01:00+00:00"),
        deal(3, 12, "2026-10-01T17:01:01+00:00"),  # Same opening order, second fill.
        deal(4, 13, "2026-10-01T17:10:00+00:00", entry=2, profit=20, swap=-2, fee=-1),
        deal(5, 14, "2026-10-01T17:20:00+00:00", entry=1, profit=5),
        deal(6, 15, "2026-10-01T17:30:00+00:00", magic=0, profit=100),
        deal(7, 16, "2026-10-01T17:40:00+00:00", magic=77, profit=200),
        deal(8, 0, "2026-10-01T17:50:00+00:00", type=2, profit=5000),  # Deposit.
    ]
    positions = [
        {"ticket": 40, "type": 0, "magic": data.settings.magic_number, "symbol": "XAUUSD", "profit": 3, "swap": -1, "time": NOW.timestamp()},
        {"ticket": 41, "type": 1, "magic": data.settings.magic_number, "symbol": "EURUSD", "profit": 4, "swap": 0, "time": NOW.timestamp()},
        {"ticket": 42, "type": 0, "magic": 0, "symbol": "XAUUSD", "profit": 999, "time": NOW.timestamp()},
    ]
    queried = []
    monkeypatch.setattr(data, "native_mt5", SimpleNamespace(positions_get=lambda: positions, history_deals_get=lambda start, end: queried.append((start, end)) or history))
    result = data.load_account_snapshot(connector(), ledger(), "XAUUSD", now=NOW)
    assert not result["errors"]
    assert result["is_demo"] is True
    assert "login" not in result["account"] and "password" not in result["account"]
    assert result["metrics"] == {
        "balance": 10_000, "equity": 10_001, "free_margin": 9_000,
        "bot_open_positions": 2, "bot_symbol_positions": 1, "trades_today": 2,
        "realized_today": 18, "floating_pnl": 6, "daily_pnl": 24,
        "daily_loss_pct": 0, "history_realized": 27,
    }
    assert len(result["deals"]) == 7 and set(result["deals"].origin) == {"Bot", "Manual", "Other EA"}
    assert str(result["deals"].time.dt.tz) == "Asia/Bangkok"
    assert queried[0][0] == datetime(2026, 9, 25, 17, tzinfo=UTC)
    assert len(result["pnl_curve"]) == 7 and result["pnl_curve"].cumulative_pnl.iloc[-1] == 27
    assert result["pnl_curve"].realized_pnl.iloc[-1] == 18


def test_failed_broker_queries_are_unknown_not_zero(monkeypatch):
    monkeypatch.setattr(data, "native_mt5", SimpleNamespace(positions_get=lambda: None, history_deals_get=lambda *args: None))
    result = data.load_account_snapshot(connector(), ledger(), "XAUUSD", now=NOW)
    assert result["metrics"]["equity"] == 10_001
    assert result["metrics"]["daily_pnl"] is None and result["metrics"]["bot_open_positions"] is None
    assert result["metrics"]["trades_today"] is None and result["pnl_curve"].empty
    assert not result["positions_available"] and not result["history_available"]
    assert len(result["errors"]) == 2


def test_empty_success_is_zero_and_legacy_logs_survive(monkeypatch):
    monkeypatch.setattr(data, "native_mt5", SimpleNamespace(positions_get=lambda: (), history_deals_get=lambda *args: ()))
    logs = [
        {"id": 3, "created_at": "2026-10-01T17:10:00Z", "level": "INFO", "message": '{"decision": "SKIP", "reason": "NO_TRADE_SIGNAL", "symbol": "XAUUSD"}'},
        {"id": 2, "created_at": "bad date", "level": "ERROR", "message": '{"malformed":'},
        {"id": 1, "created_at": "2026-10-01T17:00:00Z", "level": "WARNING", "message": "legacy text log"},
        {"id": 0, "created_at": "2026-10-01T17:00:00Z", "message": "null"},
    ]
    result = data.load_account_snapshot(connector(), ledger({"bot_logs": logs}), "XAUUSD", now=NOW)
    assert not result["errors"] and result["metrics"]["daily_pnl"] == 0 and result["metrics"]["trades_today"] == 0
    assert len(result["logs"]) == 4 and result["logs"].message.iloc[1] == '{"malformed":'
    assert result["logs"].decision.iloc[0] == "SKIP" and pd.isna(result["logs"].time.iloc[1])
    assert len(result["pnl_curve"]) == 7 and result["pnl_curve"].cumulative_pnl.eq(0).all()


def test_disconnected_still_reads_ledger_without_querying_broker(monkeypatch):
    def forbidden(*args):
        raise AssertionError("Disconnected snapshot must not query the broker")
    monkeypatch.setattr(data, "native_mt5", SimpleNamespace(positions_get=forbidden, history_deals_get=forbidden))
    result = data.load_account_snapshot(connector(False), ledger(), "XAUUSD", now=NOW)
    assert result["connected"] is False and result["is_demo"] is None
    assert all(value is None for value in result["metrics"].values())
    assert result["logs"].empty and len(result["errors"]) == 1


def test_csv_download_neutralizes_formula_text_but_preserves_numeric_losses():
    frame = pd.DataFrame({"=header": ["=HYPERLINK(\"bad\")", "  +SUM(1,2)", "\ttext", -2.5]})
    exported = pd.read_csv(__import__("io").BytesIO(data.csv_bytes(frame)))
    assert exported.columns.tolist() == ["'=header"]
    assert exported.iloc[0, 0].startswith("'=") and exported.iloc[1, 0].startswith("'  +")
    assert exported.iloc[2, 0] == "'\ttext" and exported.iloc[3, 0] == "-2.5"
