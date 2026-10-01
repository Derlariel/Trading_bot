"""Thread-safe-enough SQLite store using one connection per operation."""
from __future__ import annotations

import json
import sqlite3
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
"""


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

    def rows(self, table: str, limit: int = 100) -> list[dict[str, Any]]:
        if table not in {"signals", "trades", "news", "price_levels", "performance"}:
            raise ValueError("Table is not dashboard-readable")
        with self.connect() as db:
            return [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT ?", (limit,))]
