"""Application settings loaded from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Immutable runtime configuration."""

    symbols: tuple[str, ...] = tuple(filter(None, os.getenv("SYMBOLS", "AAPL,NVDA,TSLA").split(",")))
    timeframe: str = os.getenv("TIMEFRAME", "M15").upper()
    candle_count: int = int(os.getenv("CANDLE_COUNT", "500"))
    risk_per_trade: float = float(os.getenv("RISK_PER_TRADE", "0.01"))
    max_risk_per_trade: float = float(os.getenv("MAX_RISK_PER_TRADE", "0.02"))
    min_confidence: float = float(os.getenv("MIN_CONFIDENCE", "70"))
    min_rr: float = float(os.getenv("MIN_RR", "2"))
    atr_multiplier: float = float(os.getenv("ATR_MULTIPLIER", "1.5"))
    max_trades_per_day: int = int(os.getenv("MAX_TRADES_PER_DAY", "5"))
    max_daily_loss: float = float(os.getenv("MAX_DAILY_LOSS", "0.03"))
    max_positions: int = int(os.getenv("MAX_SIMULTANEOUS_POSITIONS", "3"))
    max_spread_points: float = float(os.getenv("MAX_SPREAD_POINTS", "50"))
    use_news: bool = _bool("USE_NEWS", True)
    use_finbert: bool = _bool("USE_FINBERT", True)
    demo_mode: bool = _bool("DEMO_MODE", True)
    live_trading: bool = _bool("LIVE_TRADING", False)
    mt5_login: int | None = int(os.environ["MT5_LOGIN"]) if os.getenv("MT5_LOGIN") else None
    mt5_password: str | None = os.getenv("MT5_PASSWORD")
    mt5_server: str | None = os.getenv("MT5_SERVER")
    alpha_vantage_key: str | None = os.getenv("ALPHA_VANTAGE_API_KEY")
    database_path: Path = Path(os.getenv("DATABASE_PATH", str(BASE_DIR / "trading_bot.db")))
    log_path: Path = Path(os.getenv("LOG_PATH", str(BASE_DIR / "bot.log")))
    magic_number: int = int(os.getenv("MAGIC_NUMBER", "260101"))
    deviation: int = int(os.getenv("DEVIATION", "20"))
    signal_weights: dict[str, float] = field(default_factory=lambda: {
        "trend": .15, "levels": .20, "indicators": .15, "volume": .10,
        "candlestick": .05, "breakout": .10, "multi_timeframe": .15, "news": .10,
    })

    def __post_init__(self) -> None:
        if not 0 < self.risk_per_trade <= self.max_risk_per_trade <= .1:
            raise ValueError("Risk settings must satisfy 0 < risk <= max risk <= 10%")
        if self.live_trading and self.demo_mode:
            raise ValueError("LIVE_TRADING and DEMO_MODE cannot both be enabled")
        if abs(sum(self.signal_weights.values()) - 1) > 1e-9:
            raise ValueError("Signal weights must total 1.0")


settings = Settings()

# Friendly module-level aliases requested by the V1 specification.
SYMBOLS, TIMEFRAME = list(settings.symbols), settings.timeframe
RISK_PER_TRADE, MIN_CONFIDENCE, MIN_RR = settings.risk_per_trade, settings.min_confidence, settings.min_rr
ATR_MULTIPLIER, MAX_TRADES_PER_DAY = settings.atr_multiplier, settings.max_trades_per_day
MAX_DAILY_LOSS, USE_NEWS, USE_FINBERT = settings.max_daily_loss, settings.use_news, settings.use_finbert
DEMO_MODE, LIVE_TRADING = settings.demo_mode, settings.live_trading
