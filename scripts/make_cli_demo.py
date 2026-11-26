"""README 의 터미널 데모 그림(docs/images/cli-demo.png).

Run from the repo root:
    uv run --no-project --with playwright python scripts/make_cli_demo.py

그림의 글자는 ``docs/images/cli-demo.txt`` 를 그대로 쓴다. 그 파일은 실제 명령 출력을 캡처한
것이다(2026-11-27, `$ ` 줄이 실행한 명령). 다시 찍으려면 같은 명령을 돌려 파일을 바꾼 뒤 이
스크립트를 다시 돌린다. 색은 CLI 의 터미널 색(_Style)과 같은 규칙으로 입힌다.
"""

from __future__ import annotations

import re
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "images" / "cli-demo.txt"
OUT = ROOT / "docs" / "images" / "cli-demo.png"
WIDTH = 1200

_ROW = re.compile(r"^(\d\d-\d\d(?: \d\d:\d\d)?)(\s+)(?:(\d{6}|[0-9A-Z]{6}) )?(.*)$")


def render_line(line: str) -> str:
    if line.startswith("$ "):
        return f'<span class="prompt">$</span> <span class="cmd">{escape(line[2:])}</span>'
    if line.startswith(" " * 6):
        return f'<span class="dim">{escape(line)}</span>'
    if line.startswith("krx-news watch:"):
        return f'<span class="bold">{escape(line)}</span>'
    match = _ROW.match(line)
    if not match:
        return escape(line)
    when, gap, code, rest = match.groups()
    html = f'<span class="dim">{escape(when)}</span>{gap}'
    if code:
        html += f'<span class="code">{code}</span> '
    if "  " in rest and code:  # 공시 줄: 회사명 두 칸 띄고 제목
        company, title = rest.split("  ", 1)
        html += f'<span class="bold">{escape(company)}</span>  {escape(title)}'
    else:
        html += escape(rest)
    return html


def page(lines: list[str]) -> str:
    body = "\n".join(f'<div class="line">{render_line(x) or "&nbsp;"}</div>' for x in lines)
    return f"""<!doctype html><meta charset="utf-8"><style>
html,body{{margin:0;background:transparent}}
.win{{width:{WIDTH}px;background:#0d1117;border-radius:12px;overflow:hidden;
  box-shadow:0 0 0 1px #30363d;font:15px/1.65 "DejaVu Sans Mono","Noto Sans KR",monospace;
  color:#e6edf3}}
.bar{{height:34px;background:#161b22;display:flex;align-items:center;gap:8px;padding:0 14px}}
.dot{{width:12px;height:12px;border-radius:50%}}
.body{{padding:16px 20px 20px}}
.line{{white-space:pre;overflow:hidden;text-overflow:ellipsis}}
.dim{{color:#7d8590}} .bold{{font-weight:700}} .code{{color:#39c5cf}}
.prompt{{color:#3fb950;font-weight:700}} .cmd{{color:#e6edf3;font-weight:700}}
</style><div class="win"><div class="bar">
<span class="dot" style="background:#ff5f57"></span><span class="dot" style="background:#febc2e">
</span><span class="dot" style="background:#28c840"></span></div>
<div class="body">{body}</div></div>"""


def main() -> None:
    from playwright.sync_api import sync_playwright

    lines = SOURCE.read_text(encoding="utf-8").rstrip("\n").splitlines()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        tab = browser.new_page(device_scale_factor=2)
        tab.set_content(page(lines))
        tab.locator(".win").screenshot(path=str(OUT), omit_background=True)
        browser.close()
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
