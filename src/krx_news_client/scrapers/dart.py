from __future__ import annotations

import calendar
import io
import logging
import os
import re
import zipfile
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from typing import Any

from bs4 import BeautifulSoup

from krx_news_client.models.schemas import (
    KST,
    Disclosure,
    DisclosureDocument,
    NewsArticle,
    NewsSource,
    is_correction,
)
from krx_news_client.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

DETAIL_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcept_no={rcept_no}"

#: ``from_env`` 가 순서대로 읽는 환경변수(scalp-it ``adapters/dart.py`` 와 같은 이름).
DEFAULT_KEY_ENV = ("DART_API_KEY", "DART_API_KEY_2", "DART_API_KEY_3")

#: ``corp_code`` 없이 list.json 을 부르면 검색기간이 **달력 3개월**로 제한된다
#: (``100 corp_code가 없는 경우 검색기간은 3개월만 가능합니다``). 90일 고정으로
#: 자르면 2월이 낀 구간에서 이 오류가 난다.
MAX_SPAN_MONTHS = 3

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


def _add_months(day: date, months: int) -> date:
    """달력 월 더하기. 말일 넘침(1/31 + 1개월)은 그 달 말일로 자른다."""
    month_index = day.month - 1 + months
    year, month = day.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def quarter_ranges(start: str, end: str) -> list[tuple[str, str]]:
    """``[start, end]``(``YYYYMMDD``)를 **달력 3개월 이하** 구간들로 쪼갠다.

    DART 가 ``corp_code`` 없는 검색을 3개월로 제한하므로 여러 해 백필은 이렇게
    나눠 불러야 한다(scalp-it ``cli_dart.py`` 에서 옮김, pandas 의존 제거).
    """
    cursor = datetime.strptime(start, "%Y%m%d").date()
    finish = datetime.strptime(end, "%Y%m%d").date()
    ranges: list[tuple[str, str]] = []
    while cursor <= finish:
        stop = min(_add_months(cursor, MAX_SPAN_MONTHS) - timedelta(days=1), finish)
        ranges.append((cursor.strftime("%Y%m%d"), stop.strftime("%Y%m%d")))
        cursor = stop + timedelta(days=1)
    return ranges


def _html_to_text(markup: str) -> str:
    soup = BeautifulSoup(markup, "lxml")
    for tag in soup(["style", "script", "head"]):
        tag.decompose()
    text = soup.get_text("\n")
    lines = (re.sub(r"[ \t\u00a0]+", " ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def _decode(raw: bytes) -> str:
    # 원문 meta 는 euc-kr 이라고 적혀 있어도 실제 바이트는 UTF-8 인 경우가 많다.
    for encoding in ("utf-8", "cp949"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


class DartScraper(BaseScraper):
    source = NewsSource.DART
    base_url = "https://opendart.fss.or.kr/api"

    #: BaseScraper's 0.5-2.0s randomized delay exists to be polite to Toss's
    #: unofficial dashboard scrape. DART is an official, keyed API whose only
    #: real constraint is the daily quota (enforced server-side via status
    #: 020, handled by key rotation above) -- inheriting Toss's throttle here
    #: would make a multi-year backfill (tens of thousands of calls) take
    #: hours instead of minutes for no correctness benefit. A caller wanting
    #: to be gentler can still pass ``sleep`` at the call site (scalp-it's
    #: former adapter did, at 0.05s).
    min_delay: float = 0.0
    max_delay: float = 0.0

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

    @classmethod
    def from_env(
        cls,
        names: Sequence[str] = DEFAULT_KEY_ENV,
        env: Mapping[str, str] | None = None,
    ) -> DartScraper:
        """환경변수(기본 ``DART_API_KEY``, ``_2``, ``_3``)에서 키를 모아 만든다.

        설정된 키가 하나도 없으면 ``ValueError`` -- 키 없이 조용히 빈 결과를
        내는 스크레이퍼를 만들지 않는다.
        """
        source = os.environ if env is None else env
        keys = [str(source.get(name) or "").strip() for name in names]
        keys = [k for k in keys if k]
        if not keys:
            raise ValueError(f"DART API key not configured (checked: {', '.join(names)})")
        return cls(keys)

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
        해에 걸친 백필은 구간을 쪼개야 한다 -- ``search_disclosures_range``를
        쓰면 ``quarter_ranges``로 알아서 나눈다.
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

    async def search_disclosures_range(
        self,
        *,
        bgn_de: str,
        end_de: str,
        corp_cls: str | Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        """3개월 제한을 넘는 기간도 한 번에. ``quarter_ranges`` × ``corp_cls`` 로 돈다.

        Args:
            corp_cls: 하나(``"Y"``), 여럿(``["Y", "K"]``), 또는 None(전체 시장).

        엄격 경로다(``search_disclosures`` 와 같은 예외). 중간에 한도가 다 차면
        ``DartQuotaExceededError`` 로 멈추므로, 이어받으려면 호출부가 구간 단위로
        진행 상황을 기록할 것.
        """
        classes: list[str | None]
        if corp_cls is None or isinstance(corp_cls, str):
            classes = [corp_cls]
        else:
            classes = list(corp_cls)
        rows: list[dict[str, Any]] = []
        for bgn, stop in quarter_ranges(bgn_de, end_de):
            for cls_ in classes:
                rows.extend(
                    await self.search_disclosures_all(bgn_de=bgn, end_de=stop, corp_cls=cls_)
                )
        return rows

    async def fetch_document(self, rcept_no: str) -> list[DisclosureDocument]:
        """공시 원문(``document.xml``). 접수번호 하나에 파일이 여럿일 수 있다.

        DART 는 성공 시 zip 을, 실패 시 ``<result><status>`` XML 을 준다. 없는
        접수번호(013)는 빈 리스트, 한도 초과(020)는 다음 키로 넘기고, 그 외
        상태는 ``DartAPIError``.
        """
        if not self.api_keys:
            raise DartQuotaExceededError("no DART API key configured")

        last_message = ""
        for _ in range(len(self.api_keys)):
            resp = await self.fetch(
                f"{self.base_url}/document.xml",
                params={"crtfc_key": self._next_key(), "rcept_no": rcept_no},
            )
            content = resp.content
            if content[:2] == b"PK":
                return self._unzip_document(rcept_no, content)
            status_match = re.search(rb"<status>(\d+)</status>", content)
            message_match = re.search(rb"<message>(.*?)</message>", content, re.S)
            status = status_match.group(1).decode() if status_match else "?"
            message = _decode(message_match.group(1)) if message_match else ""
            last_message = f"{status} {message}"
            if status == _NO_DATA:
                return []
            if status != QUOTA_EXHAUSTED_STATUS:
                raise DartAPIError(f"DART document error: {last_message}")
        raise DartQuotaExceededError(
            f"all {len(self.api_keys)} configured DART key(s) exhausted daily quota: {last_message}"
        )

    @staticmethod
    def _unzip_document(rcept_no: str, content: bytes) -> list[DisclosureDocument]:
        documents: list[DisclosureDocument] = []
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                markup = _decode(archive.read(info))
                documents.append(
                    DisclosureDocument(
                        rcept_no=rcept_no,
                        filename=info.filename,
                        html=markup,
                        text=_html_to_text(markup),
                    )
                )
        return documents

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

            # report_nm 뒤에 공백이 줄줄이 붙어 오는 경우가 있다.
            report_nm = str(item.get("report_nm") or "").strip()
            disclosures.append(
                self._make_disclosure(
                    title=report_nm,
                    url=url,
                    company=item.get("corp_name", ""),
                    ticker=item.get("stock_code", ""),
                    disclosure_type=report_nm,
                    published_at=published_at,
                    rcept_no=rcept_no,
                    corp_code=item.get("corp_code") or "",
                    corp_cls=item.get("corp_cls") or "",
                    rm=item.get("rm") or "",
                    is_correction=is_correction(report_nm),
                )
            )

        logger.info("DART: collected %d disclosures (%s ~ %s)", len(disclosures), bgn_de, end_de)
        return disclosures
