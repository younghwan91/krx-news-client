# krx-news-client

[![CI](https://github.com/younghwan91/krx-news-client/actions/workflows/ci.yml/badge.svg)](https://github.com/younghwan91/krx-news-client/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/github/license/younghwan91/krx-news-client)](https://github.com/younghwan91/krx-news-client/blob/main/LICENSE)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-younghwan--chae-0A66C2?logo=linkedin&logoColor=white)](https://www.linkedin.com/in/younghwan-chae/)

**한국 주식시장의 뉴스·공시를 모아 하나의 스키마로 내주는 Python 클라이언트 라이브러리** — DART, 토스증권.

매체마다 HTML 구조도 갱신 주기도 제각각이라, 뉴스를 쓰려는 쪽이 매번 크롤러를 다시 짜게 된다. 그 일을 한 번만 하려고 만들었다. [kiwoom-client](https://github.com/younghwan91/kiwoom-client)와 같은 성격의 라이브러리다 — 서버를 띄우지 않고, 호출한 프로세스 안에서 그때그때 매체에 직접 요청해 정규화된 결과를 돌려준다.

## 설치

Python 3.11 이상.

```bash
pip install krx-news-client
```

## 빠른 시작

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

실행하면 이런 식으로 출력된다:

```
KR 코스피, 외국인 순매수에 2%대 상승 마감 2025-06-10 15:30:00+09:00
US 엔비디아, 실적 발표 앞두고 강세 2025-06-10 14:05:00+09:00
...
```

토스 대시보드 피드는 **현재 스냅샷**이다. 해외(`nation="US"`) 기사가 절반 넘게 섞여 있고, 본문(`content`)은 비어 있으며, 과거로 넘길 수 없다. 본문과 과거 기사는 따로 가져온다:

```python
from datetime import date
from krx_news_client import TossScraper

async with TossScraper() as scraper:
    detail = await scraper.fetch_article_detail(articles[0].url)  # 본문 전체·감성 라벨·언론사 원문 URL
    history = await scraper.scrape_company_news(                  # 종목별 뉴스, 과거로 페이징
        "005930", since=date(2025, 6, 1), max_pages=20     # date 는 그날 00:00 KST
    )
    items, _ = await scraper.company_news_page("005930", number=1)  # 원본 dict 한 페이지
```

DART 공시는 API 키가 필요하다:

```python
from krx_news_client import DartScraper

async with DartScraper(api_key="...") as scraper:   # 또는 DartScraper.from_env()
    disclosures = await scraper.scrape_disclosures()  # 기본: 어제~오늘(KST), 전체 시장
```

날짜 범위·시장을 직접 지정하거나, 여러 키를 순환시켜 일 20,000건 한도를 넘는 대량 백필도 가능하다:

```python
scraper = DartScraper(api_key=["key1", "key2", "key3"])  # 한도 초과 시 다음 키로 자동 전환
disclosures = await scraper.scrape_disclosures(
    bgn_de="20250101", end_de="20250331", corp_cls="Y"  # Y=코스피, K=코스닥, N=코넥스
)
```

정규화된 `Disclosure`가 아니라 DART 원본 응답이 필요하면 `search_disclosures`(한 페이지)/`search_disclosures_all`(전 페이지)/`search_disclosures_range`(여러 해·여러 시장)를 쓴다 — 결측을 조용히 넘기지 않고 `DartAPIError`를 그대로 올리는 엄격 경로라 백필에 적합하다. DART는 기업을 지정하지 않은 검색을 **달력 3개월**로 제한하는데, `search_disclosures_range`가 `quarter_ranges`로 알아서 쪼갠다:

```python
rows = await scraper.search_disclosures_range(bgn_de="20160901", end_de="20260915", corp_cls=["Y", "K"])
docs = await scraper.fetch_document(rows[0]["rcept_no"])  # 공시 원문(document.xml) → DisclosureDocument.text
```

폴링할 때는 `Deduplicator`로 처음 본 것만 넘긴다(기사는 `id`, 공시는 접수번호 기준):

```python
from krx_news_client import Deduplicator

dedup = Deduplicator()
while True:
    for article in dedup.filter_new(await toss.scrape_news()):
        handle(article)
    await asyncio.sleep(180)
```

같은 스크레이퍼를 `asyncio.run`으로 여러 번 불러도 된다 — 이벤트 루프가 바뀌면 HTTP 클라이언트를 새로 만든다(0.3.x까지는 두 번째 호출이 조용히 일부 결과를 잃었다).

더 많은 예제는 [`examples/`](examples/) 참고.

## 수집 소스

| 소스 | 데이터 | 수집 방식 |
|---|---|---|
| DART (dart.fss.or.kr) | 공시 목록·원문 | 공식 Open API (키 필요) |
| 토스증권 (tossinvest.com) | 대시보드 뉴스·기사 본문·종목별 뉴스 | 비공식 내부 API |

수집한 기사는 매체와 무관하게 `NewsArticle`, 공시는 `Disclosure` 한 벌로 정규화한다. 소스가 늘어도 호출 코드는 그대로다.

### 토스 사용 시 주의

토스는 **비공식 내부 API**라 예고 없이 막히거나 형식이 바뀔 수 있다. 형식이 바뀌면 종목별 뉴스 경로는 빈 결과 대신 `TossResponseError`를 올린다. 종목별 뉴스(`/api/v2/news/companies/{code}`)에서 직접 확인한 함정은 다음과 같다(2026-09-15).

- **코드는 6자리만** 받는다. `A005930`이나 ISIN을 넣으면 토스는 오류 없이 0건을 준다. 그래서 라이브러리가 `A` 접두어는 벗기고, 그 외 형식이면 `ValueError`를 낸다.
- **페이지 번호는 1부터** 시작한다. `number=0`이면 토스가 400을 주므로 호출 전에 `ValueError`를 낸다.
- **`lastPage`를 믿을 수 없다.** 페이지가 `size`보다 몇 건만 모자라도 뒤에 페이지가 남아 있는데 `True`가 온다. 그래서 `scrape_company_news`는 빈 페이지가 나올 때까지 넘긴다.
- **순서가 대략적이다.** 페이지 안에서도 정렬돼 있지 않고, 이웃 페이지끼리 시각이 하루쯤 겹친다. 그래서 `since`는 페이지 전체가 그보다 오래됐을 때만 멈추는 조건으로 쓰고, 결과는 id로 중복을 걷어낸 뒤 최신순으로 정렬해 돌려준다.
- **시장 전체 기사가 섞인다.** "코스피 마감" 같은 기사는 `stockCodes`가 없으므로 `tickers`가 비어 있다.

요청 간격은 `BaseScraper`의 0.5~1.5초 무작위 지연을 토스에도 그대로 쓴다. 비공식 API라 보수적으로 두는 편이 차단 위험이 낮기 때문이다. 속도가 필요하면 `scraper.min_delay`와 `scraper.max_delay`로 조절한다. DART는 공식 API이고 일한도만 제약이라 지연이 0이다.

## 응답 필드

`NewsArticle`

| 필드 | 설명 |
|---|---|
| `id` | 고유 ID (`{source}:{url의 md5 12자}`) |
| `source` | 소스 (`dart`/`toss`) |
| `category` | `disclosure`/`market`/`stock`/`economy`/`analysis`/`breaking` |
| `title` | 제목 |
| `url` | 원문 링크 |
| `content` | 본문 (`fetch_article_detail`·`scrape_company_news`에서 채워짐) |
| `summary` | 요약 |
| `tickers` | 관련 종목코드 목록. 한국 종목은 6자리(e.g. `005930`), 해외 종목은 토스 원본 코드 |
| `author` | 작성자·언론사 |
| `published_at` | 발행 시각 (KST, tz 포함) |
| `collected_at` | 수집 시각 |
| `news_id` | 토스 기사 ID |
| `nation` | 기사 대상 시장 (`KR`/`US`) |
| `sentiment` | 토스 감성 라벨 (상세 조회 시) |
| `original_url` | 언론사 원문 URL (상세 조회 시) |

`Disclosure`는 `id`·`source`·`title`·`url`·`published_at`·`collected_at`은 같고, `category`·`content`·`summary`·`tickers`·`author`는 없는 대신 다음이 있다.

| 필드 | 설명 |
|---|---|
| `company` · `ticker` | 회사명 · 종목코드 (비상장이면 빈 문자열) |
| `disclosure_type` | 공시 제목(`report_nm`) 그대로 |
| `rcept_no` | 접수번호 — 같은 날 공시의 순서, 중복 제거 키 |
| `corp_code` · `corp_cls` | DART 고유번호 · 법인구분(`Y`/`K`/`N`/`E`) |
| `rm` | DART 비고 |
| `is_correction` | `[기재정정]`·`[첨부정정]` 등으로 시작하는 정정 공시인가 |

`published_at`은 접수**일**의 00:00 KST다 — DART 목록 API에는 접수 시각이 없다.

## 구조

```mermaid
flowchart LR
    Caller["호출 프로세스\n(예: quant-airflow)"]

    subgraph Client["krx-news-client"]
        direction TB
        Toss["TossScraper\n.scrape_news()\n.fetch_article_detail()\n.scrape_company_news()"]
        Dart["DartScraper\n.scrape_disclosures()\n.search_disclosures_range()\n.fetch_document()"]
        Base["BaseScraper\nUA 순환 · 간격 조절(throttle)\n재시도 · 429 백오프"]
        Schema["schemas.py\nNewsArticle · Disclosure\nDisclosureDocument"]

        Toss --> Base
        Dart --> Base
        Toss -->|_make_article| Schema
        Dart -->|_make_disclosure| Schema
    end

    TossAPI[("토스증권\nwts-info-api\n(비공식 내부 API)")]
    DartAPI[("DART\nopendart.fss.or.kr\n(공식 Open API)")]

    Caller -->|await scraper.scrape_news()\n / scrape_disclosures()| Client
    Base -->|POST 대시보드 피드\nGET 기사 상세·종목별 뉴스| TossAPI
    Base -->|GET list.json\n/ document.xml| DartAPI
    Client -->|list[NewsArticle]\n / list[Disclosure]| Caller
```

`BaseScraper`가 재시도(429·5xx만)·429 백오프 등 공통 처리를 맡고, 각 스크레이퍼는 매체 응답을 파싱해 정규화된 스키마로 변환하는 일만 한다. DART는 키가 여럿이면 한도 초과 시 다음 키로 자동 전환하고, 전부 소진되면 `DartQuotaExceededError`를 던져 "공시 없음"(status=013)과 "한도 초과"(status=020)를 구분할 수 있게 한다. 그 외 오류 상태는 `DartAPIError` — `search_disclosures*`는 이를 그대로 올리고(엄격), `scrape_disclosures`는 페이지 단위로 로그만 남기고 계속한다(관용적, 실시간 폴링용).

저장이 필요하면 호출하는 쪽에서 알아서 한다 (예: [quant-airflow](https://github.com/younghwan91/quant-airflow)가 이 라이브러리로 수집해 TimescaleDB에 적재).

## 라이선스

Apache License 2.0 — 전문은 [LICENSE](LICENSE) 참조.

## ⭐ 도움이 되셨다면

이 프로젝트가 유용했다면 우측 상단 **[⭐ Star](https://github.com/younghwan91/krx-news-client)** 를 눌러주세요. 검색·추천 노출이 올라가 더 많은 분들이 찾을 수 있습니다.

- 🐛 버그·질문 → [Issues](https://github.com/younghwan91/krx-news-client/issues)
- 📈 업데이트 소식 → [팔로우 @younghwan91](https://github.com/younghwan91)

## 관련 프로젝트 — 오픈소스 퀀트 스택

한국·미국 주식과 암호화폐를 아우르는 오픈소스 스택입니다. 각 저장소는 독립적으로 쓸 수 있습니다.

| 축 | 프로젝트 | 설명 |
|---|---|---|
| 🇰🇷 한국 주식 | **[kiwoom-client](https://github.com/younghwan91/kiwoom-client)** | 키움증권 REST API Python 라이브러리 — 국내주식 엔드포인트 전수·실시간 WebSocket, sync + async (`pip install kiwoom-client`) |
| 🇰🇷 한국 주식 | **[krx-fundamentals-client](https://github.com/younghwan91/krx-fundamentals-client)** | 국내 기업 펀더멘탈 Python 클라이언트 라이브러리 — 재무제표·투자지표·배당·종목 스크리닝 (DART + KRX + 네이버) |
| 🇰🇷 한국 주식 | **[krx-quant-core](https://github.com/younghwan91/krx-quant-core)** | 한국 주식 퀀트 시스템 공통 Python 코어 — KRX 호가·가격제한폭·세션 규칙, 시행일별 거래세 비용모델, 키움 주문 가드, DART 중대공시 위험 분류, 체결 시뮬레이션, Deflated Sharpe·purged CV 통계 |
| 🇰🇷 한국 주식 | **[fin-checkup](https://github.com/younghwan91/fin-checkup)** | 관심종목 위험 공시 텔레그램 알림 + DART·SEC 재무 건강검진 — 측정값과 사실만 전달한다 |
| 🇰🇷 한국 주식 | **[quant-airflow](https://github.com/younghwan91/quant-airflow)** | 시세·수급·실적을 TimescaleDB 로 수집하는 Airflow 파이프라인 — 상장폐지 종목까지 담아 생존편향을 막는다 |
| 🇰🇷 한국 주식 | **[swing-it](https://github.com/younghwan91/swing-it)** | 코스피·코스닥 알파 심사 프레임워크 — 개별 트레이드 분포로 판정하고 랜덤 음성대조·purged CV·Deflated Sharpe 를 CI 가드레일로 강제 |
| 🇺🇸 미국 주식 | **[portfolio-research](https://github.com/younghwan91/portfolio-research)** | 미국주식 팩터 엔진 — point-in-time·생존편향 보정 데이터 위에서 walk-forward 를 Deflated Sharpe·PBO 로 게이팅 (+ ETF 전술배분 TAA — 9개 사전등록, 채택 0) |
| 🇺🇸 미국 주식 | **[automated-stock-trading-systems](https://github.com/younghwan91/automated-stock-trading-systems)** | Bensdorp 의 7개 비상관 트레이딩 시스템 백테스터 (교육용 재구현) |
| ₿ 암호화폐 | **[binance-quant-engine](https://github.com/younghwan91/binance-quant-engine)** | 암호화폐 선물 백테스트·실행 엔진 — 룩어헤드 0, 백테스트↔실거래 일체화 |

## 만든 사람

**채영환 (Younghwan Chae)** · [GitHub @younghwan91](https://github.com/younghwan91) · [LinkedIn](https://www.linkedin.com/in/younghwan-chae/)

전체 오픈소스 퀀트 스택은 [프로필](https://github.com/younghwan91)에서 한눈에 볼 수 있습니다.
