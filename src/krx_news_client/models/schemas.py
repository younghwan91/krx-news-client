from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

KST = ZoneInfo("Asia/Seoul")

#: DART ``report_nm`` 앞에 붙는 정정·첨부 표시. 원 공시의 재탕이라 신선도가 낮다.
CORRECTION_MARKERS = ("[기재정정]", "[첨부정정]", "[첨부추가]", "[정정]")


def _now_kst() -> datetime:
    """수집 시각. **tz 를 붙여서** 돌려준다.

    ``datetime.now()`` 는 naive 라, 소비자가 ``timestamptz`` 컬럼(세션 TZ=UTC)에
    넣으면 KST 벽시계가 UTC 로 읽혀 9시간 미래로 밀린다(2026-09-13 실제 사고 —
    ``scrapers/toss.py`` 의 ``KST`` 주석 참고).
    """
    return datetime.now(tz=KST)


def is_correction(report_nm: str) -> bool:
    """정정·첨부 공시인가(``[기재정정]``·``[첨부정정]``·``[첨부추가]``·``[정정]``).

    DART 제목 형식 규칙일 뿐 전략 판단이 아니라서 수집 라이브러리에 둔다
    (scalp-it ``dart/classify.py`` 에서 옮김).
    """
    text = str(report_nm or "").strip()
    return any(text.startswith(marker) for marker in CORRECTION_MARKERS)


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
    tickers: list[str] = Field(
        default_factory=list,
        description="관련 종목코드. 한국 종목은 6자리(e.g. 005930), 해외 종목은 소스 원본 코드",
    )
    author: str = ""
    published_at: datetime
    collected_at: datetime = Field(default_factory=_now_kst)
    news_id: str = Field(default="", description="소스 고유 기사 ID (토스 newsId)")
    news_type: str = Field(default="", description="소스 기사 유형 (토스 newsType)")
    nation: str = Field(default="", description="기사 대상 시장 (토스: KR/US)")
    sentiment: str = Field(default="", description="소스가 붙인 감성 라벨 (토스 상세: POSITIVE 등)")
    original_url: str = Field(default="", description="언론사 원문 URL (토스 상세)")


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
    rcept_no: str = Field(default="", description="DART 접수번호. 같은 날 공시의 순서·중복 제거 키")
    corp_code: str = Field(default="", description="DART 고유번호(8자리)")
    corp_cls: str = Field(default="", description="법인구분 Y=유가 K=코스닥 N=코넥스 E=기타")
    rm: str = Field(default="", description="DART 비고(유=유가증권시장본부 소관, 정=정정 등)")
    is_correction: bool = Field(default=False, description="제목이 정정·첨부 표시로 시작하는가")


class DisclosureDocument(BaseModel):
    """DART ``document.xml`` 로 받은 공시 원문 한 파일."""

    rcept_no: str
    filename: str
    html: str = Field(description="원문 마크업(DART HTML/XML) 그대로")
    text: str = Field(description="태그·스타일을 걷어낸 본문 텍스트")
