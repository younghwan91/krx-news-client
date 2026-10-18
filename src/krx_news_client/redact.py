"""로그·예외 메시지에서 DART API 키를 가린다.

DART OpenAPI 는 키(``crtfc_key``)를 URL 쿼리로만 받는다. 그래서 요청 URL 이 찍히는
곳 -- httpx 의 ``HTTP Request: GET …`` INFO 로그, ``raise_for_status`` 가 만드는
``HTTPStatusError`` 메시지(``for url '…'``), 그걸 받아 적는 ``logger.exception`` --
마다 키가 그대로 남는다(2026-10-18 ``scripts/make_hero.py`` 에서 터미널 노출).

전역 로그 레벨을 낮추는 식으로 숨기지 않는다 -- 사용자 로깅 설정은 그대로 두고,
레코드와 예외의 문자열에서 ``crtfc_key=…`` 값만 ``***`` 로 바꾼다.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Mapping

_KEY_PATTERN = re.compile(r"(crtfc_key=)[^&\s\"'#]+")
_MASK = r"\1***"

#: ``DartScraper`` 가 만들어질 때 필터를 거는 로거. httpx 는 요청 URL 을 INFO 로
#: 찍고, httpcore 는 DEBUG 트레이스(지금은 URL 이 없지만 형식이 바뀔 수 있다),
#: 나머지는 이 라이브러리가 예외·URL 을 로그에 쓰는 모듈이다.
MASKED_LOGGERS: tuple[str, ...] = (
    "httpx",
    "httpcore",
    "krx_news_client.scrapers.base",
    "krx_news_client.scrapers.dart",
)


def mask_secrets(text: str) -> str:
    """``crtfc_key=<값>`` 을 ``crtfc_key=***`` 로 바꾼 문자열을 돌려준다."""
    return _KEY_PATTERN.sub(_MASK, text)


def _mask_arg(value: object) -> object:
    """문자열이거나(예: ``httpx.URL``) 문자열화했을 때 키가 보이는 인자만 가린다."""
    if isinstance(value, str):
        return mask_secrets(value)
    try:
        text = str(value)
    except Exception:  # noqa: BLE001 - 로그 필터가 로깅을 깨뜨리면 안 된다
        return value
    return mask_secrets(text) if _KEY_PATTERN.search(text) else value


def scrub_exception(exc: BaseException) -> BaseException:
    """예외(와 ``__cause__``/``__context__`` 사슬)의 문자열 인자에서 키를 가린다.

    ``httpx.HTTPStatusError`` 는 ``str(e)`` 가 요청 URL 을 품는다. 타입·``request``·
    ``response`` 속성은 그대로 두고 메시지만 바꾸므로 호출부의 ``except`` 는 그대로다.
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if any(isinstance(a, str) and _KEY_PATTERN.search(a) for a in current.args):
            current.args = tuple(_mask_arg(a) for a in current.args)
        current = current.__cause__ or current.__context__
    return exc


class SecretMaskingFilter(logging.Filter):
    """``LogRecord`` 의 메시지·인자·예외에서 키를 가린다. 레코드를 버리지는 않는다."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = mask_secrets(record.msg)
        args = record.args
        if isinstance(args, Mapping):
            record.args = {k: _mask_arg(v) for k, v in args.items()}
        elif isinstance(args, tuple):
            record.args = tuple(_mask_arg(a) for a in args)
        if record.exc_info and isinstance(record.exc_info, tuple) and record.exc_info[1]:
            scrub_exception(record.exc_info[1])
        if record.exc_text:
            record.exc_text = mask_secrets(record.exc_text)
        return True


def install_log_masking(logger_names: Iterable[str] = MASKED_LOGGERS) -> None:
    """로거마다 ``SecretMaskingFilter`` 를 한 번만 건다(여러 번 불러도 중복되지 않는다)."""
    for name in logger_names:
        target = logging.getLogger(name)
        if not any(isinstance(f, SecretMaskingFilter) for f in target.filters):
            target.addFilter(SecretMaskingFilter())
