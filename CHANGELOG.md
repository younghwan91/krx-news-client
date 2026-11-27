# 변경 이력

이 프로젝트는 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/) 형식을 따르며,
[유의적 버전](https://semver.org/lang/ko/)을 사용합니다.

## [Unreleased]

토스가 세션 없는 요청을 막은 뒤(2026-11-26) 뉴스 절반이 끊긴 것을 공식·공개 소스로 되살린다.
토스 차단을 우회(브라우저 세션·쿠키·헤더 위조)하지 않는다 -- 접근 통제다.

### Added

- **`YonhapScraper` -- 키 없는 연합뉴스 RSS.** 마켓+·경제·산업·전체 섹션 피드를 `NewsArticle`로 돌려준다.
  `tickers`는 제목·요약의 `회사명[005930]` 표기에서 뽑고, `pubDate`는 KST tz로 읽는다. 공개 RSS만 읽고
  기사 페이지는 긁지 않는다. 2026-11-26 확인: robots `Allow: /`(`/rss/` 허용), RSS 안내는 "비상업적
  블로그와 개인 용도만 허용", 피드 `copyright`는 "AI 학습 및 활용 금지". 정직한 User-Agent를 보낸다.
- **`NaverNewsScraper` -- 네이버 검색 API(뉴스).** `from_env()`가 `NAVER_CLIENT_ID`·`NAVER_CLIENT_SECRET`을
  읽고, 없으면 발급 방법을 담은 `NaverKeyMissingError`를 낸다. `search_news(query, tickers=..., since=...)`는
  최신순으로 최대 1,099건(`start` ≤ 1000)까지 넘기고, `display`·`start`·`sort` 범위 밖 인자는 요청 전에
  `ValueError`, API 오류는 `NaverAPIError`(401/403이면 키 안내 포함). 약관(2026-11-26 확인)상 결과 저장·
  캐싱(서버 21일 초과), AI 입력, 제3자 제공이 금지라 README "뉴스 소스와 이용 조건"에 적었다.
- **`TossBlockedError`(`TossResponseError` 하위).** 토스가 `400 invalid-client-state`를 주면 재시도 없이
  이 예외를 올리고 메시지에 대체 소스를 적는다. `scrape_news(strict=False)`도, `fetch_article_detail`
  (원래 400을 `None`으로 바꾸던 경로)도 이걸 삼키지 않는다 -- 조용한 0건·None이 되지 않게.
- `NewsSource.NAVER`·`NewsSource.YONHAP`.
- **`krx-news` CLI.** `uvx krx-news-client`(또는 설치 후 `krx-news`) 한 줄이면 키 없이 연합뉴스 마켓+ 최신
  기사가 나온다. `watch`(새 기사 60초·공시 5분 간격, 처음 본 것만), `dart`(종목·제목 키워드·시장 필터),
  `doc`(공시 원문 텍스트), `search`(네이버), `--json`. 표준 라이브러리 `argparse`만 써 의존성이 늘지 않는다.
  폴링 간격 하한(RSS 30초, DART 120초)을 둬 공개 피드와 DART 일한도를 지킨다 -- DART 전체 시장 검색은
  한 번에 수십 호출이라 `watch`는 오늘 공시만 본다.
- **MCP 서버 `krx-news-client-mcp`(`krx-news-client[mcp]`).** 도구 `recent_disclosures`·`read_disclosure`와
  프롬프트 `disclosure_briefing`. DART 전용이다 -- 연합뉴스 RSS("AI 학습 및 활용 금지")와 네이버 검색 API
  (AI 입력 금지)는 약관상 LLM 입력으로 줄 수 없어 넣지 않았다. 잘못된 인자·DART 오류는 메시지째 돌려줘
  에이전트가 고쳐 부를 수 있게 했다. MCP 레지스트리용 `server.json`.
- **`krx_news_client.queries`.** CLI 와 MCP 가 같이 쓰는 `recent_disclosures`(0~7일, 접수번호 역순)·
  `disclosure_text`·`stock_code`. 잘못된 종목코드·기간·접수번호는 요청 전에 `ValueError`. 2026-11-27 실 DART로
  `dart`·`doc`·MCP stdio 왕복을 확인했고, 방금 접수된 공시는 원문이 아직 없어 DART가 `014`를 준다(한 줄 오류로 보임).

### Changed

- **README 빠른 시작과 갤러리가 동작하는 소스로 시작한다.** 빠른 시작은 키 없는 `YonhapScraper`,
  갤러리는 DART·연합뉴스·네이버로 바꿨다. 토스 기사 본문을 LLM에 넣던 조각은 뉴스 소스 약관이 AI 이용을
  막아서 DART 공시 원문을 LLM 입력으로 만드는 조각으로 바꿨다. `examples/`·`llms.txt`·가이드도 맞췄다.
- 토스 소스는 지우지 않았다. 토스가 다시 열리면 그대로 동작한다.

### Fixed

- `Deduplicator`의 `max_size`가 1 미만이면 생성 시 `ValueError`를 발생시킨다.

## [0.5.1] - 2026-11-26

코드 변경은 없다. PyPI 페이지에 링크·키워드가 비어 있던 것을 채우는 메타데이터 릴리스다.

### Added

- **PyPI 메타데이터.** `project_urls`(Homepage·Documentation·Repository·Issues·Changelog),
  `keywords`, 분류자(라이선스·대상·`Typing :: Typed`)를 `pyproject.toml`에 넣었다.
- **[다른 방법과 비교](docs/comparison.md)(영문 `comparison.en.md`).** OpenDART 직접 호출·네이버·
  pykrx·FinanceDataReader가 다루는 범위와 코드 비교. 다른 도구 설명은 각 공식 문서 기준(2026-11-26 확인).
- **README 예제 갤러리와 실행 테스트.** 공시 알림·종목 뉴스 타임라인·뉴스+공시 타임라인·LLM 입력·
  공시 원문 5개 조각과 3줄 빠른 시작을 `tests/test_readme_gallery.py`가 목 응답으로 실행한다.

### Known issues

- **토스 요청이 `400 invalid-client-state`로 거절된다(2026-11-26 실측).** 대시보드 뉴스·종목별
  뉴스 모두 같은 응답이다. 브라우저에서는 `deviceId`·`SESSION` 등 세션 쿠키와 `app-version`·
  `browser-tab-id` 헤더가 붙은 요청이 200을 받는다(Playwright로 확인). 종목별 뉴스 화면은
  `/api/v2/news/companies/{code}/cursor` 경로도 쓴다. DART 기능은 영향이 없다.

## [0.5.0] - 2026-11-21

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

### Security

- **로그에 DART API 키가 찍히던 것을 막았다.** 키는 URL 쿼리(`crtfc_key`)로만 보낼 수 있어
  httpx 의 `HTTP Request: GET …` INFO 로그, `HTTPStatusError` 메시지(`for url '…'`),
  재시도 경고와 `scrape_disclosures` 의 예외 로그에 그대로 남았다(`logging.basicConfig(level=INFO)`
  만 켜도 터미널·CI 출력에 노출). 이제 `DartScraper` 를 만들 때 `httpx`·`httpcore`·라이브러리
  로거에 마스킹 필터를 한 번 걸고, 올리는 httpx 예외의 메시지에서도 값을 `crtfc_key=***` 로
  바꾼다. 로그 레벨은 건드리지 않는다. 직접 URL 을 로그에 쓰는 호출부는 `mask_secrets()` 를 쓸 것.

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
