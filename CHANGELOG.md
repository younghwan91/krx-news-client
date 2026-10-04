# 변경 이력

이 프로젝트는 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/) 형식을 따르며,
[유의적 버전](https://semver.org/lang/ko/)을 사용합니다.

## [Unreleased]

## [0.5.0] - 2026-10-05

### Added

- **`TossScraper.fetch_article_detail_raw()`.** 기사 상세 응답의 `result.kr` dict를
  그대로 돌려준다. `NewsArticle`이 버리는 본문 블록 구조(`type`·이미지)·`source.code`가
  필요한 호출부용 raw 경로로, `company_news_page`와 같은 성격이다. daytrade-it이
  원본 payload를 아카이브하려고 같은 요청을 따로 짜고 있던 것을 여기로 옮겼다.
  `fetch_article_detail`은 이 위에서 파싱만 한다.
- **`py.typed` 마커.** 타입 힌트를 소비자의 mypy/pyright가 읽는다(kiwoom-client와 동일).

### Fixed

- **토스 종목별 뉴스의 오프셋 한계(10,000건)에서 `scrape_company_news`가 HTTP 400으로
  죽었다.** `number × size > 10,000`이면 토스가 400 `bad-request.pagination-limit`을
  준다(2026-10-05 실측: size=100이면 101페이지, size=50이면 201페이지 — 페이지 수가 아니라
  오프셋 기준). 이제 그 직전 페이지에서 경고 로그를 남기고 모은 결과를 돌려준다. 토스가
  한계를 더 낮춰 2페이지 이후에 같은 400이 와도 마찬가지로 멈춘다(1페이지부터 400이면
  다른 문제라 그대로 올린다). `company_news_page`는 요청을 보내기 전에 `ValueError`.
- **`page_size > 100`이면 토스가 오류 없이 빈 페이지를 줘서 조용한 0건이 됐다.**
  `size`를 1~100으로 검사해 `ValueError`를 낸다.

## [0.4.0] - 2026-09-15

### Added

- 토스 기사 상세(`fetch_article_detail`)·종목별 뉴스(`scrape_company_news`·`company_news_page`),
  `news_id_from_url`·`normalize_stock_code`·`TossResponseError`.
- DART 원문(`fetch_document`)·3개월 분할 검색(`search_disclosures_range`·`quarter_ranges`)·
  `from_env`·`is_correction`.
- `Deduplicator`(폴링용 중복 제거), `async with` 지원.
- `NewsArticle`에 `news_id`·`news_type`·`nation`·`sentiment`·`original_url`,
  `Disclosure`에 `rcept_no`·`corp_code`·`corp_cls`·`rm`·`is_correction`.

### Fixed

- 같은 스크레이퍼로 `asyncio.run`을 두 번 부르면 두 번째 호출이 조용히 결측됐다
  (이벤트 루프가 바뀌면 HTTP 클라이언트를 새로 만든다).
