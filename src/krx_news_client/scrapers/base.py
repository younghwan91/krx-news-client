from __future__ import annotations

import hashlib
import logging
import random
import time
from abc import ABC, abstractmethod
from datetime import datetime

import httpx

from krx_news_client.models.schemas import Disclosure, NewsArticle, NewsCategory, NewsSource

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


class BaseScraper(ABC):
    source: NewsSource
    base_url: str
    min_delay: float = 0.5
    max_delay: float = 2.0
    timeout: float = 15.0
    max_retries: int = 3

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._last_request_time: float = 0

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": random.choice(USER_AGENTS)},
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_time
        delay = random.uniform(self.min_delay, self.max_delay)
        if elapsed < delay:
            import asyncio
            await asyncio.sleep(delay - elapsed)
        self._last_request_time = time.monotonic()

    async def fetch(self, url: str, **kwargs) -> httpx.Response:
        client = await self.get_client()
        await self._throttle()

        for attempt in range(1, self.max_retries + 1):
            try:
                resp = await client.get(url, **kwargs)
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    wait = min(60, 2**attempt * 5)
                    logger.warning("%s: Rate limited, waiting %ds", self.source.value, wait)
                    import asyncio
                    await asyncio.sleep(wait)
                    continue
                if attempt == self.max_retries:
                    raise
                logger.warning(
                    "%s: HTTP %d, retry %d/%d",
                    self.source.value, e.response.status_code,
                    attempt, self.max_retries,
                )
            except httpx.RequestError as e:
                if attempt == self.max_retries:
                    raise
                logger.warning(
                    "%s: Request error: %s, retry %d/%d",
                    self.source.value, e, attempt, self.max_retries,
                )
                import asyncio
                await asyncio.sleep(2**attempt)

        raise RuntimeError(f"Failed after {self.max_retries} retries")

    async def fetch_post(self, url: str, **kwargs) -> httpx.Response:
        client = await self.get_client()
        await self._throttle()

        for attempt in range(1, self.max_retries + 1):
            try:
                resp = await client.post(url, **kwargs)
                resp.raise_for_status()
                return resp
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                if attempt == self.max_retries:
                    raise
                logger.warning(
                    "%s: POST error: %s, retry %d/%d",
                    self.source.value, e, attempt, self.max_retries,
                )
                import asyncio
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
            published_at=published_at or datetime.now(),
        )

    def _make_disclosure(
        self,
        title: str,
        url: str,
        company: str,
        ticker: str,
        disclosure_type: str = "",
        published_at: datetime | None = None,
    ) -> Disclosure:
        return Disclosure(
            id=make_article_id(self.source.value, url),
            source=self.source,
            title=title,
            url=url,
            company=company,
            ticker=ticker,
            disclosure_type=disclosure_type,
            published_at=published_at or datetime.now(),
        )
