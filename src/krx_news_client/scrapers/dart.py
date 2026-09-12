from __future__ import annotations

import logging
from datetime import datetime, timedelta

from krx_news_client.models.schemas import KST, Disclosure, NewsArticle, NewsSource
from krx_news_client.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

DETAIL_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcept_no={rcept_no}"

#: DART 응답 status. 일한도 소진 시 이 값이 온다.
QUOTA_EXHAUSTED_STATUS = "020"


class DartQuotaExceededError(Exception):
    """DART API 키가 일한도(020)를 소진했다.

    호출부(예: 여러 키를 순환하는 상위 오케스트레이터)가 "그 날짜 범위에
    공시가 없었다"(status=013, 조용히 빈 리스트 반환)와 "한도 초과로 못
    가져왔다"를 구분할 수 있도록 별도 예외로 알린다 — 둘 다 빈 리스트로
    뭉개면 백테스팅용 히스토리에 조용한 결측이 생긴다.
    """


class DartScraper(BaseScraper):
    source = NewsSource.DART
    base_url = "https://opendart.fss.or.kr/api"

    def __init__(self, api_key: str) -> None:
        super().__init__()
        self.api_key = api_key

    async def scrape_news(self) -> list[NewsArticle]:
        return []

    async def scrape_disclosures(
        self,
        *,
        bgn_de: str | None = None,
        end_de: str | None = None,
        corp_cls: str | None = None,
    ) -> list[Disclosure]:
        """Fetch disclosures for a date range.

        Args:
            bgn_de: Range start, ``YYYYMMDD``. Defaults to yesterday (the
                "recent news feed" use case this scraper was originally
                built for) when omitted.
            end_de: Range end, ``YYYYMMDD``. Defaults to today when omitted.
            corp_cls: DART's listing-market filter (``Y``=KOSPI, ``K``=KOSDAQ,
                ``N``=KONEX, ``E``=기타). ``None`` fetches all markets, matching
                DART's own default when the param is absent.
        """
        if not self.api_key:
            logger.warning("DART API key not configured – skipping disclosure scrape")
            return []

        # 기본 범위(어제~오늘)는 **KST 기준 영업일**이어야 한다 — UTC 로 재면
        # KST 09:00 이전엔 하루 전 날짜가 나온다.
        today = datetime.now(tz=KST)
        yesterday = today - timedelta(days=1)
        bgn_de = bgn_de or yesterday.strftime("%Y%m%d")
        end_de = end_de or today.strftime("%Y%m%d")

        disclosures: list[Disclosure] = []
        page_no = 1

        while True:
            params = {
                "crtfc_key": self.api_key,
                "bgn_de": bgn_de,
                "end_de": end_de,
                "page_no": str(page_no),
                "page_count": "100",
            }
            if corp_cls:
                params["corp_cls"] = corp_cls

            try:
                resp = await self.fetch(f"{self.base_url}/list.json", params=params)
                data = resp.json()
            except Exception:
                logger.exception("DART API request failed (page %d)", page_no)
                break

            status = data.get("status")
            if status == "013":
                logger.debug("DART: no disclosures found for %s ~ %s", bgn_de, end_de)
                break
            if status == QUOTA_EXHAUSTED_STATUS:
                raise DartQuotaExceededError(
                    f"DART API key exhausted daily quota (status=020, {bgn_de}~{end_de})"
                )
            if status != "000":
                logger.error("DART API error: status=%s, message=%s", status, data.get("message"))
                break

            for item in data.get("list", []):
                rcept_no = item.get("rcept_no", "")
                url = DETAIL_URL.format(rcept_no=rcept_no)
                rcept_dt = item.get("rcept_dt", "")

                try:
                    # rcept_dt 는 접수'일'(KST)이라 시각이 없다 — 00:00 KST 로 둔다.
                    # tz 를 붙이는 이유는 toss.py 의 ``KST`` 주석과 같다: naive 로
                    # 두면 소비자의 timestamptz 컬럼에서 9시간 밀린다(날짜까지 넘어간다).
                    published_at = datetime.strptime(rcept_dt, "%Y%m%d").replace(tzinfo=KST)
                except (ValueError, TypeError):
                    published_at = datetime.now(tz=KST)

                disclosure = self._make_disclosure(
                    title=item.get("report_nm", ""),
                    url=url,
                    company=item.get("corp_name", ""),
                    ticker=item.get("stock_code", ""),
                    disclosure_type=item.get("report_nm", ""),
                    published_at=published_at,
                )
                disclosures.append(disclosure)

            total_page = int(data.get("total_page", 1))
            if page_no >= total_page:
                break
            page_no += 1

        logger.info("DART: collected %d disclosures (%s ~ %s)", len(disclosures), bgn_de, end_de)
        return disclosures
