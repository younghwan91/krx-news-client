from __future__ import annotations

import io
import logging
import zipfile
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from krx_news_client import (
    DartAPIError,
    DartQuotaExceededError,
    DartScraper,
    Deduplicator,
    SecretMaskingFilter,
    is_correction,
    mask_secrets,
    quarter_ranges,
)


class TestQuarterRanges:
    def test_splits_year_into_calendar_quarters(self):
        assert quarter_ranges("20260101", "20261231") == [
            ("20260101", "20260331"),
            ("20260401", "20260630"),
            ("20260701", "20260930"),
            ("20261001", "20261231"),
        ]

    def test_month_end_overflow_is_clamped(self):
        # 1/31 + 3개월 = 4/30(말일로 자름) → 하루 전 4/29 까지. 90일 고정 분할은
        # 2월이 낀 구간에서 DART 3개월 제한을 넘었다.
        assert quarter_ranges("20260131", "20260601") == [
            ("20260131", "20260429"),
            ("20260430", "20260601"),
        ]

    def test_single_day(self):
        assert quarter_ranges("20260105", "20260105") == [("20260105", "20260105")]

    def test_empty_when_reversed(self):
        assert quarter_ranges("20260105", "20260101") == []


class TestIsCorrection:
    @pytest.mark.parametrize(
        "title", ["[기재정정]주요사항보고서", "[첨부정정]사업보고서", "[첨부추가]x", "[정정]y"]
    )
    def test_markers(self, title):
        assert is_correction(title)

    def test_plain_title(self):
        assert not is_correction("주요사항보고서(유상증자결정)")
        assert not is_correction("")


class TestFromEnv:
    def test_collects_keys_in_order(self):
        scraper = DartScraper.from_env(env={"DART_API_KEY": "a", "DART_API_KEY_3": " c "})
        assert scraper.api_keys == ["a", "c"]

    def test_raises_without_keys(self):
        with pytest.raises(ValueError):
            DartScraper.from_env(env={})


def _ok(rows, total_page=1):
    return {"status": "000", "message": "정상", "total_page": total_page, "list": rows}


class TestDisclosureFields:
    async def test_scrape_disclosures_keeps_dart_identifiers(self, httpx_mock):
        httpx_mock.add_response(
            json=_ok(
                [
                    {
                        "corp_code": "00125080",
                        "corp_name": "AK홀딩스",
                        "stock_code": "006840",
                        "corp_cls": "Y",
                        "report_nm": "[기재정정]신규시설투자등              ",
                        "rcept_no": "20260915800820",
                        "rcept_dt": "20260915",
                        "rm": "유",
                    }
                ]
            )
        )
        async with DartScraper(api_key="k") as scraper:
            [disc] = await scraper.scrape_disclosures(bgn_de="20260915", end_de="20260915")
        assert disc.rcept_no == "20260915800820"
        assert disc.corp_code == "00125080"
        assert disc.corp_cls == "Y"
        assert disc.rm == "유"
        assert disc.title == "[기재정정]신규시설투자등"
        assert disc.is_correction


class TestSearchDisclosuresRange:
    async def test_loops_spans_and_classes(self, httpx_mock):
        httpx_mock.add_response(json=_ok([{"rcept_no": "x"}]), is_reusable=True)
        async with DartScraper(api_key="k") as scraper:
            rows = await scraper.search_disclosures_range(
                bgn_de="20260101", end_de="20260630", corp_cls=["Y", "K"]
            )
        params = [dict(r.url.params) for r in httpx_mock.get_requests()]
        assert [(p["bgn_de"], p["end_de"], p["corp_cls"]) for p in params] == [
            ("20260101", "20260331", "Y"),
            ("20260101", "20260331", "K"),
            ("20260401", "20260630", "Y"),
            ("20260401", "20260630", "K"),
        ]
        assert len(rows) == 4

    async def test_single_class_string(self, httpx_mock):
        httpx_mock.add_response(json=_ok([]))
        async with DartScraper(api_key="k") as scraper:
            await scraper.search_disclosures_range(
                bgn_de="20260101", end_de="20260105", corp_cls="K"
            )
        assert dict(httpx_mock.get_requests()[0].url.params)["corp_cls"] == "K"


def _zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, body in files.items():
            archive.writestr(name, body.encode())
    return buffer.getvalue()


def _xml_status(status: str, message: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<result><status>{status}</status><message>{message}</message></result>"
    ).encode()


class TestFetchDocument:
    async def test_unzips_and_extracts_text(self, httpx_mock):
        markup = (
            "<html><head><style>.xforms{font-size:10px}</style></head>"
            "<body><table><tr><td>신규시설투자</td><td>1,000억원</td></tr></table></body></html>"
        )
        httpx_mock.add_response(content=_zip({"20260915800820.xml": markup}))
        async with DartScraper(api_key="k") as scraper:
            [doc] = await scraper.fetch_document("20260915800820")
        params = dict(httpx_mock.get_requests()[0].url.params)
        assert params["rcept_no"] == "20260915800820"
        assert doc.filename == "20260915800820.xml"
        assert doc.html == markup
        assert doc.text == "신규시설투자\n1,000억원"

    async def test_unknown_rcept_no_returns_empty(self, httpx_mock):
        httpx_mock.add_response(content=_xml_status("013", "접수번호 오류"))
        async with DartScraper(api_key="k") as scraper:
            assert await scraper.fetch_document("20260101999999") == []

    async def test_quota_rotates_then_raises(self, httpx_mock):
        httpx_mock.add_response(content=_xml_status("020", "초과"), is_reusable=True)
        async with DartScraper(api_key=["k1", "k2"]) as scraper:
            with pytest.raises(DartQuotaExceededError):
                await scraper.fetch_document("1")
        assert len(httpx_mock.get_requests()) == 2

    async def test_other_status_raises(self, httpx_mock):
        httpx_mock.add_response(content=_xml_status("010", "등록되지 않은 인증키입니다."))
        async with DartScraper(api_key="bad") as scraper:
            with pytest.raises(DartAPIError, match="010"):
                await scraper.fetch_document("1")


class TestDeduplicator:
    def test_filters_seen(self):
        dedup = Deduplicator(key=lambda x: x)
        assert dedup.filter_new([1, 2, 2]) == [1, 2]
        assert dedup.filter_new([2, 3]) == [3]
        assert len(dedup) == 3

    def test_bounded_memory_evicts_oldest(self):
        dedup = Deduplicator(key=lambda x: x, max_size=2)
        dedup.filter_new([1, 2, 3])
        assert 1 not in dedup
        assert dedup.filter_new([1]) == [1]

    async def test_disclosures_keyed_by_rcept_no(self, httpx_mock):
        row = {"rcept_no": "r1", "corp_name": "A", "stock_code": "000001", "rcept_dt": "20260915"}
        httpx_mock.add_response(json=_ok([row]), is_reusable=True)
        dedup = Deduplicator()
        async with DartScraper(api_key="k") as scraper:
            first = await scraper.scrape_disclosures(bgn_de="20260915", end_de="20260915")
            second = await scraper.scrape_disclosures(bgn_de="20260915", end_de="20260915")
        assert len(dedup.filter_new(first)) == 1
        assert dedup.filter_new(second) == []


SECRET = "SECRETDARTKEY0123456789abcdef"


class TestKeyNeverLogged:
    """DART 키는 쿼리(``crtfc_key``)로만 보낼 수 있다 -- 그래서 URL 이 찍히는 곳마다 가려야 한다.

    2026-10-18 ``scripts/make_hero.py`` 첫 실행에서 httpx 의 ``HTTP Request: GET …?crtfc_key=…``
    INFO 로그로 키가 터미널에 그대로 노출됐다. 사용자가 ``logging.basicConfig(level=INFO)``
    만 켜도 같은 일이 난다.
    """

    async def test_httpx_request_log_masks_key(self, httpx_mock, caplog):
        caplog.set_level(logging.INFO, logger="httpx")
        httpx_mock.add_response(json=_ok([]))
        async with DartScraper(api_key=SECRET) as scraper:
            await scraper.search_disclosures(bgn_de="20260915", end_de="20260915")
        assert SECRET not in caplog.text
        # 로그 자체는 남아야 한다(레벨을 낮춰 숨기는 식의 우회가 아니다).
        assert "HTTP Request:" in caplog.text
        assert "crtfc_key=***" in caplog.text

    async def test_http_status_error_message_masks_key(self, httpx_mock):
        httpx_mock.add_response(status_code=404)
        async with DartScraper(api_key=SECRET) as scraper:
            with pytest.raises(httpx.HTTPStatusError) as excinfo:
                await scraper.search_disclosures(bgn_de="20260915", end_de="20260915")
        assert SECRET not in str(excinfo.value)
        assert SECRET not in repr(excinfo.value)
        assert "crtfc_key=***" in str(excinfo.value)
        # 호출부가 쓰는 속성은 그대로여야 한다.
        assert excinfo.value.response.status_code == 404

    async def test_lenient_scrape_exception_log_masks_key(self, httpx_mock, caplog):
        caplog.set_level(logging.DEBUG)
        httpx_mock.add_response(status_code=404)
        async with DartScraper(api_key=SECRET) as scraper:
            assert await scraper.scrape_disclosures(bgn_de="20260915", end_de="20260915") == []
        # logger.exception 의 트레이스백(exc_info)까지 포함해 어디에도 없어야 한다.
        assert SECRET not in caplog.text
        assert "DART API request failed" in caplog.text

    async def test_request_error_retry_log_masks_key(self, httpx_mock, caplog):
        caplog.set_level(logging.DEBUG)
        url = f"https://opendart.fss.or.kr/api/list.json?crtfc_key={SECRET}&x=1"
        httpx_mock.add_exception(httpx.ConnectError(f"boom {url}"))
        httpx_mock.add_response(json=_ok([]))
        async with DartScraper(api_key=SECRET) as scraper:
            scraper.max_retries = 2
            with patch("asyncio.sleep", new=AsyncMock()):
                await scraper.search_disclosures(bgn_de="20260915", end_de="20260915")
        assert SECRET not in caplog.text
        assert "retry 1/2" in caplog.text

    def test_filter_installed_once(self):
        DartScraper(api_key="a")
        DartScraper(api_key="b")
        httpx_logger = logging.getLogger("httpx")
        installed = [f for f in httpx_logger.filters if isinstance(f, SecretMaskingFilter)]
        assert len(installed) == 1

    @pytest.mark.parametrize(
        "name", ["httpcore.connection", "httpcore.http11", "httpcore.http2", "httpcore.proxy"]
    )
    def test_httpcore_child_logger_masks_key(self, name, caplog):
        # 로거 필터는 그 로거에서 만든 레코드에만 걸린다 -- 부모 "httpcore" 에 건 필터는
        # httpcore 가 실제로 쓰는 하위 로거의 레코드를 지나친다.
        DartScraper(api_key="a")
        caplog.set_level(logging.DEBUG, logger=name)
        logging.getLogger(name).debug("trace url=%s", f"https://x/list.json?crtfc_key={SECRET}")
        assert SECRET not in caplog.text
        assert "crtfc_key=***" in caplog.text

    def test_every_existing_httpcore_logger_is_masked(self):
        import httpcore  # noqa: F401 - 하위 로거를 만들게 한다

        DartScraper(api_key="a")
        children = [
            n for n in logging.root.manager.loggerDict if n.startswith("httpcore.")
        ]
        assert children, "httpcore 하위 로거가 없다 -- 테스트 전제가 깨졌다"
        for n in children:
            logger = logging.getLogger(n)
            assert any(isinstance(f, SecretMaskingFilter) for f in logger.filters), n

    def test_mask_secrets(self):
        assert mask_secrets(f"https://x/list.json?crtfc_key={SECRET}&bgn_de=1") == (
            "https://x/list.json?crtfc_key=***&bgn_de=1"
        )
        assert mask_secrets(f"url 'https://x/document.xml?crtfc_key={SECRET}'") == (
            "url 'https://x/document.xml?crtfc_key=***'"
        )
        assert mask_secrets("no key here") == "no key here"
