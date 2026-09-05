"""KRX News REST API 비동기 사용 예제.

여러 소스를 동시에 조회하여 빠르게 데이터를 가져옵니다.

필요 패키지: pip install httpx
"""

from __future__ import annotations

import asyncio

import httpx

BASE_URL = "http://localhost:8000/api/v1"
SOURCES = ["dart", "hankyung", "thebell", "toss"]


async def fetch_all_sources() -> dict[str, dict]:
    """모든 소스의 뉴스를 동시에 조회."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10) as client:
        tasks = {src: client.get(f"/news/{src}", params={"page_size": 5}) for src in SOURCES}
        results = {}
        responses = await asyncio.gather(*tasks.values(), return_exceptions=True)

        for src, resp in zip(tasks.keys(), responses):
            if isinstance(resp, Exception):
                results[src] = {"error": str(resp)}
            else:
                results[src] = resp.json()
        return results


async def search_multiple_keywords(keywords: list[str]) -> dict[str, dict]:
    """여러 키워드를 동시에 검색."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10) as client:
        tasks = {kw: client.get("/news/search", params={"q": kw}) for kw in keywords}
        results = {}
        responses = await asyncio.gather(*tasks.values(), return_exceptions=True)

        for kw, resp in zip(tasks.keys(), responses):
            if isinstance(resp, Exception):
                results[kw] = {"error": str(resp)}
            else:
                results[kw] = resp.json()
        return results


async def monitor_news(interval: int = 30) -> None:
    """주기적으로 최신 뉴스를 폴링하는 간단한 모니터."""
    seen_ids: set[str] = set()
    print(f"뉴스 모니터 시작 (매 {interval}초 갱신, Ctrl+C로 종료)\n")

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10) as client:
        while True:
            try:
                resp = await client.get("/news", params={"page_size": 20})
                resp.raise_for_status()
                data = resp.json()

                for item in data["items"]:
                    if item["id"] not in seen_ids:
                        seen_ids.add(item["id"])
                        print(f"🆕 [{item['source']}] {item['title']}")
                        print(f"   {item['url']}\n")
            except httpx.HTTPError as e:
                print(f"⚠️  요청 실패: {e}")

            await asyncio.sleep(interval)


async def main() -> None:
    print("=== 전체 소스 동시 조회 ===")
    all_news = await fetch_all_sources()
    for src, data in all_news.items():
        count = data.get("total", 0)
        print(f"  {src}: {count}건")
    print()

    print("=== 멀티 키워드 검색 ===")
    keywords = ["삼성전자", "SK하이닉스", "금리", "배당", "IPO"]
    results = await search_multiple_keywords(keywords)
    for kw, data in results.items():
        count = data.get("total", 0)
        print(f"  '{kw}': {count}건")
    print()

    print("=== 실시간 모니터 ===")
    await monitor_news(interval=30)


if __name__ == "__main__":
    asyncio.run(main())
