<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/brand/wordmark-dark.svg">
  <img alt="krx-news-client" src="docs/images/brand/wordmark-light.svg" height="52">
</picture>

# krx-news-client

**A Python client for Korean stock news and DART disclosures in one unified schema.**

Fetch full article bodies, per-ticker news history, and raw disclosure documents in one `pip install`.

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

<p align="center"><sub>DART disclosures and Toss Securities news plotted on a unified per-ticker timeline with shared fields.</sub></p>

## Quick Start

```bash
pip install krx-news-client   # Python 3.11+
```

```python
from krx_news_client import DartScraper
async with DartScraper.from_env() as dart:   # export DART_API_KEY=... (OpenDART key)
    for d in (await dart.scrape_disclosures())[:3]: print(d.published_at.date(), d.company, d.title)
```

Runs as-is in Jupyter or `python -m asyncio` (in a script, wrap it in `async def main()` and call `asyncio.run(main())`). It prints yesterday's and today's (KST) disclosures across all markets, newest first. Actual output from 2026-11-26:

```text
2026-11-25 콜마비앤에이치 중간(분기)배당락
2026-11-25 SK증권제12호스팩 주권매매거래정지              (상장폐지 사유발생)
2026-11-25 유안타제16호스팩 주권매매거래정지              (상장폐지 사유발생)
```

Get a free OpenDART API key at [opendart.fss.or.kr](https://opendart.fss.or.kr/). Toss news needs no key and comes through `TossScraper` (see the [examples gallery](#examples-gallery)).

## What It Does

| Source | Data | Collection Method |
|---|---|---|
| DART (dart.fss.or.kr) | Disclosure list & full text | Official Open API (API key required) |
| Toss Securities (tossinvest.com) | Dashboard news, article body, per-ticker news | Unofficial internal API |

- **Two sources, one schema.** `Disclosure` and `NewsArticle` share `id`, `source`, `title`, `url`, and `published_at` (tz-aware KST).
- **Exceptions instead of silent zeros.** Schema changes in Toss responses raise `TossResponseError`, invalid ticker codes or page sizes raise `ValueError`, and DART daily quota exhaustion raises `DartQuotaExceededError`.
- **Paginated per-ticker news history.** `scrape_company_news()` fetches up to 100 items per page, up to Toss's 10,000-item offset limit.
- **Separate DART polling and backfill paths.** `scrape_disclosures()` handles multi-key auto-rotation and tolerant polling, while `search_disclosures*()` and `fetch_document()` provide strict backfilling.
- **Built-in deduplication.** `Deduplicator` yields only unseen items by `id` for articles and `rcept_no` for disclosures.

See the [Guide](docs/guide.en.md#detailed-usage) and [`examples/`](examples/) for full code examples. For how this differs from calling OpenDART directly, Naver, pykrx and FinanceDataReader, see [Compared with other approaches](docs/comparison.en.md).

## Examples Gallery

The snippets below run inside `async with DartScraper.from_env() as dart, TossScraper() as toss:` (with `from datetime import date` and `from krx_news_client import DartScraper, Deduplicator, TossScraper`). Every snippet is executed against mocked responses by [`tests/test_readme_gallery.py`](tests/test_readme_gallery.py).

<!-- gallery:start -->
**Disclosure alert for a watchlist** — one turn of a polling loop. Only new filings, corrections skipped.

```python
watch, seen = {"005930", "000660"}, Deduplicator()
for d in seen.filter_new(await dart.scrape_disclosures()):
    if d.ticker in watch and not d.is_correction: print(d.company, d.title, d.url)
```

**News timeline for a ticker** — page back through a ticker's news and print oldest first.

```python
news = await toss.scrape_company_news("005930", since=date(2026, 11, 1), max_pages=3)
for a in reversed(news):  # results are newest first
    print(f"{a.published_at:%m-%d %H:%M}  {a.title}  ({a.author})")
```

**News and filings on one timeline** — both models share `published_at` (KST), `source` and `title`.

```python
news = await toss.scrape_company_news("005930", since=date(2026, 11, 20), max_pages=1)
filings = [d for d in await dart.scrape_disclosures(bgn_de="20261120") if d.ticker == "005930"]
for x in sorted([*news, *filings], key=lambda x: x.published_at): print(x.published_at.date(), x.source, x.title)
```

**Feeding an LLM** — the full body of the latest article as a prompt. Pass `prompt` to whichever LLM SDK you use.

```python
[latest] = await toss.scrape_company_news("005930", max_pages=1, page_size=1)
article = await toss.fetch_article_detail(latest.news_id)
prompt = f"Summarize this article in three lines.\n\n# {article.title}\n\n{article.content}"
```

**Disclosure full text** — fetch the document zip by receipt number and take the tag-free body.

```python
d = next(d for d in await dart.scrape_disclosures() if not d.is_correction)
[doc, *_] = await dart.fetch_document(d.rcept_no)
print(d.title, doc.text[:300])
```
<!-- gallery:end -->

## Toss Caveats

Because Toss is an unofficial internal API, it may break or block requests without notice.

> **Checked 2026-11-26:** Toss rejects requests without browser session cookies with `400 invalid-client-state`, so `TossScraper` requests currently fail. DART features are unaffected. Progress is tracked in the [CHANGELOG](CHANGELOG.md).

- **6-digit codes only.** A leading `A` is stripped automatically; any other format raises `ValueError` before requesting.
- **1-indexed pages, max size 100.** `number=0` or `size=101` or higher raises `ValueError` before requesting.
- **10,000-item offset limit.** Toss returns HTTP 400 when `number × size` exceeds 10,000, covering less than 6 months for large-cap stocks.
- **`lastPage` is unreliable.** The scraper paginates until an empty page, deduplicates by `id`, and sorts newest-first.

See [Toss Caveats](docs/guide.en.md#toss-caveats) for the full list, response fields, and architecture diagram.

## Docs

| Doc | What's inside |
|---|---|
| [Guide](docs/guide.en.md) | Detailed Toss & DART usage, design rationale, Toss API caveats, response fields, architecture |
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
