"""krx-news-client 기본 사용 예제."""

from __future__ import annotations

import asyncio

from krx_news_client import TossScraper


async def main() -> None:
    scraper = TossScraper()
    try:
        articles = await scraper.scrape_news()
        for article in articles[:5]:
            print(f"[{article.category}] {article.title} ({article.published_at})")
    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
