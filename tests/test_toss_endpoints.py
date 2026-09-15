from __future__ import annotations

import asyncio
from datetime import date, datetime

import httpx
import pytest

from krx_news_client import KST, NewsCategory, TossResponseError, TossScraper
from krx_news_client.scrapers.toss import (
    build_article_url,
    extract_body_text,
    news_id_from_url,
    normalize_stock_code,
)


class TestEventLoopReuse:
    """같은 스크레이퍼로 ``asyncio.run`` 을 두 번 부르면 새 루프용 클라이언트가 필요하다.

    예전엔 첫 루프에 묶인 클라이언트를 재사용해 두 번째 호출이 ``Event loop is
    closed`` 로 실패했고, ``scrape_news`` 가 그 예외를 피드별로 삼켜 결측이 조용히
    생겼다(실측 85건 → 35건).
    """

    def test_new_loop_gets_new_client(self):
        scraper = TossScraper()
        first = asyncio.run(scraper.get_client())
        second = asyncio.run(scraper.get_client())
        assert first is not second

    def test_same_loop_reuses_client(self):
        async def run():
            scraper = TossScraper()
            try:
                return await scraper.get_client() is await scraper.get_client()
            finally:
                await scraper.close()

        assert asyncio.run(run())

    def test_async_context_manager_closes(self):
        async def run():
            async with TossScraper() as scraper:
                client = await scraper.get_client()
            return client.is_closed

        assert asyncio.run(run())


class TestHelpers:
    def test_news_id_round_trip(self):
        url = build_article_url("yna_AKR20260913056700017")
        assert news_id_from_url(url) == "yna_AKR20260913056700017"

    def test_news_id_from_garbage(self):
        assert news_id_from_url("https://tossinvest.com/news") is None

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("A005930", "005930"),
            ("A0193K0", "0193K0"),
            ("005930", "005930"),
            # 해외 코드를 망가뜨리면 안 된다.
            ("AMX0000123", "AMX0000123"),
            ("NAS0241001", "NAS0241001"),
        ],
    )
    def test_normalize_stock_code(self, raw, expected):
        assert normalize_stock_code(raw) == expected

    def test_extract_body_text_keeps_body_blocks_only(self):
        blocks = [
            {"type": "text", "content": "[마감시황]"},
            {"type": "image", "content": "https://img/1.jpg"},
            {"type": "sub_headline", "content": "<b>소제목</b>"},
            {"type": "text", "content": "본문 <a href='x'>링크</a> 문단"},
        ]
        assert extract_body_text(blocks) == "[마감시황]\n소제목\n본문 링크 문단"


class TestDashboard:
    def test_parse_item_keeps_nation_and_news_id(self):
        item = {
            "newsId": "hankyung_1",
            "title": "엔비디아 급등",
            "createdAt": "2026-09-15T19:31:31",
            "source": "한국경제",
            "nation": "US",
            "relatedStocks": [{"stockCode": "NAS0241001", "market": "us"}],
        }
        article = TossScraper()._parse_item(item, NewsCategory.MARKET)
        assert article.nation == "US"
        assert article.news_id == "hankyung_1"
        assert article.tickers == ["NAS0241001"]

    async def test_strict_raises_on_feed_failure(self, httpx_mock):
        httpx_mock.add_response(status_code=403)
        async with TossScraper() as scraper:
            scraper.min_delay = scraper.max_delay = 0
            with pytest.raises(httpx.HTTPStatusError):
                await scraper.scrape_news(strict=True)

    async def test_lenient_swallows_feed_failure(self, httpx_mock):
        httpx_mock.add_response(status_code=403, is_reusable=True)
        async with TossScraper() as scraper:
            scraper.min_delay = scraper.max_delay = 0
            assert await scraper.scrape_news() == []

    async def test_non_retryable_4xx_is_not_retried(self, httpx_mock):
        httpx_mock.add_response(status_code=403)
        async with TossScraper() as scraper:
            scraper.min_delay = scraper.max_delay = 0
            with pytest.raises(httpx.HTTPStatusError):
                await scraper.scrape_news(strict=True)
        assert len(httpx_mock.get_requests()) == 1

    async def test_sends_referer(self, httpx_mock):
        httpx_mock.add_response(json={"result": {"news": []}}, is_reusable=True)
        async with TossScraper() as scraper:
            scraper.min_delay = scraper.max_delay = 0
            await scraper.scrape_news(strict=True)
        assert httpx_mock.get_requests()[0].headers["Referer"] == "https://tossinvest.com/"


DETAIL_PAYLOAD = {
    "result": {
        "availableLanguages": ["kr", "en"],
        "kr": {
            "id": "moneytoday_2026091515295351946",
            "title": "코스피 6627.26 마감",
            "summarySentences": ["첫 요약.", "둘째 요약."],
            "sentiment": "NEUTRAL",
            "content": [
                {"type": "text", "content": "[마감시황]"},
                {"type": "image", "content": "https://img/1.jpg"},
                {"type": "text", "content": "코스피 지수가 소폭 하락했다."},
            ],
            "source": {"code": "moneytoday", "name": "머니투데이"},
            "stockCodes": ["A005930", "A0193K0"],
            "linkUrl": "https://news.mt.co.kr/mtview.php?no=2026091515295351946&TOSS",
            "createdAt": "2026-09-15T16:02:19",
        },
    }
}


class TestArticleDetail:
    async def test_parses_detail(self, httpx_mock):
        httpx_mock.add_response(json=DETAIL_PAYLOAD)
        async with TossScraper() as scraper:
            scraper.min_delay = scraper.max_delay = 0
            article = await scraper.fetch_article_detail("moneytoday_2026091515295351946")
        request = httpx_mock.get_requests()[0]
        assert request.url.path == "/api/v2/news/moneytoday_2026091515295351946"
        assert article.content == "[마감시황]\n코스피 지수가 소폭 하락했다."
        assert article.summary == "첫 요약.\n둘째 요약."
        assert article.sentiment == "NEUTRAL"
        assert article.author == "머니투데이"
        assert article.tickers == ["005930", "0193K0"]
        assert article.original_url.startswith("https://news.mt.co.kr/")
        assert article.published_at.isoformat() == "2026-09-15T16:02:19+09:00"

    async def test_accepts_article_url(self, httpx_mock):
        httpx_mock.add_response(json=DETAIL_PAYLOAD)
        url = build_article_url("moneytoday_2026091515295351946")
        async with TossScraper() as scraper:
            scraper.min_delay = scraper.max_delay = 0
            article = await scraper.fetch_article_detail(url)
        assert article is not None
        assert article.url == url

    async def test_missing_article_returns_none(self, httpx_mock):
        httpx_mock.add_response(json={"result": None})
        async with TossScraper() as scraper:
            scraper.min_delay = scraper.max_delay = 0
            assert await scraper.fetch_article_detail("moneytoday_0000") is None

    async def test_malformed_id_returns_none(self, httpx_mock):
        httpx_mock.add_response(status_code=400)
        async with TossScraper() as scraper:
            scraper.min_delay = scraper.max_delay = 0
            assert await scraper.fetch_article_detail("nope") is None


def _company_page(items, last_page):
    return {"result": {"pagingParam": {}, "body": items, "lastPage": last_page}}


def _company_item(news_id, created_at):
    return {
        "id": news_id,
        "title": f"기사 {news_id}",
        "summary": "요약",
        "contentText": "본문 앞부분",
        "source": {"code": "yna", "name": "연합뉴스"},
        "stockCodes": None,
        "createdAt": created_at,
    }


class TestCompanyNews:
    async def test_ignores_last_page_flag_and_stops_on_empty_body(self, httpx_mock):
        # 실측: 1페이지부터 lastPage=True 인데 뒤에 페이지가 더 있다.
        httpx_mock.add_response(
            json=_company_page([_company_item("a", "2026-09-15T10:00:00")], last_page=True)
        )
        httpx_mock.add_response(
            json=_company_page([_company_item("b", "2026-09-14T10:00:00")], last_page=False)
        )
        httpx_mock.add_response(json=_company_page([], last_page=True))
        async with TossScraper() as scraper:
            scraper.min_delay = scraper.max_delay = 0
            articles = await scraper.scrape_company_news("A005930")
        requests = httpx_mock.get_requests()
        assert requests[0].url.path == "/api/v2/news/companies/005930"
        assert [dict(r.url.params)["number"] for r in requests] == ["1", "2", "3"]
        assert [a.news_id for a in articles] == ["a", "b"]
        # 시장 전체 기사(stockCodes null)에 조회 종목을 억지로 붙이지 않는다.
        assert articles[0].tickers == []
        assert articles[0].category == NewsCategory.STOCK
        assert articles[0].author == "연합뉴스"

    async def test_since_stops_only_when_whole_page_is_older(self, httpx_mock):
        # 페이지끼리 시각이 겹친다: 1페이지에 옛 기사가 섞여 있어도 계속 넘긴다.
        httpx_mock.add_response(
            json=_company_page(
                [
                    _company_item("new", "2026-09-15T10:00:00"),
                    _company_item("old", "2026-09-01T10:00:00"),
                ],
                last_page=False,
            )
        )
        httpx_mock.add_response(
            json=_company_page(
                [
                    _company_item("mid", "2026-09-12T10:00:00"),
                    _company_item("older", "2026-09-02T10:00:00"),
                ],
                last_page=False,
            )
        )
        httpx_mock.add_response(
            json=_company_page([_company_item("ancient", "2026-08-01T10:00:00")], last_page=False)
        )
        async with TossScraper() as scraper:
            scraper.min_delay = scraper.max_delay = 0
            articles = await scraper.scrape_company_news(
                "005930", since=datetime(2026, 9, 10, tzinfo=KST)
            )
        assert len(httpx_mock.get_requests()) == 3
        assert [a.news_id for a in articles] == ["new", "mid"]

    async def test_dedupes_and_sorts_across_pages(self, httpx_mock):
        httpx_mock.add_response(
            json=_company_page(
                [
                    _company_item("b", "2026-09-14T10:00:00"),
                    _company_item("a", "2026-09-15T10:00:00"),
                ],
                last_page=False,
            )
        )
        httpx_mock.add_response(
            json=_company_page([_company_item("a", "2026-09-15T10:00:00")], last_page=False)
        )
        httpx_mock.add_response(json=_company_page([], last_page=False))
        async with TossScraper() as scraper:
            scraper.min_delay = scraper.max_delay = 0
            articles = await scraper.scrape_company_news("005930")
        assert [a.news_id for a in articles] == ["a", "b"]

    async def test_respects_max_pages(self, httpx_mock):
        httpx_mock.add_response(
            json=_company_page([_company_item("a", "2026-09-15T10:00:00")], last_page=False),
            is_reusable=True,
        )
        async with TossScraper() as scraper:
            scraper.min_delay = scraper.max_delay = 0
            await scraper.scrape_company_news("005930", max_pages=2)
        assert len(httpx_mock.get_requests()) == 2

    async def test_since_accepts_date_as_kst_midnight(self, httpx_mock):
        httpx_mock.add_response(
            json=_company_page(
                [
                    _company_item("edge", "2026-09-10T00:00:00"),
                    _company_item("before", "2026-09-09T23:59:59"),
                ],
                last_page=False,
            )
        )
        httpx_mock.add_response(json=_company_page([], last_page=False))
        async with TossScraper() as scraper:
            scraper.min_delay = scraper.max_delay = 0
            articles = await scraper.scrape_company_news("005930", since=date(2026, 9, 10))
        assert [a.news_id for a in articles] == ["edge"]

    async def test_keeps_stock_codes_and_news_type(self, httpx_mock):
        item = {**_company_item("a", "2026-09-15T10:00:00"), "stockCodes": ["A005930"],
                "newsType": "NORMAL"}
        httpx_mock.add_response(json=_company_page([item], last_page=False))
        httpx_mock.add_response(json=_company_page([], last_page=True))
        async with TossScraper() as scraper:
            scraper.min_delay = scraper.max_delay = 0
            [article] = await scraper.scrape_company_news("005930")
        assert article.tickers == ["005930"]
        assert article.news_type == "NORMAL"

    @pytest.mark.parametrize("code", ["KR7005930003", "5930", "", "00593O0"])
    async def test_rejects_codes_toss_silently_answers_empty(self, code):
        # 토스는 A-접두·ISIN 에 200 + 빈 body 를 준다 -- 조용한 0건 대신 예외.
        async with TossScraper() as scraper:
            with pytest.raises(ValueError):
                await scraper.scrape_company_news(code)

    async def test_page_number_starts_at_one(self):
        async with TossScraper() as scraper:
            with pytest.raises(ValueError):
                await scraper.company_news_page("005930", number=0)

    async def test_raw_page_returns_items_and_flag(self, httpx_mock):
        item = {**_company_item("a", "2026-09-15T10:00:00"), "ticsTitles": ["반도체"]}
        httpx_mock.add_response(json=_company_page([item], last_page=True))
        async with TossScraper() as scraper:
            scraper.min_delay = scraper.max_delay = 0
            items, last_page = await scraper.company_news_page("A005930", number=2, size=50)
        params = dict(httpx_mock.get_requests()[0].url.params)
        assert params == {"number": "2", "size": "50"}
        assert items[0]["ticsTitles"] == ["반도체"]
        assert last_page is True

    async def test_schema_change_raises(self, httpx_mock):
        httpx_mock.add_response(json={"result": {"items": []}})
        async with TossScraper() as scraper:
            scraper.min_delay = scraper.max_delay = 0
            with pytest.raises(TossResponseError):
                await scraper.scrape_company_news("005930")

    async def test_http_error_raises(self, httpx_mock):
        httpx_mock.add_response(status_code=403)
        async with TossScraper() as scraper:
            scraper.min_delay = scraper.max_delay = 0
            with pytest.raises(httpx.HTTPStatusError):
                await scraper.scrape_company_news("005930")
