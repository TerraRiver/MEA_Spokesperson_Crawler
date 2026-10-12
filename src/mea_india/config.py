"""项目常量：路径、栏目定义、时间范围、接口地址。"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "mea_data"
RAW_DIR = DATA_DIR / "raw_html"
LIST_DIR = DATA_DIR / "lists"
DOCS_JSON = DATA_DIR / "mea_documents.json"
CRAWL_LOG = DATA_DIR / "crawl_log.csv"
CHECK_REPORT = DATA_DIR / "check_report.md"

BASE_URL = "https://www.mea.gov.in"

# 正式时间范围（两端包含），按页面日期判断
START_DATE = date(2020, 1, 1)
END_DATE = date(2026, 3, 31)
# 请求列表时前后各放宽，避免接口边界是否包含的不确定性；本地再严格筛选
QUERY_START = date(2019, 12, 24)
QUERY_END = date(2026, 4, 7)

LIST_PAGE_SIZE = 100
DELAY_RANGE = (2.0, 5.0)  # 每次请求之间的随机间隔（秒）


@dataclass(frozen=True)
class Section:
    name: str            # transcripts / media_responses
    file_prefix: str     # 原始 HTML 文件名前缀
    publication_id: int  # 列表接口的 publicationId
    landing_path: str    # 栏目列表页（用于建立浏览器会话）


SECTIONS = {
    "transcripts": Section("transcripts", "transcript", 49, "/media-briefings?51/Transcripts"),
    "media_responses": Section("media_responses", "response", 69, "/response-to-queries?69/Media_Queries"),
}


def list_api_url(section: Section, page: int) -> str:
    dr = f"{QUERY_START:%d/%m/%Y} - {QUERY_END:%d/%m/%Y}"
    from urllib.parse import quote

    return (
        f"{BASE_URL}/FrontEnd/FetchPublicationListingData?publicationId={section.publication_id}"
        f"&KeywordName=&SortBy=new&page={page}&PageSize={LIST_PAGE_SIZE}"
        f"&DateRange={quote(dr)}&IsInternalMEA=false&PLngId=1"
    )


def detail_api_url(doc_no: str) -> str:
    return f"{BASE_URL}/FrontEnd/FetchPublicationDetailData?pkid={doc_no}&languageId=1"
