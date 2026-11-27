"""README 의 빠른 시작·예제 갤러리 코드 조각을 목 응답으로 실제로 실행한다.

README 예제가 API 이름·인자가 바뀐 뒤에도 그대로 남아 깨지는 것을 막는다. 조각은
Jupyter 처럼 최상위 ``await`` 를 쓰므로 ``PyCF_ALLOW_TOP_LEVEL_AWAIT`` 로 컴파일한다.
"""

from __future__ import annotations

import ast
import io
import json
import re
import zipfile
from datetime import date
from pathlib import Path

import httpx
import pytest

from krx_news_client import DartScraper, Deduplicator, NaverNewsScraper, YonhapScraper
from krx_news_client.scrapers.base import BaseScraper

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
READMES = ["README.md", "README.en.md"]
FENCE = re.compile(r"```python\n(.*?)```", re.S)


def _blocks(text: str) -> list[str]:
    return FENCE.findall(text)


def _gallery(name: str) -> list[str]:
    text = (ROOT / name).read_text(encoding="utf-8")
    start, end = text.index("<!-- gallery:start -->"), text.index("<!-- gallery:end -->")
    return _blocks(text[start:end])


def _quick_start(name: str) -> str:
    return _blocks((ROOT / name).read_text(encoding="utf-8"))[0]


GALLERY = [(name, i, code) for name in READMES for i, code in enumerate(_gallery(name))]


def _dart_rows():
    def row(no, corp, code, title):
        return {
            "corp_code": "00126380", "corp_name": corp, "stock_code": code, "corp_cls": "Y",
            "report_nm": title, "rcept_no": no, "rcept_dt": "20261125", "rm": "",
        }

    return [
        row("20261125000001", "삼성전자", "005930", "[기재정정]주요사항보고서"),
        row("20261125000002", "삼성전자", "005930", "현금ㆍ현물배당결정"),
        row("20261125000003", "SK하이닉스", "000660", "단일판매ㆍ공급계약체결"),
    ]


def _zip(name: str, body: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, body.encode())
    return buffer.getvalue()


def _naver_search(request: httpx.Request) -> httpx.Response:
    payload = json.loads((FIXTURES / "naver_news.json").read_text(encoding="utf-8"))
    start = int(request.url.params["start"])
    display = int(request.url.params["display"])
    items = payload["items"][start - 1 : start - 1 + display]
    return httpx.Response(200, json={**payload, "items": items})


@pytest.fixture
def mocked_sources(httpx_mock, monkeypatch):
    for cls in (BaseScraper, YonhapScraper, NaverNewsScraper):
        monkeypatch.setattr(cls, "min_delay", 0)
        monkeypatch.setattr(cls, "max_delay", 0)
    monkeypatch.setenv("DART_API_KEY", "test-key")
    monkeypatch.setenv("NAVER_CLIENT_ID", "test-id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "test-secret")
    httpx_mock.add_response(
        url=re.compile(r"https://opendart\.fss\.or\.kr/api/list\.json.*"),
        json={"status": "000", "message": "정상", "total_page": 1, "list": _dart_rows()},
        is_reusable=True,
        is_optional=True,
    )
    httpx_mock.add_response(
        url=re.compile(r"https://opendart\.fss\.or\.kr/api/document\.xml.*"),
        content=_zip("doc.xml", "<html><body><p>배당 결정</p></body></html>"),
        is_reusable=True,
        is_optional=True,
    )
    httpx_mock.add_response(
        url=re.compile(r"https://www\.yna\.co\.kr/rss/[a-z]+\.xml"),
        content=(FIXTURES / "yonhap_market.xml").read_bytes(),
        is_reusable=True,
        is_optional=True,
    )
    httpx_mock.add_callback(
        _naver_search,
        url=re.compile(r"https://openapi\.naver\.com/v1/search/news\.json.*"),
        is_reusable=True,
        is_optional=True,
    )
    return httpx_mock


async def _run(code: str, namespace: dict) -> None:
    compiled = compile(code, "<readme>", "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
    result = eval(compiled, namespace)  # noqa: S307 -- README 코드 조각 실행이 목적
    if result is not None:
        await result


def test_gallery_found():
    # 갤러리 표식이 사라지면 아래 테스트가 0건으로 조용히 통과한다.
    for name in READMES:
        assert len(_gallery(name)) >= 3, name


def test_gallery_matches_across_languages():
    # 한/영 README 의 코드가 갈라지지 않게 -- 주석만 다를 수 있다.
    def strip(code: str) -> list[str]:
        return [re.sub(r"\s+#.*$", "", line) for line in code.splitlines()]

    ko, en = _gallery("README.md"), _gallery("README.en.md")
    assert len(ko) == len(en)
    for a, b in zip(ko, en, strict=True):
        assert [re.sub(r'f?"[^"]*"', '""', x) for x in strip(a)] == [
            re.sub(r'f?"[^"]*"', '""', x) for x in strip(b)
        ]


@pytest.mark.parametrize(("name", "index", "code"), GALLERY, ids=lambda v: str(v)[:20])
async def test_gallery_snippet_runs(mocked_sources, capsys, name, index, code):
    async with (
        DartScraper.from_env() as dart,
        YonhapScraper() as yna,
        NaverNewsScraper.from_env() as naver,
    ):
        namespace = {
            "dart": dart, "yna": yna, "naver": naver, "date": date,
            "Deduplicator": Deduplicator,
        }
        await _run(code, namespace)
    if "print(" in code:
        assert capsys.readouterr().out.strip(), f"{name} snippet {index} printed nothing"
    if "prompt" in namespace:
        assert "배당 결정" in namespace["prompt"]


@pytest.mark.parametrize("name", READMES)
async def test_quick_start_runs(mocked_sources, capsys, name):
    await _run(_quick_start(name), {})
    out = capsys.readouterr().out
    assert "KS인더스트리" in out and "['101000']" in out
