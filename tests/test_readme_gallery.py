"""README 의 빠른 시작·예제 갤러리 코드 조각을 목 응답으로 실제로 실행한다.

README 예제가 API 이름·인자가 바뀐 뒤에도 그대로 남아 깨지는 것을 막는다. 조각은
Jupyter 처럼 최상위 ``await`` 를 쓰므로 ``PyCF_ALLOW_TOP_LEVEL_AWAIT`` 로 컴파일한다.
"""

from __future__ import annotations

import ast
import io
import re
import zipfile
from datetime import date
from pathlib import Path

import httpx
import pytest

from krx_news_client import DartScraper, Deduplicator, TossScraper
from krx_news_client.scrapers.base import BaseScraper

ROOT = Path(__file__).resolve().parent.parent
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


def _toss_company(request: httpx.Request) -> httpx.Response:
    items = [
        {
            "id": f"yna_{n}",
            "title": f"삼성전자 기사 {n}",
            "summary": "요약",
            "contentText": "본문 앞부분",
            "source": {"code": "yna", "name": "연합뉴스"},
            "stockCodes": ["A005930"],
            "createdAt": f"2026-11-2{n}T10:00:00",
        }
        for n in (5, 4, 3)
    ]
    page = int(request.url.params["number"])
    size = int(request.url.params["size"])
    body = items[:size] if page == 1 else []
    return httpx.Response(200, json={"result": {"body": body, "lastPage": page > 1}})


def _toss_detail(request: httpx.Request) -> httpx.Response:
    news_id = request.url.path.rsplit("/", 1)[-1]
    detail = {
        "id": news_id,
        "title": "삼성전자 기사",
        "summarySentences": ["요약."],
        "content": [{"type": "text", "content": "본문 전체."}],
        "source": {"code": "yna", "name": "연합뉴스"},
        "stockCodes": ["A005930"],
        "createdAt": "2026-11-25T10:00:00",
    }
    return httpx.Response(200, json={"result": {"kr": detail}})


@pytest.fixture
def mocked_sources(httpx_mock, monkeypatch):
    for cls in (BaseScraper, TossScraper):
        monkeypatch.setattr(cls, "min_delay", 0)
        monkeypatch.setattr(cls, "max_delay", 0)
    monkeypatch.setenv("DART_API_KEY", "test-key")
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
    httpx_mock.add_callback(
        _toss_company,
        url=re.compile(r"https://wts-info-api\.tossinvest\.com/api/v2/news/companies/.*"),
        is_reusable=True,
        is_optional=True,
    )
    httpx_mock.add_callback(
        _toss_detail,
        url=re.compile(r"https://wts-info-api\.tossinvest\.com/api/v2/news/[^/]+$"),
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
    async with DartScraper.from_env() as dart, TossScraper() as toss:
        namespace = {
            "dart": dart, "toss": toss, "date": date, "Deduplicator": Deduplicator,
        }
        await _run(code, namespace)
    if "print(" in code:
        assert capsys.readouterr().out.strip(), f"{name} snippet {index} printed nothing"
    if "prompt" in namespace:
        assert "본문 전체." in namespace["prompt"]


@pytest.mark.parametrize("name", READMES)
async def test_quick_start_runs(mocked_sources, capsys, name):
    await _run(_quick_start(name), {})
    out = capsys.readouterr().out
    assert "삼성전자" in out
