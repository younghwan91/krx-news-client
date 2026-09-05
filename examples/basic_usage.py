"""KRX News REST API 기본 사용 예제.

서버가 실행 중이어야 합니다:
    docker compose up -d
"""

from __future__ import annotations

import httpx

BASE_URL = "http://localhost:8000/api/v1"


def get_latest_news(page: int = 1, page_size: int = 5) -> dict:
    """최신 뉴스 조회."""
    resp = httpx.get(f"{BASE_URL}/news", params={"page": page, "page_size": page_size})
    resp.raise_for_status()
    return resp.json()


def get_news_by_source(source: str, page_size: int = 5) -> dict:
    """소스별 뉴스 조회. source: dart, hankyung, thebell, toss"""
    resp = httpx.get(f"{BASE_URL}/news/{source}", params={"page_size": page_size})
    resp.raise_for_status()
    return resp.json()


def search_news(keyword: str) -> dict:
    """키워드 검색."""
    resp = httpx.get(f"{BASE_URL}/news/search", params={"q": keyword})
    resp.raise_for_status()
    return resp.json()


def get_disclosures(ticker: str | None = None) -> dict:
    """공시 조회. ticker를 넘기면 종목 필터."""
    params = {"page_size": 10}
    if ticker:
        params["ticker"] = ticker
    resp = httpx.get(f"{BASE_URL}/disclosure", params=params)
    resp.raise_for_status()
    return resp.json()


def get_crawler_status() -> list[dict]:
    """크롤러 상태 확인."""
    resp = httpx.get(f"{BASE_URL}/status")
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    print("=== 최신 뉴스 ===")
    data = get_latest_news()
    for item in data["items"]:
        print(f"  [{item['source']}] {item['title']}")
    print(f"  총 {data['total']}건\n")

    print("=== 토스증권 뉴스 ===")
    data = get_news_by_source("toss")
    for item in data["items"]:
        print(f"  {item['title']}")
    print()

    print("=== '삼성전자' 검색 ===")
    data = search_news("삼성전자")
    print(f"  검색 결과: {data['total']}건")
    for item in data["items"][:3]:
        print(f"  - {item['title']}")
    print()

    print("=== 삼성전자(005930) 공시 ===")
    data = get_disclosures("005930")
    print(f"  공시 {data['total']}건")
    for item in data["items"][:3]:
        print(f"  - {item['title']}")
    print()

    print("=== 크롤러 상태 ===")
    for s in get_crawler_status():
        status = "✅" if s["is_healthy"] else "❌"
        print(f"  {status} {s['source']}: {s.get('articles_count', 0)}건")
