"""``krx-news`` 명령. 설치 없이 ``uvx krx-news-client`` 로도 돈다.

::

    krx-news                          # 연합뉴스 마켓+ 최신 기사 (키 없음)
    krx-news news --ticker 005930     # 관심 종목 기사만
    krx-news watch --ticker 005930    # 새 기사·공시가 뜰 때마다 한 줄씩 (Ctrl+C 로 끝)
    krx-news dart --keyword 유상증자   # 최근 공시 (DART_API_KEY)
    krx-news doc 20261125000001       # 공시 원문 텍스트
    krx-news search 삼성전자           # 네이버 뉴스 검색 (NAVER_CLIENT_ID/SECRET)
    krx-news mcp                      # AI 에이전트용 MCP 서버 (krx-news-client[mcp])

표준 라이브러리 ``argparse`` 만 쓴다 -- 라이브러리 의존성을 늘리지 않는다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence
from typing import TextIO

from krx_news_client.dedup import Deduplicator
from krx_news_client.models.schemas import KST, Disclosure, NewsArticle
from krx_news_client.queries import (
    MARKETS,
    MAX_DAYS,
    disclosure_row,
    disclosure_text,
    recent_disclosures,
    stock_code,
)
from krx_news_client.scrapers.dart import DartAPIError, DartQuotaExceededError, DartScraper
from krx_news_client.scrapers.naver import NaverAPIError, NaverNewsScraper
from krx_news_client.scrapers.yonhap import FEEDS, YonhapFeedError, YonhapScraper

#: 연합뉴스 RSS 를 이보다 자주 부르지 않는다 -- 공개 피드에 예의를 지킨다.
MIN_WATCH_INTERVAL = 30
#: DART 전체 시장 검색은 한 번에 수십 호출이다. 5분 간격이면 하루 한도의 3분의 1 안쪽.
MIN_DART_INTERVAL = 120

_DART_KEY_HELP = (
    "DART_API_KEY 가 없습니다. https://opendart.fss.or.kr/ 에서 무료로 발급해 "
    "`export DART_API_KEY=...` 로 넣으세요."
)


def _version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("krx-news-client")
    except PackageNotFoundError:  # 소스 트리에서 바로 돌릴 때
        return "0+unknown"


class _Style:
    """터미널일 때만 색을 입힌다. ``NO_COLOR`` 를 따른다(https://no-color.org)."""

    def __init__(self, stream: TextIO) -> None:
        self.on = stream.isatty() and not os.environ.get("NO_COLOR")

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.on else text

    def dim(self, text: str) -> str:
        return self._wrap("2", text)

    def bold(self, text: str) -> str:
        return self._wrap("1", text)

    def accent(self, text: str) -> str:
        return self._wrap("36", text)

    def warn(self, text: str) -> str:
        return self._wrap("33", text)


def _article_line(a: NewsArticle, style: _Style) -> str:
    when = a.published_at.astimezone(KST).strftime("%m-%d %H:%M")
    tickers = style.accent(" ".join(a.tickers)) + " " if a.tickers else ""
    return f"{style.dim(when)}  {tickers}{a.title}\n             {style.dim(a.url)}"


def _disclosure_line(d: Disclosure, style: _Style) -> str:
    tag = style.warn("[정정] ") if d.is_correction else ""
    code = style.accent(d.ticker or "------")
    return (
        f"{style.dim(d.published_at.strftime('%m-%d').ljust(11))}  {code} {style.bold(d.company)}  "
        f"{tag}{' '.join(d.title.split())}\n             {style.dim(d.url)}"
    )


def _article_json(a: NewsArticle) -> dict:
    return a.model_dump(mode="json", include={
        "id", "source", "title", "url", "summary", "tickers", "published_at", "original_url",
    })


def _emit_json(rows: list[dict], out: TextIO) -> None:
    json.dump(rows, out, ensure_ascii=False, indent=2)
    out.write("\n")


def _dart_from_env() -> DartScraper:
    try:
        return DartScraper.from_env()
    except ValueError as e:
        raise SystemExit(f"krx-news: {_DART_KEY_HELP}") from e


async def _cmd_news(args: argparse.Namespace, out: TextIO) -> int:
    codes = {stock_code(t) for t in args.ticker}
    async with YonhapScraper() as yna:
        articles = await yna.scrape_news(args.feed or ["market"])
    if codes:
        articles = [a for a in articles if codes & set(a.tickers)]
    articles = articles[: args.limit]
    if args.json:
        _emit_json([_article_json(a) for a in articles], out)
        return 0
    style = _Style(out)
    for a in articles:
        print(_article_line(a, style), file=out)
    if not articles:
        print(style.dim("조건에 맞는 기사가 지금 피드에 없습니다."), file=out)
    print(style.dim("출처: 연합뉴스 RSS (비상업적 개인 용도)"), file=out)
    return 0


async def _cmd_dart(args: argparse.Namespace, out: TextIO) -> int:
    async with _dart_from_env() as dart:
        items = await recent_disclosures(
            dart,
            tickers=args.ticker,
            keyword=args.keyword,
            days=args.days,
            market=args.market,
            include_corrections=args.corrections,
            limit=args.limit,
        )
    if args.json:
        _emit_json([disclosure_row(d) for d in items], out)
        return 0
    style = _Style(out)
    for d in items:
        print(_disclosure_line(d, style), file=out)
    if not items:
        print(style.dim("조건에 맞는 공시가 없습니다."), file=out)
    return 0


async def _cmd_doc(args: argparse.Namespace, out: TextIO) -> int:
    async with _dart_from_env() as dart:
        text = await disclosure_text(dart, args.rcept_no, max_chars=args.max_chars)
    print(text, file=out)
    return 0


async def _cmd_search(args: argparse.Namespace, out: TextIO) -> int:
    tickers = [stock_code(t) for t in args.ticker] or None
    async with NaverNewsScraper.from_env() as naver:
        articles = await naver.search_news(args.query, limit=args.limit, tickers=tickers)
    if args.json:
        _emit_json([_article_json(a) for a in articles], out)
        return 0
    style = _Style(out)
    for a in articles:
        print(_article_line(a, style), file=out)
    print(style.dim("출처: 네이버 검색 API -- 원문 링크를 함께 표시하고 결과를 저장하지 마세요."),
          file=out)
    return 0


async def watch_once(
    yna: YonhapScraper,
    dart: DartScraper | None,
    seen: Deduplicator,
    codes: set[str],
    feeds: Sequence[str],
) -> list[NewsArticle | Disclosure]:
    """한 바퀴: 처음 보는 기사·공시만, 오래된 것부터."""
    found: list[NewsArticle | Disclosure] = []
    for a in seen.filter_new(await yna.scrape_news(feeds)):
        if not codes or codes & set(a.tickers):
            found.append(a)
    if dart is not None:
        # 오늘 것만 -- 폴링마다 어제까지 훑으면 키 하루 한도(2만 건)를 금방 넘긴다.
        disclosures = await recent_disclosures(dart, tickers=sorted(codes), days=0, limit=None)
        found.extend(seen.filter_new(disclosures))
    found.sort(key=lambda x: (x.published_at, getattr(x, "rcept_no", "")))
    return found


async def _cmd_watch(args: argparse.Namespace, out: TextIO) -> int:
    if args.interval < MIN_WATCH_INTERVAL:
        raise SystemExit(f"krx-news: --interval must be at least {MIN_WATCH_INTERVAL} seconds")
    if args.dart_interval < MIN_DART_INTERVAL:
        raise SystemExit(
            f"krx-news: --dart-interval must be at least {MIN_DART_INTERVAL} seconds"
        )
    codes = {stock_code(t) for t in args.ticker}
    style = _Style(out)
    dart = None
    if os.environ.get("DART_API_KEY"):
        dart = DartScraper.from_env()
    seen = Deduplicator()
    target = ", ".join(sorted(codes)) or "전 종목"
    sources = "연합뉴스" + (" + DART 공시" if dart else " (DART_API_KEY 를 넣으면 공시도)")
    print(style.bold(f"krx-news watch: {target} · {sources} · {args.interval}초마다"), file=out)
    async with YonhapScraper() as yna:
        try:
            first, last_dart = True, float("-inf")
            loop = asyncio.get_running_loop()
            while True:
                poll_dart = dart is not None and loop.time() - last_dart >= args.dart_interval
                if poll_dart:
                    last_dart = loop.time()
                items = await watch_once(
                    yna, dart if poll_dart else None, seen, codes, args.feed or ["market"]
                )
                if first and not args.backlog:
                    items = items[-args.limit :]
                for x in items:
                    line = (
                        _disclosure_line(x, style)
                        if isinstance(x, Disclosure)
                        else _article_line(x, style)
                    )
                    print(line, file=out, flush=True)
                first = False
                if args.once:
                    return 0
                await asyncio.sleep(args.interval)
        finally:
            if dart is not None:
                await dart.close()


def _cmd_mcp(args: argparse.Namespace, out: TextIO) -> int:
    from krx_news_client.mcp_server import main as mcp_main

    return mcp_main([])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="krx-news",
        description=(
            "한국 증시 뉴스·DART 공시를 터미널에서. 인자 없이 실행하면 연합뉴스 마켓+ 최신 기사."
        ),
        epilog="예: krx-news watch --ticker 005930 000660   |   krx-news dart --keyword 자기주식",
    )
    parser.add_argument("--version", action="version", version=f"krx-news {_version()}")
    sub = parser.add_subparsers(dest="command")

    def ticker_arg(p: argparse.ArgumentParser) -> None:
        p.add_argument("--ticker", "-t", nargs="+", default=[], metavar="CODE",
                       help="6자리 종목코드(여럿 가능), 예: 005930")

    def common(p: argparse.ArgumentParser, limit: int) -> None:
        p.add_argument("--limit", "-n", type=int, default=limit, help=f"최대 건수 (기본 {limit})")
        p.add_argument("--json", action="store_true", help="JSON 으로 출력")

    news = sub.add_parser("news", help="연합뉴스 최신 기사 (키 없음, 기본 명령)")
    news.add_argument("--feed", "-f", nargs="+", choices=sorted(FEEDS), help="섹션 (기본 market)")
    ticker_arg(news)
    common(news, 20)

    watch = sub.add_parser("watch", help="새 기사·공시를 실시간으로 (Ctrl+C 로 종료)")
    watch.add_argument("--feed", "-f", nargs="+", choices=sorted(FEEDS), help="섹션 (기본 market)")
    ticker_arg(watch)
    watch.add_argument("--interval", "-i", type=int, default=60, help="폴링 간격 초 (기본 60)")
    watch.add_argument("--dart-interval", type=int, default=300,
                       help=f"DART 공시 폴링 간격 초 (기본 300, 최소 {MIN_DART_INTERVAL})")
    watch.add_argument("--limit", "-n", type=int, default=10, help="시작할 때 보여 줄 최근 건수")
    watch.add_argument("--backlog", action="store_true", help="시작할 때 피드 전체를 보여 준다")
    watch.add_argument("--once", action="store_true", help="한 바퀴만 돌고 끝낸다")

    dart = sub.add_parser("dart", help="최근 DART 공시 (DART_API_KEY)")
    ticker_arg(dart)
    dart.add_argument("--keyword", "-k", help="제목 키워드, 예: 유상증자·자기주식·공급계약")
    dart.add_argument("--days", "-d", type=int, default=1,
                      help=f"최근 며칠 (0=오늘만, 최대 {MAX_DAYS}, 기본 1=어제·오늘)")
    dart.add_argument("--market", "-m", choices=sorted(MARKETS), help="시장")
    dart.add_argument("--corrections", action="store_true", help="정정·첨부 공시도 포함")
    common(dart, 30)

    doc = sub.add_parser("doc", help="공시 원문 텍스트 (DART_API_KEY)")
    doc.add_argument("rcept_no", help="14자리 접수번호 (krx-news dart 출력의 URL 끝)")
    doc.add_argument("--max-chars", type=int, default=8000, help="최대 글자 수 (기본 8000)")

    search = sub.add_parser("search", help="네이버 뉴스 검색 (NAVER_CLIENT_ID/SECRET)")
    search.add_argument("query", help="검색어, 예: 삼성전자")
    ticker_arg(search)
    common(search, 20)

    sub.add_parser("mcp", help="AI 에이전트용 MCP 서버 실행 (pip install 'krx-news-client[mcp]')")
    return parser


_COMMANDS = {
    "news": _cmd_news,
    "watch": _cmd_watch,
    "dart": _cmd_dart,
    "doc": _cmd_doc,
    "search": _cmd_search,
}


def main(argv: Sequence[str] | None = None, out: TextIO | None = None) -> int:
    out = out or sys.stdout
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if not argv or argv[0].startswith("-") and argv[0] not in {"-h", "--help", "--version"}:
        argv = ["news", *argv]
    args = parser.parse_args(argv)
    if args.command == "mcp":
        return _cmd_mcp(args, out)
    try:
        return asyncio.run(_COMMANDS[args.command](args, out))
    except KeyboardInterrupt:
        return 130
    except ValueError as e:  # 잘못된 인자·키 없음 -- 트레이스백 대신 한 줄로
        print(f"krx-news: {e}", file=sys.stderr)
        return 2
    except (DartAPIError, DartQuotaExceededError, NaverAPIError, YonhapFeedError) as e:
        # 예: 방금 접수된 공시는 원문이 아직 없어 DART 가 "014 파일이 존재하지 않습니다".
        print(f"krx-news: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

