"""``krx-news`` CLI·``queries``·MCP 서버를 목 응답으로 돌린다."""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

import pytest

from krx_news_client import DartScraper, Deduplicator, YonhapScraper
from krx_news_client.cli import main, watch_once
from krx_news_client.queries import disclosure_text, recent_disclosures, stock_code
from krx_news_client.scrapers.base import BaseScraper

FIXTURES = Path(__file__).resolve().parent / "fixtures"
LIST_URL = re.compile(r"https://opendart\.fss\.or\.kr/api/list\.json.*")
DOC_URL = re.compile(r"https://opendart\.fss\.or\.kr/api/document\.xml.*")
YNA_URL = re.compile(r"https://www\.yna\.co\.kr/rss/[a-z]+\.xml")


def _row(no, corp, code, title, cls="Y"):
    return {
        "corp_code": "00126380", "corp_name": corp, "stock_code": code, "corp_cls": cls,
        "report_nm": title, "rcept_no": no, "rcept_dt": "20261126", "rm": "",
    }


ROWS = [
    _row("20261126000001", "삼성전자", "005930", "[기재정정]주요사항보고서(자기주식취득결정)"),
    _row("20261126000003", "삼성전자", "005930", "주요사항보고서(자기주식취득결정)"),
    _row("20261126000002", "SK하이닉스", "000660", "단일판매ㆍ공급계약체결"),
    _row("20261126000004", "KS인더스트리", "101000", "주요사항보고서(유상증자결정)   (정정)", "K"),
]


def _zip(name: str, body: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, body.encode())
    return buffer.getvalue()


@pytest.fixture
def sources(httpx_mock, monkeypatch):
    for cls in (BaseScraper, YonhapScraper):
        monkeypatch.setattr(cls, "min_delay", 0)
        monkeypatch.setattr(cls, "max_delay", 0)
    monkeypatch.setenv("DART_API_KEY", "test-key")
    monkeypatch.setenv("NO_COLOR", "1")
    httpx_mock.add_response(
        url=LIST_URL,
        json={"status": "000", "message": "정상", "total_page": 1, "list": ROWS},
        is_reusable=True, is_optional=True,
    )
    httpx_mock.add_response(
        url=DOC_URL,
        content=_zip("20261126000003.xml", "<html><body><p>자기주식 100,000주 취득</p></body>"),
        is_reusable=True, is_optional=True,
    )
    httpx_mock.add_response(
        url=YNA_URL, content=(FIXTURES / "yonhap_market.xml").read_bytes(),
        is_reusable=True, is_optional=True,
    )
    return httpx_mock


def _run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, out=out)
    return code, out.getvalue()


# --- queries -----------------------------------------------------------------


async def test_recent_disclosures_filters_and_sorts(sources):
    async with DartScraper("k") as dart:
        rows = await recent_disclosures(dart, keyword="자기주식")
        assert [d.rcept_no for d in rows] == ["20261126000003"]  # 정정은 기본으로 뺀다
        rows = await recent_disclosures(dart, include_corrections=True)
        assert [d.rcept_no for d in rows] == [  # 접수번호 역순 = 최신 먼저
            "20261126000004", "20261126000003", "20261126000002", "20261126000001",
        ]
        rows = await recent_disclosures(dart, tickers=["A000660"])
        assert [d.ticker for d in rows] == ["000660"]


async def test_recent_disclosures_sends_market_code(sources):
    async with DartScraper("k") as dart:
        await recent_disclosures(dart, market="kosdaq", days=0)
    request = sources.get_requests(url=LIST_URL)[-1]
    assert request.url.params["corp_cls"] == "K"
    assert request.url.params["bgn_de"] == request.url.params["end_de"]  # days=0 = 오늘만


@pytest.mark.parametrize(
    "kwargs",
    [{"days": 8}, {"days": -1}, {"limit": 0}, {"market": "nasdaq"}, {"tickers": ["5930"]}],
)
async def test_recent_disclosures_rejects_bad_arguments_before_request(httpx_mock, kwargs):
    async with DartScraper("k") as dart:
        with pytest.raises(ValueError):
            await recent_disclosures(dart, **kwargs)
    assert not httpx_mock.get_requests()


async def test_disclosure_text_truncates(sources):
    async with DartScraper("k") as dart:
        full = await disclosure_text(dart, "20261126000003")
        assert "자기주식 100,000주 취득" in full
        short = await disclosure_text(dart, "20261126000003", max_chars=10)
    assert short.startswith(full[:10]) and "자 생략" in short


async def test_disclosure_text_missing_document_raises(httpx_mock):
    httpx_mock.add_response(
        url=DOC_URL, content=b"<result><status>013</status><message>no</message></result>"
    )
    async with DartScraper("k") as dart:
        with pytest.raises(ValueError, match="no document"):
            await disclosure_text(dart, "20261126000009")


@pytest.mark.parametrize("bad", ["123", "2026112600000a", ""])
async def test_disclosure_text_rejects_bad_rcept_no(httpx_mock, bad):
    async with DartScraper("k") as dart:
        with pytest.raises(ValueError):
            await disclosure_text(dart, bad)
    assert not httpx_mock.get_requests()


def test_stock_code():
    assert stock_code("A005930") == "005930"
    assert stock_code("0193K0") == "0193K0"
    with pytest.raises(ValueError):
        stock_code("AAPL")


# --- CLI ---------------------------------------------------------------------


def test_cli_without_arguments_prints_yonhap_market(sources):
    code, out = _run([])
    assert code == 0
    assert "KS인더스트리" in out and "연합뉴스 RSS" in out
    assert "/rss/market.xml" in str(sources.get_requests(url=YNA_URL)[0].url)


def test_cli_news_ticker_filter_and_json(sources):
    code, out = _run(["news", "--ticker", "101000", "--json"])
    rows = json.loads(out)
    assert code == 0 and len(rows) == 1 and rows[0]["tickers"] == ["101000"]


def test_cli_dart_json(sources):
    code, out = _run(["dart", "--keyword", "공급계약", "--json"])
    assert code == 0
    assert json.loads(out) == [{
        "rcept_no": "20261126000002", "date": "2026-11-26", "company": "SK하이닉스",
        "ticker": "000660", "title": "단일판매ㆍ공급계약체결", "market": "Y",
        "is_correction": False,
        "url": "https://dart.fss.or.kr/dsaf001/main.do?rcept_no=20261126000002",
    }]


def test_cli_dart_collapses_title_whitespace(sources):
    _, out = _run(["dart", "--corrections", "--ticker", "101000"])
    assert "주요사항보고서(유상증자결정) (정정)" in out


def test_cli_doc(sources):
    code, out = _run(["doc", "20261126000003"])
    assert code == 0 and "자기주식 100,000주 취득" in out


def test_cli_dart_without_key_explains(monkeypatch):
    for name in ("DART_API_KEY", "DART_API_KEY_2", "DART_API_KEY_3"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SystemExit, match="opendart.fss.or.kr"):
        main(["dart"], out=io.StringIO())


def test_cli_bad_ticker_is_one_line_error(capsys):
    assert main(["news", "--ticker", "12"], out=io.StringIO()) == 2
    assert "6-character" in capsys.readouterr().err


def test_cli_dart_api_error_is_one_line(httpx_mock, monkeypatch, capsys):
    monkeypatch.setenv("DART_API_KEY", "k")
    httpx_mock.add_response(
        url=DOC_URL, content=b"<result><status>014</status><message>no file</message></result>"
    )
    assert main(["doc", "20261126000003"], out=io.StringIO()) == 1
    assert "014" in capsys.readouterr().err


def test_cli_watch_once_shows_news_and_disclosures(sources):
    code, out = _run(["watch", "--once", "--ticker", "005930", "101000"])
    assert code == 0
    assert "KS인더스트리" in out and "자기주식취득결정" in out
    assert "[기재정정]" not in out


@pytest.mark.parametrize("argv", [["watch", "-i", "5"], ["watch", "--dart-interval", "10"]])
def test_cli_watch_refuses_aggressive_polling(argv):
    with pytest.raises(SystemExit):
        main(argv, out=io.StringIO())


async def test_watch_once_only_returns_new_items(sources):
    seen = Deduplicator()
    async with YonhapScraper() as yna, DartScraper("k") as dart:
        first = await watch_once(yna, dart, seen, set(), ["market"])
        again = await watch_once(yna, dart, seen, set(), ["market"])
    assert first and again == []


# --- MCP ---------------------------------------------------------------------


@pytest.fixture
def server():
    pytest.importorskip("mcp")
    from krx_news_client.mcp_server import build_server

    return build_server(lambda: DartScraper("k"))


async def test_mcp_lists_only_dart_tools(server):
    tools = {t.name: t for t in await server.list_tools()}
    assert set(tools) == {"recent_disclosures", "read_disclosure"}
    assert all(t.annotations.read_only_hint for t in tools.values())


def _payload(result):
    assert not result.is_error, result
    return result.structured_content


async def test_mcp_recent_and_read(server, sources):
    rows = _payload(
        await server.call_tool("recent_disclosures", {"ticker": "005930", "keyword": "자기주식"})
    )
    rows = rows.get("result", rows)
    assert [r["rcept_no"] for r in rows] == ["20261126000003"]
    text = _payload(await server.call_tool("read_disclosure", {"rcept_no": rows[0]["rcept_no"]}))
    assert "100,000주" in json.dumps(text, ensure_ascii=False)


async def test_mcp_missing_key_explains():
    pytest.importorskip("mcp")
    from krx_news_client.mcp_server import build_server

    def no_key():
        raise ValueError("DART API key not configured")

    server = build_server(no_key)
    try:
        result = await server.call_tool("recent_disclosures", {})
    except Exception as e:  # noqa: BLE001 -- SDK 버전에 따라 오류 결과 또는 예외
        message = str(e)
    else:
        assert result.is_error
        message = json.dumps(result.model_dump(mode="json"), ensure_ascii=False)
    assert "opendart.fss.or.kr" in message


async def test_mcp_has_briefing_prompt(server):
    prompts = await server.list_prompts()
    assert [p.name for p in prompts] == ["disclosure_briefing"]


# --- 문서·메타데이터가 코드와 어긋나지 않게 --------------------------------------

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("readme", ["README.md", "README.en.md"])
def test_readme_cli_commands_parse(readme):
    from krx_news_client.cli import build_parser

    text = (ROOT / readme).read_text(encoding="utf-8")
    commands = re.findall(r"`krx-news ([^`]*)`", text)
    commands += re.findall(r"^uvx krx-news-client ?([^#\n]*)", text, re.M)
    assert len(commands) >= 5
    parser = build_parser()
    for command in commands:
        argv = command.replace("(news)", "").split()
        if argv and not argv[0].startswith("-"):
            parser.parse_args(argv)  # 없는 하위 명령·옵션이면 SystemExit


def test_server_json_matches_package():
    import tomllib

    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    server = json.loads((ROOT / "server.json").read_text())
    package = server["packages"][0]
    assert server["version"] == package["version"] == version
    assert package["runtimeArguments"][0]["value"] == f"krx-news-client[mcp]=={version}"
    # uvx --from krx-news-client[mcp] krx-news-client mcp -> MCP 서버
    assert [a["value"] for a in package["packageArguments"]] == ["mcp"]


def test_readme_carries_mcp_registry_name():
    # MCP 레지스트리는 PyPI README 에서 이 줄을 찾아 패키지 소유를 확인한다.
    name = json.loads((ROOT / "server.json").read_text())["name"]
    assert f"mcp-name: {name}" in (ROOT / "README.md").read_text(encoding="utf-8")
