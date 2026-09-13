from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from krx_news_client.models.schemas import KST, Disclosure, NewsArticle, NewsSource
from krx_news_client.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

DETAIL_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcept_no={rcept_no}"

#: DART 응답 status. 일한도 소진 시 이 값이 온다.
QUOTA_EXHAUSTED_STATUS = "020"
_OK = "000"
_NO_DATA = "013"


class DartQuotaExceededError(Exception):
    """구성된 DART API 키가 **전부** 일한도(020)를 소진했다.

    호출부(예: 여러 키를 순환하는 상위 오케스트레이터)가 "그 날짜 범위에
    공시가 없었다"(status=013, 조용히 빈 리스트 반환)와 "한도 초과로 못
    가져왔다"를 구분할 수 있도록 별도 예외로 알린다 — 둘 다 빈 리스트로
    뭉개면 백테스팅용 히스토리에 조용한 결측이 생긴다.
    """


class DartAPIError(Exception):
    """DART가 성공(000)·데이터없음(013)·한도초과(020) 외의 상태를 돌려주었다.

    ``search_disclosures``/``search_disclosures_all``은 이 오류를 그대로
    올린다(엄격) -- 백필처럼 결측을 조용히 넘기면 안 되는 호출부를 위해서다.
    ``scrape_disclosures``(기존 "최근 뉴스 피드" 용도)는 이 오류를 페이지
    단위로 잡아 로그만 남기고 계속하는 예전 관용적(lenient) 동작을 유지한다.
    """


class DartScraper(BaseScraper):
    source = NewsSource.DART
    base_url = "https://opendart.fss.or.kr/api"

    def __init__(self, api_key: str | Sequence[str]) -> None:
        """Args:
        api_key: 단일 키(문자열) 또는 여러 키(로테이션용 시퀀스). 여러 키는
            일 20,000건 한도를 넘겨야 하는 대량 백필에 필요하다 -- scalp-it이
            10년치 공시 수집에 키 3개를 로테이션하던 로직을 여기로 옮겼다.
        """
        super().__init__()
        keys = [api_key] if isinstance(api_key, str) else [str(k) for k in api_key]
        self.api_keys: list[str] = [k for k in keys if k]
        #: 단일 키만 쓰던 기존 호출부와의 하위호환(``self.api_key`` 참조).
        self.api_key = self.api_keys[0] if self.api_keys else ""
        self._key_cursor = 0

    def _next_key(self) -> str:
        key = self.api_keys[self._key_cursor % len(self.api_keys)]
        self._key_cursor += 1
        return key

    async def scrape_news(self) -> list[NewsArticle]:
        return []

    async def search_disclosures(
        self,
        *,
        bgn_de: str,
        end_de: str,
        corp_cls: str | None = None,
        page_no: int = 1,
        page_count: int = 100,
    ) -> dict[str, Any]:
        """공시검색(``list.json``) 한 페이지, 원본 JSON 그대로.

        키가 여럿이면 한 키가 한도 초과(020)를 보고할 때 다음 키로 넘어가
        재시도한다 -- 모든 키가 소진돼야 ``DartQuotaExceededError``. 그 외의
        오류 상태(예: "010 등록되지 않은 키")는 ``DartAPIError``로 즉시
        올린다 -- 백필처럼 결측을 조용히 넘기면 안 되는 호출부를 위한 엄격
        경로다(관용적 처리가 필요하면 ``scrape_disclosures``를 쓸 것).
        """
        if not self.api_keys:
            raise DartQuotaExceededError("no DART API key configured")

        last_message = ""
        for _ in range(len(self.api_keys)):
            params = {
                "crtfc_key": self._next_key(),
                "bgn_de": bgn_de,
                "end_de": end_de,
                "page_no": str(page_no),
                "page_count": str(page_count),
            }
            if corp_cls:
                params["corp_cls"] = corp_cls

            resp = await self.fetch(f"{self.base_url}/list.json", params=params)
            data: dict[str, Any] = resp.json()
            status = data.get("status")
            if status == _OK:
                data.setdefault("list", [])
                return data
            if status == _NO_DATA:
                # 공시가 하루도 없는 구간은 실제로 존재한다. 오류가 아니다.
                return {**data, "list": [], "total_page": 0, "total_count": 0}
            last_message = f"{status} {data.get('message')}"
            if status != QUOTA_EXHAUSTED_STATUS:
                raise DartAPIError(f"DART API error: {last_message}")
        raise DartQuotaExceededError(
            f"all {len(self.api_keys)} configured DART key(s) exhausted daily quota: {last_message}"
        )

    async def search_disclosures_all(
        self,
        *,
        bgn_de: str,
        end_de: str,
        corp_cls: str | None = None,
    ) -> list[dict[str, Any]]:
        """구간의 모든 페이지를 raw dict 리스트로 모은다.

        DART 자체가 ``corp_code`` 없는 검색을 달력 3개월로 제한한다 -- 여러
        해에 걸친 백필은 호출부가 구간을 쪼개야 한다(scalp-it의
        ``cli_dart.py.quarter_ranges``가 참조 구현).
        """
        rows: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = await self.search_disclosures(
                bgn_de=bgn_de, end_de=end_de, corp_cls=corp_cls, page_no=page
            )
            rows.extend(payload.get("list") or [])
            total_page = int(payload.get("total_page") or 0)
            if page >= total_page:
                return rows
            page += 1

    async def scrape_disclosures(
        self,
        *,
        bgn_de: str | None = None,
        end_de: str | None = None,
        corp_cls: str | None = None,
    ) -> list[Disclosure]:
        """Fetch disclosures for a date range, mapped to the ``Disclosure`` model.

        Args:
            bgn_de: Range start, ``YYYYMMDD``. Defaults to yesterday (the
                "recent news feed" use case this scraper was originally
                built for) when omitted.
            end_de: Range end, ``YYYYMMDD``. Defaults to today when omitted.
            corp_cls: DART's listing-market filter (``Y``=KOSPI, ``K``=KOSDAQ,
                ``N``=KONEX, ``E``=기타). ``None`` fetches all markets, matching
                DART's own default when the param is absent.

        Unlike ``search_disclosures``/``search_disclosures_all``, a non-quota
        API error (``DartAPIError``) is logged and ends the fetch early
        (returning whatever was collected so far) rather than raised -- this
        method feeds a live polling loop where skipping one bad page is
        preferable to crashing it. ``DartQuotaExceededError`` still
        propagates, since a poller and a backfill both need to know the key
        is out of quota.
        """
        if not self.api_keys:
            logger.warning("DART API key not configured – skipping disclosure scrape")
            return []

        # 기본 범위(어제~오늘)는 **KST 기준 영업일**이어야 한다 -- UTC 로 재면
        # KST 09:00 이전엔 하루 전 날짜가 나온다.
        today = datetime.now(tz=KST)
        yesterday = today - timedelta(days=1)
        bgn_de = bgn_de or yesterday.strftime("%Y%m%d")
        end_de = end_de or today.strftime("%Y%m%d")

        rows: list[dict[str, Any]] = []
        page = 1
        while True:
            try:
                payload = await self.search_disclosures(
                    bgn_de=bgn_de, end_de=end_de, corp_cls=corp_cls, page_no=page
                )
            except DartQuotaExceededError:
                raise
            except Exception:  # noqa: BLE001 - lenient by design, see docstring
                logger.exception(
                    "DART API request failed (page %d), stopping with partial results", page
                )
                break
            rows.extend(payload.get("list") or [])
            total_page = int(payload.get("total_page") or 0)
            if page >= total_page:
                break
            page += 1

        disclosures: list[Disclosure] = []
        for item in rows:
            rcept_no = item.get("rcept_no", "")
            url = DETAIL_URL.format(rcept_no=rcept_no)
            rcept_dt = item.get("rcept_dt", "")

            try:
                # rcept_dt 는 접수'일'(KST)이라 시각이 없다 -- 00:00 KST 로 둔다.
                # tz 를 붙이는 이유는 toss.py 의 ``KST`` 주석과 같다: naive 로
                # 두면 소비자의 timestamptz 컬럼에서 9시간 밀린다(날짜까지 넘어간다).
                published_at = datetime.strptime(rcept_dt, "%Y%m%d").replace(tzinfo=KST)
            except (ValueError, TypeError):
                published_at = datetime.now(tz=KST)

            disclosures.append(
                self._make_disclosure(
                    title=item.get("report_nm", ""),
                    url=url,
                    company=item.get("corp_name", ""),
                    ticker=item.get("stock_code", ""),
                    disclosure_type=item.get("report_nm", ""),
                    published_at=published_at,
                )
            )

        logger.info("DART: collected %d disclosures (%s ~ %s)", len(disclosures), bgn_de, end_de)
        return disclosures
