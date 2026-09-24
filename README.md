# CRS Reports Archive | 美国国会研究局报告备份

[![CRS daily backup](https://github.com/krischen-77/crs-reports/actions/workflows/crs-backup.yml/badge.svg)](https://github.com/krischen-77/crs-reports/actions/workflows/crs-backup.yml)

每天抓取最近一周新增或更新的 CRS 报告，保存 **原始 PDF、可获得的 HTML 阅读快照、Markdown 全文**及全部已发现报告的链接目录。GitHub Actions 自动执行并提交文件，无需自建服务器。

**入口：** [最近一周报告](LATEST.md) · [全部链接 CSV](data/all-report-links.csv) · [纯文本链接](data/all-report-links.txt) · [已归档清单](data/archived-reports.csv) · [最新状态](data/status.json) · [Actions](https://github.com/krischen-77/crs-reports/actions/workflows/crs-backup.yml)

## 部署验收快照：2026-09-24

[正式工作流第 3 次运行](https://github.com/krischen-77/crs-reports/actions/runs/36005091598)于 2026-09-24 13:22 UTC / 北京时间 21:22 成功结束；24 项回归测试、文件校验、提交均通过。

| 验收项 | 结果 |
|---|---|
| 已发现报告链接目录 | 23,516 个不同报告编号 |
| 本次候选 / 成功保存 PDF | 94 / 94 个版本 |
| 累计 PDF 原文 | 94 个去重版本，70,581,433 字节，约 70.6 MB |
| HTML 阅读快照 | 91 份 |
| Markdown | 每个归档 PDF 均有对应文件 |
| PDF / 元数据错误 | 0 |
| 仍需重试 | 3 份辅助 HTML；对应 PDF 已保存 |
| 本次来源 | 官方 API 95 条记录；镜像完整目录 23,515 个编号；RSS 25 条 |

这是部署当日的静态验收快照，不随每日抓取自动改写。实时数字以 **[data/status.json](data/status.json)** 为准。`success_with_warnings` 表示原文保存成功但仍保留来源差异或辅助格式告警，不等于所有来源、所有格式都无异常。

> “全部链接”指所用公开目录中已发现的报告，不等于下载了所有历史 PDF，也不保证覆盖所有未公开或尚未收录的 CRS 产品。默认下载最近一周新增/更新的报告及未完成重试；已保存原文不会因离开一周窗口被删除。

## 自动运行规则

| 项目 | 设置 |
|---|---|
| 定时 | **每天 10:23 UTC / 北京时间 18:23**，cron `23 10 * * *` |
| 时间窗口 | UTC 当日减 7 天，起止日期均包含。例如 9 月 24 日检查 9 月 17—24 日；完整纳入边界日，避免只有日期精度的数据漏抓 |
| 新增 / 更新识别 | 镜像目录的发布日期、版本历史，结合官方 API 的发布时间与更新时间 |
| 链接目录 | 每天刷新 EveryCRSReport 完整 CSV，合并官方 API 新发现的编号，保留原目录条目 |
| 去重与版本 | 以报告编号和 PDF SHA-256 去重；不同内容分别保存，不覆盖旧 PDF |
| 重试 | 失败任务保存在 `data/pending.json`，下次继续处理，即使已离开一周窗口 |
| 手动执行 | Actions → CRS daily backup → Run workflow |

GitHub 定时任务可能排队延迟，不承诺精确到秒。官方 API 的 `updateDate` 可能只是元数据或状态更新，因此归档也可能包含发布日期较早、但本周被 API 标为更新的报告。代码和工作流更新会触发一次备份，归档提交不会循环触发。

## 数据源与免费 API

| 来源 | 用途 | 密钥 |
|---|---|---|
| Congress.gov `/v3/crsreport` | 官方编号、标题、发布日期、更新时间、文件地址，补充发现镜像未覆盖的报告 | 默认公开 `DEMO_KEY`，配额严格；建议个人免费 key |
| EveryCRSReport `reports.csv` + 每份报告 JSON | 完整公开目录、各报告版本、下载地址及来源校验信息 | 无需 |
| EveryCRSReport `rss.xml` | 补充近期发现，不用有限条数的 RSS 代替完整目录 | 无需 |
| 官方原文地址 / EveryCRSReport 镜像 | 获取原始 PDF 及 HTML 阅读材料 | 无需登录；访问拒绝或限流会记录并停止继续请求相应来源或路径类别 |

**使用的是 EveryCRSReport 第三方 RSS，不冒称 CRS 官方 RSS。** 下载先尝试元数据给出的可访问官方地址，再使用公开镜像，逐份记录实际来源。不请求旧元数据中的非公开 `www.crs.gov` 地址，不绕过登录、验证码或访问限制。

### 推荐：配置个人免费 API Key

零配置模式已跑通：公开镜像配合官方 API 的演示 key。演示 key 有共享 IP 限额，不应视为生产稳定性保证；脚本每次最多使用 20 个演示 API 请求并记录限流 / 降级。

在 <https://api.congress.gov/sign-up/> 申请个人 key，然后进入仓库 **Settings → Secrets and variables → Actions → New repository secret**，名称填写 **`CONGRESS_API_KEY`**，值填写自己的 key。

不要把 key 写进代码、README、Issue 或聊天。工作流从 GitHub Secret 注入，仅向 `api.congress.gov` 发送。提交归档使用自动提供的 `GITHUB_TOKEN`，无需个人 GitHub token。

## PDF、HTML、Markdown：保存边界

**PDF 是原件与完整图表的依据。** 必须有 PDF 文件头、能够被解析器打开；镜像提供 SHA-1 时必须完全匹配。归档另存 SHA-256，提交前逐份重新校验。失败的镜像字节不会因备用来源而被放行。

镜像 PDF 校验失败时，可独立向官方 API 解析原文地址；仅在官方元数据的发布日期与待归档版本相同的条件下尝试独立官方原文，并记录 `source_recovery`。这不是接受校验失败的镜像，也不声称两个来源的文件字节一致。官方日期不同则不拿新报告替换旧报告。

**HTML 是辅助阅读快照，不保证是官方原始字节。** 镜像可能提供清理后的 HTML 片段或由 PDF 转换的 HTML；文件名有时仍带转换前的哈希。此类文件仅在明确标为衍生格式并通过报告编号检查后保存，记录自身 SHA-256 和 `html_provenance`。HTML 失败时仍保留原始 PDF，并从 PDF 提取文本。

**Markdown 是全文转换，不是 AI 摘要或改写。** 表格、公式、外链图片及版式可能不完整；PDF 才是最终依据。无可用文本层时明确标注，不自动 OCR。

### API 版本号与 PDF 修订号

实际联调发现两者可能不同：同一发布日期的 `IF11806`，API 元数据版本为 10，但镜像给出的官方 PDF 文件名修订号为 11。因此分别保存 `api_metadata_version` 和 PDF 的 `version`，以发布日期判断补抓需要，并保留差异记录；不单凭数字不一致重复下载较旧 PDF，也不把相同日期当成字节相同的证明。

目录字段 `official_page_verified_by_api` 表示该编号曾由官方 API 返回，**不是逐个网页 HTTP 探测成功的证明**；早期报告的 Congress.gov 页面可能不存在。

## 目录结构

```text
.github/workflows/crs-backup.yml  定时备份、手动补抓、校验与提交
.github/workflows/source-check.yml  来源连通性诊断
.github/workflows/source-audit.yml  来源格式诊断
scripts/sync_crs.py             抓取、分页、下载、索引、版本与重试
tests/                         24 项离线回归测试
pdf/{类型}/                    原始 PDF
html/{类型}/                   HTML 阅读快照，衍生性质见 manifest
markdown/{类型}/               全文格式转换与来源说明
metadata/sources/{编号}.json    来源版本元数据
data/all-report-links.csv      全部已发现报告链接，UTF-8 BOM
data/all-report-links.txt      去重链接列表
data/archived-reports.csv      实际已归档版本
data/archive-manifest.json     路径、哈希、页数、实际来源、转换方式
data/catalog.json              累积发现目录
data/pending.json              继续重试的报告及版本
data/status.json               最新计数、来源覆盖、告警和错误
data/runs/                     每次运行的独立记录
data/sources/                  原始 CSV / RSS 响应
LATEST.md                      发布日期在当前窗口内的已备份报告
```

类型包括 `in-focus`、`insights`、`reports`、`sidebars`、`infographics`、`testimony`。PDF 文件名为 `报告编号vPDF修订号-发布日期-SHA256前16位.pdf`。同一天不同内容不会互相覆盖。去重统计以 manifest 为准；修订号标注迁移可能留下同内容的历史文件别名，不应按目录文件数重复计数。

## 手动运行与历史补抓

打开 **Actions → CRS daily backup → Run workflow**，分支选 `main`。

| 参数 | 默认 | 说明 |
|---|---|---|
| `days` | `7` | 回看天数，可改为 `30`、`90`；允许 1—3650 |
| `until` | 空 | 默认 UTC 今天，或指定 `YYYY-MM-DD` |
| `full_catalog` | `false` | `true` 分页刷新整个官方 API 目录，需要个人 `CONGRESS_API_KEY` |

`full_catalog` 只扩大**官方链接目录**，不会下载全部历史 PDF。扩大 `days` 才扩大原文窗口。历史版本取决于上游保存情况；API 一般描述当前元数据，不能保证复原过去某日的完整网站状态。大规模回填请按日期分批，避免超过单次 90 分钟限制。

## 故障与完整性判断

PDF 或元数据失败会让本次工作流明确失败；已经成功且通过校验的文件与重试队列仍提交。只有 HTML 失败时保留 PDF、抽取文本并记录告警。备用来源可用不等于覆盖全部官方报告；尚未进入任何公开数据源的材料可能暂时不可发现。

`data/status.json` 分开记录候选报告、尝试版本、成功版本、新增 / 累计 PDF、HTML 快照、待重试数量和来源状态。来源版本字段不同、镜像格式经过处理、校验失败后由官方独立恢复，都保留记录，不为了让状态变绿而隐去事实。

## 本地运行与维护

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

文件直接提交到 Git，不依赖会过期的 Actions artifact。长期保存会增大仓库，单个下载上限 80 MiB，超大文件明确报错；当前不自动删除历史。未来数据量大时可另行按年份拆仓或迁移存储。

第三方 Actions 固定 commit SHA，直接 Python 依赖固定版本；升级先跑测试。GitHub 可能停用长期无活动的公开仓库定时任务，应留意 Actions 页面。

## 来源与使用边界

本项目不代表 CRS、美国国会或 EveryCRSReport。报告中的第三方图片等可能保留第三方权利。仓库已有 `LICENSE` 未修改，不能据此认为来源报告和图片自动采用本项目的软件许可证。

- Congress.gov API：<https://github.com/LibraryOfCongress/api.congress.gov>
- CRS 端点：<https://github.com/LibraryOfCongress/api.congress.gov/blob/main/Documentation/CRSReportEndpoint.md>
- EveryCRSReport 数据说明：<https://www.everycrsreport.com/download.html>
- 完整目录：<https://www.everycrsreport.com/reports.csv>
- RSS：<https://www.everycrsreport.com/rss.xml>
- API key 与演示限额：<https://api.data.gov/docs/developer-manual/>
- GitHub 定时事件：<https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule>
- 目录排布参考：<https://github.com/ProfAmiot/crs-reports>。本仓库不是其副本，报告由上述公开数据源采集。
