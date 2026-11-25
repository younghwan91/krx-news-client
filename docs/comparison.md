# 다른 방법과 비교: OpenDART 직접 호출 · 네이버 금융 스크래핑 · pykrx/FinanceDataReader

한국 주식 뉴스·공시를 코드로 받는 방법은 여럿입니다. 이 문서는 각 방법이 무엇을 다루는지, krx-news-client가 그 위에 무엇을 더하는지를 정리합니다. 다른 도구에 대한 설명은 각 프로젝트의 공식 문서를 기준으로 썼고, 확인한 날짜와 출처를 함께 적었습니다(확인일 2026-11-26).

[English](comparison.en.md) · [README](../README.md)

## 한눈에 보기

| | OpenDART 직접 호출 | 네이버 | pykrx | FinanceDataReader | krx-news-client |
|---|---|---|---|---|---|
| 공시 목록 | ✅ 공식 API | — | — | — | ✅ OpenDART를 감쌈 |
| 공시 원문 | ✅ `document.xml`(zip) | — | — | — | ✅ 압축 해제·본문 텍스트까지 |
| 뉴스 제목·요약 | — | ✅ 검색 API(키워드) | — | — | ✅ 토스증권 피드 |
| 기사 본문 | — | 검색 API는 요약만 | — | — | ✅ 토스 기사 상세 |
| 종목코드로 뉴스 찾기 | — | 키워드 검색 | — | — | ✅ 종목별 뉴스 페이징 |
| 시세·시가총액·PER/PBR | — | — | ✅ | ✅ | — (다루지 않음) |
| 키·계정 | 인증키 | 검색 API는 Client ID·Secret | 일부 API는 KRX 회원 계정 | 소스에 따라 | DART만 인증키 |
| 반환 형식 | 원본 JSON | 원본 JSON | pandas DataFrame | pandas DataFrame | Pydantic 모델 |

정리하면 pykrx와 FinanceDataReader는 **시세·지표** 도구이고, OpenDART와 네이버 검색 API는 **원천 API**입니다. krx-news-client는 그 사이에서 **공시와 뉴스를 같은 모델로 묶는 얇은 클라이언트**입니다. 시세나 재무가 필요하면 pykrx·FinanceDataReader·[krx-fundamentals-client](https://github.com/younghwan91/krx-fundamentals-client)를 함께 쓰면 됩니다.

## OpenDART 직접 호출

금융감독원의 공식 Open API입니다. 공시정보, 정기보고서 주요정보, 정기보고서 재무정보, 지분공시 종합정보, 주요사항보고서 주요정보, 증권신고서 주요정보의 6개 묶음을 제공합니다.

- 40자리 인증키(`crtfc_key`)가 필요합니다.
- 공시검색(`list.json`)은 한 페이지에 최대 100건(`page_count`)이고, 기업(`corp_code`)을 지정하지 않으면 검색 기간이 3개월로 제한됩니다.
- 요청이 한도를 넘으면 status `020`을 돌려줍니다. 문서에는 "일반적으로 20,000건 이상"이라고 적혀 있습니다. 결과가 없을 때는 `013`입니다.
- 응답의 접수일자 `rcept_dt`는 날짜(YYYYMMDD)만 있고 시각은 없습니다.

출처: [OpenDART 공시검색 개발가이드](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019001), [OpenDART 소개](https://opendart.fss.or.kr/intro/main.do)

**krx-news-client가 더하는 것**

- 전 페이지를 넘겨 `Disclosure` 모델로 돌려줍니다(`scrape_disclosures`). 시각은 KST tz가 붙은 `datetime`입니다(접수일 00:00 KST).
- 3개월 제한을 `search_disclosures_range`가 달력 분기로 쪼개 여러 해 백필을 한 번에 부릅니다.
- 키를 여러 개 주면 `020`이 난 키에서 다음 키로 넘어가고, 모든 키가 소진되면 `DartQuotaExceededError`를 올립니다. "공시 없음(013)"과 "한도 초과(020)"를 구분합니다.
- `fetch_document`가 원문 zip을 풀어 마크업과 태그를 걷어낸 본문 텍스트를 함께 줍니다.
- 정정 공시 여부(`is_correction`), 접수번호 기준 중복 제거(`Deduplicator`), 로그에서 키 가리기가 들어 있습니다.

**직접 호출이 더 나은 경우**: 재무정보·지분공시 같은 공시검색 외의 API가 필요하거나, 특정 기업(`corp_code`)만 좁혀 검색하고 싶을 때입니다. krx-news-client는 공시검색과 원문만 다루고, 종목별 공시는 전체 시장을 받아 `ticker`로 거릅니다.

### 코드 비교: 하루치 공시 목록

OpenDART를 `httpx`로 직접 부르면 다음과 같습니다.

```python
import httpx

params = {"crtfc_key": KEY, "bgn_de": "20261125", "end_de": "20261125", "page_count": 100}
rows, page = [], 1
while True:
    data = httpx.get("https://opendart.fss.or.kr/api/list.json", params={**params, "page_no": page}).json()
    if data["status"] == "013":          # 결과 없음
        break
    if data["status"] != "000":          # 020 = 한도 초과 등
        raise RuntimeError(data["message"])
    rows += data["list"]
    if page >= data["total_page"]:
        break
    page += 1
for row in rows:
    print(row["rcept_dt"], row["corp_name"], row["report_nm"].strip())  # 날짜는 문자열
```

krx-news-client로는 다음과 같습니다.

```python
async with DartScraper.from_env() as dart:   # DART_API_KEY, _2, _3
    for d in await dart.scrape_disclosures(bgn_de="20261125", end_de="20261125"):
        print(d.published_at, d.company, d.title, d.is_correction)  # tz 있는 datetime
```

## 네이버

네이버로 뉴스를 받는 방법은 두 가지입니다.

**네이버 검색 API(뉴스)** 는 공식 API입니다. Client ID·Secret이 필요하고, 키워드로 검색해 `title`·`originallink`·`link`·`description`·`pubDate`를 돌려줍니다. `description`은 본문 요약이고, 한 번에 최대 100건(`display`), 시작 위치는 최대 1,000(`start`), 하루 25,000회까지 부를 수 있습니다. 정렬은 정확도순·날짜순입니다. 출처: [NAVER API HUB 뉴스 검색 문서](https://api.ncloud-docs.com/docs/naver-api-hub-search-news)

- 키워드 검색이라 종목코드 필드가 없습니다. "삼성전자"로 찾으면 다른 맥락의 기사도 함께 옵니다.
- 공시는 다루지 않습니다.
- 시장 전체를 넓게 훑거나 언론사 원문 링크가 필요할 때는 좋은 선택입니다.

**네이버 금융 페이지 스크래핑** 은 공식 API가 아닙니다. 2026-11-26 확인 시 `finance.naver.com/robots.txt`와 `m.stock.naver.com/robots.txt` 모두 일반 크롤러에 `Disallow: /`를 두고 있고, 예전에 많이 쓰던 종목 뉴스 목록 경로(`/item/news_news.naver`)는 HTTP 410을 돌려줬습니다. HTML 구조가 바뀌면 파서를 고쳐야 한다는 점도 감안해야 합니다.

**krx-news-client와의 차이**: krx-news-client는 네이버를 쓰지 않습니다. 뉴스는 토스증권에서 받는데, 토스는 기사마다 종목코드(`stockCodes`)를 붙여 주므로 종목코드로 바로 뉴스를 찾고, 기사 상세에서 본문 전체·요약 문장·감성 라벨·언론사 원문 URL을 받습니다. 대신 토스는 **비공식 내부 API**라 예고 없이 막힐 수 있습니다(아래 "한계" 참고).

## pykrx

KRX 정보데이터시스템의 데이터를 pandas로 받는 라이브러리입니다. 종목 목록, OHLCV, 시가총액, PER/PBR/배당수익률, 투자자별 거래, 외국인 보유, 공매도, 지수, ETF/ETN/ELW, 국채 수익률 함수를 제공합니다. KRX 로그인이 필요한 API는 `KRX_ID`·`KRX_PW` 환경변수로 KRX 회원 계정을 넣어야 합니다. 뉴스와 DART 공시 함수는 없습니다. 출처: [pykrx README](https://github.com/sharebook-kr/pykrx)

## FinanceDataReader

국내외 가격 데이터를 pandas로 받는 라이브러리입니다. `DataReader`로 KRX·미국·글로벌 주식, 지수, 환율, 암호화폐, 원자재 선물, 미국 국채, FRED 시계열을, `StockListing`으로 KRX·미국·중국·홍콩·일본·베트남 상장 목록을, `SnapDataReader`로 KRX 지수 구성종목과 네이버 재무제표를 받습니다. 뉴스와 공시 함수는 없습니다. 출처: [FinanceDataReader README](https://github.com/FinanceData/FinanceDataReader)

### 같이 쓰기: 시세와 뉴스를 한 표로

pykrx나 FinanceDataReader는 krx-news-client와 겹치지 않으므로 함께 쓰는 경우가 많습니다. 예를 들어 일봉 옆에 그날 공시 건수를 붙일 수 있습니다.

```python
from collections import Counter
from pykrx import stock

ohlcv = stock.get_market_ohlcv("20261101", "20261125", "005930")      # pykrx: 일봉
async with DartScraper.from_env() as dart:
    filings = [d for d in await dart.scrape_disclosures(bgn_de="20261101", end_de="20261125")
               if d.ticker == "005930"]
counts = Counter(d.published_at.date() for d in filings)
ohlcv["공시건수"] = [counts.get(day, 0) for day in ohlcv.index.date]
```

## 어떤 걸 쓰면 되나

| 하고 싶은 일 | 추천 |
|---|---|
| 시세·시가총액·투자자별 거래 | pykrx, FinanceDataReader |
| 재무제표·펀더멘탈 | OpenDART 재무정보 API, [krx-fundamentals-client](https://github.com/younghwan91/krx-fundamentals-client) |
| 키워드로 언론 기사 넓게 검색 | 네이버 검색 API |
| 공시 목록·원문을 모델로, 여러 해 백필 | krx-news-client |
| 종목코드로 뉴스와 공시를 한 타임라인에 | krx-news-client |

## 한계

- 토스증권은 비공식 내부 API입니다. 2026-11-26 확인 시 토스가 브라우저 세션 쿠키 없는 요청을 `400 invalid-client-state`로 거절하고 있어 토스 기능(`TossScraper`)이 동작하지 않습니다. DART 기능은 영향이 없습니다. 진행 상황은 [CHANGELOG](../CHANGELOG.md)에 적습니다.
- 시세·재무는 다루지 않습니다.
- DART 공시의 시각은 접수일 00:00 KST입니다. OpenDART가 시각을 주지 않기 때문입니다.
