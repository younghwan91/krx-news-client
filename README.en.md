<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/brand/wordmark-dark.svg">
  <img alt="krx-news-client" src="docs/images/brand/wordmark-light.svg" height="52">
</picture>

# krx-news-client

**A Python client for DART disclosures and Korean stock news (Yonhap RSS, Naver Search API) in one unified schema.**

From a keyless news feed to per-company news search and raw disclosure documents, in one `pip install`.

[![CI](https://github.com/younghwan91/krx-news-client/actions/workflows/ci.yml/badge.svg)](https://github.com/younghwan91/krx-news-client/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/github/license/younghwan91/krx-news-client)](LICENSE)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-younghwan--chae-0A66C2?logo=linkedin&logoColor=white)](https://www.linkedin.com/in/younghwan-chae/)

[Docs](docs/guide.en.md) · [Examples](examples/) · [한국어](README.md) · [Issues](https://github.com/younghwan91/krx-news-client/issues)

</div>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/hero-dark.png">
  <img alt="DART disclosures and Toss Securities news plotted on a unified per-ticker timeline, with two record cards sharing the same fields" src="docs/images/hero-light.png" width="100%">
</picture>

<p align="center"><sub>News and DART disclosures on one per-ticker timeline with shared fields. The news in the picture is a Toss Securities run from before the 2026-11-26 block.</sub></p>

## Quick Start

```bash
pip install krx-news-client   # Python 3.11+
```

```python
from krx_news_client import YonhapScraper
async with YonhapScraper() as yna:   # no key (Yonhap Market+ RSS)
    for a in (await yna.scrape_news())[:3]: print(f"{a.published_at:%m-%d %H:%M}", a.tickers, a.title)
```

Runs as-is in Jupyter or `python -m asyncio` (in a script, wrap it in `async def main()` and call `asyncio.run(main())`). It prints the latest Yonhap Market+ articles, newest first; a `Company[code]` mention in the article lands in `tickers`. Actual output from 2026-11-26:

```text
11-26 19:49 ['101000'] KS인더스트리, 50억원 유상증자…프라임라이트투자조합1호에 제3자배정
11-26 18:54 [] 자본시장개혁기구 수장에 메리츠 김용범…민간에 전권 부여(종합)
11-26 18:35 [] 무디스 "AI확산에 동일 산업 내 기업 간 신용도 격차 확대될 것"
```

Disclosures come through `DartScraper.from_env()` (`DART_API_KEY`, free at [opendart.fss.or.kr](https://opendart.fss.or.kr/)), and news searched by company name through `NaverNewsScraper.from_env()` (`NAVER_CLIENT_ID` and `NAVER_CLIENT_SECRET`, free from the [Naver Developers console](https://developers.naver.com/apps/#/register) with the "Search" API enabled). See the [examples gallery](#examples-gallery).

## What It Does

| Source | Data | Collection Method | Key |
|---|---|---|---|
| DART (dart.fss.or.kr) | Disclosure list & full text | Official Open API | Required (free) |
| Yonhap News (yna.co.kr) | Latest articles per section (Market+, economy, industry, all) | Public RSS | None |
| Naver Search API (openapi.naver.com) | News search by keyword or company name | Official Open API | Required (free) |
| Toss Securities (tossinvest.com) | Dashboard & per-ticker news, article body | Unofficial internal API | **Blocked since 2026-11-26** |

- **Several sources, one schema.** `Disclosure` and `NewsArticle` share `id`, `source`, `title`, `url`, and `published_at` (tz-aware KST).
- **Exceptions instead of silent zeros.** A Toss block raises `TossBlockedError`, a missing key raises `NaverKeyMissingError` or `ValueError` with how to get one, bad paging arguments raise `ValueError` before requesting, and DART daily quota exhaustion raises `DartQuotaExceededError`.
- **Per-company news search.** `NaverNewsScraper.search_news("삼성전자", tickers=["005930"])` pages newest-first, up to 1,099 items.
- **Separate DART polling and backfill paths.** `scrape_disclosures()` handles multi-key auto-rotation and tolerant polling, while `search_disclosures*()` and `fetch_document()` provide strict backfilling.
- **Built-in deduplication.** `Deduplicator` yields only unseen items by `id` for articles and `rcept_no` for disclosures.

See the [Guide](docs/guide.en.md#detailed-usage) and [`examples/`](examples/) for full code examples. For how this differs from calling OpenDART directly, Naver, pykrx and FinanceDataReader, see [Compared with other approaches](docs/comparison.en.md).

## News Sources and Terms of Use

News is other people's content, and each source allows a different scope. The library only makes the requests; keeping to these terms is up to the caller (checked on each official page on 2026-11-26).

- **Yonhap RSS**: `robots.txt` allows `/rss/`. Per the [RSS page](https://www.yna.co.kr/rss/index) the feeds are for **non-commercial blogs and personal use only**, and each feed carries "no unauthorized reproduction or redistribution, no AI training or use". Commercial use needs a separate agreement with Yonhap.
- **Naver Search API**: the [terms](https://developers.naver.com/products/terms/) require showing that results are Naver search results with the original source and link, forbid **storing or caching results** (except up to 21 days on a server for history), and forbid **feeding the data to AI or giving it to third parties**. It does not suit long-term storage or backtest datasets.
- **DART** is the Financial Supervisory Service's official Open API, suited to storing and analysing filings. For LLM input or backtest storage, use DART filings.
- Naver Finance pages (`finance.naver.com`) are `Disallow: /` in robots, so this library does not scrape them. Google News RSS (`news.google.com/rss`) is also disallowed by robots and is not included.

## Examples Gallery

The snippets below run inside `async with DartScraper.from_env() as dart, YonhapScraper() as yna, NaverNewsScraper.from_env() as naver:` (with `from datetime import date` and `from krx_news_client import DartScraper, Deduplicator, NaverNewsScraper, YonhapScraper`). Every snippet is executed against mocked responses by [`tests/test_readme_gallery.py`](tests/test_readme_gallery.py).

<!-- gallery:start -->
**Disclosure alert for a watchlist** — one turn of a polling loop. Only new filings, corrections skipped.

```python
watch, seen = {"005930", "000660"}, Deduplicator()
for d in seen.filter_new(await dart.scrape_disclosures()):
    if d.ticker in watch and not d.is_correction: print(d.company, d.title, d.url)
```

**Breaking news for a watchlist** — pick watchlist articles out of the Yonhap Market+ feed, no key needed.

```python
watch = {"101000", "005930"}
for a in await yna.scrape_news(["market", "industry"]):
    if watch & set(a.tickers): print(f"{a.published_at:%H:%M}  {a.title}  {a.url}")
```

**News search for a company** — search by company name and print oldest first, with the source link (Naver terms).

```python
news = await naver.search_news("삼성전자", tickers=["005930"], since=date(2026, 11, 20))
for a in reversed(news):  # results are newest first
    print(f"{a.published_at:%m-%d %H:%M}  {a.title}  {a.original_url}")
```

**News and filings on one timeline** — both models share `published_at` (KST), `source` and `title`.

```python
news = await naver.search_news("삼성전자", tickers=["005930"], since=date(2026, 11, 20), limit=20)
filings = [d for d in await dart.scrape_disclosures(bgn_de="20261120") if d.ticker == "005930"]
for x in sorted([*news, *filings], key=lambda x: x.published_at): print(x.published_at.date(), x.source, x.title)
```

**A filing as LLM input** — fetch the document zip by receipt number and turn the tag-free body into a prompt. Pass `prompt` to whichever LLM SDK you use.

```python
d = next(d for d in await dart.scrape_disclosures() if not d.is_correction)
[doc, *_] = await dart.fetch_document(d.rcept_no)
prompt = f"Summarize this filing in three lines.\n\n# {d.title}\n\n{doc.text[:4000]}"
```
<!-- gallery:end -->

## Toss Caveats

Because Toss is an unofficial internal API, it may break or block requests without notice.

> **Blocked since 2026-11-26:** Toss rejects requests without browser session cookies with `400 invalid-client-state`. On that response `TossScraper` does not retry and raises `TossBlockedError` (a subclass of `TossResponseError`). It does not imitate a browser session to get around the block. Get news from `YonhapScraper` or `NaverNewsScraper`. If Toss opens up again, the behaviour below still applies.

- **6-digit codes only.** A leading `A` is stripped automatically; any other format raises `ValueError` before requesting.
- **1-indexed pages, max size 100.** `number=0` or `size=101` or higher raises `ValueError` before requesting.
- **10,000-item offset limit.** Toss returns HTTP 400 when `number × size` exceeds 10,000, covering less than 6 months for large-cap stocks.
- **`lastPage` is unreliable.** The scraper paginates until an empty page, deduplicates by `id`, and sorts newest-first.

See [Toss Caveats](docs/guide.en.md#toss-caveats) for the full list, response fields, and architecture diagram.

## Docs

| Doc | What's inside |
|---|---|
| [Guide](docs/guide.en.md) | Detailed Toss & DART usage (Yonhap and Naver: this README and docstrings), design rationale, Toss API caveats, response fields, architecture |
| [Comparison](docs/comparison.en.md) | Scope and code compared with calling OpenDART directly, Naver, pykrx and FinanceDataReader |
| [Examples](examples/) | Basic usage and stock alert polling examples |
| [Changelog](CHANGELOG.md) | Release history |

## Works Well With

| Repo | What it does |
|---|---|
| [kiwoom-client](https://github.com/younghwan91/kiwoom-client) | Python client for the Kiwoom REST API: quotes, flows, order book, orders, real-time WebSocket, MCP server |
| [krx-fundamentals-client](https://github.com/younghwan91/krx-fundamentals-client) | Collects Korean company fundamentals from DART, KRX and Naver into Pydantic models |
| [fin-checkup](https://github.com/younghwan91/fin-checkup) | Free tool that reads listed companies' financial statements as 17 traffic-light metrics, with formulas and thresholds shown; no investment advice |

## Contributing & Support

- Report bugs, ask questions, or suggest features on [GitHub Issues](https://github.com/younghwan91/krx-news-client/issues).
- Author: **Younghwan Chae (채영환)** · [GitHub @younghwan91](https://github.com/younghwan91) · [LinkedIn](https://www.linkedin.com/in/younghwan-chae/)

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.
