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
    scraper = TossScraper()
    try:
        articles = await scraper.scrape_news()
        for article in articles[:5]:
            print(article.title, article.published_at)
    finally:
        await scraper.close()

asyncio.run(main())
```

실행하면 이런 식으로 출력된다:

```
코스피, 외국인 순매수에 2%대 상승 마감 2025-06-10 15:30:00+09:00
삼성전자, 3분기 실적 시장 예상 상회 2025-06-10 14:05:00+09:00
...
```

DART 공시는 API 키가 필요하다:

```python
from krx_news_client import DartScraper

scraper = DartScraper(api_key="...")
disclosures = await scraper.scrape_disclosures()
```

더 많은 예제는 [`examples/`](examples/) 참고.

## 수집 소스

| 소스 | 데이터 | 수집 방식 |
|---|---|---|
| DART (dart.fss.or.kr) | 공시 | 공식 Open API (키 필요) |
| 토스증권 (tossinvest.com) | 뉴스 | 비공식 내부 API |

수집한 기사는 매체와 무관하게 `NewsArticle`, 공시는 `Disclosure` 한 벌로 정규화한다. 소스가 늘어도 호출 코드는 그대로다.

## 응답 필드

`NewsArticle`

| 필드 | 설명 |
|---|---|
| `id` | 고유 ID (`{source}:{url의 md5 12자}`) |
| `source` | 소스 (`dart`/`toss`) |
| `category` | `disclosure`/`market`/`stock`/`economy`/`analysis`/`breaking` |
| `title` | 제목 |
| `url` | 원문 링크 |
| `content` | 본문 (있는 경우) |
| `summary` | 요약 |
| `tickers` | 관련 종목코드 목록 (e.g. `005930`) |
| `author` | 작성자·언론사 |
| `published_at` | 발행 시각 |
| `collected_at` | 수집 시각 |

`Disclosure`는 `id`·`source`·`title`·`url`·`published_at`·`collected_at`은 같고, `category`·`content`·`summary`·`tickers`·`author`는 없는 대신 `company`·`ticker`·`disclosure_type`(공시 유형)이 있다.

## 구조

```mermaid
flowchart LR
    Caller["호출 프로세스\n(예: quant-airflow)"]

    subgraph Client["krx-news-client"]
        direction TB
        Toss["TossScraper\n.scrape_news()"]
        Dart["DartScraper\n.scrape_disclosures()"]
        Base["BaseScraper\nUA 순환 · 간격 조절(throttle)\n재시도 · 429 백오프"]
        Schema["schemas.py\nNewsArticle · Disclosure"]

        Toss --> Base
        Dart --> Base
        Toss -->|_make_article| Schema
        Dart -->|_make_disclosure| Schema
    end

    TossAPI[("토스증권\nwts-info-api\n(비공식 내부 API)")]
    DartAPI[("DART\nopendart.fss.or.kr\n(공식 Open API)")]

    Caller -->|await scraper.scrape_news()\n / scrape_disclosures()| Client
    Base -->|POST 대시보드 피드| TossAPI
    Base -->|GET list.json| DartAPI
    Client -->|list[NewsArticle]\n / list[Disclosure]| Caller
```

`BaseScraper`가 재시도·429 백오프 등 공통 처리를 맡고, 각 스크레이퍼는 매체 응답을 파싱해 정규화된 스키마로 변환하는 일만 한다. DART는 일한도(status=020) 소진 시 `DartQuotaExceededError`를 던져 "공시 없음"과 "한도 초과"를 구분할 수 있게 한다.

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
| 🇰🇷 한국 주식 | **[fin-checkup](https://github.com/younghwan91/fin-checkup)** | 관심종목 위험 공시 텔레그램 알림 + DART·SEC 재무 건강검진 — 측정값과 사실만 전달한다 |
| 🇰🇷 한국 주식 | **[quant-airflow](https://github.com/younghwan91/quant-airflow)** | 시세·수급·실적을 TimescaleDB 로 수집하는 Airflow 파이프라인 — 상장폐지 종목까지 담아 생존편향을 막는다 |
| 🇰🇷 한국 주식 | **[kr-quant](https://github.com/younghwan91/kr-quant)** | 코스피·코스닥 알파 리서치 — walk-forward·랜덤 음성대조·purged CV·Deflated Sharpe 를 CI 가드레일로 강제 |
| 🇺🇸 미국 주식 | **[portfolio-research](https://github.com/younghwan91/portfolio-research)** | 미국주식 팩터 엔진 — point-in-time·생존편향 보정 데이터 위에서 walk-forward 를 Deflated Sharpe·PBO 로 게이팅 (+ ETF 전술배분 TAA — 9개 사전등록, 채택 0) |
| 🇺🇸 미국 주식 | **[automated-stock-trading-systems](https://github.com/younghwan91/automated-stock-trading-systems)** | Bensdorp 의 7개 비상관 트레이딩 시스템 백테스터 (교육용 재구현) |
| ₿ 암호화폐 | **[quantbox-engine](https://github.com/younghwan91/quantbox-engine)** | 암호화폐 선물 백테스트·실행 엔진 — 룩어헤드 0, 백테스트↔실거래 일체화 |

## 만든 사람

**채영환 (Younghwan Chae)** · [GitHub @younghwan91](https://github.com/younghwan91) · [LinkedIn](https://www.linkedin.com/in/younghwan-chae/)

전체 오픈소스 퀀트 스택은 [프로필](https://github.com/younghwan91)에서 한눈에 볼 수 있습니다.
