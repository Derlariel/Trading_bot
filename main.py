"""CLI entry point for analysis, paper/live execution, and CSV backtesting."""
from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime

import pandas as pd

from analyzers.indicator_analyzer import calculate_indicators
from analyzers.multi_timeframe import aggregate_trends
from analyzers.trend_analyzer import analyze_trend
from backtest.backtester import run_backtest
from config import settings
from database.database import Database
from mt5.connector import MT5Connector
from mt5.market_data import MarketData
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
    database.save_signal(result["plan"].to_dict())
    for item in articles:
        database.save_news(symbol, item)
    return result


async def run() -> int:
    parser = argparse.ArgumentParser(description="Safety-first MT5 trading bot")
    parser.add_argument("--symbol", default=settings.symbols[0])
    parser.add_argument("--backtest", metavar="CSV", help="Backtest OHLC[V] CSV instead of connecting to MT5")
    args = parser.parse_args()
    if args.backtest:
        candles = _csv(args.backtest)
        result = run_backtest(candles, lambda data: analyze(args.symbol, data)["plan"])
        print(pd.Series(result["metrics"]).to_string())
        return 0
    connector, database = MT5Connector(), Database()
    if not connector.initialize():
        logger.error("MT5 is unavailable. Start the terminal or use --backtest CSV.")
        return 1
    try:
        result = await analyze_symbol(args.symbol, MarketData(connector), database)
        print(pd.Series(result["plan"].to_dict()).to_string())
        logger.info("Analysis complete at %s", datetime.now(UTC).isoformat())
        return 0
    finally:
        connector.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
