"""AI 에이전트(Claude·Cursor 등)용 MCP 서버 -- DART 공시 전용.

::

    uvx --from 'krx-news-client[mcp]' krx-news-client-mcp

**왜 뉴스 도구가 없나.** 연합뉴스 RSS 는 "AI 학습 및 활용 금지", 네이버 검색 API 약관은
결과를 AI 입력으로 쓰는 것을 금한다(README "뉴스 소스와 이용 조건", 2026-11-26 확인).
MCP 도구 결과는 그대로 LLM 입력이 되므로 두 소스는 여기 넣지 않는다. DART 는 금융감독원
공식 Open API 라 이 제약이 없다.

``mcp`` 패키지는 이 모듈에서만 import 한다 -- 기본 설치(``pip install krx-news-client``)에
의존성을 더하지 않는다.
"""

from __future__ import annotations

import argparse
import functools
import sys
from collections.abc import Sequence

from krx_news_client.queries import (
    MAX_DAYS,
    disclosure_row,
    disclosure_text,
    recent_disclosures,
)
from krx_news_client.scrapers.dart import DartAPIError, DartQuotaExceededError, DartScraper

_INSTRUCTIONS = f"""\
한국 상장사 DART 전자공시를 읽는 도구입니다.
1) recent_disclosures 로 최근 공시를 찾고(종목코드·제목 키워드·시장으로 거름),
2) read_disclosure 에 그 결과의 rcept_no 를 넣어 원문 본문을 읽습니다.
기간은 최대 {MAX_DAYS}일입니다. 전체 시장 검색이라 하루치에도 DART 호출이 수십 번 들므로
종목·키워드를 좁혀 부르세요. 공시 접수일은 KST 날짜이고 시각은 없습니다.
답할 때 공시 URL(dart.fss.or.kr)을 출처로 함께 보여 주세요. 투자 권유는 하지 마세요.
"""

_MISSING_KEY = (
    "DART_API_KEY is not set. Get a free key at https://opendart.fss.or.kr/ and add it to "
    "this server's env in your MCP client config."
)


def build_server(dart_factory=DartScraper.from_env):
    """서버 객체를 만든다. 테스트는 ``dart_factory`` 로 목 스크레이퍼를 넣는다."""
    try:
        from mcp.server.mcpserver import MCPServer
        from mcp.server.mcpserver.exceptions import ToolError
        from mcp_types import ToolAnnotations
    except ImportError as e:  # pragma: no cover - 설치 안내
        raise SystemExit(
            "krx-news-client-mcp needs the mcp extra: pip install 'krx-news-client[mcp]'"
        ) from e

    from krx_news_client.cli import _version

    server = MCPServer(
        name="krx-news-client",
        title="DART 전자공시 (Korean stock filings)",
        instructions=_INSTRUCTIONS,
        website_url="https://github.com/younghwan91/krx-news-client#ai-에이전트mcp",
        version=_version(),
    )
    read_only = ToolAnnotations(readOnlyHint=True, openWorldHint=True, idempotentHint=True)

    def open_dart() -> DartScraper:
        try:
            return dart_factory()
        except ValueError as e:
            raise ToolError(_MISSING_KEY) from e

    def expected_errors(fn):
        """잘못된 인자·DART 오류는 모델이 읽고 고칠 수 있게 메시지째 돌려준다.

        SDK 는 ``ToolError`` 가 아닌 예외의 메시지를 숨긴다("Error executing tool").
        """

        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except (ValueError, DartAPIError, DartQuotaExceededError) as e:
                raise ToolError(str(e)) from e

        return wrapper

    @server.tool(name="recent_disclosures", title="최근 DART 공시 찾기", annotations=read_only)
    @expected_errors
    async def recent_disclosures_tool(
        ticker: str | None = None,
        keyword: str | None = None,
        days: int = 1,
        market: str | None = None,
        include_corrections: bool = False,
        limit: int = 30,
    ) -> list[dict]:
        """Recent Korean DART filings (공시), newest first.

        Args:
            ticker: 6-digit KRX code such as "005930" (Samsung Electronics). Omit for all.
            keyword: Text the filing title must contain, in Korean, e.g. "유상증자" (rights
                offering), "자기주식" (buyback), "공급계약" (supply contract), "배당" (dividend).
            days: 0 = today only, 1 = yesterday and today (default), up to 7.
            market: "kospi", "kosdaq", "konex" or "etc".
            include_corrections: Include amended (정정) filings.
            limit: Maximum rows, default 30.

        Each row has rcept_no; pass it to read_disclosure for the full text.
        """
        async with open_dart() as dart:
            items = await recent_disclosures(
                dart,
                tickers=[ticker] if ticker else None,
                keyword=keyword,
                days=days,
                market=market,
                include_corrections=include_corrections,
                limit=limit,
            )
        return [disclosure_row(d) for d in items]

    @server.tool(title="공시 원문 읽기", annotations=read_only)
    @expected_errors
    async def read_disclosure(rcept_no: str, max_chars: int = 8000) -> str:
        """Full text of one DART filing, tags stripped, truncated at max_chars.

        Args:
            rcept_no: 14-digit receipt number from recent_disclosures (or the end of a
                dart.fss.or.kr URL).
            max_chars: Maximum characters to return (default 8000). Raise it to read on.
        """
        async with open_dart() as dart:
            return await disclosure_text(dart, rcept_no, max_chars=max_chars)

    @server.prompt(title="종목 공시 브리핑")
    def disclosure_briefing(ticker: str, days: str = "7") -> str:
        """한 종목의 최근 공시를 찾아 원문을 읽고 브리핑한다."""
        return (
            f"recent_disclosures(ticker={ticker!r}, days={days}) 로 공시를 찾고, 정정이 아닌 "
            "주요 공시 3건까지 read_disclosure 로 원문을 읽어 무엇이 결정됐는지(금액·일정·상대방) "
            "한 건에 세 줄로 정리해 줘. 각 공시 URL 을 붙이고, 투자 판단은 하지 마."
        )

    return server


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="krx-news-client-mcp",
        description="DART 공시를 AI 에이전트에 주는 MCP 서버 (stdio). DART_API_KEY 가 필요합니다.",
        epilog=(
            "Claude Code: claude mcp add krx-news -e DART_API_KEY=... -- "
            "uvx --from 'krx-news-client[mcp]' krx-news-client-mcp"
        ),
    )
    parser.add_argument("--version", action="store_true", help="버전을 찍고 끝낸다")
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    if args.version:
        from krx_news_client.cli import _version

        print(f"krx-news-client-mcp {_version()}")
        return 0
    build_server().run("stdio")
    return 0


__all__ = ["build_server", "main"]


if __name__ == "__main__":
    sys.exit(main())
