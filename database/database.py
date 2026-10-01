"""Thread-safe-enough SQLite store using one connection per operation."""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from config import settings
from utils.time_utils import iso_now

SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, symbol TEXT NOT NULL, signal TEXT NOT NULL, confidence REAL NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, symbol TEXT NOT NULL, side TEXT NOT NULL, volume REAL NOT NULL, entry REAL NOT NULL, stop_loss REAL, take_profit REAL, status TEXT NOT NULL, pnl REAL DEFAULT 0, ticket TEXT);
CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, symbol TEXT NOT NULL, side TEXT NOT NULL, volume REAL NOT NULL, price REAL, status TEXT NOT NULL, payload TEXT);
CREATE TABLE IF NOT EXISTS positions (id INTEGER PRIMARY KEY, updated_at TEXT NOT NULL, symbol TEXT NOT NULL, side TEXT NOT NULL, volume REAL NOT NULL, entry REAL NOT NULL, current_price REAL, pnl REAL DEFAULT 0, status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS news (id INTEGER PRIMARY KEY, published_at TEXT, symbol TEXT NOT NULL, headline TEXT NOT NULL, source TEXT, url TEXT UNIQUE, sentiment REAL DEFAULT 0, importance REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS price_levels (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL, type TEXT NOT NULL, low REAL NOT NULL, high REAL NOT NULL, strength REAL NOT NULL, touches INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS bot_logs (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, level TEXT NOT NULL, message TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS performance (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, key TEXT NOT NULL, value REAL NOT NULL);
CREATE TABLE IF NOT EXISTS executed_signals (id INTEGER PRIMARY KEY, setup_id TEXT NOT NULL UNIQUE, symbol TEXT NOT NULL, timeframe TEXT NOT NULL, signal TEXT NOT NULL, candle_time TEXT NOT NULL, executed_at TEXT, ticket TEXT, status TEXT NOT NULL DEFAULT 'RESERVED');
CREATE TABLE IF NOT EXISTS signal_state (symbol TEXT NOT NULL, timeframe TEXT NOT NULL, signal TEXT NOT NULL, candle_time TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(symbol,timeframe));
CREATE TABLE IF NOT EXISTS runtime_control (id INTEGER PRIMARY KEY CHECK(id=1), mode TEXT CHECK(mode IN ('AUTO_DEMO','MANUAL','PAUSED')), worker_id TEXT, pid INTEGER, heartbeat REAL, phase TEXT NOT NULL DEFAULT 'STOPPED', stop_requested INTEGER NOT NULL DEFAULT 0, last_error TEXT, last_execution TEXT);
INSERT OR IGNORE INTO runtime_control(id) VALUES(1);
"""

WORKER_LEASE_SECONDS = 30


class Database:
    """Minimal persistence API for signals, paper trades, and dashboard queries."""

    def __init__(self, path: str | Path = settings.database_path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def save_signal(self, payload: dict[str, Any]) -> int:
        with self.connect() as db:
            cursor = db.execute(
                "INSERT INTO signals(created_at,symbol,signal,confidence,payload) VALUES(?,?,?,?,?)",
                (iso_now(), payload["symbol"], payload["signal"], payload["confidence"], json.dumps(payload)),
            )
            return int(cursor.lastrowid)

    def save_trade(self, symbol: str, side: str, volume: float, entry: float, stop_loss: float, take_profit: float, status: str = "PAPER") -> int:
        with self.connect() as db:
            cursor = db.execute(
                "INSERT INTO trades(created_at,symbol,side,volume,entry,stop_loss,take_profit,status) VALUES(?,?,?,?,?,?,?,?)",
                (iso_now(), symbol, side, volume, entry, stop_loss, take_profit, status),
            )
            return int(cursor.lastrowid)

    def save_news(self, symbol: str, item: dict[str, Any]) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO news(published_at,symbol,headline,source,url,sentiment,importance) VALUES(?,?,?,?,?,?,?)",
                (item.get("published_at"), symbol, item["headline"], item.get("source"), item.get("url"), item.get("sentiment", 0), item.get("importance", 0)),
            )

    def update_signal_state(self, symbol: str, timeframe: str, signal: str, candle_time: str) -> str | None:
        with self.connect() as db:
            row = db.execute("SELECT signal FROM signal_state WHERE symbol=? AND timeframe=?", (symbol, timeframe)).fetchone()
            db.execute(
                "INSERT INTO signal_state(symbol,timeframe,signal,candle_time,updated_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(symbol,timeframe) DO UPDATE SET signal=excluded.signal,candle_time=excluded.candle_time,updated_at=excluded.updated_at",
                (symbol, timeframe, signal, candle_time, iso_now()),
            )
            return str(row["signal"]) if row else None

    def reserve_signal(self, setup_id: str, symbol: str, timeframe: str, signal: str, candle_time: str) -> bool:
        with self.connect() as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO executed_signals(setup_id,symbol,timeframe,signal,candle_time) VALUES(?,?,?,?,?)",
                (setup_id, symbol, timeframe, signal, candle_time),
            )
            return cursor.rowcount == 1

    def complete_signal(self, setup_id: str, ticket: str | int | None) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE executed_signals SET status='EXECUTED',executed_at=?,ticket=? WHERE setup_id=?",
                (iso_now(), str(ticket or ""), setup_id),
            )

    def release_signal(self, setup_id: str) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM executed_signals WHERE setup_id=? AND status='RESERVED'", (setup_id,))

    def signal_exists(self, setup_id: str) -> bool:
        with self.connect() as db:
            return db.execute("SELECT 1 FROM executed_signals WHERE setup_id=?", (setup_id,)).fetchone() is not None

    def last_executed_signal(self, symbol: str | None = None) -> dict[str, Any] | None:
        query, params = "SELECT * FROM executed_signals WHERE status='EXECUTED'", ()
        if symbol:
            query, params = query + " AND symbol=?", (symbol,)
        with self.connect() as db:
            row = db.execute(query + " ORDER BY executed_at DESC LIMIT 1", params).fetchone()
            return dict(row) if row else None

    def save_bot_log(self, level: str, payload: dict[str, Any]) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO bot_logs(created_at,level,message) VALUES(?,?,?)", (iso_now(), level, json.dumps(payload)))

    def runtime_state(self) -> dict[str, Any]:
        with self.connect() as db:
            return dict(db.execute("SELECT * FROM runtime_control WHERE id=1").fetchone())

    def set_runtime_mode(self, mode: str, *, stop: bool = False) -> None:
        if mode not in {"AUTO_DEMO", "MANUAL", "PAUSED"}:
            raise ValueError("Unknown controller mode")
        with self.connect() as db:
            db.execute("UPDATE runtime_control SET mode=?,stop_requested=MAX(stop_requested,?) WHERE id=1", (mode, int(stop)))
            db.execute("INSERT INTO bot_logs(created_at,level,message) VALUES(?,?,?)", (iso_now(), "INFO", json.dumps({"event": "CONTROL", "mode": mode, "stop_requested": stop})))

    def claim_worker(self, token: str, *, manual: bool = False) -> bool:
        now = time.time()
        with self.connect() as db:
            cursor = db.execute(
                "UPDATE runtime_control SET worker_id=?,pid=NULL,heartbeat=?,phase='STARTING',stop_requested=0,last_error=NULL,mode=CASE WHEN ? THEN 'MANUAL' ELSE mode END "
                "WHERE id=1 AND (worker_id IS NULL OR heartbeat<?)",
                (token, now, manual, now - WORKER_LEASE_SECONDS),
            )
            return cursor.rowcount == 1

    def touch_worker(self, token: str, *, phase: str | None = None, pid: int | None = None, error: str | None = None, execution: dict[str, Any] | None = None) -> bool:
        fields: dict[str, Any] = {"heartbeat": time.time()}
        if phase is not None:
            fields["phase"] = phase
        if pid is not None:
            fields["pid"] = pid
        if error is not None:
            fields["last_error"] = error
        if execution is not None:
            fields["last_execution"] = json.dumps(execution)
        with self.connect() as db:
            cursor = db.execute(f"UPDATE runtime_control SET {','.join(key + '=?' for key in fields)} WHERE id=1 AND worker_id=?", (*fields.values(), token))
            return cursor.rowcount == 1

    def release_worker(self, token: str, error: str | None = None) -> None:
        with self.connect() as db:
            db.execute("UPDATE runtime_control SET worker_id=NULL,pid=NULL,phase='STOPPED',last_error=COALESCE(?,last_error) WHERE id=1 AND worker_id=?", (error, token))

    def rows(self, table: str, limit: int = 100) -> list[dict[str, Any]]:
        if table not in {"signals", "trades", "news", "price_levels", "performance", "bot_logs", "executed_signals"}:
            raise ValueError("Table is not dashboard-readable")
        with self.connect() as db:
            return [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT ?", (limit,))]
