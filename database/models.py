"""Shared domain models."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class SignalType(str, Enum):
    STRONG_BUY = "STRONG BUY"
    BUY = "BUY"
    WAIT = "WAIT"
    SELL = "SELL"
    STRONG_SELL = "STRONG SELL"


@dataclass(frozen=True)
class PriceZone:
    type: str
    low: float
    high: float
    strength: float
    touches: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TradePlan:
    symbol: str
    signal: SignalType
    confidence: float
    entry_zone: tuple[float, float]
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    risk_reward: float
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["signal"] = self.signal.value
        return data
