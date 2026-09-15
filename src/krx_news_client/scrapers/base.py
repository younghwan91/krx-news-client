from __future__ import annotations

import asyncio
import hashlib
import logging
import random
import time
from abc import ABC, abstractmethod
from datetime import datetime

import httpx

from krx_news_client.models.schemas import (
    KST,
    Disclosure,
    NewsArticle,
    NewsCategory,
    NewsSource,
)

logger = logging.getLogger(__name__)

USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"
    ),
]


def make_article_id(source: str, url: str) -> str:
    url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
    return f"{source}:{url_hash}"


def _is_retryable_status(status_code: int) -> bool:
    """429·5xx 만 재시도한다. 400/404 같은 4xx 는 다시 보내도 같은 답이다."""
    return status_code == 429 or status_code >= 500


class BaseScraper(ABC):
    source: NewsSource
    base_url: str
    min_delay: float = 0.5
    max_delay: float = 2.0
    timeout: float = 15.0
    max_retries: int = 3
    #: 소스별 기본 헤더(User-Agent 외). 하위 클래스가 덮어쓴다.
    default_headers: dict[str, str] = {}

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._client_loop: asyncio.AbstractEventLoop | None = None
        self._last_request_time: float = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.close()

    async def get_client(self) -> httpx.AsyncClient:
        """현재 이벤트 루프에 묶인 httpx 클라이언트를 돌려준다.

        httpx.AsyncClient 의 커넥션 풀은 만들어진 루프에 묶인다. 같은 스크레이퍼로
        ``asyncio.run`` 을 두 번 부르면 첫 루프는 이미 닫혀 있어서, 예전처럼
        ``is_closed`` 만 보고 재사용하면 ``RuntimeError: Event loop is closed`` 가
        난다 -- 그리고 ``scrape_news`` 가 피드별 예외를 삼키므로 **조용히 결측**이
        된다(2026-09-14 scalp-it 이 코스닥 공시를 이렇게 놓쳤다). 루프가 바뀌었으면
        옛 클라이언트는 버리고(죽은 루프에서 aclose 할 수 없다) 새로 만든다.
        """
        loop = asyncio.get_running_loop()
        if self._client is not None and self._client_loop is not loop:
            self._client = None
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": random.choice(USER_AGENTS), **self.default_headers},
            )
            self._client_loop = loop
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            if self._client_loop is asyncio.get_running_loop():
                await self._client.aclose()
        self._client = None
        self._client_loop = None

    async def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_time
        delay = random.uniform(self.min_delay, self.max_delay)
        if elapsed < delay:
            await asyncio.sleep(delay - elapsed)
        self._last_request_time = time.monotonic()

    async def fetch(self, url: str, **kwargs) -> httpx.Response:
        return await self._request("GET", url, **kwargs)

    async def fetch_post(self, url: str, **kwargs) -> httpx.Response:
        return await self._request("POST", url, **kwargs)

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        client = await self.get_client()
        await self._throttle()

        for attempt in range(1, self.max_retries + 1):
            try:
                resp = await client.request(method, url, **kwargs)
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if not _is_retryable_status(status) or attempt == self.max_retries:
                    raise
                wait = min(60, 2**attempt * 5) if status == 429 else 2**attempt
                logger.warning(
                    "%s: HTTP %d on %s, retry %d/%d in %ds",
                    self.source.value, status, method, attempt, self.max_retries, wait,
                )
                await asyncio.sleep(wait)
            except httpx.RequestError as e:
                if attempt == self.max_retries:
                    raise
                logger.warning(
                    "%s: Request error: %s, retry %d/%d",
                    self.source.value, e, attempt, self.max_retries,
                )
                await asyncio.sleep(2**attempt)

        raise RuntimeError(f"Failed after {self.max_retries} retries")

    @abstractmethod
    async def scrape_news(self) -> list[NewsArticle]:
        ...

    async def scrape_disclosures(self) -> list[Disclosure]:
        return []

    def _make_article(
        self,
        title: str,
        url: str,
        category: NewsCategory,
        content: str = "",
        summary: str = "",
        tickers: list[str] | None = None,
        author: str = "",
        published_at: datetime | None = None,
        **extra,
    ) -> NewsArticle:
        return NewsArticle(
            id=make_article_id(self.source.value, url),
            source=self.source,
            category=category,
            title=title,
            url=url,
            content=content,
            summary=summary,
            tickers=tickers or [],
            author=author,
            published_at=published_at or datetime.now(tz=KST),
            **extra,
        )

    def _make_disclosure(
        self,
        title: str,
        url: str,
        company: str,
        ticker: str,
        disclosure_type: str = "",
        published_at: datetime | None = None,
        **extra,
    ) -> Disclosure:
        return Disclosure(
            id=make_article_id(self.source.value, url),
            source=self.source,
            title=title,
            url=url,
            company=company,
            ticker=ticker,
            disclosure_type=disclosure_type,
            published_at=published_at or datetime.now(tz=KST),
            **extra,
        )
