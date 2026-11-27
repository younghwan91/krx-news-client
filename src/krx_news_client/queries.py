"""CLI 와 MCP 서버가 같이 쓰는 DART 조회 조각.

두 진입점이 같은 필터·정렬·자르기를 쓰도록 여기 한 곳에 둔다. 라이브러리 사용자도
그대로 쓸 수 있다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from krx_news_client.models.schemas import KST, Disclosure
from krx_news_client.scrapers.dart import DartScraper
from krx_news_client.scrapers.toss import normalize_stock_code

#: ``corp_code`` 없는 전체 시장 검색은 하루에도 수십 페이지다. 에이전트가 무심코
#: 한 달치를 부르며 키 한도를 태우지 않게 막는다.
MAX_DAYS = 7

MARKETS = {"kospi": "Y", "kosdaq": "K", "konex": "N", "etc": "E"}


def stock_code(code: str) -> str:
    """``005930``·``A005930`` → ``005930``. 그 밖의 형식은 ``ValueError``(조용한 0건 방지)."""
    normalized = normalize_stock_code(code)
    if not (len(normalized) == 6 and normalized.isalnum()):
        raise ValueError(f"ticker must be a 6-character KRX code like 005930, got {code!r}")
    return normalized


def _market_code(market: str | None) -> str | None:
    if not market:
        return None
    code = MARKETS.get(market.lower(), market.upper())
    if code not in MARKETS.values():
        raise ValueError(f"unknown market {market!r}; choose from {sorted(MARKETS)}")
    return code


async def recent_disclosures(
    dart: DartScraper,
    *,
    tickers: list[str] | None = None,
    keyword: str | None = None,
    days: int = 1,
    market: str | None = None,
    include_corrections: bool = False,
    limit: int | None = 50,
) -> list[Disclosure]:
    """최근 ``days`` 일(오늘 포함, KST) 공시를 걸러 최신 접수 순으로.

    Args:
        tickers: 6자리 종목코드들. 비우면 전 종목.
        keyword: 공시 제목에 들어 있어야 할 말(예: ``"유상증자"``, ``"자기주식"``).
        days: 0 이면 오늘만, 1 이면 어제·오늘(``scrape_disclosures`` 기본과 같음),
            최대 ``MAX_DAYS``. 전체 시장 검색이라 하루에 수십 호출이 든다.
        market: ``kospi``·``kosdaq``·``konex``·``etc`` 또는 DART 코드(Y·K·N·E).
        include_corrections: False 면 정정·첨부 공시를 뺀다.
        limit: 돌려줄 최대 건수. None 이면 전부.
    """
    if not 0 <= days <= MAX_DAYS:
        raise ValueError(f"days must be between 0 and {MAX_DAYS}, got {days}")
    if limit is not None and limit < 1:
        raise ValueError(f"limit must be positive, got {limit}")
    codes = {stock_code(t) for t in tickers or []}
    today = datetime.now(tz=KST)
    items = await dart.scrape_disclosures(
        bgn_de=(today - timedelta(days=days)).strftime("%Y%m%d"),
        end_de=today.strftime("%Y%m%d"),
        corp_cls=_market_code(market),
    )
    picked = [
        d
        for d in items
        if (not codes or d.ticker in codes)
        and (not keyword or keyword in d.title)
        and (include_corrections or not d.is_correction)
    ]
    # rcept_dt 에 시각이 없어 같은 날끼리는 접수번호가 곧 접수 순서다.
    picked.sort(key=lambda d: d.rcept_no, reverse=True)
    return picked if limit is None else picked[:limit]


async def disclosure_text(dart: DartScraper, rcept_no: str, *, max_chars: int = 8000) -> str:
    """접수번호의 원문 파일들을 태그 걷어낸 텍스트 하나로, ``max_chars`` 에서 자른다.

    없는 접수번호면 ``ValueError`` -- 빈 문자열을 "본문 없음"으로 오해하지 않게 한다.
    """
    if not (rcept_no.isdigit() and len(rcept_no) == 14):
        raise ValueError(f"rcept_no must be 14 digits, got {rcept_no!r}")
    if max_chars < 1:
        raise ValueError(f"max_chars must be positive, got {max_chars}")
    documents = await dart.fetch_document(rcept_no)
    if not documents:
        raise ValueError(f"DART has no document for rcept_no {rcept_no}")
    text = "\n\n".join(f"## {doc.filename}\n\n{doc.text}" for doc in documents)
    if len(text) > max_chars:
        omitted = len(text) - max_chars
        text = f"{text[:max_chars]}\n\n[... {omitted:,}자 생략 -- max_chars 를 늘려 더 읽기]"
    return text


def disclosure_row(d: Disclosure) -> dict[str, str | bool]:
    """에이전트·JSON 출력용 납작한 dict. 날짜는 접수일(KST)."""
    return {
        "rcept_no": d.rcept_no,
        "date": d.published_at.date().isoformat(),
        "company": d.company,
        "ticker": d.ticker,
        "title": " ".join(d.title.split()),  # DART 제목 안의 긴 공백 덩어리를 접는다
        "market": d.corp_cls,
        "is_correction": d.is_correction,
        "url": d.url,
    }
