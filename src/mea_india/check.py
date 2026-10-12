"""质量检查：生成 mea_data/check_report.md。

人工抽查结果写在 mea_data/spot_check.json（{doc_id: {"result": "...", "note": "..."}}），
GlobalSecurity 核对结果来自 globalsec 步骤生成的 globalsecurity_check.json；两者缺失时报告中标为未执行。
"""

import json
import random
import re
from collections import Counter, defaultdict
from datetime import datetime

from .config import CHECK_REPORT, DATA_DIR, END_DATE, SECTIONS, START_DATE
from .details import latest_log_by_doc
from .globalsec import GS_RESULT
from .lists import read_list_csv
from .parse import build_documents

SPOT_CHECK = DATA_DIR / "spot_check.json"
SPOT_SEED = 20260331
SHORT_CONTENT = 200
# 天城文、孟加拉文等印度文字及阿拉伯文（乌尔都语）
NON_LATIN_SCRIPT = re.compile(r"[\u0900-\u0DFF\u0600-\u06FF]")


def months_in_range() -> list[str]:
    out, y, m = [], START_DATE.year, START_DATE.month
    while (y, m) <= (END_DATE.year, END_DATE.month):
        out.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def md_escape(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def spot_sample(docs: list[dict]) -> list[dict]:
    return random.Random(SPOT_SEED).sample(docs, min(10, len(docs)))


def generate_report():
    docs, warnings, removed = build_documents()
    by_id = {d["id"]: d for d in docs}
    removed_ids = {r["id"] for r in removed}
    out: list[str] = []
    w = out.append

    w("# 质量检查报告\n")
    w(f"生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}　时间范围：{START_DATE} 至 {END_DATE}（按页面日期，两端包含）\n")

    # 1. 总数核对
    w("## 1. 总数核对\n")
    w("核对口径：列表接口在时间范围内返回的条数（网站显示的总数包含全部年份，不直接用于核对）。\n")
    w("| 栏目 | 列表条数 | 最终入库 | 去重删除 | 缺失 |")
    w("| --- | --- | --- | --- | --- |")
    missing_all = []
    for s in SECTIONS.values():
        rows = read_list_csv(s)
        ids = {f"mea_{s.name}_{r['doc_no']}" for r in rows}
        got = {d["id"] for d in docs if d["section"] == s.name}
        dup = {i for i in removed_ids if i.startswith(f"mea_{s.name}_")}
        missing = sorted(ids - got - dup)
        missing_all += [(i, r) for r in rows for i in [f"mea_{s.name}_{r['doc_no']}"] if i in missing]
        w(f"| {s.name} | {len(rows)} | {len(got)} | {len(dup)} | {len(missing)} |")
    w("")
    if missing_all:
        w("缺失篇目：\n")
        for i, r in missing_all:
            w(f"- `{i}` {r['list_date']} {md_escape(r['title'])}")
        w("")
    else:
        w("列表中的篇目全部入库。\n")

    w("### GlobalSecurity.org 交叉核对（例行记者会）\n")
    if GS_RESULT.exists():
        gs = json.loads(GS_RESULT.read_text(encoding="utf-8"))
        w(f"方法：对数据中没有 `weekly_briefing` 的周（共 {len(gs['gap_weeks'])} 个），逐日探测 GlobalSecurity 转载网址"
          "（含次周周一，因转载可能晚一天）。\n")
        if gs["found"]:
            w("| 空周（周一） | GlobalSecurity 日期 | 标题 | 网址 |")
            w("| --- | --- | --- | --- |")
            for f in gs["found"]:
                w(f"| {f['week']} | {f['gs_date']} | {md_escape(f['title'])} | {f['url']} |")
            w("\n以上篇目需回到外交部网站确认是否漏抓。\n")
        else:
            w("空周内 GlobalSecurity 上均未找到转载，未发现漏抓。\n")
    else:
        w("**未执行**（运行 `mea-india globalsec` 后重新生成报告）。\n")

    # 2. 按月统计
    w("## 2. 按月统计\n")
    cnt = defaultdict(Counter)
    for d in docs:
        m = d["publication_date"][:7]
        cnt[m][d["section"]] += 1
        if d["doc_type"] == "weekly_briefing":
            cnt[m]["weekly"] += 1
    w("| 月份 | transcripts | 其中 weekly_briefing | media_responses | 备注 |")
    w("| --- | --- | --- | --- | --- |")
    flagged = []
    for m in months_in_range():
        c = cnt[m]
        note = ""
        if c["weekly"] == 0:
            note = "⚠ 无例行记者会"
        elif c["weekly"] == 1:
            note = "例行记者会仅 1 篇"
        if note:
            flagged.append(m)
        w(f"| {m} | {c['transcripts']} | {c['weekly']} | {c['media_responses']} | {note} |")
    w("")
    w(f"需回网站确认的月份（例行记者会为 0 或 1 篇）：{', '.join(flagged) if flagged else '无'}\n")

    # 3. 类型统计
    w("## 3. 类型统计\n")
    tc = Counter(d["doc_type"] for d in docs)
    w("| doc_type | 篇数 |")
    w("| --- | --- |")
    for t in ("weekly_briefing", "special_briefing", "other_briefing", "media_response"):
        w(f"| {t} | {tc[t]} |")
    w("")
    others = [d for d in docs if d["doc_type"] == "other_briefing"]
    w(f"`other_briefing` 全部标题（{len(others)} 篇）：\n")
    for d in others:
        w(f"- `{d['id']}` {d['publication_date']} {md_escape(d['title'])}")
    w("")

    # 4. 空值检查
    w("## 4. 空值检查\n")
    short = [d for d in docs if len(d["content"]) < SHORT_CONTENT]
    w(f"`content` 为空或少于 {SHORT_CONTENT} 个字符：{len(short)} 篇\n")
    for d in short:
        w(f"- `{d['id']}` {d['publication_date']}（{len(d['content'])} 字符）{md_escape(d['title'])}")
    no_sp = [d for d in docs if d["spokesperson"] is None]
    w(f"\n`spokesperson` 为 null：{len(no_sp)} 篇\n")
    for d in no_sp:
        w(f"- `{d['id']}` {d['publication_date']} [{d['doc_type']}] {md_escape(d['title'])}")
    no_bd = [x for x in warnings if x["kind"] == "no_briefing_date"]
    w(f"\nTranscripts 标题中未解析出 `briefing_date`：{len(no_bd)} 篇\n")
    for x in no_bd:
        w(f"- `{x['id']}` {md_escape(by_id[x['id']]['title']) if x['id'] in by_id else ''}")
    w("")

    # 5. 去重
    w("## 5. 去重\n")
    if removed:
        w("| 删除的记录 | 保留的记录 | 原因 | 标题 |")
        w("| --- | --- | --- | --- |")
        for r in removed:
            w(f"| `{r['id']}` | `{r['duplicate_of']}` | {r['reason']} | {md_escape(r['title'])} |")
    else:
        w("未发现网址或正文完全相同的重复记录。")
    w("")

    # 6. 语言检查
    w("## 6. 语言检查\n")
    w("全部以英文接口（`PLngId=1` / `languageId=1`）抓取。检查标题和正文中是否含印度文字（天城文等）或阿拉伯文字符；"
      "拉丁字母拼写的印地语问答属正常内容。\n")
    bad = [(d, len(NON_LATIN_SCRIPT.findall(d["title"] + d["content"]))) for d in docs]
    bad = [(d, n) for d, n in bad if n]
    if bad:
        for d, n in bad:
            w(f"- `{d['id']}` 含 {n} 个非拉丁文字字符：{md_escape(d['title'])}")
    else:
        w("未发现非英文版本混入。")
    w("")

    # 7. 人工抽查
    w("## 7. 人工抽查\n")
    spot = json.loads(SPOT_CHECK.read_text(encoding="utf-8")) if SPOT_CHECK.exists() else {}
    w(f"随机抽取 10 篇（随机种子 {SPOT_SEED}），与网站原页面逐篇对照标题、日期和正文。\n")
    w("| id | 日期 | 标题 | 结果 | 说明 |")
    w("| --- | --- | --- | --- | --- |")
    for d in spot_sample(docs):
        r = spot.get(d["id"], {})
        w(f"| `{d['id']}` | {d['publication_date']} | {md_escape(d['title'])} | {r.get('result', '待核对')} | {md_escape(r.get('note', ''))} |")
    w("")

    # 8. 失败清单
    w("## 8. 失败清单\n")
    failed = [r for r in latest_log_by_doc().values() if r["success"] != "True"]
    if failed:
        w("| 栏目 | 编号 | 网址 | 最后抓取时间 | 原因 |")
        w("| --- | --- | --- | --- | --- |")
        for r in failed:
            w(f"| {r['section']} | {r['doc_no']} | {r['url']} | {r['crawl_time']} | {md_escape(r['error'])} |")
    else:
        w("日志中没有最终失败的篇目。")
    w("")

    # 9. 其他解析警告
    w("## 9. 其他解析警告\n")
    kinds = {
        "pdf_link": "正文含 PDF 链接（需确认是否为只有 PDF 附件的篇目）",
        "date_mismatch": "详情页日期与列表日期不一致",
        "title_mismatch": "详情页标题与列表标题不一致",
        "tag_mismatch": "详情页标签与列表标签不一致",
        "crawl_note": "抓取备注",
    }
    any_w = False
    for k, label in kinds.items():
        items = [x for x in warnings if x["kind"] == k]
        if not items:
            continue
        any_w = True
        w(f"**{label}**（{len(items)} 篇）\n")
        for x in items:
            w(f"- `{x['id']}`：{md_escape(x['message'])}")
        w("")
    if not any_w:
        w("无。\n")

    CHECK_REPORT.write_text("\n".join(out), encoding="utf-8")
    print(f"报告已生成 -> {CHECK_REPORT.relative_to(DATA_DIR.parent)}")
