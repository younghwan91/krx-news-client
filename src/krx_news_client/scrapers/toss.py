from __future__ import annotations

import json
import logging
import re
import urllib.parse
from datetime import date, datetime
from typing import Any

import httpx

from krx_news_client.models.schemas import KST, NewsArticle, NewsCategory, NewsSource
from krx_news_client.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# 토스가 주는 ``createdAt``은 오프셋 없는 KST 벽시계다("2026-09-05T18:10:12").
# 그대로 naive 로 두면 소비자가 ``timestamptz`` 컬럼(세션 TZ=UTC)에 넣는 순간
# 9시간 미래로 밀린다 — 2026-09-13 실제로 그렇게 밀려 있는 걸 발견해 고쳤다
# (quant-airflow news_articles 의 시각 분포가 장중엔 비고 저녁 17~18시에 몰려
# 보였다. 9시간 되돌리면 장전 08시·개장 09시·마감 15시 피크로 정확히 맞는다).

API_BASE = "https://wts-info-api.tossinvest.com"
DASHBOARD_NEWS_URL = f"{API_BASE}/api/v1/dashboard/wts/news"
#: 기사 모달용 상세. 대시보드 피드(요약만)와 달리 본문 블록·원문 URL·감성 라벨·
#: 관련 종목 전체를 언론사와 무관하게 같은 모양으로 준다. 없는 기사는 200
#: ``{"result": null}``, 형식이 틀린 ID 는 400. (daytrade-it 에서 2026-09-13 발견)
NEWS_DETAIL_URL = f"{API_BASE}/api/v2/news/{{news_id}}"
#: 종목별 뉴스 히스토리. 대시보드는 스냅샷이라 백필이 안 되는데 이건 과거로 계속
#: 넘길 수 있다. 코드는 **6자리만** 받는다 -- ``A005930``·ISIN 은 오류 없이 빈
#: 목록이 온다. (daytrade-it 에서 2026-09-15 확인)
#:
#: 페이징 함정(2026-09-15 실측, 005930 size=100 8페이지):
#: - ``lastPage`` 는 믿으면 안 된다. 페이지가 ``size`` 보다 1~3건 모자라면(서버가
#:   일부를 걸러내는 듯) 뒤에 페이지가 더 있어도 True 가 온다 -- 1페이지부터 True.
#:   끝은 빈 ``body`` 로만 판단한다.
#: - "최신순"은 대략적일 뿐이다. 페이지 안도 정렬돼 있지 않고, 이웃 페이지의 시각
#:   범위가 하루쯤 겹친다. 그래서 ``since`` 는 **페이지 전체**가 그보다 오래됐을
#:   때만 멈추는 조건으로 쓴다.
COMPANY_NEWS_URL = f"{API_BASE}/api/v2/news/companies/{{code}}"

# dashboard feed type -> NewsCategory
FEED_TYPES: dict[str, NewsCategory] = {
    "ALL_HIGHLIGHT": NewsCategory.MARKET,
    "HOT": NewsCategory.BREAKING,
    "SOARING_STOCK": NewsCategory.STOCK,
}

_BODY_BLOCK_TYPES = ("summary", "sub_headline", "text")
_STOCK_CODE_RE = re.compile(r"^[0-9A-Z]{6}$")


class TossResponseError(ValueError):
    """토스 응답이 예상한 모양(``result.body`` 리스트 등)이 아니다.

    비공식 API 라 형식이 예고 없이 바뀔 수 있다. 백필 경로에서 이걸 빈 결과로
    뭉개면 조용한 결측이 되므로 예외로 올린다.
    """
_TAG_RE = re.compile(r"<[^>]+>")


def build_article_url(news_id: str) -> str:
    content_params = json.dumps(
        {"id": news_id}, ensure_ascii=False, separators=(",", ":")
    )
    query = urllib.parse.urlencode(
        {"contentType": "news", "contentParams": content_params}
    )
    return f"https://tossinvest.com/news?{query}"


def news_id_from_url(url: str) -> str | None:
    """``build_article_url`` 의 역. 토스 기사 URL 에서 newsId 를 꺼낸다."""
    try:
        params = urllib.parse.parse_qs(urllib.parse.urlparse(str(url)).query)
        return str(json.loads(params["contentParams"][0])["id"])
    except (KeyError, IndexError, ValueError, TypeError):
        return None


def normalize_stock_code(code: str) -> str:
    """토스 한국 종목코드(``A005930``·``A0193K0``)를 6자리로.

    7자리이고 ``A`` 로 시작할 때만 벗긴다 -- 해외 코드(``AMX…``, ``NAS…``)에
    ``removeprefix("A")`` 를 무조건 걸면 코드가 망가진다.
    """
    code = str(code or "").strip()
    if len(code) == 7 and code.startswith("A"):
        return code[1:]
    return code


def extract_body_text(blocks: list[dict[str, Any]] | None) -> str:
    """상세 응답의 ``content`` 블록에서 본문(요약·소제목·문단)만 태그 없이 잇는다."""
    parts = [
        _TAG_RE.sub("", block.get("content") or "").strip()
        for block in blocks or []
        if block.get("type") in _BODY_BLOCK_TYPES
    ]
    return "\n".join(p for p in parts if p)


class TossScraper(BaseScraper):
    source = NewsSource.TOSS
    base_url = API_BASE
    min_delay = 0.5
    max_delay = 1.5
    default_headers = {"Referer": "https://tossinvest.com/"}

    async def scrape_news(self, *, strict: bool = False) -> list[NewsArticle]:
        """대시보드 3개 피드의 현재 스냅샷.

        대시보드는 증분 피드가 아니라 스냅샷이다(30초 간격이면 몇 분 동안 거의
        100% 중복) -- 폴링한다면 ``news_id`` 로 중복을 걸러야 한다. 응답에 본문이
        없으므로 ``content`` 는 비어 있다; 본문은 ``fetch_article_detail``.

        Args:
            strict: False(기본)면 피드 하나가 실패해도 로그만 남기고 나머지를
                돌려준다. True 면 첫 실패를 그대로 올린다 -- 결측을 조용히 넘기면
                안 되는 호출부용.
        """
        articles: list[NewsArticle] = []
        for feed_type, category in FEED_TYPES.items():
            try:
                articles.extend(await self._fetch_feed(feed_type, category))
            except Exception:
                if strict:
                    raise
                logger.exception("Failed to scrape Toss feed %s", feed_type)
        return articles

    async def _fetch_feed(
        self, feed_type: str, category: NewsCategory
    ) -> list[NewsArticle]:
        resp = await self.fetch_post(
            DASHBOARD_NEWS_URL, json={"type": feed_type}
        )
        payload = resp.json()
        items = payload.get("result", {}).get("news", [])
        return [
            article
            for item in items
            if (article := self._parse_item(item, category)) is not None
        ]

    def _parse_item(self, item: dict, category: NewsCategory) -> NewsArticle | None:
        news_id = item.get("newsId")
        title = item.get("title")
        if not news_id or not title:
            return None

        return self._make_article(
            title=title,
            url=build_article_url(news_id),
            category=category,
            content=item.get("contentText", ""),
            summary=item.get("summary", ""),
            tickers=self._extract_tickers(item),
            author=item.get("source", ""),
            published_at=self._parse_date(item.get("createdAt")),
            news_id=news_id,
            news_type=item.get("newsType") or "",
            nation=item.get("nation") or "",
        )

    async def fetch_article_detail(self, news_id_or_url: str) -> NewsArticle | None:
        """기사 하나의 전체 본문. 없는 기사면 None.

        Args:
            news_id_or_url: 토스 newsId(``NewsArticle.news_id``) 또는 토스 기사 URL
                (``NewsArticle.url``).

        반환 ``NewsArticle`` 은 ``content`` 에 본문 전체, ``summary`` 에 토스 요약
        문장, ``sentiment``·``original_url`` 까지 채운다. ``category`` 는 상세에
        정보가 없어 ``MARKET`` 이다.
        """
        news_id = news_id_from_url(news_id_or_url) if "://" in news_id_or_url else news_id_or_url
        if not news_id:
            return None
        try:
            resp = await self.fetch(NEWS_DETAIL_URL.format(news_id=news_id))
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (400, 404):
                return None
            raise
        detail = ((resp.json() or {}).get("result") or {}).get("kr")
        if not detail or not detail.get("title"):
            return None

        source = detail.get("source") or {}
        return self._make_article(
            title=detail["title"],
            url=build_article_url(news_id),
            category=NewsCategory.MARKET,
            content=extract_body_text(detail.get("content")),
            summary="\n".join(detail.get("summarySentences") or []),
            tickers=[normalize_stock_code(c) for c in detail.get("stockCodes") or [] if c],
            author=source.get("name", "") if isinstance(source, dict) else str(source),
            published_at=self._parse_date(detail.get("createdAt")),
            news_id=news_id,
            news_type=detail.get("newsType") or "",
            sentiment=detail.get("sentiment") or "",
            original_url=detail.get("linkUrl") or "",
        )

    async def company_news_page(
        self, code: str, number: int = 1, size: int = 100
    ) -> tuple[list[dict[str, Any]], bool]:
        """종목별 뉴스 한 페이지, 원본 dict 그대로 → ``(items, last_page)``.

        ``NewsArticle`` 에 없는 필드(``source.code``·``ticsTitles``·``stockInfo`` 등)가
        필요한 호출부용 raw 경로. HTTP 오류·형식 이상은 예외로 올린다(엄격).
        ``last_page`` 는 토스가 준 값을 그대로 전하지만 **믿으면 안 된다**
        (``COMPANY_NEWS_URL`` 주석).

        Raises:
            ValueError: 코드가 6자리 형식이 아니거나 ``number < 1``(토스는 400).
            TossResponseError: 응답에 ``result.body`` 리스트가 없다.
        """
        stock_code = self._validate_code(code)
        if number < 1:
            raise ValueError(f"number starts at 1 (got {number})")
        resp = await self.fetch(
            COMPANY_NEWS_URL.format(code=stock_code),
            params={"number": number, "size": size},
        )
        payload = resp.json()
        result = payload.get("result") if isinstance(payload, dict) else None
        body = result.get("body") if isinstance(result, dict) else None
        if not isinstance(body, list):
            raise TossResponseError(f"unexpected Toss company news payload for {stock_code}")
        return body, bool(result.get("lastPage"))

    async def scrape_company_news(
        self,
        code: str,
        *,
        since: date | datetime | None = None,
        max_pages: int = 10,
        page_size: int = 100,
    ) -> list[NewsArticle]:
        """종목 하나의 뉴스를 과거로 넘겨 모은다(백필 가능). 결과는 최신순, id 중복 제거.

        Args:
            code: 종목코드. ``005930`` 또는 ``A005930`` (6자리로 정규화). ISIN 등
                다른 형식은 ``ValueError`` -- 토스는 이런 코드에 오류 없이 0건을 준다.
            since: 이 시각 이후 기사만. ``date`` 면 그날 00:00 KST, naive
                ``datetime`` 이면 KST 로 본다. 한 페이지가 통째로 이보다 오래됐으면
                더 넘기지 않는다(``COMPANY_NEWS_URL`` 주석 참고).
            max_pages: 최대 페이지 수(페이지당 ``page_size`` 건).
            page_size: 페이지 크기. 100 까지 동작 확인.

        종목 페이지에는 시장 전체 기사(예: "코스피 마감")도 섞인다 -- 이런 기사는
        ``tickers`` 가 비어 있다. 요청 간격은 ``BaseScraper`` 의 0.5~1.5초 무작위
        지연을 그대로 쓴다(``min_delay``/``max_delay`` 로 조절).
        """
        self._validate_code(code)
        since_at = self._since_to_datetime(since)

        by_id: dict[str, NewsArticle] = {}
        for page in range(1, max_pages + 1):
            body, _last_page = await self.company_news_page(code, page, page_size)
            if not body:
                break
            parsed = [
                article
                for item in body
                if (article := self._parse_company_item(item)) is not None
            ]
            for article in parsed:
                if since_at is None or article.published_at >= since_at:
                    # 페이지 경계에서 새 기사가 끼어들면 같은 기사가 두 번 온다.
                    by_id.setdefault(article.news_id, article)
            if since_at is not None and parsed and max(a.published_at for a in parsed) < since_at:
                break
        return sorted(by_id.values(), key=lambda a: a.published_at, reverse=True)

    @staticmethod
    def _validate_code(code: str) -> str:
        stock_code = normalize_stock_code(code)
        if not _STOCK_CODE_RE.match(stock_code):
            raise ValueError(
                f"Toss company news needs a 6-char KRX code like 005930 (got {code!r})"
            )
        return stock_code

    @staticmethod
    def _since_to_datetime(since: date | datetime | None) -> datetime | None:
        if since is None:
            return None
        if not isinstance(since, datetime):
            return datetime(since.year, since.month, since.day, tzinfo=KST)
        return since if since.tzinfo is not None else since.replace(tzinfo=KST)

    def _parse_company_item(self, item: dict) -> NewsArticle | None:
        news_id = item.get("id")
        title = item.get("title")
        published_at = self._parse_date(item.get("createdAt"))
        if not news_id or not title or published_at is None:
            return None
        source = item.get("source") or {}
        return self._make_article(
            title=title,
            url=build_article_url(news_id),
            category=NewsCategory.STOCK,
            content=item.get("contentText") or "",
            summary=item.get("summary") or "",
            # 시장 전체 기사는 stockCodes 가 null -- 조회한 종목을 억지로 붙이지 않는다.
            tickers=[normalize_stock_code(c) for c in item.get("stockCodes") or [] if c],
            author=source.get("name", "") if isinstance(source, dict) else str(source),
            published_at=published_at,
            news_id=news_id,
            news_type=item.get("newsType") or "",
            nation="KR",
        )

    @staticmethod
    def _extract_tickers(item: dict) -> list[str]:
        tickers = []
        for stock in item.get("relatedStocks") or []:
            code = stock.get("stockCode", "")
            if code:
                tickers.append(normalize_stock_code(code))
        return tickers

    @staticmethod
    def _parse_date(text: str | None) -> datetime | None:
        """토스 ``createdAt``을 **tz 있는** datetime 으로 읽는다.

        오프셋이 없으면 KST 로 간주한다(토스는 한국 서비스이고, 실측 시각 분포가
        KST 장 시간대와 맞는다 — 모듈 상단 ``KST`` 주석 참고). 오프셋이 붙어
        오면 그걸 그대로 존중한다.
        """
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=KST)
        return parsed
