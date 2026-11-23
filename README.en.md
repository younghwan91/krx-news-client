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

> `fetch_article_detail_raw`, 10,000-offset limit handling for per-ticker news, `size` validation, and DART key log masking landed after PyPI 0.4.0 and are currently only on `main`. Install from Git to use them: `pip install "krx-news-client @ git+https://github.com/younghwan91/krx-news-client"`.

```python
import asyncio
from krx_news_client import TossScraper

async def main():
    async with TossScraper() as scraper:
        articles = await scraper.scrape_news()
        for article in articles[:5]:
            print(article.nation, article.title, article.published_at)

asyncio.run(main())
```

You will see recent domestic (`KR`) and US (`US`) headlines with tz-aware KST timestamps:

```text
KR 코스피, 외국인 순매수에 2%대 상승 마감 2025-06-10 15:30:00+09:00
US 엔비디아, 실적 발표 앞두고 강세 2025-06-10 14:05:00+09:00
...
```

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

See the [Guide](docs/guide.en.md#detailed-usage) and [`examples/`](examples/) for full code examples.

## Toss Caveats

Because Toss is an unofficial internal API, it may break or block requests without notice.

- **6-digit codes only.** A leading `A` is stripped automatically; any other format raises `ValueError` before requesting.
- **1-indexed pages, max size 100.** `number=0` or `size=101` or higher raises `ValueError` before requesting.
- **10,000-item offset limit.** Toss returns HTTP 400 when `number × size` exceeds 10,000, covering less than 6 months for large-cap stocks.
- **`lastPage` is unreliable.** The scraper paginates until an empty page, deduplicates by `id`, and sorts newest-first.

See [Toss Caveats](docs/guide.en.md#toss-caveats) for the full list, response fields, and architecture diagram.

## Docs

| Doc | What's inside |
|---|---|
| [Guide](docs/guide.en.md) | Detailed Toss & DART usage, design rationale, Toss API caveats, response fields, architecture |
| [Examples](examples/) | Basic usage and stock alert polling examples |
| [Changelog](CHANGELOG.md) | Release history |

## Contributing & Support

- Report bugs, ask questions, or suggest features on [GitHub Issues](https://github.com/younghwan91/krx-news-client/issues).
- Author: **Younghwan Chae (채영환)** · [GitHub @younghwan91](https://github.com/younghwan91) · [LinkedIn](https://www.linkedin.com/in/younghwan-chae/)

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.
