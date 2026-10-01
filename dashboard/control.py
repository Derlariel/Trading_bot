"""Shared SQLite controller; the dashboard never places an order itself."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from uuid import uuid4

from config import BASE_DIR, settings
from database.database import Database, WORKER_LEASE_SECONDS
from mt5.connector import MT5Connector, native_mt5


def load_status(database: Database) -> dict:
    state = database.runtime_state()
    age = max(0, time.time() - state["heartbeat"]) if state["heartbeat"] else None
    fresh = age is not None and age < WORKER_LEASE_SECONDS
    state["mode_source"] = "CONTROLLER" if state["mode"] else "ENVIRONMENT"
    state["mode"] = state["mode"] or ("AUTO_DEMO" if settings.auto_trade and settings.demo_mode else "MANUAL")
    state["state"] = "STOPPED" if not state["worker_id"] else "STALE" if not fresh else "STOPPING" if state["stop_requested"] else "STARTING" if state["phase"] == "STARTING" else "RUNNING"
    state["running"] = state["state"] in {"RUNNING", "STARTING", "STOPPING"}
    state["heartbeat_age"] = age
    state["heartbeat_at"] = datetime.fromtimestamp(state["heartbeat"], UTC).isoformat() if state["heartbeat"] else None
    state["last_execution"] = json.loads(state["last_execution"]) if state["last_execution"] else {}
    return state


def set_mode(database: Database, mode: str, connector: MT5Connector) -> dict:
    if mode not in {"AUTO_DEMO", "MANUAL", "PAUSED"}:
        raise ValueError("Unknown controller mode")
    if mode == "AUTO_DEMO":
        if not connector.is_connected():
            raise ConnectionError("Connect MT5 to a Demo account before enabling Auto Demo")
        account = connector.account_info()
        if account.get("trade_mode") != getattr(native_mt5, "ACCOUNT_TRADE_MODE_DEMO", 0):
            raise ValueError("Auto Demo requires a verified MT5 Demo account")
    database.set_runtime_mode(mode)
    return load_status(database)


def start_worker(database: Database) -> dict:
    token = uuid4().hex
    # Each dashboard start requires a separate, explicit Auto Demo selection.
    if not database.claim_worker(token, manual=True):
        return load_status(database)
    try:
        environment = {**os.environ, "DATABASE_PATH": str(database.path.resolve())}
        subprocess.Popen(
            [sys.executable, str(BASE_DIR / "main.py"), "--symbol", settings.symbols[0], "--watch", "60", "--worker-token", token],
            cwd=BASE_DIR, env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as error:
        database.release_worker(token, str(error))
        raise
    database.save_bot_log("INFO", {"event": "WORKER_START", "mode": "MANUAL"})
    return load_status(database)


def stop_worker(database: Database) -> dict:
    database.set_runtime_mode("PAUSED", stop=True)
    return load_status(database)
