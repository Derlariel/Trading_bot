"""Lazy FinBERT sentiment so technical analysis never depends on model startup."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from utils.logger import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def _pipeline() -> Any:
    from transformers import pipeline
    return pipeline("text-classification", model="ProsusAI/finbert", tokenizer="ProsusAI/finbert", top_k=None)


def analyze_sentiment(text: str) -> dict[str, float | str]:
    """Return label probabilities and signed score; neutral on model failure."""
    if not text.strip():
        return {"label": "neutral", "positive": 0, "neutral": 1, "negative": 0, "score": 0}
    try:
        values = _pipeline()(text[:2000])[0]
        probabilities = {item["label"].lower(): float(item["score"]) for item in values}
        label = max(probabilities, key=probabilities.get)  # type: ignore[arg-type]
        return {"label": label, **probabilities, "score": probabilities.get("positive", 0) - probabilities.get("negative", 0)}
    except Exception as error:  # Model/network errors must not disable technical analysis.
        logger.warning("FinBERT unavailable: %s", error)
        return {"label": "neutral", "positive": 0, "neutral": 1, "negative": 0, "score": 0}
