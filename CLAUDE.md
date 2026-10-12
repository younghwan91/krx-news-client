# krx-news-client

토스증권·DART 뉴스/공시를 `NewsArticle`/`Disclosure` 로 정규화해 돌려주는 **클라이언트 라이브러리**(공개 PyPI 패키지).
사용법·토스 함정(코드 6자리·페이지 1부터·size≤100·오프셋 10,000·`lastPage` 불신)은 `README.md`, 변경 이력은 `CHANGELOG.md`.

## 명령

```bash
uv run --extra dev pytest tests/ -q        # ~100 tests, 1초 미만. HTTP 는 pytest-httpx 목
uv run --extra dev ruff check src tests    # CI 는 핀 없는 최신 ruff
```

## 설계 결정 (되돌리지 말 것)

- **서버가 아니다.** 예전 FastAPI+Redis 서버(krx-news-rest-api)를 걷어내고 kiwoom-client 식 라이브러리로 바꿨다(455d8fc) —
  사용자: "트레이딩 데이터 소스… 서버를 남한테 해줄 이유가 없다". 스케줄러·캐시·저장 계층을 다시 넣지 않는다. 저장은 호출자 몫
  (quant-airflow 가 TimescaleDB 에 적재, 폴링 중복 제거는 `Deduplicator`).
- **공통 데이터 로직은 이 레포로 올린다.** daytrade-it·scalp-it 에 흩어진 토스/DART 요청·파싱은 여기로 옮기고 소비자는 라이브러리를 쓴다
  (0.4.0 PR #6, 0.5.0 `fetch_article_detail_raw`). 결과는 백테스트·실매매 입력이라 시각(KST tz)·티커·중복이 틀리면 안 된다
  — 9시간 밀림 버그(86cc785) 전례.
- 토스는 비공식 내부 API 다. 동작을 바꾸기 전에 실제 요청으로 확인하고, 확인한 날짜와 결과를 README "토스 사용 시 주의"·CHANGELOG 에 남긴다.
  조용한 0건보다 `ValueError`/`TossResponseError` 가 낫다는 게 지금까지의 방침이다.
- DART: `search_disclosures*` 는 엄격(오류를 올림, 백필용), `scrape_disclosures` 는 관용(로그 후 계속, 폴링용). 이 구분을 섞지 않는다.

## 소비자와 릴리스

- 소비자: daytrade-it·scalp-it(`krx-news-client>=0.4.0`, PyPI), quant-airflow Docker 이미지(git sha 고정 86cc785).
  scalp-it 은 사전등록 연구라 `is_correction` 의 정정 표시 목록이 바뀌면 그쪽 테스트가 일부러 실패한다.
- 버전은 `pyproject.toml` + `CHANGELOG.md`. 태그 `vX.Y.Z` 푸시 → `publish.yml` 이 PyPI 배포. **태그·배포는 사용자가 정한다** —
  자율 작업은 PR 머지까지 하고 "태그는 사용자 몫"으로 보고한다(0.4.0 은 사용자 지시로 배포, 0.5.0 은 main 에만 있고 PyPI 미배포).
- DART 키(`DART_API_KEY`, `_2`, `_3`)는 `~/git/quant-airflow/.env` 에 있고 Airflow 수집과 같은 키다(키당 일 20,000건).
  실 API 로 대량 백필을 돌리면 그날 수집 한도를 먹는다 — 사용자 확인 후에.
- 공개 레포다. 커밋·README 에 키·사내 정보를 넣지 않는다.
