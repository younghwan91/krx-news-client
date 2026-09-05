from __future__ import annotations

import pytest

from krx_news_api.models.schemas import NewsArticle, NewsCategory, NewsSource
from krx_news_api.scrapers.base import BaseScraper, make_article_id
from krx_news_api.scrapers.toss import TossScraper, build_article_url


class ConcreteScraper(BaseScraper):
    source = NewsSource.HANKYUNG
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
        assert article.source == NewsSource.HANKYUNG
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
        assert disc.source == NewsSource.HANKYUNG
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
        assert article.published_at.isoformat() == "2026-09-05T18:10:12"

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
