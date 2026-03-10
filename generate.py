"""
Pixiv 일간 랭킹 필터 생성기
- Pixiv ranking JSON API에서 전체 500작품 수집
- yes_rank == 0 (첫 등장) 또는 yes_rank > 500 (전날 500위 초과) 필터링
- 썸네일 다운로드 후 index.html 생성
"""

import json
import os
import sys
import time
import shutil
from pathlib import Path
from datetime import datetime, timezone, timedelta

import requests

# ── Settings ────────────────────────────────────────────────────────────────
IMG_DIR = Path("img")
OUT_HTML = Path("index.html")
DELAY = 0.3  # seconds between requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.pixiv.net/",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

# JST = UTC+9
JST = timezone(timedelta(hours=9))


# ── Fetch ranking ────────────────────────────────────────────────────────────
def fetch_page(page: int, mode: str, content: str) -> dict | None:
    params = {"mode": mode, "content": content, "format": "json", "p": page}
    for attempt in range(3):
        try:
            r = requests.get(
                "https://www.pixiv.net/ranking.php",
                params=params,
                headers=HEADERS,
                timeout=20,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"  page {page} attempt {attempt+1} failed: {e}")
            time.sleep(2)
    return None


def fetch_all(mode: str = "daily", content: str = "illust") -> tuple[list[dict], str]:
    works, ranking_date = [], ""
    for page in range(1, 11):
        print(f"  Fetching page {page}/10 …", end="\r")
        data = fetch_page(page, mode, content)
        if not data or "contents" not in data:
            print(f"\n  Stopped at page {page} (no data)")
            break
        if not ranking_date:
            ranking_date = data.get("date", "")
        works.extend(data["contents"])
        time.sleep(DELAY)
    print(f"\n  Fetched {len(works)} works total.")
    return works, ranking_date


# ── Filter ───────────────────────────────────────────────────────────────────
def is_new_entry(work: dict) -> bool:
    try:
        yes_rank = int(work.get("yes_rank", 0))
    except (TypeError, ValueError):
        yes_rank = 0
    return yes_rank == 0 or yes_rank > 500


def badge_info(work: dict) -> tuple[str, str]:
    """Returns (label, css_class)"""
    try:
        yes_rank = int(work.get("yes_rank", 0))
    except (TypeError, ValueError):
        yes_rank = 0
    if yes_rank == 0:
        return "첫 등장", "badge-first"
    return f"전날 {yes_rank}위", "badge-prev"


# ── Image download ───────────────────────────────────────────────────────────
def download_thumb(url: str, illust_id: int | str) -> str:
    """Download thumbnail and return relative path, or empty string on failure."""
    ext = url.rsplit(".", 1)[-1].split("?")[0]
    local = IMG_DIR / f"{illust_id}.{ext}"
    if local.exists():
        return str(local)
    try:
        r = requests.get(url, headers=HEADERS, timeout=20, stream=True)
        r.raise_for_status()
        with open(local, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return str(local)
    except Exception as e:
        print(f"  Image fail {illust_id}: {e}")
        return ""


# ── HTML generation ──────────────────────────────────────────────────────────
CARD_TMPL = """\
<div class="card">
  <a class="thumb-link" href="https://www.pixiv.net/artworks/{illust_id}" target="_blank" rel="noopener">
    {img_tag}
    <span class="rank-num">#{rank}</span>
  </a>
</div>"""


def escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
    )


def make_cards(works: list[dict]) -> str:
    parts = []
    total = len(works)
    for i, w in enumerate(works):
        print(f"  Building card {i+1}/{total} …", end="\r")

        illust_id = w["illust_id"]
        rank = w["rank"]
        title = w.get("title", "")

        local_img = w.get("_local_img", "")
        if local_img:
            img_tag = f'<img src="{local_img}" alt="{escape_html(title)}" loading="lazy" />'
        else:
            img_tag = '<div class="img-placeholder">이미지 없음</div>'

        parts.append(CARD_TMPL.format(
            illust_id=illust_id,
            rank=rank,
            img_tag=img_tag,
        ))
    print()
    return "\n".join(parts)


HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Pixiv 일간 — 신규 진입 작품 {display_date}</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Hiragino Sans",sans-serif;background:#111;color:#e0e0e0}}

/* Header */
header{{background:#0078cc;color:#fff;padding:0 32px;height:58px;display:flex;align-items:center;gap:14px;
  position:sticky;top:0;z-index:100;box-shadow:0 2px 10px rgba(0,0,0,.5)}}
.logo{{font-size:22px;font-weight:800;letter-spacing:-0.5px}}
.logo span{{color:#ffe44d}}
.subtitle{{font-size:13px;opacity:.8}}
.refresh-btn{{margin-left:auto;display:inline-flex;align-items:center;gap:6px;
  background:rgba(255,255,255,.15);color:#fff;border:1px solid rgba(255,255,255,.3);
  border-radius:8px;padding:6px 14px;font-size:13px;font-weight:600;text-decoration:none;
  cursor:pointer;transition:background .2s}}
.refresh-btn:hover{{background:rgba(255,255,255,.28)}}

/* Meta bar */
.meta-bar{{background:#1a1a1a;border-bottom:1px solid #2a2a2a;padding:12px 32px;
  display:flex;align-items:center;gap:12px;font-size:13px;color:#aaa}}
.meta-bar .date-str{{font-weight:700;font-size:16px;color:#fff}}

/* Gallery — 3열 고정 */
.gallery{{max-width:1400px;margin:0 auto;padding:28px 24px;
  display:grid;grid-template-columns:repeat(3,1fr);gap:24px}}

/* Card */
.card{{background:#1e1e1e;border-radius:12px;overflow:hidden;
  box-shadow:0 2px 8px rgba(0,0,0,.4);transition:box-shadow .2s,transform .2s;position:relative}}
.card:hover{{box-shadow:0 8px 28px rgba(0,0,0,.7);transform:translateY(-4px)}}
.thumb-link{{display:block;position:relative;overflow:hidden;
  background:#2a2a2a;aspect-ratio:3/4;text-decoration:none}}
.thumb-link img{{width:100%;height:100%;object-fit:contain;display:block;transition:transform .35s}}
.card:hover .thumb-link img{{transform:scale(1.04)}}
.img-placeholder{{width:100%;height:100%;display:flex;align-items:center;justify-content:center;
  font-size:13px;color:#555}}

/* Overlays */
.rank-num{{position:absolute;top:10px;left:10px;background:rgba(0,0,0,.7);color:#fff;
  font-size:13px;font-weight:700;padding:3px 9px;border-radius:6px}}

/* Footer */
footer{{text-align:center;padding:40px;font-size:12px;color:#444}}
footer a{{color:#4db8ff;text-decoration:none}}
footer a:hover{{text-decoration:underline}}

/* Empty */
.empty{{grid-column:1/-1;text-align:center;padding:80px;color:#555;font-size:15px}}

@media(max-width:900px){{
  .gallery{{grid-template-columns:repeat(2,1fr);gap:16px;padding:16px}}
  header{{padding:0 16px}}
  .meta-bar{{padding:10px 16px}}
}}
@media(max-width:540px){{
  .gallery{{grid-template-columns:1fr;gap:14px;padding:12px}}
}}
</style>
</head>
<body>

<header>
  <div class="logo">Pixiv<span>NEW</span></div>
  <div class="subtitle">일간 랭킹 신규 진입 작품 모아보기</div>
  <a class="refresh-btn" href="https://github.com/philocsera/Daily-Pixiv/actions/workflows/update.yml" target="_blank">&#x21bb; 지금 갱신</a>
</header>

<div class="meta-bar">
  <span class="date-str">{display_date} 일간 랭킹</span>
  <span style="color:#555;font-size:12px">갱신: {updated_at} KST</span>
  <span style="margin-left:auto;color:#4db8ff;font-weight:700">{filtered_count}작품</span>
</div>

<div class="gallery">
{cards}
</div>

<footer>
  데이터 출처: <a href="https://www.pixiv.net/ranking.php?mode=daily&content=illust" target="_blank">Pixiv 일간 랭킹</a>
  &nbsp;·&nbsp; 매일 자동 갱신 (GitHub Actions)
</footer>

</body>
</html>
"""


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    mode = "daily"
    content = "illust"

    print("=== Pixiv 일간 랭킹 필터 생성 시작 ===")

    # 1. Fetch
    print("\n[1/4] 랭킹 데이터 수집 중...")
    all_works, ranking_date = fetch_all(mode, content)

    # 2. Filter
    print("[2/4] 신규 진입 작품 필터링...")
    filtered = [w for w in all_works if is_new_entry(w)]
    print(f"  {len(all_works)}작품 → {len(filtered)}작품 (신규 진입)")

    if not filtered:
        print("  신규 진입 작품이 없습니다. HTML을 비어있는 상태로 생성합니다.")

    # 3. Download thumbnails
    print("[3/4] 썸네일 다운로드 중...")
    IMG_DIR.mkdir(exist_ok=True)
    # Clean up old images not in current set
    current_ids = {str(w["illust_id"]) for w in filtered}
    for old in IMG_DIR.iterdir():
        stem = old.stem
        if stem not in current_ids:
            old.unlink(missing_ok=True)

    for i, w in enumerate(filtered):
        illust_id = w["illust_id"]
        print(f"  [{i+1}/{len(filtered)}] {illust_id} …", end="\r")
        local = download_thumb(w.get("url", ""), illust_id)
        w["_local_img"] = local
        time.sleep(0.1)
    print()

    # 4. Generate HTML
    print("[4/4] HTML 생성 중...")
    cards_html = make_cards(filtered) if filtered else '<div class="empty">오늘은 신규 진입 작품이 없습니다.</div>'

    # Date formatting
    now_jst = datetime.now(JST)
    updated_at = now_jst.strftime("%Y-%m-%d %H:%M")

    if ranking_date and len(ranking_date) == 8:
        try:
            rd = datetime.strptime(ranking_date, "%Y%m%d")
            display_date = rd.strftime("%Y년 %m월 %d일")
        except Exception:
            display_date = ranking_date
    else:
        display_date = now_jst.strftime("%Y년 %m월 %d일")

    html = HTML_TEMPLATE.format(
        display_date=display_date,
        updated_at=updated_at,
        filtered_count=len(filtered),
        total_count=len(all_works),
        cards=cards_html,
    )

    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"  {OUT_HTML} 생성 완료 ({OUT_HTML.stat().st_size // 1024} KB)")
    print(f"\n=== 완료: {len(filtered)}개 신규 진입 작품 ===")


if __name__ == "__main__":
    main()
