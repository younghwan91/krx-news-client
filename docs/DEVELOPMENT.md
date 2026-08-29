# 개발 가이드

## 로컬 환경

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

docker compose up -d redis                      # Redis 만 띄우기
uvicorn krx_news_api.main:app --reload
```

## 환경변수

`.env.example` 을 복사해 쓴다. `docker compose` 는 `REDIS_URL` 을 서비스 이름으로 덮어쓴다.

| 변수 | 기본값 | 설명 |
|-----|-------|------|
| `REDIS_URL` | `redis://localhost:6379` | Redis 연결 URL |
| `DART_API_KEY` | (빈 값) | DART Open API 키 — 없으면 DART 소스만 빠진다 |
| `CRAWL_INTERVAL_NEWS` | `300` | 뉴스 크롤링 주기 (초) |
| `CRAWL_INTERVAL_DISCLOSURE` | `60` | 공시 크롤링 주기 (초) |
| `LOG_LEVEL` | `INFO` | 로그 레벨 |
| `HOST` / `PORT` / `WORKERS` | `0.0.0.0` / `8000` / `1` | 서버 바인드·워커 |
| `CORS_ORIGINS` | `["*"]` | CORS 허용 origin |

## 테스트 · 린트

```bash
pytest              # Redis 불필요 — fakeredis 로 대체된다
ruff check src/ tests/
ruff format src/ tests/
```

## 새 뉴스 소스 추가

1. `models/schemas.py` 의 `NewsSource` enum 에 값 추가
2. `scrapers/` 에 `BaseScraper` 를 상속한 파일 생성
3. `scrape_news()` 또는 `scrape_disclosures()` 구현
4. `services/scheduler.py` 의 `get_scrapers()` 에 등록

```python
from krx_news_api.models.schemas import NewsArticle, NewsCategory, NewsSource
from krx_news_api.scrapers.base import BaseScraper


class ExampleScraper(BaseScraper):
    source = NewsSource.EXAMPLE
    base_url = "https://example.com"
    min_delay = 1.0
    max_delay = 2.0

    async def scrape_news(self) -> list[NewsArticle]:
        resp = await self.fetch(f"{self.base_url}/news")
        # HTML 파싱 후 _make_article() 로 생성
        return [self._make_article(title=..., url=..., category=NewsCategory.MARKET)]
```

`BaseScraper` 가 재시도·요청 간격·User-Agent 순환을 이미 처리하므로 파싱만 신경 쓰면 된다.

## 배포

```bash
docker compose up -d
docker compose logs -f api
docker compose down
```

프로덕션에서는 `LOG_LEVEL=WARNING`, `WORKERS` 상향, `CORS_ORIGINS` 를 실제 도메인으로 좁히는 정도면 충분하다. 워커를 여러 개 띄우면 워커마다 스케줄러가 하나씩 뜨므로, 크롤링을 한 번만 돌리려면 스케줄러 전용 프로세스를 따로 두는 편이 낫다.

## 예제 코드

| 파일 | 설명 |
|------|------|
| [`basic_usage.py`](../examples/basic_usage.py) | 동기 방식 기본 사용법 |
| [`async_usage.py`](../examples/async_usage.py) | 비동기 동시 조회 + 실시간 모니터 |
| [`stock_alert.py`](../examples/stock_alert.py) | 관심 종목 공시·뉴스 알림 |

```bash
pip install httpx
python examples/basic_usage.py
```
