好的，以下是任务说明全文，你可以直接复制使用。
# 印度外交部记者会实录与答记者问爬取任务说明

## 一、任务背景与目标

请完整抓取印度外交部官网两个栏目在 2020 年 1 月 1 日至 2026 年 3 月 31 日期间发布的全部英文文本，约 700 篇，整理成结构化数据。数据将用于研究印度政府在中印边界问题上的官方表态，并与同一时间段的印度媒体报道语料对照分析。

本任务只负责完整、原样地收集和整理数据，**不需要做任何内容筛选或判断**。哪些内容涉华、涉及边界，由后续分析统一处理。

## 二、数据来源与抓取范围

数据来源为印度外交部官网 www.mea.gov.in，抓取以下两个栏目在时间范围内的**全部**文本。

| 栏目 | 网站路径 | 内容 | 预计篇数 |
| --- | --- | --- | --- |
| Transcripts（记者会实录） | Media → Media Briefings → Transcripts | 外交部发言人例行记者会、线上记者会、专题吹风会的文字实录，问答格式 | 约 500 篇 |
| Response to Media Queries（答记者问） | Media → Media Releases → Response to Media Queries | 发言人针对具体事件发布的书面回应，篇幅短 | 约 200 篇 |

抓取范围的几条规则：

- **时间**：发布日期在 2020-01-01 至 2026-03-31 之间，两端都包含。"发布日期"指网站页面日期（列表页和详情页 `.date` 显示的日期），与网站自身的日期筛选口径一致；标题括号中的记者会召开日期另存为 `briefing_date`，不用于判断范围。
- **不按标签筛选**：网站上的 Tags 筛选（包括 China 标签）一律不用，两个栏目都全量抓取。
- **不按标题筛选**：Transcripts 栏目里有多种标题，例如 "Transcript of Weekly Media Briefing…"、"Transcript of Virtual Weekly Media Briefing…"（2020—2021 年疫情期间）、"Special Briefing…"，全部都要。
- **只要英文版**：部分文件有印地语或其他语言版本，只保留英文版。列表和详情一律以英文（`PLngId=1` / `languageId=1`）请求；**不统计**哪些篇目另有其他语言版本。

## 三、技术要求

外交部网站可能有反爬虫机制。本项目技术栈为 **Python + Selenium**（驱动真实 Chrome 浏览器），按以下步骤进行。

1. **先摸清网站结构**。网站近期改版，列表内容可能由后台接口动态加载。用浏览器打开列表页，按 F12 打开开发者工具的 Network（网络）标签，翻到第 2 页，找到返回列表数据的请求，记下它的网址和参数。直接请求这个接口抓列表，比解析整页网页简单。
2. **先抓列表，再抓详情页**。先把两个栏目的完整列表（标题、日期、网址、标签）抓下来存成文件，再逐篇抓取详情页。
3. **先存原始 HTML，再解析**。每篇详情页的 HTML 原样保存到本地，以后修改解析规则时不需要重新爬取。
4. **应对反爬**：
    - 使用 Selenium 驱动真实 Chrome 浏览器，同一浏览器会话保持 cookie；
    - 单线程，每次请求间隔 2—5 秒（随机），不要并发；
    - 仍然被拦截时暂停并记录，再商量处理方式。
5. **记录日志，支持断点续爬**。每篇记录抓取时间和是否成功，失败的单独列出后补爬，不要从头重来。

### 网站结构（2026-10-12 浏览器探查结果）

网站已改版，列表和正文都由后台接口以 **HTML 片段**（不是 JSON）动态加载：

| 用途 | 接口 | 说明 |
| --- | --- | --- |
| 列表 | `/FrontEnd/FetchPublicationListingData?publicationId={ID}&KeywordName=&SortBy=new&page={N}&PageSize=100&DateRange={起} - {止}&IsInternalMEA=false&PLngId=1` | 每条为 `.pressRelesastBox`：日期 `.date`、标题与网址 `.pressTitle a`、标签 `.tags a`；总数见 `.paginationBox` 中 "Displaying Item x To y of N" |
| 详情 | `/FrontEnd/FetchPublicationDetailData?pkid={网站编号}&languageId=1` | 日期 `.date`、标题 `h2.titleText`、正文 `.description`、标签 `.tags a` |

- 栏目编号：Transcripts 为 `publicationId=49`（注意页面网址 `media-briefings?51/Transcripts` 中的 51 不是接口编号）；Response to Media Queries 为 `publicationId=69`（页面 `response-to-queries?69/Media_Queries`）。
- `DateRange` 只接受 `dd/mm/yyyy - dd/mm/yyyy`，其他格式会被静默忽略并返回全部年份。由于无法验证接口对边界日期是否包含，列表抓取时把范围前后各放宽约一周，再在本地按页面日期严格筛选 2020-01-01 至 2026-03-31（两端包含）。
- 详情页网址格式：`https://www.mea.gov.in/media-briefings?dtl/{编号}/{标题slug}`、`https://www.mea.gov.in/response-to-queries?dtl/{编号}/{标题slug}`。
- 探查时范围内条数：Transcripts 458 篇（全站 3217），Response to Media Queries 222 篇（全站 392），网址无重复。
- 2020—2021 年老页面段落多以 `<br>` 分隔而非 `<p>`。

**备用核对来源**：GlobalSecurity.org 转载了外交部的例行记者会实录，网址规律为 `globalsecurity.org/wmd/library/news/india/年份/india-年月日-india-meab01.htm`，例如 https://www.globalsecurity.org/wmd/library/news/india/2024/india-240912-india-meab01.htm 。它只用于核对篇数或补缺，不作为正式数据来源。注意网址里的日期是转载日期，可能比记者会晚一天，日期一律以正文标题为准。

## 四、交付物与目录结构

请把以下内容打包成一个文件夹交付：

1. **原始 HTML**：每篇保存两个文件：
    - 整页：Selenium 渲染完成（`.description` 出现）后的完整页面源码，文件名 `类型_日期_网站编号.html`，例如 `transcript_2024-09-12_38297.html`、`response_2022-03-23_34982.html`；
    - 正文片段：详情接口返回的 HTML 片段原样保存，文件名 `类型_日期_网站编号.fragment.html`，解析以此为准。

    日期为页面日期（`publication_date`）。网站编号取详情页网址中的数字编号；没有编号时用标题前几个英文单词代替。
2. **列表文件**：两个栏目各一份 CSV，记录列表页上的标题、日期、网址、标签。
3. **结构化数据** `mea_documents.json`：两个栏目合并为一个文件，字段见第五节。
4. **抓取日志** `crawl_log.csv`：每篇一行，记录网址、抓取时间、是否成功、失败原因。
5. **质量检查报告** `check_report.md`：内容见第七节。
6. **代码和说明**：爬虫和解析脚本，以及一份 README，说明运行环境、依赖包和运行步骤。

```
mea_data/
├── raw_html/
│   ├── transcripts/          # *.html 整页 + *.fragment.html 正文片段
│   └── media_responses/
├── lists/
│   ├── transcripts_list.csv
│   └── media_responses_list.csv
├── mea_documents.json
├── crawl_log.csv
├── check_report.md
├── code/
└── README.md
```

## 五、数据字段规范

`mea_documents.json` 为 UTF-8 编码的 JSON 数组，每篇文本一条记录，按日期升序排列。保存时不要转义中文和特殊字符（Python 中设置 `ensure_ascii=False`）。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | 字符串 | 唯一编号，格式为 `mea_{section}_{网站编号}`，如 `mea_transcripts_38297`、`mea_media_responses_34982` |
| section | 字符串 | 所属栏目：`transcripts` 或 `media_responses` |
| doc_type | 字符串 | 文本类型，取值规则见下表 |
| title | 字符串 | 标题，原样保留 |
| publication_date | 字符串 | 发布日期，格式 `YYYY-MM-DD`，取页面日期（详情页 `.date`，与列表日期一致） |
| briefing_date | 字符串或 null | 标题末尾括号中的日期（如 "(January 30, 2020)"），格式 `YYYY-MM-DD`；常比 `publication_date` 早一天；标题中没有日期时填 null |
| url | 字符串 | 详情页网址 |
| tags | 字符串列表 | 网站标签，没有则为空列表 |
| spokesperson | 字符串或 null | 发言人姓名，从正文中 "Shri ……, Official Spokesperson" 一类表述提取；找不到填 null |
| content | 字符串 | 清洗后的正文，规则见第六节 |
| raw_file | 字符串 | 对应整页原始 HTML 文件的相对路径 |
| raw_fragment_file | 字符串 | 对应正文片段 HTML 文件的相对路径 |
| crawl_time | 字符串 | 抓取时间，格式 `YYYY-MM-DD HH:MM:SS` |

`doc_type` 按标题判断，不区分大小写，按表中顺序依次匹配，命中即停：

| 取值 | 判断规则 |
| --- | --- |
| weekly_briefing | Transcripts 栏目，标题含 "Weekly Media Briefing"（包括 "Virtual Weekly Media Briefing"、"Bi-weekly Media Briefing"） |
| special_briefing | Transcripts 栏目，标题匹配正则 `special.*briefing`，即 "Special" 在前、"Briefing" 在后，中间可有其他词，如 "Special Briefing"、"Special Media Briefing"、"Special media briefing"、"Special Virtual Briefing" |
| other_briefing | Transcripts 栏目中不符合以上两条的 |
| media_response | Response to Media Queries 栏目的全部文本 |

## 六、文本清洗规则

清洗只去掉网页框架，**正文内容一个字都不改**。

要去掉的：

- 导航栏、菜单、页眉页脚、侧边栏、分享按钮、"相关链接"等网页元素；
- HTML 标签和脚本，HTML 实体转换为正常字符（如 `&amp;` 转为 `&`）；
- 行首行尾多余的空格，以及连续的空行（合并为一个）；
- 正文末尾指向其他语言版本 PDF 的链接：链接文字为 "Click here for Xxx version"（如 "Click here for Assamese version"，常见于 2025 年以后的 Response to Media Queries，通常为 11 种印度地方语言）且指向 `.pdf` 文件的链接，连同其后的 PDF 图标一并去掉。紧邻其前的落款（如 "New Delhi" 和日期行）属于正文，保留。

要保留的：

- **段落分隔**：段落之间用一个换行符 `\n` 分隔，不要把全文拼成一段；
- **说话人标识**：如 "Shri Randhir Jaiswal, Official Spokesperson:"、"Sidhant:"，后续要靠它切分问答；
- **印地语内容和翻译**：实录中有拉丁字母拼写的印地语问答，后面附有方括号标注的 "Approximate Translation" 英文意译，两者都原样保留，不要删除或自行翻译；
- 原文中的拼写错误、口语化表达和不完整句子，一律不改；
- 原文本身的字符缺失也不修补。例如 2020 年部分实录网站源码中撇号缺失（"I'll" 写作 "Ill"、"we've" 写作 "weve"），原样保留。

段落切分：`.description` 内的 `<p>`、`<div>` 等块级元素边界和 `<br>` 均视为换行；只做 HTML 实体解码（含 `&nbsp;` 转为空格）、行首行尾空白去除和空行合并，不做其他字符替换（如不统一引号、不改 Unicode 字符）。

如果某篇详情页没有正文、只提供 PDF 附件，请下载 PDF 并在 `content` 中填入 PDF 提取的文字，同时在质量检查报告中列出这些篇目。

## 七、质量检查要求

爬取完成后，请做以下检查，并把结果写进 `check_report.md`：

- [ ] **总数核对**：两个栏目各抓到多少篇，与列表中落在时间范围内的条数是否一致（网站显示的总数通常包含全部年份，不直接用于核对）；例行记者会另用 GlobalSecurity.org 交叉核对（该站无可用目录页，做法是：对数据中没有 `weekly_briefing` 的周，逐日探测其转载网址，含次周周一；探到的篇目回外交部网站确认是否漏抓）。不一致时列出缺失或多出的篇目。
- [ ] **按月统计**：按栏目和月份统计篇数，做成一张表。例行记者会大约每周一次，某个月份为 0 篇或明显偏少时，回到网站确认是确实没有发布，还是漏抓了。
- [ ] **类型统计**：按 `doc_type` 统计篇数，并列出所有 `other_briefing` 的标题，方便确认分类。
- [ ] **空值检查**：列出 `content` 为空或少于 200 个字符、`spokesperson` 为 null 的篇目。
- [ ] **去重**：检查是否有网址或正文完全相同的重复记录，有则只保留一条，并在报告中说明。
- [ ] **语言检查**：确认没有非英文版本混入（全部以 `languageId=1` 抓取；检查标题和正文中不含天城文字符，拉丁字母拼写的印地语问答属正常内容）。
- [ ] **人工抽查**：随机抽 10 篇，逐篇和网站原页面对照，确认标题、日期和正文完整无误，在报告中列出抽查的篇目和结果。
- [ ] **失败清单**：日志中最终仍然失败的篇目及原因。

## 八、可选扩展任务：切分发言轮次

这一部分不是必做项，开始前请先确认。

任务是把记者会实录（`weekly_briefing`、`special_briefing`、`other_briefing`）按说话人切分成发言轮次，输出 `mea_turns.json`。之所以切成"轮次"而不是直接配成"问答对"，是因为发言人经常把几位记者的问题合并起来一起回答，自动配对容易出错，配对留到后续分析时处理。

| 字段 | 说明 |
| --- | --- |
| turn_id | 编号，格式为 `文档id_序号`，如 `mea_transcripts_38297_015` |
| doc_id | 所属文档的 id |
| publication_date | 日期 |
| order | 在该篇实录中的顺序，从 1 开始 |
| speaker | 说话人原文标识，如 "Shri Randhir Jaiswal, Official Spokesperson" |
| speaker_role | `spokesperson`（发言人）、`official`（其他官员，如专题吹风会上的外交秘书）、`journalist`（记者）、`moderator`（主持人或代读问题的官员）、`unknown` |
| outlet | 记者自报的所属媒体，如 WION、PTI、ANI，识别不出填 null |
| text | 这一轮的发言内容，原样保留 |

切分时要注意两种特殊情况：

- 2020—2021 年的线上记者会，问题由外交部官员代读，格式类似 "Gautam Lahiri is asking, …"。这类轮次的 `speaker_role` 标为 `moderator`，提问记者的姓名尽量识别出来，记在 `speaker` 中。
- 记者常在发言开头自报姓名和媒体，例如 "Sidhant from WION"，`outlet` 从这里提取。

## 九、时间安排与沟通

建议分三步交付，每一步确认后再进行下一步，避免返工：

1. **样例交付**：两个栏目各抓时间范围内（截至 2026-03-31）最新的 10 篇，按本说明的格式整理后先发给我确认。
2. **全量交付**：样例确认无误后全量抓取，交付全部数据、日志和质量检查报告。
3. **可选任务**：如需要，再确认是否进行发言轮次切分。

其他事项：

- 遇到本说明没有覆盖的情况，例如网站结构和描述不符、某类页面格式特殊，请先记录下来问我，不要自行决定处理方式。
- 数据仅用于学术研究，抓取时请控制频率，不要对网站造成负担。
- 截止日期：待定。