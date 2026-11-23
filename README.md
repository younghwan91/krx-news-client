<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/brand/wordmark-dark.svg">
  <img alt="krx-news-client" src="docs/images/brand/wordmark-light.svg" height="52">
</picture>

# krx-news-client

**DART 공시와 토스증권 뉴스를 한 스키마로 받는 한국 주식 뉴스·공시 Python 클라이언트입니다.**

기사 본문, 종목별 과거 뉴스, 공시 원문까지 `pip install` 한 줄로 바로 씁니다.

[![CI](https://github.com/younghwan91/krx-news-client/actions/workflows/ci.yml/badge.svg)](https://github.com/younghwan91/krx-news-client/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/github/license/younghwan91/krx-news-client)](LICENSE)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-younghwan--chae-0A66C2?logo=linkedin&logoColor=white)](https://www.linkedin.com/in/younghwan-chae/)

[문서](docs/guide.md) · [예제](examples/) · [English](README.en.md) · [이슈 제보](https://github.com/younghwan91/krx-news-client/issues)

</div>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/hero-dark.png">
  <img alt="DART 공시와 토스증권 뉴스를 종목별 한 타임라인에 찍고, 두 출처가 같은 필드로 채워진 레코드 카드 두 장" src="docs/images/hero-light.png" width="100%">
</picture>

<p align="center"><sub>DART 공시와 토스증권 뉴스를 종목별 한 타임라인에 묶어 같은 필드로 돌려줍니다.</sub></p>

## 빠른 시작

```bash
pip install krx-news-client   # Python 3.11 이상
```

> `fetch_article_detail_raw`, 종목별 뉴스의 10,000건 오프셋 한계 처리, `size` 검증, DART 키 로그 마스킹은 PyPI 0.4.0 이후에 추가되어 현재 `main` 브랜치에만 있습니다. 최신 기능을 쓰려면 `pip install "krx-news-client @ git+https://github.com/younghwan91/krx-news-client"`로 설치하세요.

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

실행하면 국내(`KR`)와 해외(`US`) 최신 뉴스 제목과 KST 발행 시각이 출력됩니다.

```text
KR 코스피, 외국인 순매수에 2%대 상승 마감 2025-06-10 15:30:00+09:00
US 엔비디아, 실적 발표 앞두고 강세 2025-06-10 14:05:00+09:00
...
```

## 무엇을 하나

| 소스 | 데이터 | 수집 방식 |
|---|---|---|
| DART (dart.fss.or.kr) | 공시 목록·원문 | 공식 Open API (키 필요) |
| 토스증권 (tossinvest.com) | 대시보드 뉴스·기사 본문·종목별 뉴스 | 비공식 내부 API |

- **두 출처를 한 스키마로 묶습니다.** `Disclosure`와 `NewsArticle`이 `id`·`source`·`title`·`url`·`published_at`(KST, tz 포함)을 같은 이름으로 갖습니다.
- **조용한 0건 대신 예외를 올립니다.** 토스 응답 형식이 바뀌면 `TossResponseError`, 잘못된 종목코드나 페이지 크기는 `ValueError`, DART 일한도 소진은 `DartQuotaExceededError`를 냅니다.
- **종목별 과거 뉴스를 페이지로 넘깁니다.** `scrape_company_news()`로 최대 100건씩 토스가 허용하는 오프셋 10,000건까지 조회합니다.
- **DART 폴링과 백필을 나눕니다.** `scrape_disclosures()`는 다중 키 자동 전환과 관용적 폴링을, `search_disclosures*()`·`fetch_document()`는 엄격한 백필을 맡습니다.
- **중복을 걸러냅니다.** `Deduplicator`가 기사는 `id`, 공시는 접수번호(`rcept_no`) 기준으로 처음 본 항목만 넘깁니다.

상세 코드 예제는 [가이드](docs/guide.md#상세-사용법)와 [`examples/`](examples/)에서 볼 수 있습니다.

## 토스 사용 시 주의

토스는 비공식 내부 API라 예고 없이 막히거나 형식이 바뀔 수 있습니다.

- **코드는 6자리만 받습니다.** `A` 접두어는 자동으로 벗기며 그 외 형식은 요청 전에 `ValueError`를 냅니다.
- **페이지는 1부터, 크기는 100까지입니다.** `number=0`이나 `size=101` 이상은 요청 전에 `ValueError`를 냅니다.
- **오프셋 한계가 10,000건입니다.** `number × size`가 10,000을 넘기면 토스가 400을 주므로 대형주는 6개월에 못 미칩니다.
- **`lastPage`를 믿을 수 없습니다.** 빈 페이지가 나올 때까지 넘기고 `id`로 중복을 걷어낸 뒤 최신순으로 정렬합니다.

전체 주의사항과 응답 필드, 아키텍처는 [토스 사용 시 주의](docs/guide.md#토스-사용-시-주의)에 정리해 두었습니다.

## 문서

| 문서 | 내용 |
|---|---|
| [가이드](docs/guide.md) | 토스·DART 상세 사용법, 설계 배경, 토스 API 주의사항, 응답 필드, 구조 |
| [예제](examples/) | 기본 사용법과 종목 알림 폴링 예제 |
| [변경 이력](CHANGELOG.md) | 버전별 변경 사항 |

## 기여 및 지원

- 버그 제보, 질문, 기능 제안은 [GitHub Issues](https://github.com/younghwan91/krx-news-client/issues)에 남겨 주세요.
- 만든 사람: **채영환 (Younghwan Chae)** · [GitHub @younghwan91](https://github.com/younghwan91) · [LinkedIn](https://www.linkedin.com/in/younghwan-chae/)

## 라이선스

Apache License 2.0 — 전문은 [LICENSE](LICENSE)를 참고하세요.
