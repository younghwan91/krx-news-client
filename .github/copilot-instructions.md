# Copilot Instructions — krx-news-client

## Build, Test, Lint

```bash
# Setup (venv)
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run full test suite
pytest

# Run single test file or test
pytest tests/test_models.py -v
pytest tests/test_scrapers.py::TestBaseScraper::test_make_article -v

# Lint & format
ruff check src/
ruff format src/
```

## Architecture

**Client library, not a server.** Each `*Scraper` calls its source directly (HTTP) when invoked and returns normalized `NewsArticle`/`Disclosure` objects — no background process, no cache, no scheduling. Callers (e.g. an Airflow collector) decide when to call and where to store results.

### Key layers

- `scrapers/base.py` — `BaseScraper`: shared httpx client, retry/backoff, throttling, user-agent rotation
- `scrapers/{toss,hankyung,thebell,dart}.py` — one scraper per source
- `models/schemas.py` — `NewsArticle`, `Disclosure`, `NewsCategory`, `NewsSource`
