"""TheBell (더벨) scraper.

Collects financial analysis articles from https://www.thebell.co.kr.
Focuses on free/public articles available without login.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from krx_news_client.models.schemas import NewsArticle, NewsCategory, NewsSource
from krx_news_client.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Section codes mapped to NewsCategory
_SECTION_CATEGORY: dict[str, NewsCategory] = {
    "00": NewsCategory.ANALYSIS,   # 전체
    "01": NewsCategory.ECONOMY,    # 금융
    "02": NewsCategory.MARKET,     # 산업
    "04": NewsCategory.ANALYSIS,   # 부동산
}

_FREE_LIST_URL = (
    "https://www.thebell.co.kr/free/content/ArticleList.asp"
)

# 6-digit KRX ticker pattern
_TICKER_RE = re.compile(r"\b(\d{6})\b")


class TheBellScraper(BaseScraper):
    """Scrapes free article listings from TheBell (thebell.co.kr)."""

    source = NewsSource.THEBELL
    base_url = "https://www.thebell.co.kr"
    min_delay = 0.5
    max_delay = 2.0

    def __init__(self, *, pages: int = 2, sections: tuple[str, ...] = ("00",)) -> None:
        super().__init__()
        self._pages = pages
        self._sections = sections

    async def scrape_news(self) -> list[NewsArticle]:
        """Scrape free articles from TheBell across configured sections."""
        seen_urls: set[str] = set()
        articles: list[NewsArticle] = []

        for svccode in self._sections:
            category = _SECTION_CATEGORY.get(svccode, NewsCategory.ANALYSIS)
            for page in range(1, self._pages + 1):
                page_articles = await self._scrape_list_page(page, svccode, category)
                for article in page_articles:
                    if article.url not in seen_urls:
                        seen_urls.add(article.url)
                        articles.append(article)

        logger.info("TheBell: collected %d articles", len(articles))
        return articles

    async def _scrape_list_page(
        self, page: int, svccode: str, category: NewsCategory
    ) -> list[NewsArticle]:
        """Fetch and parse a single listing page."""
        params = {"page": str(page), "svccode": svccode}

        try:
            resp = await self.fetch(_FREE_LIST_URL, params=params)
        except Exception:
            logger.warning(
                "TheBell: failed to fetch page %d (svccode=%s)", page, svccode, exc_info=True
            )
            return []

        return self._parse_list_page(resp.text, category)

    def _parse_list_page(self, html: str, category: NewsCategory) -> list[NewsArticle]:
        """Parse an article listing page into NewsArticle objects."""
        soup = BeautifulSoup(html, "lxml")
        articles: list[NewsArticle] = []

        # TheBell uses various list structures; try common patterns
        items = (
            soup.select("div.articleList li")
            or soup.select("ul.newsList li")
            or soup.select("div.listContent dl")
            or soup.select("div.content_list_wrap li")
            or soup.select("div#contents li")
        )

        if items:
            for item in items:
                article = self._parse_list_item(item, category)
                if article is not None:
                    articles.append(article)
            return articles

        # Fallback: scan for any <a> tags pointing to article detail pages
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            if "ArticleView" not in href and "article.asp" not in href.lower():
                continue

            title = link.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            url = self._resolve_url(href)
            published_at = self._find_nearby_date(link)
            summary = self._find_nearby_summary(link)

            articles.append(
                self._make_article(
                    title=title,
                    url=url,
                    category=category,
                    summary=summary,
                    published_at=published_at,
                )
            )

        return articles

    def _parse_list_item(self, item: Tag, category: NewsCategory) -> NewsArticle | None:
        """Extract article data from a single list item element."""
        link = item.find("a", href=True)
        if link is None:
            return None

        title = link.get_text(strip=True)
        if not title or len(title) < 5:
            return None

        href = link.get("href", "")
        url = self._resolve_url(href)

        # Summary: look for a secondary text block (p, span.summary, dd, etc.)
        summary = ""
        for sel in ("p", "span.summary", "dd", "div.summary", "span.lead"):
            tag = item.select_one(sel)
            if tag and tag.get_text(strip=True) != title:
                summary = tag.get_text(strip=True)
                break

        published_at = self._extract_date_from_element(item)
        author = self._extract_author(item)

        return self._make_article(
            title=title,
            url=url,
            category=category,
            summary=summary,
            author=author,
            published_at=published_at,
        )

    # ------------------------------------------------------------------
    # Date parsing helpers
    # ------------------------------------------------------------------

    _DATE_PATTERNS: list[tuple[str, str]] = [
        # "2024.06.15 14:30"
        (r"\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}", "%Y.%m.%d %H:%M"),
        # "2024.06.15"
        (r"\d{4}\.\d{2}\.\d{2}", "%Y.%m.%d"),
        # "2024-06-15 14:30"
        (r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}", "%Y-%m-%d %H:%M"),
        # "2024-06-15"
        (r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d"),
    ]

    @classmethod
    def _try_parse_date(cls, text: str) -> datetime | None:
        """Attempt to extract a datetime from a text string."""
        for pattern, fmt in cls._DATE_PATTERNS:
            match = re.search(pattern, text)
            if match:
                try:
                    return datetime.strptime(match.group(), fmt)
                except ValueError:
                    continue
        return None

    def _extract_date_from_element(self, element: Tag) -> datetime:
        """Search an element and its children for a recognisable date string."""
        for sel in ("span.date", "span.time", "em.date", "span.writeDate", "time"):
            tag = element.select_one(sel)
            if tag:
                dt = self._try_parse_date(tag.get_text(strip=True))
                if dt:
                    return dt

        text = element.get_text(" ", strip=True)
        dt = self._try_parse_date(text)
        return dt or datetime.now()

    def _find_nearby_date(self, link: Tag) -> datetime:
        """Find a date near a link tag by checking siblings and parent."""
        parent = link.parent
        if parent:
            dt = self._try_parse_date(parent.get_text(" ", strip=True))
            if dt:
                return dt

            # Check next siblings
            for sibling in link.next_siblings:
                if isinstance(sibling, Tag):
                    dt = self._try_parse_date(sibling.get_text(strip=True))
                    if dt:
                        return dt

        return datetime.now()

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_author(element: Tag) -> str:
        """Try to pull an author name from common selectors."""
        for sel in ("span.writer", "span.author", "em.writer"):
            tag = element.select_one(sel)
            if tag:
                return tag.get_text(strip=True)
        return ""

    @staticmethod
    def _find_nearby_summary(link: Tag) -> str:
        """Try to extract summary text near a link."""
        parent = link.parent
        if parent is None:
            return ""
        for sibling in link.next_siblings:
            if isinstance(sibling, Tag):
                text = sibling.get_text(strip=True)
                if text and len(text) > 10:
                    return text
        return ""

    def _resolve_url(self, href: str) -> str:
        """Turn a relative or partial URL into an absolute one."""
        if href.startswith("http"):
            return href
        return urljoin(self.base_url + "/", href.lstrip("/"))
