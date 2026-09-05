# Copilot Instructions — KRX News REST API

## Build, Test, Lint

```bash
# Setup (venv)
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run server (dev)
uvicorn krx_news_api.main:app --reload

# Run full test suite
pytest

# Run single test file or test
pytest tests/test_models.py -v
pytest tests/test_scrapers.py::TestBaseScraper::test_make_article -v

# Lint & format
ruff check src/
ruff format src/

# Docker
docker compose up -d          # Full stack (API + Redis)
docker compose up -d redis    # Redis only (for local dev)
```

## Architecture

**Cache-first REST API** — background scrapers periodically crawl news sources and store in Redis. API endpoints read directly from cache for low-latency responses.

```
FastAPI ─→ Routes ─→ Cache Service ─→ Redis (read)
                                        ↑
APScheduler ─→ Scrapers ─→ Cache Service ─→ Redis (write)
```

### Key layers

- **`scrapers/`** — One module per news source, all extend `BaseScraper`. Each implements `scrape_news()` and/or `scrape_disclosures()`. The base class handles HTTP retries, rate limiting, and User-Agent rotation.
- **`services/cache.py`** — Redis read/write layer. All data flows through here. Uses sorted sets (by publish time) for the combined feed, lists for per-source feeds.
- **`services/scheduler.py`** — APScheduler runs crawl jobs at configured intervals. Disclosures (KIND/DART) every 60s, news every 300s.
- **`routes/news.py`** — FastAPI router. All endpoints read from Redis cache only.
- **`models/schemas.py`** — Pydantic models. `NewsArticle` and `Disclosure` are the two core data types. All sources normalize into these.

### News sources

| Source | Type | Module | Interval |
|--------|------|--------|----------|
| KIND (kind.krx.co.kr) | 공시 (disclosures) | `scrapers/kind.py` | 60s |
| DART (dart.fss.or.kr) | 공시 (disclosures) | `scrapers/dart.py` | 60s |
| Naver Finance | 뉴스 | `scrapers/naver.py` | 300s |
| 한국경제 (Hankyung) | 뉴스 | `scrapers/hankyung.py` | 300s |
| 더벨 (TheBell) | 뉴스 | `scrapers/thebell.py` | 300s |
| 토스증권 (Toss) | 뉴스 | `scrapers/toss.py` | 300s |

## Conventions

- **src-layout** — All source under `src/krx_news_api/`. Import as `from krx_news_api.xxx import yyy`.
- **async everywhere** — All scrapers, cache operations, and routes are async. Use `httpx.AsyncClient` (not `requests`).
- **Adding a new scraper**: Create `scrapers/new_source.py` extending `BaseScraper`, add the source to `NewsSource` enum, register in `scheduler.py`'s `get_scrapers()`.
- **Article IDs** — `{source}:{md5(url)[:12]}` format via `make_article_id()`. Deterministic dedup by URL.
- **Rate limiting** — Each scraper sets `min_delay`/`max_delay` between requests. Naver is 1-3s, others 0.5-2s.
- **Config** — `pydantic-settings` loads from `.env` file. See `.env.example` for all variables.
- **Encoding** — Naver Finance uses `euc-kr`. KRX data may use `cp949`. Always handle explicitly.
- **Ruff** — Line length 100, target Python 3.11. Run `ruff check` before committing.
