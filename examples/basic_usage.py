"""krx-news-client 기본 사용 예제."""

from __future__ import annotations

import asyncio

from krx_news_client import YonhapScraper


async def main() -> None:
    # 키 없이 연합뉴스 마켓+ RSS. 개인·비상업 용도만 허용된다(README "뉴스 소스와 이용 조건").
    scraper = YonhapScraper()
    try:
        articles = await scraper.scrape_news(["market"])
        for article in articles[:5]:
            print(f"[{article.category}] {article.title} ({article.published_at})")
    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
