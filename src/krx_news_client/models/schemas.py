from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

KST = ZoneInfo("Asia/Seoul")


def _now_kst() -> datetime:
    """수집 시각. **tz 를 붙여서** 돌려준다.

    ``datetime.now()`` 는 naive 라, 소비자가 ``timestamptz`` 컬럼(세션 TZ=UTC)에
    넣으면 KST 벽시계가 UTC 로 읽혀 9시간 미래로 밀린다(2026-09-13 실제 사고 —
    ``scrapers/toss.py`` 의 ``KST`` 주석 참고).
    """
    return datetime.now(tz=KST)


class NewsSource(StrEnum):
    DART = "dart"
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
    collected_at: datetime = Field(default_factory=_now_kst)


class Disclosure(BaseModel):
    id: str
    source: NewsSource
    title: str
    url: str
    company: str
    ticker: str
    disclosure_type: str = ""
    published_at: datetime
    collected_at: datetime = Field(default_factory=_now_kst)
