"""krx-news-client — 한국 주식시장 뉴스/공시 수집 클라이언트 라이브러리."""

from krx_news_client.dedup import Deduplicator
from krx_news_client.models.schemas import (
    KST,
    Disclosure,
    DisclosureDocument,
    NewsArticle,
    NewsCategory,
    NewsSource,
    is_correction,
)
from krx_news_client.scrapers.base import BaseScraper
from krx_news_client.scrapers.dart import (
    DartAPIError,
    DartQuotaExceededError,
    DartScraper,
    quarter_ranges,
)
from krx_news_client.scrapers.toss import (
    TossResponseError,
    TossScraper,
    news_id_from_url,
    normalize_stock_code,
)

__all__ = [
    "KST",
    "BaseScraper",
    "DartAPIError",
    "DartQuotaExceededError",
    "DartScraper",
    "Deduplicator",
    "Disclosure",
    "DisclosureDocument",
    "NewsArticle",
    "NewsCategory",
    "NewsSource",
    "TossResponseError",
    "TossScraper",
    "is_correction",
    "news_id_from_url",
    "normalize_stock_code",
    "quarter_ranges",
]
