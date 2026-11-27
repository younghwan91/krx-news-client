"""연합뉴스 RSS 피드 -- 키 없이 받는 한국 증시 뉴스.

연합뉴스가 공개로 내놓은 RSS(``https://www.yna.co.kr/rss/index``)만 읽는다. 기사
페이지는 긁지 않는다. 2026-11-26 확인:

- ``robots.txt`` 는 ``User-agent: * / Allow: /`` 이고 ``/rss/`` 는 막혀 있지 않다
  (막힌 것은 ``/search/``·일부 ``/view/`` 등).
- RSS 안내 페이지: "비상업적 블로그와 개인적인 용도로만 RSS 피드를 사용하는 것을
  허용", "사전 서면 허가 없이 RSS 서비스를 상업적으로 이용하는 것을 금지".
  피드의 ``<copyright>`` 는 "무단 전재-재배포, AI 학습 및 활용 금지".

그래서 이 스크레이퍼는 개인·비상업 용도의 제목·요약·링크 수집용이다. 상업적으로
쓰거나 AI 에 넣으려면 연합뉴스와 따로 협의해야 한다(README "뉴스 소스와 이용 조건").

피드는 섹션별 최신 기사 스냅샷이다(약 120건, 시간당 갱신). 과거로 넘기는 페이징은
없다 -- 폴링하며 ``Deduplicator`` 로 새 기사만 거르는 용도다.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from datetime import datetime
from email.utils import parsedate_to_datetime

from lxml import etree

from krx_news_client.models.schemas import KST, NewsArticle, NewsCategory, NewsSource
from krx_news_client.scrapers.base import LIBRARY_USER_AGENT, BaseScraper

logger = logging.getLogger(__name__)

RSS_URL = "https://www.yna.co.kr/rss/{feed}.xml"

#: 증시에 쓸 만한 섹션 피드 → 카테고리. 전체 목록은 https://www.yna.co.kr/rss/index
FEEDS: dict[str, NewsCategory] = {
    "market": NewsCategory.MARKET,  # 마켓+ (증권부 기사, 공시 속보 포함)
    "economy": NewsCategory.ECONOMY,
    "industry": NewsCategory.ECONOMY,
    "news": NewsCategory.BREAKING,  # 전 섹션 최신기사
}
DEFAULT_FEEDS: tuple[str, ...] = ("market",)

_DC = "{http://purl.org/dc/elements/1.1/}"
#: 연합뉴스는 상장사 이름 뒤에 종목코드를 대괄호로 붙인다: ``KS인더스트리[101000]``.
#: 신규 코드는 영숫자 6자리(``0193K0``)라 첫 자리 숫자 + 영숫자 5자리로 받는다.
_TICKER_RE = re.compile(r"\[([0-9][0-9A-Z]{5})\]")
_NEWS_ID_RE = re.compile(r"/view/([A-Z0-9]+)")
_XML_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)


class YonhapFeedError(ValueError):
    """연합뉴스 RSS 응답이 RSS 2.0 모양(``rss/channel``)이 아니다."""


def extract_tickers(*texts: str) -> list[str]:
    """제목·요약에서 ``회사명[005930]`` 형식의 종목코드를 순서대로, 중복 없이 뽑는다."""
    seen: dict[str, None] = {}
    for text in texts:
        for code in _TICKER_RE.findall(text or ""):
            seen.setdefault(code, None)
    return list(seen)


def parse_rss_date(text: str | None) -> datetime | None:
    """RFC 822 ``pubDate``(``Thu, 26 Nov 2026 19:49:41 +0900``)를 KST tz datetime 으로."""
    if not text:
        return None
    try:
        parsed = parsedate_to_datetime(text.strip())
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=KST)
    return parsed.astimezone(KST)


class YonhapScraper(BaseScraper):
    """연합뉴스 섹션 RSS → ``NewsArticle``. 키가 필요 없다.

    ``content`` 는 비어 있고(RSS 에 본문이 없다), ``summary`` 는 피드가 준 앞부분
    요약, ``tickers`` 는 제목·요약의 ``[종목코드]`` 표기에서 뽑는다.
    """

    source = NewsSource.YONHAP
    base_url = "https://www.yna.co.kr"
    min_delay = 0.5
    max_delay = 1.0
    #: 브라우저인 척하지 않는다 -- 공개 RSS 라 그럴 이유가 없다.
    default_headers = {"User-Agent": LIBRARY_USER_AGENT}

    async def scrape_news(
        self, feeds: Iterable[str] = DEFAULT_FEEDS, *, strict: bool = False
    ) -> list[NewsArticle]:
        """섹션 피드들의 현재 스냅샷, 최신순. 같은 기사가 여러 피드에 있으면 한 번만.

        Args:
            feeds: ``FEEDS`` 의 키(기본 ``("market",)``). 모르는 이름은 ``ValueError``.
            strict: False(기본)면 피드 하나가 실패해도 로그만 남기고 나머지를
                돌려준다. True 면 첫 실패를 그대로 올린다.
        """
        names = list(feeds)
        unknown = [name for name in names if name not in FEEDS]
        if unknown:
            raise ValueError(f"unknown Yonhap feed(s) {unknown}; choose from {sorted(FEEDS)}")
        by_id: dict[str, NewsArticle] = {}
        for name in names:
            try:
                articles = await self.fetch_feed(name)
            except Exception:
                if strict:
                    raise
                logger.exception("Failed to scrape Yonhap feed %s", name)
                continue
            for article in articles:
                by_id.setdefault(article.id, article)
        return sorted(by_id.values(), key=lambda a: a.published_at, reverse=True)

    async def fetch_feed(self, feed: str) -> list[NewsArticle]:
        """피드 하나. HTTP 오류와 형식 이상(``YonhapFeedError``)은 그대로 올린다."""
        if feed not in FEEDS:
            raise ValueError(f"unknown Yonhap feed {feed!r}; choose from {sorted(FEEDS)}")
        resp = await self.fetch(RSS_URL.format(feed=feed))
        return self.parse_feed(resp.content, FEEDS[feed])

    def parse_feed(self, xml: bytes, category: NewsCategory) -> list[NewsArticle]:
        try:
            root = etree.fromstring(xml, parser=_XML_PARSER)
        except etree.XMLSyntaxError as e:
            raise YonhapFeedError(f"Yonhap RSS is not valid XML: {e}") from e
        channel = root.find("channel") if root.tag == "rss" else None
        if channel is None:
            raise YonhapFeedError(f"unexpected Yonhap RSS root <{root.tag}>")
        return [
            article
            for item in channel.iterfind("item")
            if (article := self._parse_item(item, category)) is not None
        ]

    def _parse_item(self, item: etree._Element, category: NewsCategory) -> NewsArticle | None:
        title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or item.findtext("guid") or "").strip()
        published_at = parse_rss_date(item.findtext("pubDate"))
        if not title or not url or published_at is None:
            return None
        summary = (item.findtext("description") or "").strip()
        match = _NEWS_ID_RE.search(url)
        return self._make_article(
            title=title,
            url=url,
            category=category,
            summary=summary,
            tickers=extract_tickers(title, summary),
            author=(item.findtext(f"{_DC}creator") or "").strip(),
            published_at=published_at,
            news_id=match.group(1) if match else "",
            nation="KR",
            original_url=url,
        )
