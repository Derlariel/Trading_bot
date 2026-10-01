"""Read-only console snapshots. Money metrics are bot-only unless account-wide.

All displayed timestamps use Asia/Bangkok. ``None`` metrics mean unavailable,
not zero. Broker tables cover the whole account; ``symbol`` only scopes the
bot_symbol_positions metric. Local execution/paper records are a separate ledger
and must not be presented as broker fills or account equity history.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd

from config import settings
from mt5.connector import native_mt5

TIMEZONE = "Asia/Bangkok"
POSITION_COLUMNS = ["ticket", "time", "symbol", "side", "origin", "volume", "price_open", "price_current", "sl", "tp", "profit", "swap", "floating_pnl", "magic"]
DEAL_COLUMNS = ["ticket", "order", "position_id", "time", "symbol", "side", "entry", "origin", "volume", "price", "profit", "commission", "swap", "fee", "net_pnl", "magic"]
LOG_COLUMNS = ["id", "time", "level", "symbol", "timeframe", "decision", "reason", "signal", "confidence", "rr", "message"]


def _frame(rows: list[dict], columns: list[str], date_columns: tuple[str, ...] = ()) -> pd.DataFrame:
    frame = pd.DataFrame(rows).reindex(columns=columns)
    for name in date_columns:
        frame[name] = pd.to_datetime(frame[name], utc=True, errors="coerce", format="mixed").dt.tz_convert(TIMEZONE)
    return frame


def _origin(magic: Any) -> str:
    return "Bot" if magic == settings.magic_number else "Manual" if magic == 0 else "Other EA"


def _broker_frame(rows: Any, *, positions: bool) -> pd.DataFrame:
    records = []
    for row in rows:
        record = dict(row) if isinstance(row, dict) else row._asdict()
        if record.get("type") not in (0, 1):
            continue  # Deposits, credits and other cash operations are not trades.
        record["side"] = "BUY" if record["type"] == 0 else "SELL"
        record["origin"] = _origin(record.get("magic"))
        record["time"] = pd.to_datetime(record.get("time_msc") or record.get("time"), unit="ms" if record.get("time_msc") else "s", utc=True, errors="coerce")
        keys = ("profit", "swap") if positions else ("profit", "commission", "swap", "fee")
        record["floating_pnl" if positions else "net_pnl"] = sum(float(record.get(key) or 0) for key in keys)
        if not positions:
            record["entry"] = {0: "IN", 1: "OUT", 2: "INOUT", 3: "OUT_BY"}.get(record.get("entry"), "UNKNOWN")
        records.append(record)
    return _frame(records, POSITION_COLUMNS if positions else DEAL_COLUMNS, ("time",)).sort_values("time", ascending=False)


def _logs(rows: list[dict]) -> pd.DataFrame:
    records = []
    for row in rows:
        message = str(row.get("message", ""))
        try:
            payload = json.loads(message)
        except (TypeError, ValueError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        record = {key: payload.get(key) for key in LOG_COLUMNS if key not in {"id", "time", "level", "message"}}
        # Keep plain-text legacy logs and tolerate malformed JSON without losing the row.
        record.update(id=row.get("id"), time=row.get("created_at"), level=row.get("level", "INFO"), message=payload.get("reason") or payload.get("message") or message)
        records.append(record)
    return _frame(records, LOG_COLUMNS, ("time",))


def load_account_snapshot(connector: Any, database: Any, symbol: str, history_days: int = 7, *, now: datetime | None = None) -> dict[str, Any]:
    """Query MT5 and the local ledger without initializing MT5 or sending orders.

    ``pnl_curve`` columns: time, realized_pnl, cumulative_pnl (bot net realized
    cash flow for the selected history window, *not* a reconstructed equity).
    Broker failures are listed in errors and preserve unknown money/count metrics.
    ``now`` is an aware datetime override for deterministic offline checks.
    """
    if not isinstance(history_days, int) or not 1 <= history_days <= 365:
        raise ValueError("history_days must be between 1 and 365")
    current = pd.Timestamp(now or datetime.now(UTC))
    if current.tzinfo is None:
        raise ValueError("now must include a timezone")
    current = current.tz_convert(TIMEZONE)
    today = current.normalize()
    start = today - timedelta(days=history_days - 1)
    errors: list[str] = []
    snapshot: dict[str, Any] = {
        "account": {}, "connected": False, "is_demo": None,
        "positions": _broker_frame([], positions=True), "deals": _broker_frame([], positions=False),
        "errors": errors, "as_of": current, "timezone": TIMEZONE,
        "pnl_curve": pd.DataFrame(columns=["time", "realized_pnl", "cumulative_pnl"]),
    }
    metrics = {key: None for key in ("balance", "equity", "free_margin", "bot_open_positions", "bot_symbol_positions", "trades_today", "realized_today", "floating_pnl", "daily_pnl", "daily_loss_pct", "history_realized")}
    snapshot["metrics"] = metrics

    try:
        snapshot["connected"] = bool(connector.is_connected())
        if snapshot["connected"] and connector.terminal_info().get("connected") is False:
            snapshot["connected"] = False
    except Exception as error:
        errors.append(f"MT5 connection unavailable ({type(error).__name__})")
    positions_ok = history_ok = False
    if snapshot["connected"]:
        try:
            info = connector.account_info()
            if not info:
                raise ConnectionError("Account query returned no result")
            snapshot["account"] = {key: info[key] for key in ("balance", "equity", "margin", "margin_free", "currency", "leverage", "trade_mode", "trade_allowed", "trade_expert") if key in info}
            snapshot["is_demo"] = info["trade_mode"] == 0 if "trade_mode" in info else None
            for output, key in (("balance", "balance"), ("equity", "equity"), ("free_margin", "margin_free")):
                if info.get(key) is not None:
                    metrics[output] = float(info[key])
        except Exception as error:
            errors.append(f"MT5 account unavailable ({type(error).__name__})")
        # Native queries preserve None (failure), which connector list helpers erase.
        try:
            rows = native_mt5.positions_get()
            if rows is None:
                raise ConnectionError("Positions query returned no result")
            snapshot["positions"] = _broker_frame(rows, positions=True)
            positions_ok = True
        except Exception as error:
            errors.append(f"MT5 positions unavailable ({type(error).__name__})")
        try:
            rows = native_mt5.history_deals_get(start.tz_convert("UTC").to_pydatetime(), current.tz_convert("UTC").to_pydatetime())
            if rows is None:
                raise ConnectionError("History query returned no result")
            snapshot["deals"] = _broker_frame(rows, positions=False)
            history_ok = True
        except Exception as error:
            errors.append(f"MT5 deal history unavailable ({type(error).__name__})")
    else:
        errors.append("MT5 disconnected; broker metrics are unavailable")
    snapshot["positions_available"], snapshot["history_available"] = positions_ok, history_ok

    if positions_ok:
        bot = snapshot["positions"].loc[lambda frame: frame.origin.eq("Bot")]
        metrics.update(bot_open_positions=len(bot), bot_symbol_positions=int(bot.symbol.eq(symbol).sum()), floating_pnl=float(bot.floating_pnl.sum()))
    if history_ok:
        bot = snapshot["deals"].loc[lambda frame: frame.origin.eq("Bot") & frame.time.ge(start) & frame.time.le(current)]
        recent = bot.loc[bot.time.ge(today)]
        opening = recent.loc[recent.entry.isin(["IN", "INOUT"])]
        # Partial fills share an order; reversals open exposure and count once too.
        identities = {("order", row.order) if pd.notna(row.order) and row.order else ("deal", row.ticket) for row in opening.itertuples()}
        metrics.update(trades_today=len(identities), realized_today=float(recent.net_pnl.sum()), history_realized=float(bot.net_pnl.sum()))
        curve = bot.groupby(bot.time.dt.normalize()).net_pnl.sum().reindex(pd.date_range(start, today, freq="D"), fill_value=0).rename_axis("time").reset_index(name="realized_pnl")
        curve["cumulative_pnl"] = curve.realized_pnl.cumsum()
        snapshot["pnl_curve"] = curve
    if positions_ok and history_ok:
        metrics["daily_pnl"] = metrics["realized_today"] + metrics["floating_pnl"]
        if metrics["balance"] is not None and metrics["balance"] > 0:
            metrics["daily_loss_pct"] = max(0, -metrics["daily_pnl"] / metrics["balance"] * 100)

    for table, key, columns, date_columns in (
        ("executed_signals", "executed", ["id", "setup_id", "symbol", "timeframe", "signal", "candle_time", "executed_at", "ticket", "status"], ("candle_time", "executed_at")),
        ("trades", "paper", ["id", "created_at", "symbol", "side", "volume", "entry", "stop_loss", "take_profit", "status", "pnl", "ticket"], ("created_at",)),
        ("bot_logs", "logs", LOG_COLUMNS, ("time",)),
    ):
        try:
            # ponytail: latest 5,000 local rows; add pagination only when auditing older records.
            rows = database.rows(table, limit=5000)
            snapshot[key] = _logs(rows) if table == "bot_logs" else _frame(rows, columns, date_columns)
        except Exception as error:
            errors.append(f"Local {table} unavailable ({type(error).__name__})")
            snapshot[key] = _frame([], columns, date_columns)
    return snapshot


def csv_bytes(frame: pd.DataFrame) -> bytes:
    """UTF-8 CSV download, neutralizing text that spreadsheet apps execute."""
    def safe(value: Any) -> Any:
        return "'" + value if isinstance(value, str) and (value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n"))) else value

    return frame.map(safe).rename(columns=safe).to_csv(index=False).encode("utf-8-sig")
