"""폴링용 중복 제거.

토스 대시보드는 스냅샷이라 30초 간격으로 부르면 몇 분 동안 거의 전부 같은
기사가 다시 온다. DART ``scrape_disclosures`` 도 어제~오늘 구간을 매번 통째로
준다. 폴링 루프는 "처음 본 것만" 넘기면 되고, 그 판단을 여기서 한다
(daytrade-it 의 토스·DART 폴러에 거의 같은 코드가 두 벌 있던 것을 합쳤다).
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Hashable, Iterable
from typing import Generic, TypeVar

from krx_news_client.models.schemas import Disclosure, NewsArticle

T = TypeVar("T")


def default_key(item: NewsArticle | Disclosure) -> Hashable:
    """기사는 ``id``(source:url 해시), 공시는 접수번호가 있으면 접수번호."""
    if isinstance(item, Disclosure) and item.rcept_no:
        return f"{item.source.value}:{item.rcept_no}"
    return item.id


class Deduplicator(Generic[T]):
    """본 적 없는 항목만 통과시킨다. 메모리는 최근 ``max_size`` 개로 제한한다.

    Example::

        dedup = Deduplicator()
        while True:
            for article in dedup.filter_new(await toss.scrape_news()):
                handle(article)
            await asyncio.sleep(180)
    """

    def __init__(
        self,
        key: Callable[[T], Hashable] = default_key,  # type: ignore[assignment]
        max_size: int = 50_000,
    ) -> None:
        self._key = key
        self._max_size = max_size
        self._seen: OrderedDict[Hashable, None] = OrderedDict()

    def __len__(self) -> int:
        return len(self._seen)

    def __contains__(self, item: T) -> bool:
        return self._key(item) in self._seen

    def filter_new(self, items: Iterable[T]) -> list[T]:
        """``items`` 중 처음 보는 것만 순서대로 돌려주고 본 것으로 기록한다."""
        fresh: list[T] = []
        for item in items:
            k = self._key(item)
            if k in self._seen:
                self._seen.move_to_end(k)
                continue
            self._seen[k] = None
            fresh.append(item)
        while len(self._seen) > self._max_size:
            self._seen.popitem(last=False)
        return fresh

    def mark_seen(self, items: Iterable[T]) -> None:
        """재시작 직후 이미 처리한 항목을 채워 넣을 때 쓴다."""
        self.filter_new(items)
