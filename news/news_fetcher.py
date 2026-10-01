"""News facade combining GDELT, importance, and optional FinBERT."""
from __future__ import annotations

from config import settings
from news.finbert_analyzer import analyze_sentiment
from news.gdelt_client import search_gdelt
from news.news_score import importance


async def fetch_news(symbol: str, company: str = "", keywords: tuple[str, ...] = ()) -> list[dict[str, object]]:
    query = " OR ".join(filter(None, (symbol, company, *keywords)))
    articles = await search_gdelt(query)
    for article in articles:
        text = f"{article['headline']} {article.get('summary', '')}"
        sentiment = analyze_sentiment(text) if settings.use_finbert else {"label": "neutral", "score": 0}
        article.update(sentiment=float(sentiment["score"]), sentiment_label=sentiment["label"], importance=importance(text))
    return articles
