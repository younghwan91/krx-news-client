"""GitHub social preview (1280x640 PNG) for this repo.

Run from the repo root:
    uv run --no-project --with playwright python scripts/make_social.py
    # -> docs/images/social-preview.png

The card shows the wordmark (docs/images/brand/wordmark-dark.svg), the README's one-line pitch
copied verbatim (the bold line under the title), the README's next sentence, and the mark.
No numbers are written here, so nothing can drift from the README.
Fonts: Noto Sans KR must be installed (fc-list :lang=ko). Playwright needs Chromium
(`uv run --no-project --with playwright playwright install chromium`).
Upload is manual: Settings -> General -> Social preview -> Edit -> Upload (GitHub has no API).
"""

from __future__ import annotations

import re
import struct
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
BRAND = ROOT / "docs" / "images" / "brand"
OUT = ROOT / "docs" / "images" / "social-preview.png"
W, H = 1280, 640
MAX_BYTES = 1_000_000


def _plain(md: str) -> str:
    """Markdown emphasis and code ticks off; the words stay as written."""
    return re.sub(r"[*_`]", "", md).strip()


def readme_text(readme: str) -> tuple[str, str, str]:
    """(repo name, pitch, next sentence) from the README head.

    The pitch is the first line that is wholly bold (``**...**``) after the ``# name`` title.
    The next sentence is the first sentence of the following plain paragraph.
    """
    name = re.search(r"^# (\S+)\s*$", readme, re.MULTILINE)
    if not name:
        raise SystemExit("README.md has no '# <name>' title")
    rest = readme[name.end():]
    pitch = re.search(r"^\*\*(.+)\*\*\s*$", rest, re.MULTILINE)
    if not pitch:
        raise SystemExit("README.md has no bold one-line pitch under the title")
    sub = ""
    for line in rest[pitch.end():].splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(("[", "<", "!", "#", "|", "`")):
            break
        sub = _plain(line)
        if len(sub) > 60:  # a long paragraph keeps only its first sentence
            sub = re.split(r"(?<=\.)\s+", sub)[0]
        break
    return name.group(1), _plain(pitch.group(1)), sub


def _svg(path: Path) -> str:
    svg = path.read_text("utf-8").strip()
    return re.sub(r'\s(width|height)="[^"]*"', "", svg, count=2)


def _accent(mark_svg: str) -> str:
    m = re.search(r'<rect[^>]*fill="(#[0-9A-Fa-f]{6})"', mark_svg)
    color = m.group(1) if m else "#94A3B8"
    r, g, b = (int(color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    if 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.15:  # too dark to read on the dark card
        return "#94A3B8"
    return color


def card_html() -> str:
    name, pitch, sub = readme_text(README.read_text("utf-8"))
    wordmark = _svg(BRAND / "wordmark-dark.svg")
    mark = _svg(BRAND / "mark.svg")
    accent = _accent(mark)
    sub_html = f'<p class="sub">{escape(sub)}</p>' if sub else ""
    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><style>
*{{box-sizing:border-box;margin:0}}
body{{width:{W}px;height:{H}px;overflow:hidden;background:#0d1117;color:#e6edf3;
  font-family:"Noto Sans KR",sans-serif;position:relative}}
.band{{position:absolute;top:0;left:0;right:0;height:8px;background:{accent}}}
.l{{position:absolute;left:72px;top:72px;bottom:64px;width:870px;display:flex;flex-direction:column}}
.wm svg{{height:60px;width:auto;display:block}}
.box{{flex:1;display:flex;flex-direction:column;justify-content:center;min-height:0}}
h1{{font-weight:700;line-height:1.3;letter-spacing:-.01em;word-break:keep-all}}
.sub{{font-size:28px;line-height:1.45;color:#9aa4b2;margin-top:22px;word-break:keep-all}}
.foot{{font-size:24px;color:#9aa4b2}}
.foot b{{color:#e6edf3;font-weight:500}}
.r{{position:absolute;right:72px;top:50%;transform:translateY(-50%);width:224px;height:224px;
  border-radius:50px;box-shadow:0 0 0 2px #30363d}}
.r svg{{width:224px;height:224px;display:block}}
</style></head><body><div class="band"></div>
<div class="l"><div class="wm">{wordmark}</div>
<div class="box"><h1 id="h">{escape(pitch)}</h1>{sub_html}</div>
<p class="foot">github.com/younghwan91/<b>{escape(name)}</b></p></div>
<div class="r">{mark}</div>
<script>
// Largest headline size (56px down to 34px) that keeps the text box inside the column.
const h=document.getElementById('h'),box=h.parentElement;
for(let s=56;s>=34;s-=2){{h.style.fontSize=s+'px';if(box.scrollHeight<=box.clientHeight)break;}}
</script></body></html>"""


def png_size(path: Path) -> tuple[int, int]:
    return struct.unpack(">II", path.read_bytes()[16:24])


def main() -> int:
    from playwright.sync_api import sync_playwright  # only when rendering

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H})
        page.route("http*://**", lambda r: r.abort())  # no remote fonts or images
        page.set_content(card_html(), wait_until="load")
        page.evaluate("document.fonts.ready")
        page.screenshot(path=str(OUT), clip={"x": 0, "y": 0, "width": W, "height": H})
        browser.close()
    size, nbytes = png_size(OUT), OUT.stat().st_size
    if size != (W, H) or nbytes >= MAX_BYTES:
        print(f"{OUT}: {size}, {nbytes} bytes - must be {W}x{H} and < 1 MB", file=sys.stderr)
        return 1
    print(f"{OUT.relative_to(ROOT)}: {size[0]}x{size[1]}, {nbytes:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
