# 기여 가이드

krx-news-client 에 관심 가져 주셔서 감사합니다. 버그 제보, 문서 수정, 코드 기여를 모두 받습니다.
처음이라면 [good first issue](https://github.com/younghwan91/krx-news-client/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) 목록에서 시작하세요.

> English: PRs and issues in English are welcome. Short version: `uv run --extra dev pytest tests/ -q` and
> `uv run --extra dev ruff check src tests` must pass; use English Conventional Commits; open a PR from a branch.

## 개발 환경

Python 3.11 이상과 [uv](https://docs.astral.sh/uv/) 를 권장합니다.

```bash
git clone https://github.com/younghwan91/krx-news-client.git
cd krx-news-client
uv run --extra dev pytest tests/ -q     # 첫 실행 때 .venv 를 만들고 의존성을 설치합니다
```

uv 없이는 `python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"` 후 `pytest tests/ -q` 를 돌립니다.

## 테스트와 린트

```bash
uv run --extra dev pytest tests/ -q        # 1초 안팎
uv run --extra dev ruff check src tests    # CI 는 버전을 고정하지 않은 최신 ruff 를 씁니다
```

- 테스트의 HTTP 는 모두 [pytest-httpx](https://colin-b.github.io/pytest_httpx/) 목입니다. 토스·DART 서버에 실제 요청을 보내는 테스트는 받지 않습니다.
- DART 키(`DART_API_KEY`)나 토스 응답 원문을 커밋·이슈·PR 에 넣지 마세요.
- 토스는 비공식 내부 API 입니다. 동작을 바꿀 때는 실제 응답으로 확인한 날짜와 결과를 README 의 "토스 사용 시 주의" 에 남겨 주세요.
- 조용히 0건을 돌려주기보다 `ValueError`/`TossResponseError` 를 올리는 쪽이 이 라이브러리의 방침입니다.

## 커밋과 PR

1. `main` 에서 브랜치를 만듭니다(`feat/…`, `fix/…`, `docs/…`).
2. 커밋 메시지는 **영어 [Conventional Commits](https://www.conventionalcommits.org/)** 입니다(`fix(toss): handle empty page`). 본문에는 왜 바꿨는지 적어 주세요.
3. 새 동작에는 테스트를 붙이고 위 두 명령이 통과하는지 확인한 뒤 PR 을 엽니다. 작고 한 가지 일만 하는 PR 이 빨리 머지됩니다.
4. CI(ruff·pytest 3.11~3.13)가 통과해야 머지됩니다. 버전(`pyproject.toml`)과 태그는 메인테이너가 정합니다.

## 이슈

- 버그·기능 제안: [Issues](https://github.com/younghwan91/krx-news-client/issues)
- good first issue: [목록 보기](https://github.com/younghwan91/krx-news-client/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)
