"""토스 대체 소스(연합뉴스 RSS·네이버 검색 API)와 토스 차단 오류.

``fixtures/yonhap_market.xml`` 은 2026-11-26 실제 ``/rss/market.xml`` 응답에서 항목 4개만
남긴 녹화본이다(구조·제목·시각은 그대로, 요약은 기사 전재를 피하려고 짧게 고쳐 썼다).
``fixtures/naver_news.json`` 은 네이버 공식 문서의 응답 형식대로 만든 합성 응답이다
(키 없이 녹화할 수 없어서 -- 언론사 URL 은 example 도메인).
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import httpx
import pytest

from krx_news_client import (
    KST,
    NaverAPIError,
    NaverKeyMissingError,
    NaverNewsScraper,
    NewsCategory,
    NewsSource,
    TossBlockedError,
    TossResponseError,
    TossScraper,
    YonhapFeedError,
    YonhapScraper,
)
from krx_news_client.scrapers.base import BaseScraper

FIXTURES = Path(__file__).parent / "fixtures"
YONHAP_XML = (FIXTURES / "yonhap_market.xml").read_bytes()
NAVER_JSON = json.loads((FIXTURES / "naver_news.json").read_text(encoding="utf-8"))
NAVER_URL = re.compile(r"https://openapi\.naver\.com/v1/search/news\.json.*")
BLOCKED = {"error": {"statusCode": 400, "code": "invalid-client-state", "message": None}}


@pytest.fixture(autouse=True)
def _no_delay(monkeypatch):
    for cls in (BaseScraper, TossScraper, YonhapScraper, NaverNewsScraper):
        monkeypatch.setattr(cls, "min_delay", 0)
        monkeypatch.setattr(cls, "max_delay", 0)


class TestYonhap:
    async def test_parses_recorded_feed(self, httpx_mock):
        httpx_mock.add_response(url="https://www.yna.co.kr/rss/market.xml", content=YONHAP_XML)
        async with YonhapScraper() as yna:
            articles = await yna.scrape_news(strict=True)
        assert len(articles) == 4
        first = articles[0]
        assert first.source is NewsSource.YONHAP
        assert first.category is NewsCategory.MARKET
        assert first.title.startswith("KS인더스트리")
        assert first.tickers == ["101000"]
        assert first.news_id == "AKR20261126185200008"
        assert first.author == "증권부"
        assert first.published_at.tzinfo is not None
        assert first.published_at.utcoffset() == KST.utcoffset(first.published_at)
        assert first.published_at.hour == 19
        assert first.content == ""
        # 종목코드 없는 시장 기사는 tickers 가 비어 있다.
        assert any(not a.tickers for a in articles)
        assert [a.published_at for a in articles] == sorted(
            (a.published_at for a in articles), reverse=True
        )

    async def test_dedups_across_feeds(self, httpx_mock):
        for feed in ("market", "economy"):
            httpx_mock.add_response(
                url=f"https://www.yna.co.kr/rss/{feed}.xml", content=YONHAP_XML
            )
        async with YonhapScraper() as yna:
            articles = await yna.scrape_news(["market", "economy"])
        assert len(articles) == 4

    async def test_sends_honest_user_agent(self, httpx_mock):
        httpx_mock.add_response(url="https://www.yna.co.kr/rss/market.xml", content=YONHAP_XML)
        async with YonhapScraper() as yna:
            await yna.fetch_feed("market")
        assert httpx_mock.get_request().headers["User-Agent"].startswith("krx-news-client")

    async def test_unknown_feed_raises(self):
        async with YonhapScraper() as yna:
            with pytest.raises(ValueError, match="unknown Yonhap feed"):
                await yna.scrape_news(["sports-typo"])

    async def test_non_rss_strict_raises_lenient_logs(self, httpx_mock):
        httpx_mock.add_response(
            url="https://www.yna.co.kr/rss/market.xml", content=b"<html></html>",
            is_reusable=True,
        )
        async with YonhapScraper() as yna:
            with pytest.raises(YonhapFeedError):
                await yna.scrape_news(strict=True)
            assert await yna.scrape_news() == []

    def test_ignores_external_entities(self):
        evil = (
            b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
            b"<rss><channel><item><title>&x;</title><link>https://www.yna.co.kr/view/AKR1</link>"
            b"<pubDate>Thu, 26 Nov 2026 19:49:41 +0900</pubDate></item></channel></rss>"
        )
        articles = YonhapScraper().parse_feed(evil, NewsCategory.MARKET)
        assert all("root:" not in a.title for a in articles)


class TestNaver:
    def test_from_env_missing_key_says_how_to_get_one(self):
        with pytest.raises(NaverKeyMissingError, match="developers.naver.com") as info:
            NaverNewsScraper.from_env(env={"NAVER_CLIENT_ID": "id"})
        assert "NAVER_CLIENT_SECRET" in str(info.value)
        assert "NAVER_CLIENT_ID not" not in str(info.value)

    def test_repr_hides_key(self):
        scraper = NaverNewsScraper("my-id", "my-secret")
        assert "my-secret" not in repr(scraper) and "my-id" not in repr(scraper)

    async def test_search_parses_and_sends_keys(self, httpx_mock):
        httpx_mock.add_response(url=NAVER_URL, json=NAVER_JSON)
        scraper = NaverNewsScraper.from_env(
            env={"NAVER_CLIENT_ID": "cid", "NAVER_CLIENT_SECRET": "csecret"}
        )
        async with scraper:
            articles = await scraper.search_news("삼성전자", tickers=["005930"])
        request = httpx_mock.get_request()
        assert request.headers["X-Naver-Client-Id"] == "cid"
        assert request.headers["X-Naver-Client-Secret"] == "csecret"
        assert request.url.params["query"] == "삼성전자"
        assert request.url.params["sort"] == "date"
        assert len(articles) == 3
        first = articles[0]
        assert first.source is NewsSource.NAVER
        assert first.title == '삼성전자, "HBM4 양산" 공급 확대'  # <b>·&quot; 제거
        assert first.summary.startswith("삼성전자[005930]")
        assert first.url.startswith("https://n.news.naver.com/")
        assert first.original_url == "https://www.example-press.co.kr/news/1001"
        assert first.published_at.hour == 19 and first.published_at.tzinfo is not None
        # 호출자가 준 종목 + 요약의 [코드] 표기
        assert articles[1].tickers == ["005930", "000660"]

    async def test_since_filters_and_stops(self, httpx_mock):
        httpx_mock.add_response(url=NAVER_URL, json=NAVER_JSON)
        async with NaverNewsScraper("cid", "cs") as scraper:
            articles = await scraper.search_news("삼성전자", since=date(2026, 11, 20))
        assert len(articles) == 2
        assert all(a.published_at.date() >= date(2026, 11, 20) for a in articles)

    async def test_pages_until_limit(self, httpx_mock):
        def page(request: httpx.Request) -> httpx.Response:
            start = int(request.url.params["start"])
            display = int(request.url.params["display"])
            items = [
                {
                    "title": f"기사 {n}",
                    "link": f"https://n.news.naver.com/a/{n}",
                    "originallink": f"https://press.example/{n}",
                    "description": "",
                    "pubDate": "Thu, 26 Nov 2026 10:00:00 +0900",
                }
                for n in range(start, start + display)
            ]
            return httpx.Response(200, json={"total": 999, "items": items})

        httpx_mock.add_callback(page, url=NAVER_URL, is_reusable=True)
        async with NaverNewsScraper("cid", "cs") as scraper:
            articles = await scraper.search_news("코스피", limit=150)
        starts = [int(r.url.params["start"]) for r in httpx_mock.get_requests()]
        assert starts == [1, 101]
        assert len(articles) == 150

    @pytest.mark.parametrize(
        ("kwargs", "match"),
        [({"display": 101}, "display"), ({"start": 1001}, "start"), ({"sort": "new"}, "sort")],
    )
    async def test_validates_before_request(self, kwargs, match):
        async with NaverNewsScraper("cid", "cs") as scraper:
            with pytest.raises(ValueError, match=match):
                await scraper.search_news_page("코스피", **kwargs)

    async def test_auth_error_points_to_key_registration(self, httpx_mock):
        httpx_mock.add_response(
            url=NAVER_URL, status_code=401,
            json={"errorMessage": "Authentication failed", "errorCode": "024"},
        )
        async with NaverNewsScraper("bad", "bad") as scraper:
            with pytest.raises(NaverAPIError, match="developers.naver.com") as info:
                await scraper.search_news("코스피")
        assert info.value.code == "024" and info.value.status_code == 401


class TestTossBlocked:
    async def test_company_news_raises_blocked(self, httpx_mock):
        httpx_mock.add_response(status_code=400, json=BLOCKED)
        async with TossScraper() as toss:
            with pytest.raises(TossBlockedError, match="YonhapScraper") as info:
                await toss.scrape_company_news("005930", max_pages=1)
        assert isinstance(info.value, TossResponseError)
        assert info.value.response.status_code == 400
        assert len(httpx_mock.get_requests()) == 1  # 재시도하지 않는다

    async def test_dashboard_lenient_still_raises(self, httpx_mock):
        httpx_mock.add_response(status_code=400, json=BLOCKED)
        async with TossScraper() as toss:
            with pytest.raises(TossBlockedError, match="NaverNewsScraper"):
                await toss.scrape_news()

    async def test_detail_does_not_turn_block_into_none(self, httpx_mock):
        httpx_mock.add_response(status_code=400, json=BLOCKED)
        async with TossScraper() as toss:
            with pytest.raises(TossBlockedError):
                await toss.fetch_article_detail("abc123")

    async def test_other_400_unchanged(self, httpx_mock):
        httpx_mock.add_response(
            status_code=400, json={"error": {"code": "bad-request.pagination-limit"}}
        )
        async with TossScraper() as toss:
            with pytest.raises(httpx.HTTPStatusError):
                await toss.company_news_page("005930", 1, 10)
