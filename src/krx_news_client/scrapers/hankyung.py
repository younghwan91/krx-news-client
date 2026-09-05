"""한국경제(Hankyung) 뉴스 스크레이퍼."""

from __future__ import annotations

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup, Tag

from krx_news_client.models.schemas import NewsArticle, NewsCategory, NewsSource
from krx_news_client.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# 한국경제 사이트 개편(2024~) 이후의 섹션 경로.
#   - /koreamarket  : 국내 증시
#   - /economy      : 경제
#   - /globalmarket : 글로벌 마켓
_SECTIONS: list[tuple[str, NewsCategory]] = [
    ("/koreamarket", NewsCategory.STOCK),
    ("/economy", NewsCategory.ECONOMY),
    ("/globalmarket", NewsCategory.MARKET),
]

# 기사 URL 패턴. 기사 ID는 숫자뿐 아니라 끝에 영문자가 붙기도 한다(예: .../article/202606122455i).
_ARTICLE_URL = re.compile(r"^https?://www\.hankyung\.com/article/[0-9A-Za-z]+")


class HankyungScraper(BaseScraper):
    """한국경제 증권·경제·마켓 뉴스 스크레이퍼."""

    source = NewsSource.HANKYUNG
    base_url = "https://www.hankyung.com"
    min_delay = 0.8
    max_delay = 1.5

    async def scrape_news(self) -> list[NewsArticle]:
        articles: list[NewsArticle] = []
        for path, category in _SECTIONS:
            try:
                section_articles = await self._scrape_section(path, category)
                articles.extend(section_articles)
                logger.info(
                    "Hankyung %s: collected %d articles",
                    path,
                    len(section_articles),
                )
            except Exception:
                logger.exception("Hankyung %s: failed to scrape", path)
        return articles

    async def _scrape_section(
        self,
        path: str,
        category: NewsCategory,
    ) -> list[NewsArticle]:
        url = f"{self.base_url}{path}"
        resp = await self.fetch(url)
        soup = BeautifulSoup(resp.text, "lxml")

        articles: list[NewsArticle] = []
        seen_urls: set[str] = set()

        # 개편된 레이아웃은 제목을 `.news-tit` 안의 <a>로 노출한다.
        # 컨테이너 클래스(.news-item/.news-cont/.item)는 섹션마다 들쭉날쭉해서
        # 제목 링크를 기준으로 파싱하는 편이 안정적이다.
        for link_tag in soup.select(".news-tit a[href]"):
            article = self._parse_title_link(link_tag, category, seen_urls)
            if article:
                articles.append(article)

        # 마크업이 또 바뀌었을 때를 대비한 최후의 폴백.
        if not articles:
            articles.extend(
                self._extract_article_links(soup, category, seen_urls)
            )

        return articles

    def _parse_title_link(
        self,
        link_tag: Tag,
        category: NewsCategory,
        seen_urls: set[str],
    ) -> NewsArticle | None:
        article_url = str(link_tag.get("href", "")).split("?")[0]
        if not article_url:
            return None
        if not article_url.startswith("http"):
            article_url = f"{self.base_url}{article_url}"
        if not _ARTICLE_URL.match(article_url):
            return None
        if article_url in seen_urls:
            return None
        seen_urls.add(article_url)

        title = link_tag.get_text(strip=True)
        if not title:
            return None

        # 요약(lead)·작성일은 제목을 감싸는 텍스트 컨테이너 안에 있으면 가져온다.
        summary = ""
        published_at: datetime | None = None
        container = link_tag.find_parent(
            class_=["txt-cont", "news-cont", "news-item", "item"]
        )
        if isinstance(container, Tag):
            lead_tag = container.select_one("p.lead, .lead, .summary")
            if lead_tag:
                summary = lead_tag.get_text(strip=True)
            date_tag = container.select_one(".date, .time, time, .txt-date")
            if date_tag:
                date_text = date_tag.get("datetime") or date_tag.get_text(strip=True)
                published_at = self._parse_datetime(date_text)

        return self._make_article(
            title=title,
            url=article_url,
            category=category,
            summary=summary,
            published_at=published_at,
        )

    def _extract_article_links(
        self,
        soup: BeautifulSoup,
        category: NewsCategory,
        seen_urls: set[str],
    ) -> list[NewsArticle]:
        """Last-resort extraction of article links from the page."""
        articles: list[NewsArticle] = []
        for a_tag in soup.select("a[href]"):
            href = str(a_tag.get("href", "")).split("?")[0]
            if not href.startswith("http"):
                href = f"{self.base_url}{href}"
            if not _ARTICLE_URL.match(href):
                continue
            if href in seen_urls:
                continue
            seen_urls.add(href)

            title = a_tag.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            articles.append(
                self._make_article(
                    title=title,
                    url=href,
                    category=category,
                )
            )
        return articles

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        value = value.strip()
        for fmt in (
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y.%m.%d %H:%M:%S",
            "%Y.%m.%d %H:%M",
            "%Y.%m.%d",
            "%Y-%m-%d",
        ):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        return None
