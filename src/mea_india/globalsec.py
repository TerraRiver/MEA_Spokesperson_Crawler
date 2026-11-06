"""用 GlobalSecurity.org 转载的例行记者会交叉核对：只探测我们数据中没有例行记者会的周，找可能漏抓的篇目。

GlobalSecurity 没有可用的目录页，只能按网址规律逐日探测：
globalsecurity.org/wmd/library/news/india/{年}/india-{yymmdd}-india-meab01.htm
网址日期是转载日期，可能比记者会晚一天。结果写入 mea_data/globalsecurity_check.json，由 check 汇入报告。
"""

import json
from datetime import date, timedelta

from .browser import Browser
from .config import DATA_DIR, END_DATE, START_DATE
from .parse import build_documents

GS_BASE = "https://www.globalsecurity.org"
GS_RESULT = DATA_DIR / "globalsecurity_check.json"


def gs_url(d: date) -> str:
    return f"{GS_BASE}/wmd/library/news/india/{d.year}/india-{d:%y%m%d}-india-meab01.htm"


def weeks_without_weekly_briefing(docs: list[dict]) -> list[date]:
    """返回范围内没有任何 weekly_briefing 的周（以周一表示）。"""
    covered = set()
    for d in docs:
        if d["doc_type"] == "weekly_briefing":
            for key in ("publication_date", "briefing_date"):
                if d[key]:
                    day = date.fromisoformat(d[key])
                    covered.add(day - timedelta(days=day.weekday()))
    monday = START_DATE - timedelta(days=START_DATE.weekday())
    gaps = []
    while monday <= END_DATE:
        if monday not in covered:
            gaps.append(monday)
        monday += timedelta(days=7)
    return gaps


def run_globalsecurity_check(headless: bool = True):
    docs, _, _ = build_documents()
    gaps = weeks_without_weekly_briefing(docs)
    print(f"没有例行记者会的周：{len(gaps)} 个，逐日探测 GlobalSecurity")

    found = []
    errors = []
    with Browser(headless=headless) as b:
        b.open(GS_BASE + "/wmd/library/news/india/index.html")
        for monday in gaps:
            # 该周周一至周日，以及次周周一（转载可能晚一天）
            for i in range(8):
                day = monday + timedelta(days=i)
                if not (START_DATE <= day <= END_DATE + timedelta(days=1)):
                    continue
                url = gs_url(day)
                status, text = b.fetch(url)
                if status == 200:
                    title = ""
                    if "<title>" in text:
                        title = text.split("<title>", 1)[1].split("</title>", 1)[0].strip()
                    found.append({"week": monday.isoformat(), "gs_date": day.isoformat(), "url": url, "title": title})
                    print(f"  找到 {day}：{title}")
                elif status != 404:
                    errors.append({"week": monday.isoformat(), "gs_date": day.isoformat(), "url": url, "status": status})
                    print(f"  ⚠ {day} 请求异常：HTTP {status} ({url})")

    result = {
        "gap_weeks": [m.isoformat() for m in gaps],
        "found": found,
        "errors": errors,
    }
    GS_RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"完成：{len(gaps)} 个空周中，GlobalSecurity 上找到 {len(found)} 篇，请求异常 {len(errors)} 次 -> {GS_RESULT.name}")
