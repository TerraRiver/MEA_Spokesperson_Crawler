"""逐篇抓取详情页：保存渲染后整页 + 详情接口原始片段，写抓取日志，支持断点续爬。"""

import csv
import traceback
from datetime import datetime
from pathlib import Path

from selenium.common.exceptions import TimeoutException, WebDriverException

from .browser import Browser
from .config import CRAWL_LOG, DATA_DIR, RAW_DIR, SECTIONS, Section, detail_api_url
from .lists import read_list_csv

LOG_FIELDS = ["section", "doc_no", "url", "crawl_time", "success", "error", "raw_file", "raw_fragment_file"]


def raw_paths(section: Section, row: dict) -> tuple[Path, Path]:
    stem = f"{section.file_prefix}_{row['list_date']}_{row['doc_no']}"
    folder = RAW_DIR / section.name
    return folder / f"{stem}.html", folder / f"{stem}.fragment.html"


def read_log() -> list[dict]:
    if not CRAWL_LOG.exists():
        return []
    with open(CRAWL_LOG, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def latest_log_by_doc() -> dict[tuple[str, str], dict]:
    """同一篇多次抓取时以最后一条记录为准。"""
    latest = {}
    for r in read_log():
        latest[(r["section"], r["doc_no"])] = r
    return latest


def append_log(entry: dict):
    new = not CRAWL_LOG.exists()
    CRAWL_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CRAWL_LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if new:
            w.writeheader()
        w.writerow(entry)


def fetch_one(browser: Browser, section: Section, row: dict) -> dict:
    page_path, frag_path = raw_paths(section, row)
    page_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "section": section.name,
        "doc_no": row["doc_no"],
        "url": row["url"],
        "crawl_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "success": "False",
        "error": "",
        "raw_file": str(page_path.relative_to(DATA_DIR)),
        "raw_fragment_file": str(frag_path.relative_to(DATA_DIR)),
    }
    try:
        try:
            page = browser.open(row["url"], wait_css=".pressReleaseContent .description")
        except TimeoutException:
            # 没有 .description 的特殊页面（如只有 PDF）也要保存下来，交给解析和质检处理
            page = browser.driver.page_source
            entry["error"] = "等待 .description 超时；"

        fragment = browser.captured_response(f"FetchPublicationDetailData?pkid={row['doc_no']}&")
        if fragment is None:
            status, fragment = browser.fetch(detail_api_url(row["doc_no"]))
            if status != 200:
                raise RuntimeError(f"详情接口 HTTP {status}")
        if "titleText" not in fragment:
            raise RuntimeError("详情片段中没有标题（titleText），疑似被拦截或页面异常")

        page_path.write_text(page, encoding="utf-8")
        frag_path.write_text(fragment, encoding="utf-8")
        entry["success"] = "True"
    except (WebDriverException, RuntimeError, OSError) as e:
        entry["error"] += f"{type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}"
        traceback.print_exc(limit=1)
    return entry


def crawl_details(limit: int | None = None, only_failed: bool = False, headless: bool = True):
    """limit：每个栏目只取最新的 N 篇（样例交付用）；only_failed：只补爬日志中失败的篇目。"""
    latest = latest_log_by_doc()
    todo: list[tuple[Section, dict]] = []
    for section in SECTIONS.values():
        rows = sorted(read_list_csv(section), key=lambda r: (r["list_date"], int(r["doc_no"] or 0)), reverse=True)
        if limit:
            rows = rows[:limit]
        for row in rows:
            log = latest.get((section.name, row["doc_no"]))
            done = log and log["success"] == "True" and all(p.exists() for p in raw_paths(section, row))
            if done:
                continue
            if only_failed and not log:
                continue
            todo.append((section, row))

    print(f"待抓取 {len(todo)} 篇")
    if not todo:
        return
    ok = fail = 0
    with Browser(headless=headless) as b:
        for i, (section, row) in enumerate(todo, 1):
            entry = fetch_one(b, section, row)
            append_log(entry)
            if entry["success"] == "True":
                ok += 1
            else:
                fail += 1
            print(f"[{i}/{len(todo)}] {section.name} {row['list_date']} {row['doc_no']} "
                  f"{'OK' if entry['success'] == 'True' else 'FAIL ' + entry['error']}", flush=True)
    print(f"完成：成功 {ok}，失败 {fail}")
