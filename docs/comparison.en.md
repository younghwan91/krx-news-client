# Compared with other approaches: calling OpenDART directly · scraping Naver Finance · pykrx/FinanceDataReader

There are several ways to get Korean stock news and disclosures from code. This page lists what each one covers and what krx-news-client adds on top. Statements about other tools follow their own official docs; the date checked and the sources are given (checked 2026-11-26).

[한국어](comparison.md) · [README](../README.en.md)

## At a glance

| | OpenDART directly | Naver | pykrx | FinanceDataReader | krx-news-client |
|---|---|---|---|---|---|
| Disclosure list | ✅ official API | — | — | — | ✅ wraps OpenDART |
| Disclosure document | ✅ `document.xml` (zip) | — | — | — | ✅ unzipped, plus plain text |
| News headline/summary | — | ✅ Search API (keyword) | — | — | ✅ Toss Securities feed |
| Full article body | — | Search API returns a summary | — | — | ✅ Toss article detail |
| News by ticker | — | keyword search | — | — | ✅ per-ticker news paging |
| Prices, market cap, PER/PBR | — | — | ✅ | ✅ | — (out of scope) |
| Key/account | API key | Search API: Client ID/Secret | some APIs need a KRX member account | depends on source | API key for DART only |
| Returns | raw JSON | raw JSON | pandas DataFrame | pandas DataFrame | Pydantic models |

In short, pykrx and FinanceDataReader are **price and indicator** tools, and OpenDART and the Naver Search API are **source APIs**. krx-news-client sits between them as a **thin client that puts disclosures and news into the same models**. For prices or financials, use pykrx, FinanceDataReader or [krx-fundamentals-client](https://github.com/younghwan91/krx-fundamentals-client) alongside it.

## Calling OpenDART directly

The official Open API of Korea's Financial Supervisory Service. It has six groups: disclosure information, periodic-report key information, periodic-report financial information, ownership disclosures, major-matters reports, and securities registration statements.

- Needs a 40-character API key (`crtfc_key`).
- Disclosure search (`list.json`) returns at most 100 rows per page (`page_count`), and without `corp_code` the search period is limited to 3 months.
- Over the limit it returns status `020`; the docs say this is "generally 20,000 requests or more". No results is `013`.
- The receipt date `rcept_dt` is a date (YYYYMMDD) with no time.

Sources: [OpenDART disclosure search guide](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019001), [OpenDART intro](https://opendart.fss.or.kr/intro/main.do)

**What krx-news-client adds**

- Walks every page and returns `Disclosure` models (`scrape_disclosures`), timestamps as tz-aware KST `datetime` (receipt date at 00:00 KST).
- `search_disclosures_range` splits a multi-year backfill into calendar quarters to stay within the 3-month limit.
- With several keys it moves to the next key on `020`, and raises `DartQuotaExceededError` when all are spent, so "no disclosures (013)" and "quota exceeded (020)" stay distinct.
- `fetch_document` unzips the document and returns the markup plus tag-free text.
- Correction flag (`is_correction`), de-duplication by receipt number (`Deduplicator`), and API-key masking in logs.

**When calling it directly is better**: when you need APIs beyond disclosure search (financial statements, ownership disclosures), or want to search one company by `corp_code`. krx-news-client covers disclosure search and documents only, and per-ticker disclosures are fetched market-wide then filtered by `ticker`.

### Code: one day of disclosures

Calling OpenDART with `httpx`:

```python
import httpx

params = {"crtfc_key": KEY, "bgn_de": "20261125", "end_de": "20261125", "page_count": 100}
rows, page = [], 1
while True:
    data = httpx.get("https://opendart.fss.or.kr/api/list.json", params={**params, "page_no": page}).json()
    if data["status"] == "013":          # no results
        break
    if data["status"] != "000":          # 020 = quota exceeded, etc.
        raise RuntimeError(data["message"])
    rows += data["list"]
    if page >= data["total_page"]:
        break
    page += 1
for row in rows:
    print(row["rcept_dt"], row["corp_name"], row["report_nm"].strip())  # date is a string
```

With krx-news-client:

```python
async with DartScraper.from_env() as dart:   # DART_API_KEY, _2, _3
    for d in await dart.scrape_disclosures(bgn_de="20261125", end_de="20261125"):
        print(d.published_at, d.company, d.title, d.is_correction)  # tz-aware datetime
```

## Naver

There are two ways to get news from Naver.

**Naver Search API (news)** is an official API. It needs a Client ID and Secret, searches by keyword, and returns `title`, `originallink`, `link`, `description` and `pubDate`. `description` is a summary of the body; up to 100 results per call (`display`), start position up to 1,000 (`start`), and 25,000 calls per day. Sort by relevance or date. Source: [NAVER API HUB news search docs](https://api.ncloud-docs.com/docs/naver-api-hub-search-news)

- Keyword search has no ticker field; searching "삼성전자" also returns articles from other contexts.
- No disclosures.
- A good choice for broad coverage across the press or when you need the publisher's original link.

**Scraping Naver Finance pages** is not an official API. Checked 2026-11-26: both `finance.naver.com/robots.txt` and `m.stock.naver.com/robots.txt` have `Disallow: /` for general crawlers, and the once-common per-ticker news list path (`/item/news_news.naver`) returned HTTP 410. Parsers also need fixing whenever the HTML changes.

**Difference from krx-news-client**: krx-news-client does not use Naver. News comes from Toss Securities, which tags each article with tickers (`stockCodes`), so news can be looked up by ticker directly, and the article detail gives the full body, summary sentences, a sentiment label and the publisher's URL. Toss is, however, an **unofficial internal API** and can break without notice (see "Limits" below).

## pykrx

A library that returns KRX data as pandas. It has functions for ticker lists, OHLCV, market cap, PER/PBR/dividend yield, trading by investor type, foreign ownership, short selling, indices, ETF/ETN/ELW and treasury yields. APIs that need a KRX login require a KRX member account through the `KRX_ID` and `KRX_PW` environment variables. It has no news or DART disclosure functions. Source: [pykrx README](https://github.com/sharebook-kr/pykrx)

## FinanceDataReader

A library that returns Korean and global price data as pandas. `DataReader` covers KRX/US/global stocks, indices, FX, crypto, commodity futures, US treasuries and FRED series; `StockListing` covers KRX, US, Chinese, Hong Kong, Japanese and Vietnamese listings; `SnapDataReader` covers KRX index constituents and Naver financial statements. It has no news or disclosure functions. Source: [FinanceDataReader README](https://github.com/FinanceData/FinanceDataReader)

### Using them together: prices and filings in one table

pykrx and FinanceDataReader don't overlap with krx-news-client, so they are often used together. For example, add a daily filing count next to daily bars:

```python
from collections import Counter
from pykrx import stock

ohlcv = stock.get_market_ohlcv("20261101", "20261125", "005930")      # pykrx: daily bars
async with DartScraper.from_env() as dart:
    filings = [d for d in await dart.scrape_disclosures(bgn_de="20261101", end_de="20261125")
               if d.ticker == "005930"]
counts = Counter(d.published_at.date() for d in filings)
ohlcv["filings"] = [counts.get(day, 0) for day in ohlcv.index.date]
```

## Which one to use

| You want | Use |
|---|---|
| Prices, market cap, trading by investor type | pykrx, FinanceDataReader |
| Financial statements, fundamentals | OpenDART financial APIs, [krx-fundamentals-client](https://github.com/younghwan91/krx-fundamentals-client) |
| Broad keyword search across the press | Naver Search API |
| Disclosure lists and documents as models, multi-year backfill | krx-news-client |
| News and disclosures for a ticker on one timeline | krx-news-client |

## Limits

- Toss Securities is an unofficial internal API. As of 2026-11-26, Toss rejects requests without browser session cookies with `400 invalid-client-state`, so the Toss features (`TossScraper`) do not work. DART features are unaffected. Progress is tracked in the [CHANGELOG](../CHANGELOG.md).
- No prices or financials.
- DART disclosure times are the receipt date at 00:00 KST, because OpenDART gives no time.
