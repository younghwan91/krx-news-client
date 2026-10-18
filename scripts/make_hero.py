"""README 히어로 이미지: 두 출처(DART 공시, 토스증권 뉴스)가 한 스키마의 한 타임라인이 된다.

실행 (레포 루트, 공통 접두 ``uv run --with matplotlib --with numpy python``):
    scripts/make_hero.py              # 실수집 → docs/images/hero-data.json → PNG 두 장
    scripts/make_hero.py --from-json  # 저장된 JSON 으로 다시 그리기 (네트워크 없음)

DART 키는 환경변수(``DART_API_KEY``, ``_2``, ``_3``)로만 읽는다 — 값을 출력하지 않는다.
토스는 비공식 API 라 실패하면 로그만 남기고 DART 만으로 그린다.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent))
from hero_style import caption, render_both  # noqa: E402

KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "images" / "hero-data.json"

#: 그림에 보일 종목 (위→아래 순서). 이름은 영어로 — 그림 안 글자는 영어.
TICKERS = [
    ("005930", "Samsung Electronics"),
    ("000660", "SK hynix"),
    ("005380", "Hyundai Motor"),
    ("035420", "NAVER"),
    ("068270", "Celltrion"),
    ("051910", "LG Chem"),
    ("105560", "KB Financial"),
    ("028260", "Samsung C&T"),
]
WINDOW_DAYS = 3
TOSS_MAX_PAGES = 6  # 종목당 최대 600건 — 대형주 3일치가 대략 이 안에 든다


# ---------------------------------------------------------------- collect
async def collect(end: date) -> dict:
    from krx_news_client import DartScraper, TossScraper

    start = end - timedelta(days=WINDOW_DAYS - 1)
    codes = {c for c, _ in TICKERS}
    items: list[dict] = []
    errors: dict[str, str] = {}

    # DART: 한 주 전체 시장 목록을 받아 종목으로 거른다 (요청 수십 건, 한도 20,000 대비 미미).
    try:
        async with DartScraper.from_env() as dart:
            rows = await dart.scrape_disclosures(
                bgn_de=start.strftime("%Y%m%d"), end_de=end.strftime("%Y%m%d")
            )
        for d in rows:
            if d.ticker in codes:
                items.append({
                    "source": d.source.value, "ticker": d.ticker, "title": d.title,
                    "published_at": d.published_at.isoformat(), "url": d.url,
                    "rcept_no": d.rcept_no, "is_correction": d.is_correction,
                })
        logging.info("DART: %d rows in window, %d for chosen tickers", len(rows),
                     sum(1 for i in items if i["source"] == "dart"))
    except Exception as e:  # noqa: BLE001
        errors["dart"] = f"{type(e).__name__}: {e}"
        logging.exception("DART collection failed")

    # Toss: 종목별 뉴스 페이지, since=창 시작. 비공식 API 라 실패해도 계속.
    try:
        async with TossScraper() as toss:
            for code, _ in TICKERS:
                arts = await toss.scrape_company_news(code, since=start, max_pages=TOSS_MAX_PAGES)
                n = 0
                for a in arts:
                    if not (start <= a.published_at.astimezone(KST).date() <= end):
                        continue
                    items.append({
                        "source": a.source.value, "ticker": code, "tickers": a.tickers,
                        "title": a.title, "published_at": a.published_at.isoformat(),
                        "url": a.url, "news_id": a.news_id, "author": a.author,
                    })
                    n += 1
                logging.info("Toss %s: %d articles in window", code, n)
    except Exception as e:  # noqa: BLE001
        errors["toss"] = f"{type(e).__name__}: {e}"
        logging.exception("Toss collection failed")

    return {
        "collected_at": datetime.now(tz=KST).isoformat(),
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "tickers": [{"code": c, "name": n} for c, n in TICKERS],
        "errors": errors,
        "items": items,
    }


# ---------------------------------------------------------------- draw
def _hours(ts: str, start: date) -> float:
    dt = datetime.fromisoformat(ts).astimezone(KST)
    return (dt - datetime.combine(start, datetime.min.time(), tzinfo=KST)).total_seconds() / 3600


def _fmt(ts: str) -> str:
    return datetime.fromisoformat(ts).astimezone(KST).strftime("%Y-%m-%d %H:%M +09:00")


def _ellipsis(s: str, n: int) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _card(fig, p, x0, y0, w, h, color, head, fields):
    """레코드 카드 한 장 (figure 좌표). head 는 출처 라벨, fields 는 (이름, 값) 목록."""
    from matplotlib.patches import FancyBboxPatch

    box = FancyBboxPatch((x0, y0), w, h, boxstyle="round,pad=0,rounding_size=0.008",
                         transform=fig.transFigure, fc=p["surface2"], ec=p["grid"], lw=1,
                         zorder=1)
    fig.add_artist(box)
    # 출처 색 띠 (왼쪽 세로)
    fig.add_artist(FancyBboxPatch((x0, y0), 0.006, h, boxstyle="square,pad=0",
                                  transform=fig.transFigure, fc=color, ec="none", zorder=2))
    fig.text(x0 + 0.018, y0 + h - 0.035, head, color=p["ink"], fontsize=11, weight="bold",
             ha="left", va="top", transform=fig.transFigure)
    row_h = (h - 0.08) / len(fields)
    for i, (k, v) in enumerate(fields):
        y = y0 + h - 0.085 - i * row_h
        fig.text(x0 + 0.018, y, k, color=p["ink3"], fontsize=9.5, family="monospace",
                 ha="left", va="top", transform=fig.transFigure)
        fig.text(x0 + 0.115, y, v, color=p["ink2"], fontsize=9.5,
                 ha="left", va="top", transform=fig.transFigure)


def draw_factory(data: dict):
    start = date.fromisoformat(data["window"]["start"])
    end = date.fromisoformat(data["window"]["end"])
    tickers = data["tickers"]
    rows = {t["code"]: i for i, t in enumerate(tickers)}
    items = [it for it in data["items"] if it["ticker"] in rows
             and start <= datetime.fromisoformat(it["published_at"]).astimezone(KST).date() <= end]
    dart = [it for it in items if it["source"] == "dart"]
    toss = [it for it in items if it["source"] == "toss"]
    n_days = (end - start).days + 1

    def draw(fig, _ax, p):
        _ax.remove()
        # 위: 타임라인, 아래: 카드 두 장 (figure 좌표로 직접 배치)
        ax = fig.add_axes([0.14, 0.44, 0.84, 0.43])
        colors = {"dart": p["blue"], "toss": p["amber"]}

        # DART 는 접수일만 있어 00:00 에 찍힌다. 같은 행의 점은 세로 레인으로 벌려 겹침을 줄인다 —
        # 행 안의 세로 위치는 뜻이 없다. 레인은 "가장 오래 비어 있던 것"부터 채운다(비스웜).
        px_per_hour = 0.84 * fig.get_figwidth() * fig.dpi / (n_days * 24)
        gap_h = 8 * fig.dpi / 72 * 1.05 / px_per_hour  # 마커 지름(8pt) 만큼의 시간 간격

        def swarm(seq, spread, lanes):
            offs = ([-spread + 2 * spread * i / (lanes - 1) for i in range(lanes)]
                    if lanes > 1 else [0.0])
            order = sorted(range(len(seq)), key=lambda i: seq[i]["published_at"])
            last = {r: [-1e9] * lanes for r in rows.values()}
            pos = [0.0] * len(seq)
            centre = sorted(range(lanes), key=lambda k: abs(offs[k]))
            for i in order:
                x = _hours(seq[i]["published_at"], start)
                r = rows[seq[i]["ticker"]]
                free = [k for k in centre if last[r][k] + gap_h <= x]
                k = free[0] if free else min(range(lanes), key=lambda k: last[r][k])
                last[r][k] = x
                pos[i] = offs[k]
            return pos

        for src, seq, z, lanes in (("toss", toss, 3, 7), ("dart", dart, 4, 5)):
            if not seq:
                continue
            offs = swarm(seq, 0.33 if src == "toss" else 0.22, lanes)
            xs = [_hours(it["published_at"], start) for it in seq]
            ys = [rows[it["ticker"]] + o for it, o in zip(seq, offs)]
            ax.scatter(xs, ys, s=64, color=colors[src], edgecolors=p["surface"], linewidths=1.2,
                       alpha=0.9, zorder=z,
                       label=f"DART filing (n={len(seq)})" if src == "dart"
                       else f"Toss news (n={len(seq)})")

        ax.set_xticks([d * 24 for d in range(n_days + 1)])
        ax.set_xticklabels(
            [(start + timedelta(days=d)).strftime("%b %d") for d in range(n_days + 1)], ha="left")
        ax.set_xticks([d * 24 + 12 for d in range(n_days)], minor=True)
        ax.tick_params(axis="x", which="minor", length=0)
        x_end = min(n_days * 24, _hours(data["collected_at"], start) + 1)
        ax.set_xlim(-1, x_end + 1)  # set_xticks 뒤에 — 눈금이 범위를 늘리지 않게
        ax.grid(True, axis="x", which="major")
        ax.grid(False, axis="y")
        ax.set_yticks(range(len(tickers)))
        ax.set_yticklabels([f"{t['name']}  {t['code']}" for t in tickers])
        ax.set_ylim(len(tickers) - 0.5, -0.5)
        for y in range(len(tickers)):
            ax.axhline(y, color=p["grid"], lw=1, zorder=0)
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.set_xlabel("published_at (KST)", labelpad=4)
        ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=2, handletextpad=0.3,
                  columnspacing=1.6, borderaxespad=0.0)
        fig.suptitle("News and filings from two sources, one schema, one timeline",
                     x=0.01, y=1.0, ha="left", fontsize=16, weight="bold", color=p["ink"])

        # 카드: 실제 레코드 하나씩
        def pick(seq):
            if not seq:
                return None
            plain = [it for it in seq if not it.get("is_correction")] or seq
            return max(plain, key=lambda it: it["published_at"])

        d, t = pick(dart), pick(toss)
        cw, ch, cy = 0.41, 0.27, 0.03
        if d:
            _card(fig, p, 0.14, cy, cw, ch, p["blue"], "Disclosure  (source=dart)", [
                ("published_at", _fmt(d["published_at"])),
                ("ticker", d["ticker"]),
                ("title", _ellipsis(d["title"], 34)),
                ("rcept_no", d["rcept_no"]),
            ])
        if t:
            _card(fig, p, 0.57, cy, cw, ch, p["amber"], "NewsArticle  (source=toss)", [
                ("published_at", _fmt(t["published_at"])),
                ("tickers", ", ".join(t.get("tickers") or [t["ticker"]])[:30]),
                ("title", _ellipsis(t["title"], 34)),
                ("news_id", t["news_id"]),
            ])
        caption(fig, (
            f"Live pull with krx-news-client on {data['collected_at'][:10]}, "
            f"window {start:%Y-%m-%d} to {end:%Y-%m-%d}. DART Open API: filings carry "
            "the receipt date only, drawn at 00:00 KST.\n"
            "Toss Securities company news endpoint, "
            f"up to {TOSS_MAX_PAGES * 100} articles per ticker."
        ), p)

    return draw


# ---------------------------------------------------------------- main
def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # httpx 가 찍는 요청 URL 에 DART 키가 실린다 — 출력하지 않는다.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-json", action="store_true", help="수집 없이 hero-data.json 으로 그린다")
    ap.add_argument("--end", default=None, help="창 마지막 날 YYYY-MM-DD (기본 오늘 KST)")
    args = ap.parse_args()

    if args.from_json:
        data = json.loads(DATA.read_text())
    else:
        end = date.fromisoformat(args.end) if args.end else datetime.now(tz=KST).date()
        data = asyncio.run(collect(end))
        DATA.parent.mkdir(parents=True, exist_ok=True)
        DATA.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
        logging.info("saved %s (%d items)", DATA, len(data["items"]))

    paths = render_both(draw_factory(data), out_dir=str(ROOT / "docs" / "images"), name="hero",
                        figsize=(12, 5))
    for pth in paths:
        print(pth)


if __name__ == "__main__":
    main()
