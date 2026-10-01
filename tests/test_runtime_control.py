"""Controller checks use temporary databases and fake MT5; never start a bot."""
import time
from types import SimpleNamespace

import pytest

from dashboard import control
from database.database import Database, WORKER_LEASE_SECONDS
import mt5.order_manager as order_module


def demo_connector(mode=0):
    return SimpleNamespace(is_connected=lambda: True, account_info=lambda: {"trade_mode": mode})


def fake_broker(monkeypatch):
    sent = []
    native = SimpleNamespace(
        ACCOUNT_TRADE_MODE_DEMO=0, TRADE_ACTION_DEAL=1, ORDER_TYPE_BUY=0, ORDER_TYPE_SELL=1,
        ORDER_TIME_GTC=0, ORDER_FILLING_IOC=1, ORDER_FILLING_FOK=0, ORDER_FILLING_RETURN=2,
        TRADE_RETCODE_DONE=10009, symbol_info_tick=lambda symbol: SimpleNamespace(ask=100., bid=99.9),
        symbol_info=lambda symbol: SimpleNamespace(filling_mode=2),
        order_check=lambda request: SimpleNamespace(retcode=0),
        order_send=lambda request: sent.append(request) or SimpleNamespace(retcode=10009, price=100., _asdict=lambda: {"order": 7}),
    )
    monkeypatch.setattr(order_module, "native_mt5", native)
    monkeypatch.setattr(order_module, "settings", SimpleNamespace(auto_trade=False, demo_mode=False, live_trading=False, deviation=20, magic_number=2601001, timeframe="M15"))
    return native, sent


def send(orders):
    return orders.market_order("XAUUSD", "BUY", .01, 98, 104, SimpleNamespace(approved=True, reasons=()))


def test_mode_requires_current_demo_and_persists(tmp_path):
    db = Database(tmp_path / "control.db")
    control.set_mode(db, "MANUAL", demo_connector())
    for connector in (demo_connector(2), demo_connector(None)):
        with pytest.raises(ValueError, match="Demo account"):
            control.set_mode(db, "AUTO_DEMO", connector)
        assert control.load_status(db)["mode"] == "MANUAL"
    control.set_mode(db, "AUTO_DEMO", demo_connector())
    assert control.load_status(Database(db.path))["mode"] == "AUTO_DEMO"


def test_worker_start_is_single_hidden_and_manual(tmp_path, monkeypatch):
    db = Database(tmp_path / "control.db")
    control.set_mode(db, "AUTO_DEMO", demo_connector())
    launched = []
    monkeypatch.setattr(control.subprocess, "Popen", lambda *args, **kwargs: launched.append((args, kwargs)))
    first = control.start_worker(db)
    second = control.start_worker(Database(db.path))
    assert len(launched) == 1 and first["worker_id"] == second["worker_id"]
    assert first["state"] == "STARTING" and first["mode"] == "MANUAL"
    assert launched[0][0][0][0] == control.sys.executable
    assert launched[0][1]["env"]["DATABASE_PATH"] == str(db.path.resolve())
    assert launched[0][1]["stdout"] == control.subprocess.DEVNULL
    db.touch_worker(first["worker_id"], phase="ANALYZING", pid=42)
    assert control.load_status(db)["state"] == "RUNNING"
    stopped = control.stop_worker(db)
    assert stopped["state"] == "STOPPING" and stopped["mode"] == "PAUSED"
    db.release_worker(first["worker_id"])
    assert control.load_status(db)["state"] == "STOPPED"


def test_failed_launch_releases_lease_and_records_error(tmp_path, monkeypatch):
    db = Database(tmp_path / "control.db")
    def fail(*args, **kwargs):
        raise OSError("test launch failure")
    monkeypatch.setattr(control.subprocess, "Popen", fail)
    with pytest.raises(OSError):
        control.start_worker(db)
    state = control.load_status(db)
    assert state["state"] == "STOPPED" and state["last_error"] == "test launch failure"


def test_expired_worker_cannot_send_or_release_new_owner(tmp_path, monkeypatch):
    db = Database(tmp_path / "control.db")
    fake_broker(monkeypatch)
    control.set_mode(db, "AUTO_DEMO", demo_connector())
    assert db.claim_worker("old")
    with db.connect() as connection:
        connection.execute("UPDATE runtime_control SET heartbeat=?", (time.time() - WORKER_LEASE_SECONDS - 1,))
    assert control.load_status(db)["state"] == "STALE"
    assert db.claim_worker("new")
    assert send(order_module.OrderManager(demo_connector(), db, worker_id="old"))["reason"] == "WORKER_LEASE_LOST"
    db.release_worker("old")
    assert db.runtime_state()["worker_id"] == "new"


def test_auto_demo_overrides_environment_but_rechecks_account(tmp_path, monkeypatch):
    db = Database(tmp_path / "control.db")
    _, sent = fake_broker(monkeypatch)
    connector = demo_connector()
    control.set_mode(db, "AUTO_DEMO", connector)
    orders = order_module.OrderManager(connector, db)
    assert send(orders)["ok"] and len(sent) == 1
    connector.account_info = lambda: {"trade_mode": 2}
    assert send(orders)["reason"] == "DEMO_ACCOUNT_REQUIRED" and len(sent) == 1


@pytest.mark.parametrize("mode", ["MANUAL", "PAUSED"])
def test_mode_changed_during_broker_check_prevents_send(tmp_path, monkeypatch, mode):
    db = Database(tmp_path / "control.db")
    native, sent = fake_broker(monkeypatch)
    control.set_mode(db, "AUTO_DEMO", demo_connector())
    def check(request):
        control.set_mode(db, mode, demo_connector())
        return SimpleNamespace(retcode=0)
    native.order_check = check
    result = send(order_module.OrderManager(demo_connector(), db))
    assert not result["ok"] and not sent


def test_control_read_failure_blocks_broker_send(tmp_path, monkeypatch):
    db = Database(tmp_path / "control.db")
    _, sent = fake_broker(monkeypatch)
    def fail():
        raise OSError("controller unavailable")
    monkeypatch.setattr(db, "runtime_state", fail)
    assert send(order_module.OrderManager(demo_connector(), db))["reason"] == "RUNTIME_CONTROL_UNAVAILABLE"
    assert not sent
