"""네이버 검색 API(뉴스) -- 키워드·종목명으로 찾는 공식 뉴스 검색.

공식 오픈 API(https://developers.naver.com/docs/serviceapi/search/news/news.md)만
부른다. 네이버 금융 페이지는 robots ``Disallow: /`` 라 긁지 않는다.

- 인증: 네이버 개발자 센터(https://developers.naver.com/apps/#/register)에서
  애플리케이션을 등록하고 "검색" API 를 고르면 Client ID·Secret 이 나온다(무료).
  환경변수 ``NAVER_CLIENT_ID``·``NAVER_CLIENT_SECRET`` 로 넘긴다.
- 한도: 검색 API 전체 하루 25,000회, ``display`` 1~100, ``start`` 1~1000(그래서
  한 검색어로 최대 1,099건까지만 넘길 수 있다), ``sort`` 는 ``sim``·``date``.

이용 약관(2026-11-26 확인, https://developers.naver.com/products/terms/ 의
"네이버 검색 API 서비스")이 다른 소스보다 빡빡하다. 호출자가 지켜야 한다:

- 결과가 네이버 검색결과임을 표시하고, 원본 출처와 원본 링크를 함께 보여 줄 것.
- 결과를 복사·저장·캐싱하지 말 것(예외: 서비스 연속성용 임시 보관 -- 서버는 이력
  조회 목적 최대 21일). 장기 아카이브·백테스트 적재 용도로는 쓸 수 없다.
- 데이터를 AI 에 입력하거나 학습·평가에 쓰지 말 것, 제3자에게 제공·판매하지 말 것.
"""

from __future__ import annotations

import html
import logging
import os
import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from krx_news_client.models.schemas import KST, NewsArticle, NewsCategory, NewsSource
from krx_news_client.scrapers.base import LIBRARY_USER_AGENT, BaseScraper
from krx_news_client.scrapers.yonhap import extract_tickers

logger = logging.getLogger(__name__)

NEWS_SEARCH_URL = "https://openapi.naver.com/v1/search/news.json"
CLIENT_ID_ENV = "NAVER_CLIENT_ID"
CLIENT_SECRET_ENV = "NAVER_CLIENT_SECRET"
MAX_DISPLAY = 100
MAX_START = 1000
SORTS = ("date", "sim")
#: 키 발급 안내. 키가 없거나 거절될 때 예외 메시지에 붙인다.
KEY_HELP = (
    "Register an app at https://developers.naver.com/apps/#/register, enable the "
    "'검색' (Search) API, then export NAVER_CLIENT_ID and NAVER_CLIENT_SECRET "
    "(free, 25,000 calls/day)."
)
#: ``scrape_news()`` 가 기본으로 찾는 시장 전체 검색어.
DEFAULT_MARKET_QUERIES: tuple[str, ...] = ("증시",)

_TAG_RE = re.compile(r"<[^>]+>")


class NaverAPIError(RuntimeError):
    """네이버 검색 API 가 오류를 돌려줬다(``errorCode`` 예: ``SE01``·``024``)."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        hint = f" -- {KEY_HELP}" if status_code in (401, 403) else ""
        super().__init__(f"Naver search API {status_code} {code}: {message}{hint}")


class NaverKeyMissingError(ValueError):
    """Client ID·Secret 이 없다. 메시지에 발급 방법이 들어 있다."""


def clean_text(text: str | None) -> str:
    """검색어 강조 ``<b>`` 태그와 HTML 엔티티(``&quot;``)를 걷어낸다."""
    return html.unescape(_TAG_RE.sub("", text or "")).strip()


def parse_pub_date(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        parsed = parsedate_to_datetime(text.strip())
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=KST)
    return parsed.astimezone(KST)


class NaverNewsScraper(BaseScraper):
    """네이버 뉴스 검색 → ``NewsArticle``. Client ID·Secret 이 필요하다.

    ``url`` 은 네이버 뉴스 링크(네이버에 없는 기사면 원문 링크), ``original_url`` 은
    언론사 원문, ``summary`` 는 네이버가 준 요약 패시지, ``content`` 는 비어 있다.
    ``author`` 는 비어 있다 -- API 가 언론사 이름을 주지 않는다(원문 도메인으로 판단).
    """

    source = NewsSource.NAVER
    base_url = "https://openapi.naver.com"
    # 공식 키 API 라 토스용 무작위 지연이 필요 없다. 한도는 서버가 일 25,000회로 건다.
    min_delay = 0.1
    max_delay = 0.1
    default_headers = {"User-Agent": LIBRARY_USER_AGENT}

    def __init__(self, client_id: str, client_secret: str) -> None:
        super().__init__()
        if not client_id or not client_secret:
            raise NaverKeyMissingError(f"Naver client id/secret missing. {KEY_HELP}")
        self._client_id = client_id
        self._client_secret = client_secret

    def __repr__(self) -> str:  # 키를 repr 에 싣지 않는다
        return f"{type(self).__name__}(client_id='***')"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> NaverNewsScraper:
        """``NAVER_CLIENT_ID``·``NAVER_CLIENT_SECRET`` 에서 키를 읽는다. 없으면 발급 안내로 실패."""
        source = os.environ if env is None else env
        client_id = str(source.get(CLIENT_ID_ENV) or "").strip()
        client_secret = str(source.get(CLIENT_SECRET_ENV) or "").strip()
        missing = [
            name
            for name, value in ((CLIENT_ID_ENV, client_id), (CLIENT_SECRET_ENV, client_secret))
            if not value
        ]
        if missing:
            raise NaverKeyMissingError(f"{' and '.join(missing)} not set. {KEY_HELP}")
        return cls(client_id, client_secret)

    async def search_news_page(
        self, query: str, *, display: int = MAX_DISPLAY, start: int = 1, sort: str = "date"
    ) -> dict[str, Any]:
        """검색 한 페이지, 원본 JSON 그대로(``total``·``start``·``display``·``items``).

        Raises:
            ValueError: 빈 검색어, ``display`` 1~100 밖, ``start`` 1~1000 밖, 모르는
                ``sort`` -- 요청 전에 막는다(네이버는 400 SE02/SE03/SE04).
            NaverAPIError: 네이버가 오류를 줬다. 401/403 이면 키 발급 안내가 붙는다.
        """
        if not query or not query.strip():
            raise ValueError("query must not be empty")
        if not 1 <= display <= MAX_DISPLAY:
            raise ValueError(f"display must be 1..{MAX_DISPLAY} (got {display})")
        if not 1 <= start <= MAX_START:
            raise ValueError(f"start must be 1..{MAX_START} (got {start})")
        if sort not in SORTS:
            raise ValueError(f"sort must be one of {SORTS} (got {sort!r})")
        try:
            resp = await self.fetch(
                NEWS_SEARCH_URL,
                params={"query": query, "display": display, "start": start, "sort": sort},
                headers={
                    "X-Naver-Client-Id": self._client_id,
                    "X-Naver-Client-Secret": self._client_secret,
                },
            )
        except httpx.HTTPStatusError as e:
            raise self._api_error(e.response) from e
        payload = resp.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise NaverAPIError(resp.status_code, "", "unexpected payload (no items list)")
        return payload

    async def search_news(
        self,
        query: str,
        *,
        limit: int = 100,
        sort: str = "date",
        since: date | datetime | None = None,
        tickers: Sequence[str] | None = None,
        category: NewsCategory = NewsCategory.STOCK,
    ) -> list[NewsArticle]:
        """검색어 하나로 최대 ``limit`` 건. 결과는 최신순(``sort="date"``) 또는 정확도순.

        Args:
            query: 검색어. 종목은 이름으로 찾는다(``"삼성전자"``) -- 6자리 코드로는
                기사가 거의 안 걸린다.
            limit: 최대 건수, 1~1099(``start`` ≤ 1000 이라 그 너머는 못 넘긴다).
            sort: ``"date"``(최신순) 또는 ``"sim"``(정확도순).
            since: 이 시각 이후 기사만(``date`` 면 그날 00:00 KST). ``sort="date"`` 일
                때 한 페이지가 통째로 이보다 오래됐으면 더 넘기지 않는다.
            tickers: 결과에 붙일 종목코드(예: ``["005930"]``). 비우면 제목·요약의
                ``회사명[005930]`` 표기에서만 뽑는다 -- 검색어 결과가 그 종목 기사라는
                보장이 없어서 자동으로 붙이지 않는다.
        """
        if not 1 <= limit <= MAX_START + MAX_DISPLAY - 1:
            raise ValueError(f"limit must be 1..{MAX_START + MAX_DISPLAY - 1} (got {limit})")
        since_at = _since_to_datetime(since)
        by_id: dict[str, NewsArticle] = {}
        start = 1
        while len(by_id) < limit and start <= MAX_START:
            display = min(MAX_DISPLAY, limit - len(by_id))
            payload = await self.search_news_page(query, display=display, start=start, sort=sort)
            items = payload["items"]
            parsed = [
                a for item in items if (a := self._parse_item(item, category, tickers)) is not None
            ]
            for article in parsed:
                if since_at is None or article.published_at >= since_at:
                    by_id.setdefault(article.id, article)
            if len(items) < display:
                break
            if (
                since_at is not None
                and sort == "date"
                and parsed
                and max(a.published_at for a in parsed) < since_at
            ):
                break
            start += display
        articles = list(by_id.values())[:limit]
        if sort == "date":
            articles.sort(key=lambda a: a.published_at, reverse=True)
        return articles

    async def scrape_news(
        self, queries: Sequence[str] = DEFAULT_MARKET_QUERIES, *, limit: int = 100
    ) -> list[NewsArticle]:
        """시장 전체 검색어(기본 ``"증시"``)의 최신 기사, 최신순·id 중복 제거."""
        by_id: dict[str, NewsArticle] = {}
        for query in queries:
            for article in await self.search_news(
                query, limit=limit, category=NewsCategory.MARKET
            ):
                by_id.setdefault(article.id, article)
        return sorted(by_id.values(), key=lambda a: a.published_at, reverse=True)

    def _parse_item(
        self, item: dict[str, Any], category: NewsCategory, tickers: Sequence[str] | None
    ) -> NewsArticle | None:
        title = clean_text(item.get("title"))
        url = str(item.get("link") or item.get("originallink") or "").strip()
        published_at = parse_pub_date(item.get("pubDate"))
        if not title or not url or published_at is None:
            return None
        summary = clean_text(item.get("description"))
        found = extract_tickers(title, summary)
        return self._make_article(
            title=title,
            url=url,
            category=category,
            summary=summary,
            tickers=list(dict.fromkeys([*(tickers or []), *found])),
            published_at=published_at,
            nation="KR",
            original_url=str(item.get("originallink") or "").strip(),
        )

    @staticmethod
    def _api_error(response: httpx.Response) -> NaverAPIError:
        try:
            body = response.json()
        except ValueError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        return NaverAPIError(
            response.status_code,
            str(body.get("errorCode") or ""),
            str(body.get("errorMessage") or response.reason_phrase),
        )


def _since_to_datetime(since: date | datetime | None) -> datetime | None:
    if since is None:
        return None
    if not isinstance(since, datetime):
        return datetime(since.year, since.month, since.day, tzinfo=KST)
    return since if since.tzinfo is not None else since.replace(tzinfo=KST)
