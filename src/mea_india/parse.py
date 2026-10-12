"""离线解析本地保存的详情片段，生成 mea_documents.json。"""

import json
import re
from datetime import datetime

from bs4 import BeautifulSoup, NavigableString, Tag

from .config import DATA_DIR, DOCS_JSON, SECTIONS, Section
from .details import latest_log_by_doc, raw_paths
from .lists import TAG_SEP, parse_page_date, read_list_csv

# 渲染时会产生换行的块级元素
BLOCK_TAGS = {
    "p", "div", "li", "ul", "ol", "table", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "pre", "section", "article", "header", "footer", "dl", "dt", "dd",
}
HTML_WS = re.compile(r"[ \t\n\r\f]+")  # HTML 中的空白（不含 &nbsp;）在渲染时折叠为一个空格

_HON = r"(?:Shri|Sh\.?|Mr\.?|Dr\.?)"
_NAME = r"([A-Z][A-Za-z\-]+(?:\s+[A-Z][A-Za-z\-]+){0,3})"
SPOKESPERSON_PATTERNS = [
    # "Shri Randhir Jaiswal, Official Spokesperson" / "Sh Anurag Srivastava, (Official Spokesperson)"
    re.compile(rf"\b{_HON}\s*{_NAME}\s*,\s*\(?\s*(?i:Official Spokesperson)"),
    # "Official Spokesperson Shri Randhir Jaiswal said" / "Official Spokesperson, Raveesh Kumar:" / "MEA Spokesperson Raveesh Kumar said"
    re.compile(rf"(?i:Official|MEA)\s+(?i:Spokesperson)\s*,?\s+(?:{_HON}\s*)?{_NAME}"),
]

_MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
# 标题中的日期写法："January 30, 2020"、"18 June 2020"、"11th December 2020"、"19th Nov 2020"、"06-June-2022"
TITLE_DATE = re.compile(
    rf"(?:{_MONTH}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}"
    rf"|\d{{1,2}}(?:st|nd|rd|th)?[\s-]+{_MONTH},?[\s-]+\d{{4}})",
    re.I,
)
TITLE_DATE_FORMATS = ["%B %d %Y", "%d %B %Y", "%b %d %Y", "%d %b %Y"]


def doc_type(section: Section, title: str) -> str:
    if section.name == "media_responses":
        return "media_response"
    t = title.lower()
    if "weekly media briefing" in t:
        return "weekly_briefing"
    if re.search(r"special.*briefing", t):
        return "special_briefing"
    return "other_briefing"


def briefing_date(title: str) -> str | None:
    """取标题中最后一个可识别的日期（括号内外均可），统一为 YYYY-MM-DD；没有则返回 None。"""
    found = TITLE_DATE.findall(title)
    if not found:
        return None
    raw = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", found[-1], flags=re.I)
    raw = re.sub(r"\bSept\b", "Sep", raw.replace(",", " ").replace("-", " ").replace(".", " "), flags=re.I)
    raw = " ".join(raw.split())
    for fmt in TITLE_DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            pass
    return None
    raw = " ".join(re.sub(r"\bSept\b", "Sep", found[-1]).split())
    for fmt in TITLE_DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def html_to_text(node: Tag) -> str:
    """按浏览器渲染语义把 HTML 转成文本：块级元素和 <br> 产生换行，其余文本原样拼接。"""
    parts: list[str] = []

    def walk(el):
        for child in el.children:
            if isinstance(child, NavigableString):
                if child.__class__.__name__ in ("Comment", "Doctype", "Declaration", "ProcessingInstruction"):
                    continue
                parts.append(HTML_WS.sub(" ", str(child)))
            elif isinstance(child, Tag):
                name = child.name.lower()
                if name in ("script", "style", "noscript"):
                    continue
                if name == "br":
                    parts.append("\n")
                elif name in BLOCK_TAGS:
                    parts.append("\n")
                    walk(child)
                    parts.append("\n")
                elif name in ("td", "th"):
                    walk(child)
                    parts.append(" ")
                else:
                    walk(child)

    walk(node)
    text = "".join(parts).replace("\xa0", " ")
    lines = [ln.strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def find_spokesperson(content: str) -> str | None:
    for pat in SPOKESPERSON_PATTERNS:
        m = pat.search(content)
        if m:
            return m.group(1).strip()
    return None


LANG_VERSION_LINK = re.compile(r"^\s*Click here for .+ version\s*$", re.I)


def is_pdf(href: str) -> bool:
    return href.lower().split("?")[0].endswith(".pdf")


def remove_language_pdf_links(desc: Tag) -> list[str]:
    """去掉正文末尾 "Click here for Xxx version" 形式的其他语言 PDF 链接（连同其后的 PDF 图标），返回被去掉的链接。"""
    removed = []
    for a in desc.select("a[href]"):
        if is_pdf(a["href"]) and LANG_VERSION_LINK.match(a.get_text()):
            icon = a.find_next_sibling()
            if icon is not None and icon.name == "img" and "pdfIcon" in (icon.get("class") or []):
                icon.decompose()
            removed.append(a["href"])
            a.decompose()
    return removed


def parse_fragment(fragment: str) -> dict:
    soup = BeautifulSoup(fragment, "lxml")
    root = soup.select_one(".pressReleaseContent") or soup
    title_el = root.select_one("h2.titleText")
    date_el = root.select_one(".date")
    desc = root.select_one(".description")
    lang_pdfs = remove_language_pdf_links(desc) if desc else []
    pdfs = [a.get("href") for a in (desc or root).select("a[href]") if is_pdf(a.get("href", ""))]
    return {
        "title": HTML_WS.sub(" ", title_el.get_text()).replace("\xa0", " ").strip() if title_el else "",
        "page_date": parse_page_date(date_el.get_text()).isoformat() if date_el else None,
        "tags": [t.get_text(strip=True) for t in root.select(".tags a")],
        "content": html_to_text(desc) if desc else "",
        "pdf_links": pdfs,
        "language_pdf_links": lang_pdfs,
    }


def build_documents() -> tuple[list[dict], list[dict], list[dict]]:
    """返回 (去重后的文档, 警告, 被去重删掉的记录)。警告为 {id, kind, message}。"""
    latest = latest_log_by_doc()
    docs, warnings = [], []

    def warn(doc_id, kind, message):
        warnings.append({"id": doc_id, "kind": kind, "message": message})

    for section in SECTIONS.values():
        for row in read_list_csv(section):
            log = latest.get((section.name, row["doc_no"]))
            page_path, frag_path = raw_paths(section, row)
            if not (log and log["success"] == "True" and frag_path.exists()):
                continue
            p = parse_fragment(frag_path.read_text(encoding="utf-8"))
            doc_id = f"mea_{section.name}_{row['doc_no']}"
            if p["page_date"] != row["list_date"]:
                warn(doc_id, "date_mismatch", f"详情页日期 {p['page_date']} 与列表日期 {row['list_date']} 不一致")
            if p["pdf_links"]:
                warn(doc_id, "pdf_link", f"正文含 PDF 链接：{', '.join(p['pdf_links'])}")
            list_tags = row["tags"].split(TAG_SEP) if row["tags"] else []
            if p["tags"] != list_tags:
                warn(doc_id, "tag_mismatch", "详情页标签与列表标签不一致")
            if p["title"] != row["title"]:
                warn(doc_id, "title_mismatch", f"详情页标题与列表标题不一致（列表：{row['title']}）")
            # 答记者问标题中的日期是事件日期，不是记者会日期
            bdate = briefing_date(p["title"]) if section.name == "transcripts" else None
            if section.name == "transcripts" and bdate is None:
                warn(doc_id, "no_briefing_date", "标题中未解析出记者会日期")
            if log.get("error"):
                warn(doc_id, "crawl_note", f"抓取备注：{log['error']}")
            docs.append({
                "id": doc_id,
                "section": section.name,
                "doc_type": doc_type(section, p["title"]),
                "title": p["title"],
                "publication_date": p["page_date"] or row["list_date"],
                "briefing_date": bdate,
                "url": row["url"],
                "tags": p["tags"],
                "spokesperson": find_spokesperson(p["content"]),
                "content": p["content"],
                "raw_file": str(page_path.relative_to(DATA_DIR)),
                "raw_fragment_file": str(frag_path.relative_to(DATA_DIR)),
                "crawl_time": log["crawl_time"],
            })
    docs.sort(key=lambda d: (d["publication_date"], d["section"], int(d["id"].rsplit("_", 1)[1])))

    # 去重：网址相同或正文完全相同（非空）的只保留第一条
    kept, removed, seen_url, seen_content = [], [], {}, {}
    for d in docs:
        dup_of = seen_url.get(d["url"]) or (seen_content.get(d["content"]) if d["content"] else None)
        if dup_of:
            removed.append({"id": d["id"], "title": d["title"], "duplicate_of": dup_of,
                            "reason": "网址相同" if d["url"] in seen_url else "正文完全相同"})
            continue
        seen_url[d["url"]] = d["id"]
        seen_content.setdefault(d["content"], d["id"])
        kept.append(d)
    return kept, warnings, removed


def write_documents():
    docs, warnings, removed = build_documents()
    DOCS_JSON.write_text(json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写出 {len(docs)} 篇 -> {DOCS_JSON.relative_to(DATA_DIR.parent)}")
    for r in removed:
        print(f"  去重：{r['id']} 与 {r['duplicate_of']} {r['reason']}，已删除")
    for w in warnings:
        print(f"  ⚠ {w['id']}：{w['message']}")
    return docs, warnings, removed
