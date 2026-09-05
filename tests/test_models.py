from __future__ import annotations

from datetime import datetime

from krx_news_client.models.schemas import (
    Disclosure,
    NewsArticle,
    NewsCategory,
    NewsSource,
)


class TestNewsArticle:
    def test_create_article(self):
        article = NewsArticle(
            id="toss:abc123",
            source=NewsSource.TOSS,
            category=NewsCategory.MARKET,
            title="삼성전자 실적 발표",
            url="https://example.com/article/1",
            content="삼성전자가 분기 실적을 발표했습니다.",
            tickers=["005930"],
            published_at=datetime(2024, 1, 15, 9, 0),
        )
        assert article.source == NewsSource.TOSS
        assert article.tickers == ["005930"]
        assert "삼성전자" in article.title

    def test_article_defaults(self):
        article = NewsArticle(
            id="test:1",
            source=NewsSource.HANKYUNG,
            category=NewsCategory.DISCLOSURE,
            title="Test",
            url="https://example.com",
            published_at=datetime.now(),
        )
        assert article.content == ""
        assert article.tickers == []
        assert article.author == ""

    def test_article_serialization(self):
        article = NewsArticle(
            id="test:1",
            source=NewsSource.TOSS,
            category=NewsCategory.STOCK,
            title="테스트 기사",
            url="https://example.com",
            published_at=datetime(2024, 1, 1),
        )
        json_str = article.model_dump_json()
        restored = NewsArticle.model_validate_json(json_str)
        assert restored.title == article.title
        assert restored.source == article.source


class TestDisclosure:
    def test_create_disclosure(self):
        disc = Disclosure(
            id="dart:xyz789",
            source=NewsSource.DART,
            title="주요사항보고서",
            url="https://dart.fss.or.kr/disclosure/1",
            company="삼성전자",
            ticker="005930",
            disclosure_type="주요사항보고서",
            published_at=datetime(2024, 1, 15),
        )
        assert disc.ticker == "005930"
        assert disc.company == "삼성전자"
