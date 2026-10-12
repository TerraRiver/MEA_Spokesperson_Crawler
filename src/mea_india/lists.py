"""抓取两个栏目的完整列表，保存原始列表片段和 CSV。"""

import csv
import math
import re
from datetime import datetime

from bs4 import BeautifulSoup

from .browser import Browser
from .config import BASE_URL, END_DATE, LIST_DIR, LIST_PAGE_SIZE, SECTIONS, START_DATE, Section, list_api_url

HTML_WS = re.compile(r"[ \t\n\r\f]+")  # 与 parse.py 一致：按 HTML 渲染语义折叠空白

LIST_FIELDS = ["section", "doc_no", "title", "list_date", "list_date_raw", "url", "tags"]
TAG_SEP = " | "


def parse_page_date(raw: str):
    """'25 March, 2026' -> date"""
    return datetime.strptime(" ".join(raw.split()), "%d %B, %Y").date()


def parse_list_fragment(text: str, section: Section) -> tuple[list[dict], int | None]:
    soup = BeautifulSoup(text, "lxml")
    total = None
    pag = soup.select_one(".paginationBox")
    if pag:
        m = re.search(r"of\s+(\d+)", pag.get_text(" "))
        total = int(m.group(1)) if m else None
    rows = []
    for box in soup.select(".pressRelesastBox"):
        a = box.select_one(".pressTitle a")
        href = a["href"]
        m = re.search(r"dtl/(\d+)", href)
        raw_date = box.select_one(".date").get_text(strip=True)
        rows.append({
            "section": section.name,
            "doc_no": m.group(1) if m else "",
            "title": HTML_WS.sub(" ", a.get_text()).replace("\xa0", " ").strip(),
            "list_date": parse_page_date(raw_date).isoformat(),
            "list_date_raw": raw_date,
            "url": BASE_URL + href,
            "tags": TAG_SEP.join(t.get_text(strip=True) for t in box.select(".tags a")),
        })
    return rows, total


def crawl_section_list(browser: Browser, section: Section) -> list[dict]:
    raw_dir = LIST_DIR / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    browser.open(section.landing_path)

    rows, page, pages, total = [], 1, 1, None
    while page <= pages:
        status, text = browser.fetch(list_api_url(section, page))
        if status != 200:
            raise RuntimeError(f"{section.name} 列表第 {page} 页请求失败：HTTP {status}")
        (raw_dir / f"{section.name}_page{page:02d}.html").write_text(text, encoding="utf-8")
        page_rows, page_total = parse_list_fragment(text, section)
        if page == 1:
            total = page_total or 0
            pages = max(1, math.ceil(total / LIST_PAGE_SIZE))
        rows.extend(page_rows)
        print(f"  {section.name} 第 {page}/{pages} 页：{len(page_rows)} 条")
        page += 1

    if len(rows) != total:
        print(f"  ⚠ {section.name}：接口显示 {total} 条，实际解析 {len(rows)} 条")

    in_range = [r for r in rows if START_DATE.isoformat() <= r["list_date"] <= END_DATE.isoformat()]
    dropped = len(rows) - len(in_range)
    print(f"  {section.name}：放宽范围内 {len(rows)} 条，严格范围内 {len(in_range)} 条（剔除缓冲区 {dropped} 条）")
    return in_range


def write_list_csv(section: Section, rows: list[dict]):
    LIST_DIR.mkdir(parents=True, exist_ok=True)
    with open(LIST_DIR / f"{section.name}_list.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LIST_FIELDS)
        w.writeheader()
        w.writerows(rows)


def read_list_csv(section: Section) -> list[dict]:
    path = LIST_DIR / f"{section.name}_list.csv"
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# 列表外补充篇目：详情页存在但不出现在网站任何列表中，按编号直接抓取
SUPPLEMENTS: dict[str, list[dict]] = {
    "transcripts": [
        {
            "doc_no": "40219",
            "title": "Transcript of Weekly Media Briefing by the Official Spokesperson (October 16, 2025)",
            "list_date": "2025-10-16",
            "url": BASE_URL + "/media-briefings?dtl/40219/Transcript_of_Weekly_Media_Briefing_by_the_Official_Spokesperson_October_16_2025",
            "note": "列表外篇目，经 GlobalSecurity 交叉核对发现（转载日期 2025-10-16）",
        },
        {
            "doc_no": "40245",
            "title": "Transcript of Weekly Media Briefing by the Official Spokesperson (October 30, 2025)",
            "list_date": "2025-10-30",
            "url": BASE_URL + "/media-briefings?dtl/40245/Transcript_of_Weekly_Media_Briefing_by_the_Official_Spokesperson_October_30_2025",
            "note": "列表外篇目，经 GlobalSecurity 交叉核对发现（转载日期 2025-10-30）",
        },
    ],
    "media_responses": [],
}


def read_rows(section: Section) -> list[dict]:
    """待抓取/解析的全部篇目：网站列表（source=site_list）+ 列表外补充（source=supplement）。"""
    rows = [dict(r, source="site_list", note="") for r in read_list_csv(section)]
    listed = {r["doc_no"] for r in rows}
    for sup in SUPPLEMENTS.get(section.name, []):
        if sup["doc_no"] in listed:
            print(f"  提示：补充篇目 {section.name} {sup['doc_no']} 已出现在网站列表中，按列表处理")
            continue
        rows.append(dict(sup, section=section.name, list_date_raw="", tags="", source="supplement"))
    return rows


def crawl_lists(headless: bool = True):
    with Browser(headless=headless) as b:
        for section in SECTIONS.values():
            rows = crawl_section_list(b, section)
            write_list_csv(section, rows)
