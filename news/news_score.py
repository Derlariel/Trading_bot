"""News importance and aggregate sentiment."""
from __future__ import annotations

HIGH_IMPACT = ("federal reserve", "fomc", "interest rate", "cpi", "nfp", "gdp", "inflation", "earnings", "sec", "ceo", "bankruptcy", "merger", "acquisition", "geopolitical")


def importance(text: str) -> float:
    matches = sum(term in text.lower() for term in HIGH_IMPACT)
    return min(1.0, .25 + matches * .25)


def aggregate(items: list[dict[str, object]]) -> float:
    weighted = [(float(item.get("sentiment", 0)), float(item.get("importance", .25))) for item in items]
    total = sum(weight for _, weight in weighted)
    return sum(score * weight for score, weight in weighted) / total if total else 0.0
