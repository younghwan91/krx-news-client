"""종목 알림 예제.

관심 종목 키워드가 포함된 토스 뉴스를 주기적으로 확인하고 새 항목이 있으면
알림을 출력합니다. 실제 서비스에서는 send_alert()를 Slack/Telegram/Discord
웹훅으로 교체하세요. (DART 공시를 함께 보려면 DartScraper(api_key=...)를
추가로 호출하면 됩니다.)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from krx_news_client import NewsArticle, TossScraper


@dataclass
class WatchItem:
    name: str
    ticker: str
    keywords: list[str] = field(default_factory=list)


# 관심 종목 설정
WATCHLIST: list[WatchItem] = [
    WatchItem(name="삼성전자", ticker="005930", keywords=["삼성전자", "삼성", "반도체"]),
    WatchItem(name="SK하이닉스", ticker="000660", keywords=["SK하이닉스", "하이닉스", "HBM"]),
    WatchItem(name="LG에너지솔루션", ticker="373220", keywords=["LG에너지", "배터리", "2차전지"]),
    WatchItem(name="현대차", ticker="005380", keywords=["현대차", "현대자동차", "전기차"]),
    WatchItem(name="NAVER", ticker="035420", keywords=["네이버", "NAVER", "AI"]),
]


def matches(article: NewsArticle, item: WatchItem) -> bool:
    if item.ticker in article.tickers:
        return True
    return any(kw in article.title for kw in item.keywords)


def send_alert(item_name: str, title: str, url: str) -> None:
    """알림 전송 (콘솔 출력). 실제로는 Slack/Telegram 웹훅으로 교체."""
    print(f"📰 [{item_name}] {title}\n   🔗 {url}\n")


async def run_alert_loop(interval: int = 60) -> None:
    """메인 감시 루프 — 매 주기마다 토스 뉴스를 다시 가져와 관심 종목과 대조한다."""
    seen_ids: set[str] = set()
    names = ", ".join(w.name for w in WATCHLIST)
    print(f"📡 종목 알림 시작: {names}")
    print(f"   갱신 주기: {interval}초 | Ctrl+C로 종료\n")

    scraper = TossScraper()
    try:
        while True:
            try:
                articles = await scraper.scrape_news()
            except Exception as e:  # noqa: BLE001 — 한 주기 실패해도 다음 주기에 계속
                print(f"⚠️  뉴스 조회 실패: {e}")
                await asyncio.sleep(interval)
                continue

            for article in articles:
                if article.id in seen_ids:
                    continue
                for item in WATCHLIST:
                    if matches(article, item):
                        seen_ids.add(article.id)
                        send_alert(item.name, article.title, article.url)
                        break

            await asyncio.sleep(interval)
    finally:
        await scraper.close()


if __name__ == "__main__":
    try:
        asyncio.run(run_alert_loop(interval=60))
    except KeyboardInterrupt:
        print("\n종목 알림 종료.")
