from __future__ import annotations

from datetime import UTC, timedelta

import pytest

from krx_news_client.models.schemas import NewsArticle, NewsCategory, NewsSource
from krx_news_client.scrapers.base import BaseScraper, make_article_id
from krx_news_client.scrapers.dart import DartAPIError, DartQuotaExceededError, DartScraper
from krx_news_client.scrapers.toss import TossScraper, build_article_url


class ConcreteScraper(BaseScraper):
    source = NewsSource.DART
    base_url = "https://example.com"

    async def scrape_news(self) -> list[NewsArticle]:
        return []


class TestMakeArticleId:
    def test_deterministic(self):
        id1 = make_article_id("naver", "https://example.com/1")
        id2 = make_article_id("naver", "https://example.com/1")
        assert id1 == id2

    def test_different_urls(self):
        id1 = make_article_id("naver", "https://example.com/1")
        id2 = make_article_id("naver", "https://example.com/2")
        assert id1 != id2

    def test_format(self):
        aid = make_article_id("kind", "https://example.com/1")
        assert aid.startswith("kind:")
        assert len(aid) == len("kind:") + 12


class TestBaseScraper:
    def test_make_article(self):
        scraper = ConcreteScraper()
        article = scraper._make_article(
            title="Test Article",
            url="https://example.com/1",
            category=NewsCategory.MARKET,
            content="Some content",
            tickers=["005930"],
        )
        assert isinstance(article, NewsArticle)
        assert article.source == NewsSource.DART
        assert article.title == "Test Article"
        assert article.tickers == ["005930"]

    def test_make_disclosure(self):
        scraper = ConcreteScraper()
        disc = scraper._make_disclosure(
            title="공시제목",
            url="https://example.com/disc/1",
            company="삼성전자",
            ticker="005930",
            disclosure_type="주요사항보고서",
        )
        assert disc.source == NewsSource.DART
        assert disc.company == "삼성전자"

    @pytest.mark.asyncio
    async def test_scrape_news_interface(self):
        scraper = ConcreteScraper()
        result = await scraper.scrape_news()
        assert result == []

    @pytest.mark.asyncio
    async def test_scrape_disclosures_default(self):
        scraper = ConcreteScraper()
        result = await scraper.scrape_disclosures()
        assert result == []


class TestBuildArticleUrl:
    def test_contains_news_id(self):
        url = build_article_url("chosunbiz_2026090501194")
        assert url.startswith("https://tossinvest.com/news?")
        assert "contentType=news" in url
        assert "chosunbiz_2026090501194" in url


class TestTossScraper:
    def test_parse_item(self):
        scraper = TossScraper()
        item = {
            "newsId": "chosunbiz_2026090501703",
            "title": "포스코-현대제철 미국 합작 제철소",
            "summary": "장인화 포스코그룹 회장은...",
            "contentText": "장인화 포스코그룹 회장은...",
            "createdAt": "2026-09-05T18:10:12",
            "source": "조선비즈",
            "newsType": "finance_category",
            "relatedStocks": [
                {"stockCode": "A005490", "stockName": "POSCO홀딩스"},
                {"stockCode": "A004020", "stockName": "현대제철"},
            ],
            "nation": "KR",
        }

        article = scraper._parse_item(item, NewsCategory.MARKET)

        assert isinstance(article, NewsArticle)
        assert article.source == NewsSource.TOSS
        assert article.category == NewsCategory.MARKET
        assert article.title == item["title"]
        assert article.author == "조선비즈"
        assert article.tickers == ["005490", "004020"]
        # KST 오프셋이 붙어야 한다 — naive 로 두면 소비자 timestamptz 에서 9시간
        # 밀린다(2026-09-13 사고, _parse_date 주석 참고).
        assert article.published_at.isoformat() == "2026-09-05T18:10:12+09:00"

    def test_parse_item_without_related_stocks(self):
        scraper = TossScraper()
        item = {
            "newsId": "tokenpost_P00420260905402964",
            "title": "테슬라 사이버캡 조사 착수",
            "createdAt": "2026-09-05T17:06:56",
            "source": "토큰포스트",
        }

        article = scraper._parse_item(item, NewsCategory.BREAKING)

        assert article is not None
        assert article.tickers == []

    def test_parse_item_missing_required_fields(self):
        scraper = TossScraper()
        assert scraper._parse_item({}, NewsCategory.MARKET) is None
        assert scraper._parse_item({"title": "제목만 있음"}, NewsCategory.MARKET) is None

    def test_parse_date_invalid(self):
        assert TossScraper._parse_date("not-a-date") is None
        assert TossScraper._parse_date(None) is None

    def test_parse_date_treats_naive_as_kst(self):
        """토스 createdAt 은 오프셋 없는 KST 벽시계다.

        naive 로 흘리면 소비자(quant-airflow)가 timestamptz 컬럼에 넣는 순간
        UTC 로 읽혀 9시간 미래로 밀린다 — 2026-09-13 실제로 그렇게 쌓여 있던
        걸 발견해 고쳤다. 여기서 그 회귀를 막는다.
        """
        got = TossScraper._parse_date("2026-09-05T18:10:12")
        assert got is not None
        assert got.tzinfo is not None
        assert got.utcoffset() == timedelta(hours=9)
        # UTC 로 환산하면 같은 날 09:10 — 저장 시 밀리지 않는다.
        assert got.astimezone(UTC).isoformat() == "2026-09-05T09:10:12+00:00"

    def test_parse_date_respects_explicit_offset(self):
        got = TossScraper._parse_date("2026-09-05T18:10:12+00:00")
        assert got is not None
        assert got.utcoffset() == timedelta(0)


class TestDartScraper:
    @pytest.mark.asyncio
    async def test_scrape_disclosures_quota_exceeded(self, httpx_mock):
        httpx_mock.add_response(json={"status": "020", "message": "사용한도 초과"})
        scraper = DartScraper(api_key="dummy")
        try:
            with pytest.raises(DartQuotaExceededError):
                await scraper.scrape_disclosures()
        finally:
            await scraper.close()

    @pytest.mark.asyncio
    async def test_scrape_disclosures_no_data(self, httpx_mock):
        httpx_mock.add_response(json={"status": "013", "message": "조회된 데이터가 없습니다"})
        scraper = DartScraper(api_key="dummy")
        try:
            result = await scraper.scrape_disclosures()
        finally:
            await scraper.close()
        assert result == []

    @pytest.mark.asyncio
    async def test_scrape_disclosures_parses_list(self, httpx_mock):
        httpx_mock.add_response(
            json={
                "status": "000",
                "message": "정상",
                "page_no": 1,
                "total_page": 1,
                "list": [
                    {
                        "rcept_no": "20260905000123",
                        "corp_name": "삼성전자",
                        "stock_code": "005930",
                        "report_nm": "주요사항보고서",
                        "rcept_dt": "20260905",
                    },
                ],
            }
        )
        scraper = DartScraper(api_key="dummy")
        try:
            result = await scraper.scrape_disclosures()
        finally:
            await scraper.close()
        assert len(result) == 1
        assert result[0].ticker == "005930"
        assert result[0].company == "삼성전자"

    @pytest.mark.asyncio
    async def test_scrape_disclosures_uses_explicit_date_range(self, httpx_mock):
        # 명시적 bgn_de/end_de 를 주면 그대로 요청 파라미터에 실려야 한다 —
        # 기본값(어제~오늘)으로 조용히 덮어쓰이면 히스토리 백필이 못 쓰인다.
        httpx_mock.add_response(json={"status": "013", "message": "없음"})
        scraper = DartScraper(api_key="dummy")
        try:
            await scraper.scrape_disclosures(bgn_de="20260101", end_de="20260107")
        finally:
            await scraper.close()
        request = httpx_mock.get_requests()[0]
        params = dict(request.url.params)
        assert params["bgn_de"] == "20260101"
        assert params["end_de"] == "20260107"
        assert "corp_cls" not in params

    @pytest.mark.asyncio
    async def test_scrape_disclosures_passes_corp_cls_when_given(self, httpx_mock):
        httpx_mock.add_response(json={"status": "013", "message": "없음"})
        scraper = DartScraper(api_key="dummy")
        try:
            await scraper.scrape_disclosures(corp_cls="Y")
        finally:
            await scraper.close()
        request = httpx_mock.get_requests()[0]
        assert dict(request.url.params)["corp_cls"] == "Y"


class TestDartScraperMultiKeyAndRawSearch:
    """다중 키 로테이션 + raw row 검색 -- scalp-it의 10년 백필용
    ``adapters/dart.py``에 있던 로직을 여기로 옮긴 부분. Disclosure 모델에는
    없는 ``rcept_no``/``corp_cls`` 원본 필드가 필요한 호출부를 위한 것이다.
    """

    def test_single_key_still_works_via_api_key_alias(self):
        scraper = DartScraper(api_key="dummy")
        assert scraper.api_keys == ["dummy"]
        assert scraper.api_key == "dummy"

    @pytest.mark.asyncio
    async def test_search_disclosures_returns_raw_payload(self, httpx_mock):
        httpx_mock.add_response(
            json={
                "status": "000",
                "message": "정상",
                "page_no": 1,
                "total_page": 1,
                "list": [{"rcept_no": "20260814000123", "corp_cls": "K", "stock_code": "073540"}],
            }
        )
        scraper = DartScraper(api_key="k1")
        try:
            payload = await scraper.search_disclosures(
                bgn_de="20260810", end_de="20260814", corp_cls="K"
            )
        finally:
            await scraper.close()
        assert payload["list"][0]["rcept_no"] == "20260814000123"
        assert payload["list"][0]["corp_cls"] == "K"

    @pytest.mark.asyncio
    async def test_rate_limited_key_falls_through_to_next(self, httpx_mock):
        httpx_mock.add_response(json={"status": "020", "message": "요청 제한을 초과하였습니다."})
        httpx_mock.add_response(
            json={
                "status": "000",
                "message": "정상",
                "page_no": 1,
                "total_page": 1,
                "list": [{"rcept_no": "1"}],
            }
        )
        scraper = DartScraper(api_key=["k1", "k2"])
        try:
            payload = await scraper.search_disclosures(bgn_de="20260810", end_de="20260814")
        finally:
            await scraper.close()
        assert payload["list"][0]["rcept_no"] == "1"
        keys_used = [dict(r.url.params)["crtfc_key"] for r in httpx_mock.get_requests()]
        assert keys_used == ["k1", "k2"]

    @pytest.mark.asyncio
    async def test_all_keys_rate_limited_raises_quota_exceeded(self, httpx_mock):
        httpx_mock.add_response(json={"status": "020", "message": "초과"})
        httpx_mock.add_response(json={"status": "020", "message": "초과"})
        scraper = DartScraper(api_key=["k1", "k2"])
        try:
            with pytest.raises(DartQuotaExceededError):
                await scraper.search_disclosures(bgn_de="20260810", end_de="20260814")
        finally:
            await scraper.close()

    @pytest.mark.asyncio
    async def test_other_error_status_raises_dart_api_error(self, httpx_mock):
        httpx_mock.add_response(json={"status": "010", "message": "등록되지 않은 키입니다."})
        scraper = DartScraper(api_key="k1")
        try:
            with pytest.raises(DartAPIError):
                await scraper.search_disclosures(bgn_de="20260101", end_de="20260101")
        finally:
            await scraper.close()

    @pytest.mark.asyncio
    async def test_search_disclosures_all_walks_every_page(self, httpx_mock):
        for page in (1, 2, 3):
            httpx_mock.add_response(
                json={
                    "status": "000",
                    "message": "정상",
                    "page_no": page,
                    "total_page": 3,
                    "list": [{"rcept_no": f"page{page}"}],
                }
            )
        scraper = DartScraper(api_key="k1")
        try:
            rows = await scraper.search_disclosures_all(
                bgn_de="20260810", end_de="20260814", corp_cls="K"
            )
        finally:
            await scraper.close()
        assert [r["rcept_no"] for r in rows] == ["page1", "page2", "page3"]

    @pytest.mark.asyncio
    async def test_scrape_disclosures_keeps_partial_results_on_mid_stream_error(self, httpx_mock):
        # 1페이지 성공, 2페이지에서 예상치 못한 오류 -- lenient 경로(scrape_disclosures)는
        # 예외를 던지지 않고 1페이지분만 반환해야 한다 (기존 동작 보존).
        httpx_mock.add_response(
            json={
                "status": "000",
                "message": "정상",
                "page_no": 1,
                "total_page": 2,
                "list": [
                    {
                        "rcept_no": "ok",
                        "corp_name": "삼성전자",
                        "stock_code": "005930",
                        "rcept_dt": "20260905",
                    }
                ],
            }
        )
        httpx_mock.add_response(json={"status": "999", "message": "알수없는오류"})
        scraper = DartScraper(api_key="k1")
        try:
            result = await scraper.scrape_disclosures(bgn_de="20260905", end_de="20260906")
        finally:
            await scraper.close()
        assert len(result) == 1
        assert result[0].ticker == "005930"
