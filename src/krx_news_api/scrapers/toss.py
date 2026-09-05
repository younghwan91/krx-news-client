from __future__ import annotations

import json
import logging
import urllib.parse
from datetime import datetime

from krx_news_api.models.schemas import NewsArticle, NewsCategory, NewsSource
from krx_news_api.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

DASHBOARD_NEWS_URL = "https://wts-info-api.tossinvest.com/api/v1/dashboard/wts/news"

# dashboard feed type -> NewsCategory
FEED_TYPES: dict[str, NewsCategory] = {
    "ALL_HIGHLIGHT": NewsCategory.MARKET,
    "HOT": NewsCategory.BREAKING,
    "SOARING_STOCK": NewsCategory.STOCK,
}


def build_article_url(news_id: str) -> str:
    content_params = json.dumps(
        {"id": news_id}, ensure_ascii=False, separators=(",", ":")
    )
    query = urllib.parse.urlencode(
        {"contentType": "news", "contentParams": content_params}
    )
    return f"https://tossinvest.com/news?{query}"


class TossScraper(BaseScraper):
    source = NewsSource.TOSS
    base_url = "https://wts-info-api.tossinvest.com"
    min_delay = 0.5
    max_delay = 1.5

    async def scrape_news(self) -> list[NewsArticle]:
        articles: list[NewsArticle] = []
        for feed_type, category in FEED_TYPES.items():
            try:
                articles.extend(await self._fetch_feed(feed_type, category))
            except Exception:
                logger.exception("Failed to scrape Toss feed %s", feed_type)
        return articles

    async def _fetch_feed(
        self, feed_type: str, category: NewsCategory
    ) -> list[NewsArticle]:
        resp = await self.fetch_post(
            DASHBOARD_NEWS_URL, json={"type": feed_type}
        )
        payload = resp.json()
        items = payload.get("result", {}).get("news", [])
        return [
            article
            for item in items
            if (article := self._parse_item(item, category)) is not None
        ]

    def _parse_item(self, item: dict, category: NewsCategory) -> NewsArticle | None:
        news_id = item.get("newsId")
        title = item.get("title")
        if not news_id or not title:
            return None

        return self._make_article(
            title=title,
            url=build_article_url(news_id),
            category=category,
            content=item.get("contentText", ""),
            summary=item.get("summary", ""),
            tickers=self._extract_tickers(item),
            author=item.get("source", ""),
            published_at=self._parse_date(item.get("createdAt")),
        )

    @staticmethod
    def _extract_tickers(item: dict) -> list[str]:
        tickers = []
        for stock in item.get("relatedStocks") or []:
            code = stock.get("stockCode", "")
            if code:
                tickers.append(code.removeprefix("A"))
        return tickers

    @staticmethod
    def _parse_date(text: str | None) -> datetime | None:
        if not text:
            return None
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None
