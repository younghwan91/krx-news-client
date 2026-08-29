# API 레퍼런스

서버 실행 후 [Swagger UI](http://localhost:8000/docs) / [ReDoc](http://localhost:8000/redoc) 에서 직접 호출해볼 수 있다. 이 문서는 그 요약본이다.

## 엔드포인트

| 메서드 | 엔드포인트 | 설명 | 파라미터 |
|-------|-----------|------|---------|
| `GET` | `/api/v1/news` | 전체 뉴스 목록 | `source`, `page`, `page_size` |
| `GET` | `/api/v1/news/search` | 키워드 검색 | `q` (필수), `page`, `page_size` |
| `GET` | `/api/v1/news/{source}` | 소스별 뉴스 | `page`, `page_size` |
| `GET` | `/api/v1/disclosure` | 공시 목록 | `source`, `ticker`, `page`, `page_size` |
| `GET` | `/api/v1/disclosure/{ticker}` | 종목별 공시 | `page`, `page_size` |
| `GET` | `/api/v1/status` | 크롤러 상태 | — |
| `GET` | `/health` | 헬스체크 | — |

**공통 파라미터**

- `page` — 페이지 번호 (기본 1, 최소 1)
- `page_size` — 페이지 크기 (기본 20, 최소 1, 최대 100)
- `source` — `kind`, `dart`, `naver`, `hankyung`, `thebell`

## 요청/응답 예시

### 최신 뉴스

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

### 검색 · 소스별 조회

```bash
curl "http://localhost:8000/api/v1/news/search?q=삼성전자"
curl "http://localhost:8000/api/v1/news/naver"
curl "http://localhost:8000/api/v1/news/hankyung"
```

검색은 캐시된 기사의 **제목·본문**에 질의어가 들어 있는지 보는 부분 문자열 매칭이다. 형태소 분석이나 랭킹은 없다.

### 공시

```bash
curl "http://localhost:8000/api/v1/disclosure"              # 전체
curl "http://localhost:8000/api/v1/disclosure/005930"       # 삼성전자
curl "http://localhost:8000/api/v1/disclosure?source=kind"  # KIND 만
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

### 크롤러 상태

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
  }
]
```

## 에러 응답

| 코드 | 의미 | 본문 |
|-----|------|------|
| `422` | 유효성 검증 실패 | FastAPI 기본 형식 |
| `503` | Redis 연결 실패 | `{"detail": "Cache service unavailable"}` |
| `500` | 서버 내부 에러 | `{"detail": "Internal server error"}` |

## 캐시 구조

| 데이터 | Redis 자료구조 | TTL | 키 |
|-------|--------------|-----|-----|
| 전체 뉴스 | Sorted Set (발행시간 score) | 1시간 | `news:all` |
| 소스별 뉴스 | List | 1시간 | `news:{source}` |
| 전체 공시 | Sorted Set | 24시간 | `disclosure:all` |
| 소스별 공시 | List | 24시간 | `disclosure:{source}` |
| 검색 결과 | String (JSON) | 5분 | `search:{query}:{page}:{size}` |
| 크롤러 상태 | String (JSON) | 없음 | `crawler:status:{source}` |

소스별 캐시는 크롤링할 때마다 `DELETE` 후 다시 채워지는 스냅샷이고, `*:all` Sorted Set 은 발행시간 기준으로 누적된다.
