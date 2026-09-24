# CRS Reports Archive | 美国国会研究局报告备份

[![CRS daily backup](https://github.com/krischen-77/crs-reports/actions/workflows/crs-backup.yml/badge.svg)](https://github.com/krischen-77/crs-reports/actions/workflows/crs-backup.yml)

每天抓取最近一周新增或更新的 CRS 报告，备份 **原始 PDF、可获得的 HTML 阅读快照、便于检索的 Markdown 全文**，同时保存全部已发现报告的链接目录、来源元数据、校验值及运行记录。无需自建服务器；GitHub Actions 自动执行，并把备份提交到本仓库。

**入口：** [最近一周已备份报告](LATEST.md) · [全部已发现报告链接 CSV](data/all-report-links.csv) · [纯文本链接](data/all-report-links.txt) · [实际归档清单](data/archived-reports.csv) · [最近运行状态](data/status.json) · [Actions](https://github.com/krischen-77/crs-reports/actions/workflows/crs-backup.yml)

> “全部链接”指公开数据源目录中已发现的报告，不等于下载了所有历史报告，也不保证覆盖所有曾经撰写或未公开的 CRS 产品。原文下载范围是最近一周新增/更新的报告及未完成的重试任务；已保存文件不会因离开一周窗口被删除。判断完整性请看 `data/status.json`，不要把“有链接”视为“已下载原文”。

## 自动运行

| 项目 | 设置 |
|---|---|
| 时间 | 每天 **10:23 UTC / 北京时间 18:23**，cron `23 10 * * *` |
| 回看窗口 | UTC 当日减 7 天，起止日期均包含。例如 9 月 24 日运行，检查 9 月 17—24 日；完整纳入边界日避免日期精度不足造成遗漏 |
| 新增/更新识别 | 镜像目录的发布日期及版本历史，结合官方 API 的发布时间、更新时间 |
| 链接目录 | 每天刷新 EveryCRSReport 完整 CSV，合并官方 API 新发现的编号；保留旧目录条目 |
| 原文保存 | 原始 PDF 按内容校验值去重；不同内容的版本分别保留 |
| 失败处理 | 成功文件先校验、提交；失败报告进入持久队列，下次继续尝试，不受一周窗口限制 |
| 初次部署 / 修改代码 | 自动触发一次；也支持手动运行 |

GitHub 定时任务可能排队延迟，不是精确到秒的执行承诺。官方 API 的 `updateDate` 可能只是元数据或状态更新，因此归档也可能包含发布日期早于一周、但本周被 API 标为更新的报告。

## 数据源

| 来源 | 用途 | 密钥 |
|---|---|---|
| Congress.gov `/v3/crsreport` | 官方编号、标题、发布日期、更新时间及文件地址；补充发现镜像未覆盖的报告 | 默认公开 `DEMO_KEY`，配额严格；建议配置个人免费 key |
| EveryCRSReport `reports.csv` + 单份报告 JSON | 完整公开目录、各报告版本、PDF/HTML 地址和来源校验信息 | 无需 |
| EveryCRSReport `rss.xml` | 补充近期发现，**不能用有限条数的 RSS 代替完整目录** | 无需 |
| Congress.gov 原文 / EveryCRSReport 镜像 | 获取 PDF 原件和 HTML 阅读材料 | 无需登录；访问拒绝或限流时记录并停止继续请求相应来源或路径类别 |

**RSS 使用的是 EveryCRSReport 第三方信息源，不冒称 CRS 官方 RSS。** 原始链接来自公开元数据；下载时优先尝试可访问的官方地址，再使用对应的公开镜像。每份文件都记录实际下载来源。不会请求旧元数据中非公开的 `www.crs.gov` 地址，也不会绕过登录、验证码或访问限制。

### PDF、HTML 与 Markdown 的区别

**PDF 是原件与完整图表的依据。** 文件必须有 PDF 文件头，能够被 PDF 解析器打开；上游提供 SHA-1 时必须完全匹配。归档另存 SHA-256，提交前逐份再次核验。PDF 校验不会因备用来源而放宽。

**HTML 是辅助阅读快照，不保证是官方原始字节。** EveryCRSReport 可能提供清理过的 HTML 片段或从 PDF 转换的 HTML；其文件名可能仍携带转换前的哈希。镜像 HTML 与原始哈希不一致时，仅在明确标为衍生版本且通过报告编号检查后保存，记录自身 SHA-256 和 `html_provenance`。HTML 不可获取时保留 PDF，并抽取 PDF 文本生成 Markdown；不会为了让任务变绿而伪造原文。

**Markdown 是全文格式转换，不是 AI 摘要或改写。** 表格、公式、外链图片和排版可能不完整，原始 PDF 才是最终依据。无可用文本层时明确标注，不自动 OCR。

### API 版本号与 PDF 修订号

2026-09-24 的实际联调发现，两者可能不同，例如同一发布日期的 `IF11806`，API 元数据为版本 10，镜像提供的官方 PDF 地址修订号为 11。因此分别保留 `api_metadata_version` 和 PDF 的 `version`，以发布日期判断是否还需要补抓，并记录差异；不声称不同来源字节一致，也不单凭数字不一致重复下载较旧 PDF。

目录中 `official_page_verified_by_api` 表示该编号曾由官方 API 返回，**不是逐个网页 HTTP 探测成功的证明**。旧报告的 Congress.gov 页面可能不存在。

## 目录结构

```text
.github/workflows/crs-backup.yml  定时备份、手动补抓、校验和提交
.github/workflows/source-check.yml  来源连通性诊断
.github/workflows/source-audit.yml  来源格式诊断
scripts/sync_crs.py             抓取、分页、下载、索引、版本与重试逻辑
tests/                         22 项离线回归测试
pdf/{类型}/                    原始 PDF
html/{类型}/                   HTML 阅读快照，来源及衍生性质见 manifest
markdown/{类型}/               转换后的全文与来源说明
metadata/sources/{编号}.json    来源版本元数据
data/all-report-links.csv      全部已发现报告的链接目录，UTF-8 BOM
data/all-report-links.txt      去重链接列表
data/archived-reports.csv      实际已归档的报告版本
data/archive-manifest.json     路径、哈希、页数、实际来源、转换方式
data/catalog.json              累积发现目录
data/pending.json              下次继续重试的报告及版本
data/status.json               最新运行状态、来源覆盖、计数、告警与错误
data/runs/                     每次运行的独立记录
data/sources/                  原始 CSV / RSS 响应
LATEST.md                      发布日期在当前窗口内的已备份报告
```

类型目录包括 `in-focus`、`insights`、`reports`、`sidebars`、`infographics` 和 `testimony`。PDF 文件名：

```text
报告编号vPDF修订号-发布日期-SHA256前16位.pdf
```

同一天不同内容的 PDF 不互相覆盖。统计以 `archive-manifest.json` 的“报告编号 + PDF SHA-256”去重记录为准；迁移修订号标注时可能留下同一内容的历史文件别名，不应按目录文件数重复统计。

## 手动运行与历史补抓

打开 **Actions → CRS daily backup → Run workflow**，分支选 `main`。

| 参数 | 默认 | 说明 |
|---|---|---|
| `days` | `7` | 向前回看天数，可填 `30`、`90` 等；范围 1—3650 |
| `until` | 空 | 默认 UTC 今天；历史补抓可填写 `YYYY-MM-DD` |
| `full_catalog` | `false` | `true` 分页刷新整个官方 API 目录，需要个人 `CONGRESS_API_KEY` |

`full_catalog` 仅扩大**官方链接目录**，不会自动下载全部历史 PDF。扩大 `days` 才扩大原文时间窗口；历史版本可得性取决于上游保存情况，API 元数据一般描述当前状态，不能保证复原过去某日的完整网站状态。大规模回填请分批，避免超过单次任务 90 分钟限制。

### 推荐配置个人免费 API Key

零配置模式已实现：使用公开镜像，辅以 API 的公开 `DEMO_KEY`。演示 key 有共享 IP 限额，不应视为生产稳定性保证。脚本最多使用 20 个演示 API 请求，并记录限流/降级情况。更稳定的官方核对及全量官方目录可这样配置：

1. 在 <https://api.congress.gov/sign-up/> 申请个人 key。
2. 仓库 **Settings → Secrets and variables → Actions → New repository secret**。
3. 名称填 **`CONGRESS_API_KEY`**，值填自己的 key。

不要将 key 写进代码、README、Issue 或聊天。工作流只通过 Secret 注入，并只向 `api.congress.gov` 发送；提交归档使用 GitHub 自动提供的 `GITHUB_TOKEN`，无需额外个人 GitHub token。

## 完整性与故障状态

`data/status.json` 分开记录目录数、候选报告数、尝试版本数、成功版本数、新增/累计 PDF 数、HTML 快照数、待重试数量以及来源状态。

- **PDF 或元数据失败**：本次运行明确失败；已成功且校验通过的文件和重试队列仍提交。
- **仅 HTML 失败**：保留 PDF 和抽取文本，标记告警并继续重试 HTML。
- **来源不可用但备用来源可用**：标注降级，不能据此推断覆盖全部官方报告。
- **源站版本字段不同 / HTML 为衍生格式**：记录来源差异，不伪称字节级原件一致。

API `updateDate`、目录日期及 RSS 均有同步延迟，尚未进入任何数据源的报告可能暂时不可发现。每次运行的状态比静态 README 更能反映当前覆盖情况。

## 本地运行

```bash
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/sync_crs.py --days 7
# 通过环境变量安全设置个人 CONGRESS_API_KEY 后：
python scripts/sync_crs.py --days 7 --full-catalog
```

## 保存与维护

备份直接提交到 Git，不依赖会过期的 Actions artifact。长期归档会增大仓库；单个下载上限为 80 MiB，超大文件会明确报错，不悄悄跳过。当前不自动删除历史；未来数据量增大时可另行按年份拆仓或迁移存储。

第三方 Actions 固定 commit SHA，直接 Python 依赖固定版本；更新后先运行测试。公开仓库长期无活动时 GitHub 可能停用定时任务，应留意 Actions 页面。归档提交不包含代码路径，不会循环触发工作流。

## 来源与使用边界

本项目是独立备份，不代表 CRS、美国国会或 EveryCRSReport。CRS 报告包含的第三方图片等可能保留第三方权利。已有 `LICENSE` 未修改，不能据此认为来源报告和第三方图片自动采用本项目的软件许可证。

- Congress.gov API：<https://github.com/LibraryOfCongress/api.congress.gov>
- CRS API 说明：<https://github.com/LibraryOfCongress/api.congress.gov/blob/main/Documentation/CRSReportEndpoint.md>
- EveryCRSReport 数据说明：<https://www.everycrsreport.com/download.html>
- 完整目录：<https://www.everycrsreport.com/reports.csv>
- RSS：<https://www.everycrsreport.com/rss.xml>
- API key 与演示限额：<https://api.data.gov/docs/developer-manual/>
- GitHub 定时事件：<https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule>
- 排布参考：<https://github.com/ProfAmiot/crs-reports>；本仓库不是其副本，报告由以上公开数据源采集。
