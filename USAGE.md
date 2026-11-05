# MEA_Spokesperson_Crawler 运行说明

抓取印度外交部官网 Transcripts 与 Response to Media Queries 两个栏目（2020-01-01 至 2026-03-31）的全部英文文本。任务要求与数据规则见 [README.md](README.md)。

## 运行环境

- macOS / Linux / Windows，Python 3.12（见 `.python-version`）
- [uv](https://docs.astral.sh/uv/) 管理依赖
- 本机已安装 Google Chrome（默认优先调用；不可用时回退至 Playwright Chromium，可通过 `uv run playwright install chromium` 安装）

依赖包（见 `pyproject.toml`）：`playwright`、`beautifulsoup4`、`lxml`。

```bash
uv sync
uv run playwright install chromium
```

## 运行步骤

所有命令默认无头模式运行浏览器，加 `--headed` 可显示浏览器窗口（如 `uv run mea-india --headed fetch`）。

| 步骤 | 命令 | 产出 |
| --- | --- | --- |
| 1. 抓列表 | `uv run mea-india list` | `mea_data/lists/*_list.csv`，原始列表片段在 `mea_data/lists/raw/` |
| 2. 抓详情 | `uv run mea-india fetch` | `mea_data/raw_html/`（整页 `.html` + 正文片段 `.fragment.html`），`mea_data/crawl_log.csv` |
| 3. 解析 | `uv run mea-india parse` | `mea_data/mea_documents.json` |
| 4. GlobalSecurity 核对（可选） | `uv run mea-india globalsec` | `mea_data/globalsecurity_check.json` |
| 5. 质量检查 | `uv run mea-india check` | `mea_data/check_report.md` |

- **断点续爬**：`fetch` 会跳过日志中已成功且文件存在的篇目，中断后直接重跑即可；`fetch --only-failed` 只补爬失败过的篇目。
- **样例**：`fetch --limit 10` 每个栏目只抓最新的 10 篇。
- **限速**：单线程，每次请求间隔随机 2—5 秒。
- **离线解析**：`parse` 和 `check` 只读本地文件，修改解析规则后重跑即可，无需重新爬取。
- **人工抽查**：`check` 按固定随机种子抽 10 篇；核对结果写入 `mea_data/spot_check.json`（格式 `{"mea_transcripts_40987": {"result": "通过", "note": ""}}`）后重跑 `check`。

## 代码结构

```
src/mea_india/
├── config.py     路径、栏目编号、时间范围、接口地址
├── stealth.py    指纹隐匿补丁（STEALTH_INIT_SCRIPT）与生物力学鼠标/滚轮拟真操作
├── browser.py    Playwright 封装：优先本机 Chrome、限速、429/503 退避重试、页面内同源请求、捕获接口原始响应
├── lists.py      列表抓取与解析
├── details.py    详情抓取、抓取日志、断点续爬
├── parse.py      正文清洗、字段提取、去重
├── globalsec.py  GlobalSecurity.org 交叉核对
└── check.py      质量检查报告
```
