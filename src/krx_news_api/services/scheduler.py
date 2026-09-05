from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from krx_news_api.config import settings
from krx_news_api.models.schemas import NewsSource
from krx_news_api.scrapers.base import BaseScraper
from krx_news_api.scrapers.dart import DartScraper
from krx_news_api.scrapers.hankyung import HankyungScraper
from krx_news_api.scrapers.thebell import TheBellScraper
from krx_news_api.scrapers.toss import TossScraper
from krx_news_api.services.cache import (
    cache_articles,
    cache_disclosures,
    update_crawler_status,
)

logger = logging.getLogger(__name__)

_scrapers: dict[NewsSource, BaseScraper] = {}
_scheduler: AsyncIOScheduler | None = None


def get_scrapers() -> dict[NewsSource, BaseScraper]:
    global _scrapers
    if not _scrapers:
        _scrapers = {
            NewsSource.DART: DartScraper(),
            NewsSource.HANKYUNG: HankyungScraper(),
            NewsSource.THEBELL: TheBellScraper(),
            NewsSource.TOSS: TossScraper(),
        }
    return _scrapers


async def crawl_source(source: NewsSource) -> None:
    scraper = get_scrapers().get(source)
    if not scraper:
        return

    try:
        articles = await scraper.scrape_news()
        disclosures = await scraper.scrape_disclosures()

        count = 0
        if articles:
            count += await cache_articles(source, articles)
        if disclosures:
            count += await cache_disclosures(source, disclosures)

        await update_crawler_status(source, articles_count=count)
        logger.info("Crawled %s: %d items", source.value, count)

    except Exception as e:
        logger.error("Failed to crawl %s: %s", source.value, e, exc_info=True)
        await update_crawler_status(source, error=str(e))
    finally:
        await scraper.close()


async def crawl_all_news() -> None:
    for source in [
        NewsSource.HANKYUNG,
        NewsSource.THEBELL,
        NewsSource.TOSS,
    ]:
        await crawl_source(source)


async def crawl_all_disclosures() -> None:
    for source in [NewsSource.DART]:
        await crawl_source(source)


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    _scheduler = AsyncIOScheduler()

    _scheduler.add_job(
        crawl_all_disclosures,
        "interval",
        seconds=settings.crawl_interval_disclosure,
        id="crawl_disclosures",
        name="Crawl disclosures (DART)",
        misfire_grace_time=30,
    )

    _scheduler.add_job(
        crawl_all_news,
        "interval",
        seconds=settings.crawl_interval_news,
        id="crawl_news",
        name="Crawl news (Hankyung + TheBell + Toss)",
        misfire_grace_time=60,
    )

    _scheduler.start()
    logger.info(
        "Scheduler started: disclosures every %ds, news every %ds",
        settings.crawl_interval_disclosure,
        settings.crawl_interval_news,
    )
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler stopped")
