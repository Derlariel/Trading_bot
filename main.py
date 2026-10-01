"""CLI entry point for analysis, paper/live execution, and CSV backtesting."""
from __future__ import annotations

import argparse
import asyncio
import os
from datetime import UTC, datetime
from threading import Event, Thread
from uuid import uuid4

import pandas as pd

from analyzers.indicator_analyzer import calculate_indicators
from analyzers.multi_timeframe import aggregate_trends
from analyzers.trend_analyzer import analyze_trend
from backtest.backtester import run_backtest
from config import settings
from database.database import Database
from mt5.chart_exporter import export_overlay
from mt5.connector import MT5Connector
from mt5.market_data import MarketData
from mt5.order_manager import OrderManager
from news.news_fetcher import fetch_news
from news.news_score import aggregate
from strategy.strategy import analyze
from utils.logger import get_logger

logger = get_logger(__name__)


def _csv(path: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if "time" in frame:
        frame["time"] = pd.to_datetime(frame["time"], utc=True)
    return frame


async def analyze_symbol(symbol: str, market: MarketData, database: Database) -> dict[str, object]:
    frames, trends = {}, {}
    for timeframe in ("H4", "H1", "M15", "M5"):
        try:
            frames[timeframe] = market.get_candles(symbol, timeframe, settings.candle_count)
            trends[timeframe] = analyze_trend(calculate_indicators(frames[timeframe]))
        except (ConnectionError, ValueError) as error:
            logger.warning("%s %s unavailable: %s", symbol, timeframe, error)
    if settings.timeframe not in frames:
        frames[settings.timeframe] = market.get_candles(symbol, settings.timeframe, settings.candle_count)
    multi = aggregate_trends(trends)
    articles = await fetch_news(symbol) if settings.use_news else []
    news_score = aggregate(articles)
    result = analyze(symbol, frames[settings.timeframe], float(multi["score"]), news_score)
    database.save_signal({**result["plan"].to_dict(), "timeframe": settings.timeframe, "candle_time": result["candles"].time.iloc[-1].isoformat()})
    for item in articles:
        database.save_news(symbol, item)
    return result


async def run() -> int:
    parser = argparse.ArgumentParser(description="Safety-first MT5 trading bot")
    parser.add_argument("--symbol", default=settings.symbols[0])
    parser.add_argument("--backtest", metavar="CSV", help="Backtest OHLC[V] CSV instead of connecting to MT5")
    parser.add_argument("--watch", type=int, metavar="SECONDS", help="Repeat analysis and refresh the MT5 chart overlay")
    parser.add_argument("--worker-token", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.watch is not None and args.watch < 5:
        parser.error("--watch must be at least 5 seconds")
    if args.backtest:
        candles = _csv(args.backtest)
        result = run_backtest(candles, lambda data: analyze(args.symbol, data)["plan"])
        print(pd.Series(result["metrics"]).to_string())
        return 0
    connector, database = MT5Connector(), Database()
    token = args.worker_token or uuid4().hex
    if args.worker_token:
        claimed = database.touch_worker(token, phase="CONNECTING", pid=os.getpid())
    else:
        claimed = database.claim_worker(token)
        if claimed:
            database.touch_worker(token, phase="CONNECTING", pid=os.getpid())
    if not claimed:
        logger.error("Another bot worker already owns this database; use the controller to stop it first.")
        return 1
    orders = OrderManager(connector, database, worker_id=token)
    stopped = Event()

    def heartbeat() -> None:
        while not stopped.wait(5):
            try:
                if not database.touch_worker(token):
                    stopped.set()
            except Exception:
                logger.exception("Worker heartbeat unavailable; blocking further execution")
                stopped.set()

    watcher = Thread(target=heartbeat, daemon=True)
    watcher.start()
    try:
        if not connector.initialize():
            error = "MT5 is unavailable. Start the terminal or use --backtest CSV."
            database.touch_worker(token, error=error)
            logger.error(error)
            return 1
        while not stopped.is_set():
            control = database.runtime_state()
            if control["stop_requested"] or control["worker_id"] != token:
                break
            if control["mode"] == "PAUSED":
                database.touch_worker(token, phase="PAUSED")
                if args.watch is None:
                    return 0
                await asyncio.sleep(1)
                continue
            try:
                database.touch_worker(token, phase="ANALYZING")
                result = await analyze_symbol(args.symbol, MarketData(connector), database)
                candle_time = result["candles"].time.iloc[-1]
                execution = orders.auto_order(result["plan"], settings.timeframe, candle_time)
                database.touch_worker(token, phase="EXPORTING", execution=execution)
                overlay = export_overlay(connector, args.symbol, settings.timeframe, result, execution)
                print(pd.Series(result["plan"].to_dict()).to_string())
                logger.info("Analysis complete at %s; MT5 overlay: %s; execution=%s", datetime.now(UTC).isoformat(), overlay, execution)
                database.touch_worker(token, phase="IDLE", error="")
            except Exception as error:
                logger.exception("Watch iteration failed for %s", args.symbol)
                database.touch_worker(token, phase="ERROR", error=str(error))
                database.save_bot_log("ERROR", {"event": "ITERATION_FAILED", "symbol": args.symbol, "reason": str(error)})
                if args.watch is None:
                    return 1
            if args.watch is None:
                return 0
            for _ in range(args.watch):
                if stopped.is_set() or database.runtime_state()["stop_requested"]:
                    break
                await asyncio.sleep(1)
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as error:
        logger.exception("Worker stopped after controller failure")
        try:
            database.touch_worker(token, phase="ERROR", error=str(error))
        except Exception:
            pass
        return 1
    finally:
        stopped.set()
        watcher.join(timeout=2)
        connector.disconnect()
        try:
            database.release_worker(token)
        except Exception:
            logger.exception("Unable to release worker lease; it will expire")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
