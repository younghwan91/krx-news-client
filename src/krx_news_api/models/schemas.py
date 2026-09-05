from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class NewsSource(StrEnum):
    KIND = "kind"
    DART = "dart"
    NAVER = "naver"
    HANKYUNG = "hankyung"
    THEBELL = "thebell"
    TOSS = "toss"


class NewsCategory(StrEnum):
    DISCLOSURE = "disclosure"
    MARKET = "market"
    STOCK = "stock"
    ECONOMY = "economy"
    ANALYSIS = "analysis"
    BREAKING = "breaking"


class NewsArticle(BaseModel):
    id: str = Field(description="고유 ID (source:hash)")
    source: NewsSource
    category: NewsCategory
    title: str
    url: str
    content: str = ""
    summary: str = ""
    tickers: list[str] = Field(default_factory=list, description="관련 종목코드 (e.g. 005930)")
    author: str = ""
    published_at: datetime
    collected_at: datetime = Field(default_factory=datetime.now)


class Disclosure(BaseModel):
    id: str
    source: NewsSource
    title: str
    url: str
    company: str
    ticker: str
    disclosure_type: str = ""
    published_at: datetime
    collected_at: datetime = Field(default_factory=datetime.now)


class PaginatedResponse(BaseModel):
    items: list[NewsArticle | Disclosure]
    total: int
    page: int
    page_size: int
    has_next: bool


class CrawlerStatus(BaseModel):
    source: NewsSource
    last_crawled_at: datetime | None = None
    articles_count: int = 0
    is_healthy: bool = True
    error: str | None = None
