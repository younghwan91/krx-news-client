# KRX News REST API

[![CI](https://github.com/younghwan91/krx-news-rest-api/actions/workflows/ci.yml/badge.svg)](https://github.com/younghwan91/krx-news-rest-api/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/github/license/younghwan91/krx-news-rest-api)](https://github.com/younghwan91/krx-news-rest-api/blob/main/LICENSE)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-younghwan--chae-0A66C2?logo=linkedin&logoColor=white)](https://www.linkedin.com/in/younghwan-chae/)

한국 주식시장 뉴스와 공시 정보를 다양한 매체에서 자동 수집하여 제공하는 REST API입니다.

백그라운드 스케줄러가 주기적으로 뉴스를 크롤링하여 Redis에 캐싱하고, API 요청 시 캐시에서 즉시 응답하는 **캐시 우선(cache-first)** 아키텍처로 설계되었습니다.

## 주요 기능

- 📰 **5개 뉴스/공시 소스** 자동 수집 — KIND, DART, 네이버 금융, 한국경제, 더벨
- ⚡ **저지연 응답** — Redis 캐시에서 즉시 조회, 크롤링 대기 없음
- 🔄 **백그라운드 크롤링** — 공시 60초, 뉴스 5분 간격 자동 갱신
- 🔍 **키워드/종목 검색** — 제목 및 본문 기반 전문 검색
- 📊 **크롤러 상태 모니터링** — 소스별 수집 현황, 에러 상태 실시간 확인
- 🛡️ **안정적 수집** — 자동 재시도, 요청 간격 조절, User-Agent 순환
- 🐳 **Docker 원클릭 배포** — `docker compose up -d` 로 즉시 실행

---

## 빠른 시작

### Docker로 실행 (권장)

```bash
git clone https://github.com/younghwan91/krx-news-rest-api.git
cd krx-news-rest-api

cp .env.example .env          # 환경변수 설정
# .env 파일에서 DART_API_KEY 입력 (선택, https://opendart.fss.or.kr 에서 무료 발급)

docker compose up -d           # API 서버 + Redis 시작
```

```bash
# 헬스체크
curl http://localhost:8000/health
# {"status":"ok"}

# Swagger UI 확인
open http://localhost:8000/docs
```

### 로컬 개발 환경

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Redis 실행 (Docker)
docker compose up -d redis

# 개발 서버 실행 (자동 리로드)
uvicorn krx_news_api.main:app --reload
```

서버가 시작되면 자동으로 모든 소스에서 뉴스/공시 수집을 시작합니다.

---

## API 문서

서버 실행 후 **Swagger UI**에서 전체 API를 확인하고 테스트할 수 있습니다:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### 엔드포인트 목록

| 메서드 | 엔드포인트 | 설명 | 파라미터 |
|-------|-----------|------|---------|
| `GET` | `/api/v1/news` | 전체 뉴스 목록 | `source`, `page`, `page_size` |
| `GET` | `/api/v1/news/search` | 키워드 검색 | `q` (필수), `page`, `page_size` |
| `GET` | `/api/v1/news/{source}` | 소스별 뉴스 | `page`, `page_size` |
| `GET` | `/api/v1/disclosure` | 공시 목록 | `source`, `ticker`, `page`, `page_size` |
| `GET` | `/api/v1/disclosure/{ticker}` | 종목별 공시 | `page`, `page_size` |
| `GET` | `/api/v1/status` | 크롤러 상태 | — |
| `GET` | `/health` | 헬스체크 | — |

**공통 파라미터:**
- `page` — 페이지 번호 (기본값: 1, 최소: 1)
- `page_size` — 페이지 크기 (기본값: 20, 최소: 1, 최대: 100)
- `source` — 뉴스 소스 필터 (`kind`, `dart`, `naver`, `hankyung`, `thebell`)

### 요청/응답 예시

#### 최신 뉴스 조회

```bash
curl "http://localhost:8000/api/v1/news?page=1&page_size=5"
```

```json
{
  "items": [
    {
      "id": "naver:a1b2c3d4e5f6",
      "source": "naver",
      "category": "market",
      "title": "코스피, 외국인 매수세에 2,650선 돌파",
      "url": "https://finance.naver.com/news/...",
      "content": "...",
      "summary": "",
      "tickers": [],
      "author": "",
      "published_at": "2026-03-31T09:30:00",
      "collected_at": "2026-03-31T09:35:12"
    }
  ],
  "total": 142,
  "page": 1,
  "page_size": 5,
  "has_next": true
}
```

#### 키워드 검색

```bash
# 삼성전자 관련 뉴스 검색
curl "http://localhost:8000/api/v1/news/search?q=삼성전자"
```

**검색 추천 키워드:**

| 카테고리 | 추천 키워드 |
|---------|-----------|
| 종목명 | `삼성전자`, `SK하이닉스`, `카카오`, `네이버`, `현대차` |
| 시장 동향 | `코스피`, `코스닥`, `환율`, `금리`, `외국인` |
| 산업/섹터 | `반도체`, `2차전지`, `바이오`, `AI`, `자동차` |
| 이벤트 | `실적`, `배당`, `유상증자`, `공모`, `합병` |
| 거시경제 | `기준금리`, `CPI`, `GDP`, `연준`, `한은` |

#### 소스별 뉴스 조회

```bash
# 네이버 금융 뉴스만 조회
curl "http://localhost:8000/api/v1/news/naver"

# 한국경제 뉴스만 조회
curl "http://localhost:8000/api/v1/news/hankyung"
```

#### 공시 조회

```bash
# 전체 공시 목록
curl "http://localhost:8000/api/v1/disclosure"

# 삼성전자(005930) 공시만 조회
curl "http://localhost:8000/api/v1/disclosure/005930"

# KIND 공시만 필터링
curl "http://localhost:8000/api/v1/disclosure?source=kind"
```

```json
{
  "items": [
    {
      "id": "kind:x9y8z7w6v5u4",
      "source": "kind",
      "title": "주요사항보고서(자기주식취득결정)",
      "url": "https://kind.krx.co.kr/disclosure/...",
      "company": "삼성전자",
      "ticker": "005930",
      "disclosure_type": "주요사항보고서",
      "published_at": "2026-03-31T08:45:00",
      "collected_at": "2026-03-31T08:46:02"
    }
  ],
  "total": 38,
  "page": 1,
  "page_size": 20,
  "has_next": true
}
```

#### 크롤러 상태 확인

```bash
curl "http://localhost:8000/api/v1/status"
```

```json
[
  {
    "source": "kind",
    "last_crawled_at": "2026-03-31T09:30:12",
    "articles_count": 45,
    "is_healthy": true,
    "error": null
  },
  {
    "source": "dart",
    "last_crawled_at": "2026-03-31T09:30:15",
    "articles_count": 23,
    "is_healthy": true,
    "error": null
  }
]
```

### 에러 응답

| 상태 코드 | 의미 | 예시 |
|----------|------|------|
| `200` | 성공 | 정상 응답 |
| `422` | 유효성 검증 실패 | 필수 파라미터 누락, 잘못된 값 |
| `503` | Redis 연결 실패 | `{"detail": "Cache service unavailable"}` |
| `500` | 서버 내부 에러 | `{"detail": "Internal server error"}` |

---

## 뉴스 소스

### 공시 (Disclosures)

| 소스 | URL | 수집 주기 | 인증 | 설명 |
|-----|-----|----------|------|------|
| **KIND** | kind.krx.co.kr | 60초 | 불필요 | 한국거래소 기업공시 시스템. KOSPI/KOSDAQ/KONEX 전체 공시 |
| **DART** | dart.fss.or.kr | 60초 | API 키 | 금융감독원 전자공시. 사업보고서, 주요사항보고서 등 |

### 뉴스 (News)

| 소스 | URL | 수집 주기 | 카테고리 | 설명 |
|-----|-----|----------|---------|------|
| **네이버 금융** | finance.naver.com | 5분 | 시황/전망, 종목분석, 공시 | 국내 최대 포털 증권 뉴스 |
| **한국경제** | hankyung.com | 5분 | 증권, 경제, 마켓 | 한국 대표 경제 일간지 |
| **더벨** | thebell.co.kr | 5분 | 금융, 산업, 분석 | 금융 전문 심층 분석 매체 |

> **참고:** DART API 키가 없어도 나머지 4개 소스는 정상 작동합니다. DART API 키는 [opendart.fss.or.kr](https://opendart.fss.or.kr)에서 무료 발급 가능합니다.

---

## 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                         FastAPI 서버                             │
│                                                                  │
│   ┌─────────┐     ┌───────────────┐     ┌───────┐              │
│   │ Client  │────→│ Routes (API)  │────→│ Redis │ ← 즉시 응답   │
│   └─────────┘     └───────────────┘     └───┬───┘              │
│                                              │                   │
│   ┌──────────────────────────────────────────┘                   │
│   │  백그라운드 크롤링 (APScheduler)                              │
│   │                                                              │
│   │  ┌─────────────┐     ┌────────────┐     ┌───────┐          │
│   │  │  Scrapers   │────→│ 정규화/파싱 │────→│ Redis │          │
│   │  │             │     └────────────┘     └───────┘          │
│   │  │ · KIND      │                                            │
│   │  │ · DART      │  공시: 매 60초                              │
│   │  │ · Naver     │  뉴스: 매 300초                             │
│   │  │ · Hankyung  │                                            │
│   │  │ · TheBell   │                                            │
│   │  └─────────────┘                                            │
│   └──────────────────────────────────────────────────────────────│
└─────────────────────────────────────────────────────────────────┘
```

### 프로젝트 구조

```
src/krx_news_api/
├── main.py              # FastAPI 앱, 미들웨어, lifespan
├── config.py            # pydantic-settings 환경변수 설정
├── models/
│   └── schemas.py       # Pydantic 모델 (NewsArticle, Disclosure 등)
├── routes/
│   └── news.py          # REST API 엔드포인트 (7개)
├── scrapers/
│   ├── base.py          # BaseScraper (retry, rate limit, UA rotation)
│   ├── kind.py          # KIND 한국거래소 공시
│   ├── dart.py          # DART 전자공시 Open API
│   ├── naver.py         # 네이버 금융 뉴스
│   ├── hankyung.py      # 한국경제 뉴스
│   └── thebell.py       # 더벨 금융 분석
└── services/
    ├── cache.py         # Redis 캐시 읽기/쓰기
    └── scheduler.py     # APScheduler 백그라운드 크롤링
```

### 데이터 흐름

1. **서버 시작** → 모든 소스에서 초기 크롤링 실행
2. **스케줄러** → 공시 60초, 뉴스 300초 간격으로 반복 크롤링
3. **스크래퍼** → 각 소스에서 HTML 파싱 또는 API 호출
4. **정규화** → 모든 뉴스를 `NewsArticle`, 공시를 `Disclosure` 통일 스키마로 변환
5. **Redis 저장** → Sorted Set(발행시간 기준) + List(소스별) 로 캐싱
6. **API 응답** → Redis에서 직접 읽어 즉시 반환

### 캐시 전략

| 데이터 | Redis 구조 | TTL | 키 패턴 |
|-------|-----------|-----|---------|
| 전체 뉴스 | Sorted Set | 1시간 | `news:all` |
| 소스별 뉴스 | List | 1시간 | `news:{source}` |
| 전체 공시 | Sorted Set | 24시간 | `disclosure:all` |
| 소스별 공시 | List | 24시간 | `disclosure:{source}` |
| 검색 결과 | String (JSON) | 5분 | `search:{query}:{page}:{size}` |
| 크롤러 상태 | String (JSON) | 없음 | `crawler:status:{source}` |

---

## 환경변수

`.env` 파일 또는 환경변수로 설정합니다. `.env.example`을 복사하여 사용하세요.

```bash
cp .env.example .env
```

| 변수 | 기본값 | 필수 | 설명 |
|-----|-------|------|------|
| `REDIS_URL` | `redis://localhost:6379` | — | Redis 연결 URL |
| `DART_API_KEY` | — | 선택 | DART Open API 키 ([발급](https://opendart.fss.or.kr)) |
| `CRAWL_INTERVAL_NEWS` | `300` | — | 뉴스 크롤링 주기 (초) |
| `CRAWL_INTERVAL_DISCLOSURE` | `60` | — | 공시 크롤링 주기 (초) |
| `LOG_LEVEL` | `INFO` | — | 로그 레벨 (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `HOST` | `0.0.0.0` | — | 서버 바인드 주소 |
| `PORT` | `8000` | — | 서버 포트 |
| `WORKERS` | `1` | — | Uvicorn 워커 수 |
| `CORS_ORIGINS` | `["*"]` | — | CORS 허용 origin 목록 |

---

## 개발

### 테스트

```bash
# 전체 테스트 (Redis 불필요 — fakeredis로 자동 mock)
pytest

# 상세 출력
pytest -v

# 단일 테스트
pytest tests/test_api.py::test_health -v

# 특정 파일
pytest tests/test_models.py -v
```

### 린트 & 포맷

```bash
# 린트 검사
ruff check src/ tests/

# 자동 수정
ruff check --fix src/ tests/

# 코드 포맷팅
ruff format src/ tests/
```

### 새 뉴스 소스 추가하기

1. `models/schemas.py`의 `NewsSource` enum에 소스 추가
2. `scrapers/` 디렉토리에 새 스크래퍼 파일 생성 (`BaseScraper` 상속)
3. `scrape_news()` 및/또는 `scrape_disclosures()` 구현
4. `services/scheduler.py`의 `get_scrapers()`에 등록

```python
# scrapers/example.py
from krx_news_api.scrapers.base import BaseScraper
from krx_news_api.models.schemas import NewsArticle, NewsSource, NewsCategory

class ExampleScraper(BaseScraper):
    source = NewsSource.EXAMPLE
    base_url = "https://example.com"
    min_delay = 1.0
    max_delay = 2.0

    async def scrape_news(self) -> list[NewsArticle]:
        resp = await self.fetch(f"{self.base_url}/news")
        # HTML 파싱 후 _make_article()로 생성
        return [self._make_article(title=..., url=..., category=NewsCategory.MARKET)]
```

---

## 배포

### Docker Compose (권장)

```bash
docker compose up -d           # 시작
docker compose logs -f api     # 로그 확인
docker compose down            # 중지
```

### 프로덕션 설정 예시

```env
REDIS_URL=redis://redis:6379
DART_API_KEY=your_api_key_here
CRAWL_INTERVAL_NEWS=300
CRAWL_INTERVAL_DISCLOSURE=60
LOG_LEVEL=WARNING
WORKERS=4
CORS_ORIGINS=["https://yourdomain.com"]
```

---

## 예제 코드

`examples/` 디렉토리에 바로 실행 가능한 예제가 포함되어 있습니다.

| 파일 | 설명 |
|------|------|
| [`basic_usage.py`](examples/basic_usage.py) | 동기 방식 기본 사용법 (뉴스 조회, 검색, 공시, 크롤러 상태) |
| [`async_usage.py`](examples/async_usage.py) | 비동기 동시 조회 + 실시간 뉴스 모니터 |
| [`stock_alert.py`](examples/stock_alert.py) | 관심 종목 공시/뉴스 알림 시스템 |

```bash
# 서버 실행 후
pip install httpx
python examples/basic_usage.py
```

---

## 기술 스택

| 구성 요소 | 기술 |
|----------|------|
| 프레임워크 | [FastAPI](https://fastapi.tiangolo.com/) |
| HTTP 클라이언트 | [httpx](https://www.python-httpx.org/) (async) |
| HTML 파싱 | [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/) + lxml |
| 캐시 | [Redis](https://redis.io/) (redis-py async) |
| 스케줄러 | [APScheduler](https://apscheduler.readthedocs.io/) |
| 설정 관리 | [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) |
| 린트/포맷 | [Ruff](https://docs.astral.sh/ruff/) |
| 테스트 | [pytest](https://pytest.org/) + fakeredis |
| CI/CD | GitHub Actions |
| 컨테이너 | Docker + docker-compose |

---

## 라이선스

MIT


---

## ⭐ 도움이 되셨다면

이 프로젝트가 유용했다면 우측 상단 **[⭐ Star](https://github.com/younghwan91/krx-news-rest-api)** 를 눌러주세요. 검색·추천 노출이 올라가 더 많은 분들이 찾을 수 있습니다.

- 🐛 버그·질문 → [Issues](https://github.com/younghwan91/krx-news-rest-api/issues)
- 📈 업데이트 소식 → [팔로우 @younghwan91](https://github.com/younghwan91)

## 관련 프로젝트 — 한국 주식 퀀트 스택

시세·펀더멘탈·뉴스 수집 REST API부터 데이터 파이프라인, 백테스트·알파 리서치까지 이어지는 오픈소스 스택의 일부입니다.

| 프로젝트 | 설명 |
|---|---|
| **[kiwoom-rest-api](https://github.com/younghwan91/kiwoom-rest-api)** | 키움증권 REST API Python 라이브러리 — 207개 엔드포인트 + 실시간 WebSocket |
| **[krx-fundamentals-api](https://github.com/younghwan91/krx-fundamentals-api)** | 국내 기업 펀더멘탈 REST API — 재무제표·투자지표·배당·종목 스크리닝 (DART + KRX + 네이버) |
| **[quant-airflow](https://github.com/younghwan91/quant-airflow)** | 시세·수급·실적 데이터를 TimescaleDB로 수집하는 Airflow 파이프라인 |
| **[kr-quant](https://github.com/younghwan91/kr-quant)** | 코스피·코스닥 알파 리서치 — walk-forward·랜덤 음성대조를 강제하는 검증 가드레일 |
| **[quantbox-engine](https://github.com/younghwan91/quantbox-engine)** | 암호화폐 선물 백테스트·실행 엔진 — 룩어헤드 0, 백테스트↔실거래 일체화 |
| **[opt_portfolio](https://github.com/younghwan91/opt_portfolio)** | VAA 기반 전술적 자산배분 백테스트·운용 시스템 |
| **[automated-stock-trading-systems](https://github.com/younghwan91/automated-stock-trading-systems)** | Bensdorp의 7개 비상관 트레이딩 시스템 백테스터 (교육용 재구현) |

## 만든 사람

**채영환 (Younghwan Chae)** · [GitHub @younghwan91](https://github.com/younghwan91) · [LinkedIn](https://www.linkedin.com/in/younghwan-chae/)

전체 오픈소스 퀀트 스택은 [프로필](https://github.com/younghwan91)에서 한눈에 볼 수 있습니다.
