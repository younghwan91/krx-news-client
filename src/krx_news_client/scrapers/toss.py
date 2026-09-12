from __future__ import annotations

import json
import logging
import urllib.parse
from datetime import datetime

from krx_news_client.models.schemas import KST, NewsArticle, NewsCategory, NewsSource
from krx_news_client.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# 토스가 주는 ``createdAt``은 오프셋 없는 KST 벽시계다("2026-09-05T18:10:12").
# 그대로 naive 로 두면 소비자가 ``timestamptz`` 컬럼(세션 TZ=UTC)에 넣는 순간
# 9시간 미래로 밀린다 — 2026-09-13 실제로 그렇게 밀려 있는 걸 발견해 고쳤다
# (quant-airflow news_articles 의 시각 분포가 장중엔 비고 저녁 17~18시에 몰려
# 보였다. 9시간 되돌리면 장전 08시·개장 09시·마감 15시 피크로 정확히 맞는다).

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
        """토스 ``createdAt``을 **tz 있는** datetime 으로 읽는다.

        오프셋이 없으면 KST 로 간주한다(토스는 한국 서비스이고, 실측 시각 분포가
        KST 장 시간대와 맞는다 — 모듈 상단 ``KST`` 주석 참고). 오프셋이 붙어
        오면 그걸 그대로 존중한다.
        """
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=KST)
        return parsed
