# CRS Reports Archive | 美国国会研究局报告备份

[![CRS daily backup](https://github.com/krischen-77/crs-reports/actions/workflows/crs-backup.yml/badge.svg)](https://github.com/krischen-77/crs-reports/actions/workflows/crs-backup.yml)

每天抓取最近一周新增或更新的 CRS 报告，备份 **原始 PDF、可获得的 HTML 原文、便于检索的 Markdown 全文**，同时保存报告链接目录、来源元数据、版本校验值与运行记录。无需自建服务器；备份由 GitHub Actions 执行并提交到本仓库。

**入口：** [最近一周已备份报告](LATEST.md) · [全部已发现报告链接 CSV](data/all-report-links.csv) · [纯文本链接](data/all-report-links.txt) · [实际归档清单](data/archived-reports.csv) · [最近运行状态](data/status.json) · [Actions](https://github.com/krischen-77/crs-reports/actions/workflows/crs-backup.yml)

> “全部链接”指已发现的公开目录中的报告编号，不等于已下载所有历史报告。默认只下载一周窗口内的原文，已有原文永久保留；未公开、未收录、尚未被数据源同步的报告不保证覆盖。请以 `data/status.json` 的来源状态、错误及待重试数判断本次完整性，而不是仅看文件夹是否存在。

## 自动运行

- **每天 10:23 UTC / 北京时间 18:23**：`23 10 * * *`。GitHub 调度可能排队延迟，并非精确到秒的执行承诺。
- **滚动回看 7 天**：UTC 当日减 7 天，起止日期都包含。例如 9 月 24 日运行，检查 9 月 17—24 日；起始日整日纳入是为避免只有日期、没有时间的数据被漏掉。
- 按目录中的报告发布/修订日期，以及官方 API 的更新日期发现变化；每日重叠抓取，以内容校验值去重。
- 同一周有多个版本时逐版保存；同一天内容发生变化也保留不同文件，不覆盖旧 PDF。
- 每日刷新 EveryCRSReport 的完整公开 CSV 目录；官方 API 默认检查最近一周更新。RSS 只补充发现，不用有限条数的 feed 代替完整目录。
- 每次运行都保留状态凭证和失败队列。失败的报告在下次运行继续尝试，**即使已经离开一周窗口也不会丢弃待办**。

## 数据源与可靠性

| 来源 | 用途 | 是否需要密钥 |
|---|---|---|
| Congress.gov 官方 API `/v3/crsreport` | 官方报告编号、版本、发布时间与更新时间；补充发现镜像尚未覆盖的报告 | 默认使用公开、严格限量的 `DEMO_KEY`；可配置个人免费 key |
| EveryCRSReport 完整 CSV + 每份报告 JSON | 全目录链接、原文下载地址、多个历史版本与来源 SHA-1 | 不需要 |
| EveryCRSReport RSS | 补充近期报告发现；**这是第三方 RSS，不是 CRS 官方 RSS** | 不需要 |
| Congress.gov 原文地址 / EveryCRSReport 原文镜像 | 原始 PDF 和可获得的 HTML | 不需要；遇到 403/429 记录异常并停止对该主机继续请求 |

下载时优先尝试元数据给出的 Congress.gov 原文地址，失败或内容与该版本校验值不符时使用公开镜像。**每份文件记录实际下载 URL，不把镜像下载冒充官方网站直接下载。** 本项目不绕过验证码、登录、403 或访问限制。

PDF 必须有 PDF 文件头、可被 PDF 解析器打开，并在上游提供 SHA-1 时与上游版本校验值一致；归档后另记 SHA-256。官网 HTML 可能是可变的最新版本，因此版本校验不匹配时转用对应历史 HTML 快照。

CSV 目录包含早期报告，官方公开集合与第三方集合范围不同；旧报告的 Congress.gov 链接可能不存在。`official_page_verified_by_api` 只表示该编号已从官方 API 返回，**不是每个网页逐一 HTTP 探测成功的证明**。

## 仓库结构

```text
.github/workflows/crs-backup.yml  每日自动备份、手动补抓和完整性校验
.github/workflows/source-check.yml  手动连通性诊断
scripts/sync_crs.py             抓取、分页、下载、版本管理、索引和重试
 tests/test_sync.py             离线回归测试（目录名无前导空格）
pdf/{类型}/                    原始 PDF：完整原文、图表和版式以此为准
html/{类型}/                   可获得的 HTML 原文快照
markdown/{类型}/               从 HTML/PDF 转换的全文，附来源元数据
metadata/sources/{编号}.json    每份报告的来源版本元数据
data/all-report-links.csv      全部已发现报告的链接目录，UTF-8 BOM
data/all-report-links.txt      去重后的链接列表
data/archived-reports.csv      实际已备份的报告版本，不含仅有链接的报告
data/archive-manifest.json     文件路径、来源、SHA-256、页数和转换方式
data/catalog.json              累积发现目录，不因本次来源缩减删除旧条目
data/pending.json              下次继续重试的报告和文件
data/status.json               最新运行状态、计数、覆盖范围、告警和错误
data/runs/                     历次运行凭证
data/sources/                  最新 CSV 与 RSS 原始响应
LATEST.md                      本次时间窗口内已备份报告的阅读入口
```

类型包括 `in-focus`、`insights`、`reports`、`sidebars`、`infographics` 和 `testimony`。PDF 文件名为：

```text
报告编号v版本号-发布日期-SHA256前16位.pdf
```

Markdown 是机器转换的全文，**不是 AI 摘要或重新撰写**。HTML 不可获得时从 PDF 文本层抽取；无法抽取文本时明确标注，不擅自 OCR。表格、公式及版面可能与 PDF 不同；HTML/Markdown 引用的外链图片没有全部离线保存，完整图表请阅读原始 PDF。

## 手动运行与补抓

打开 **Actions → CRS daily backup → Run workflow**，分支选择 `main`。

| 参数 | 默认值 | 说明 |
|---|---|---|
| `days` | `7` | 向前回看天数；可改为 `30`、`90` 等，范围 1—3650 |
| `until` | 空 | 默认 UTC 今天；历史补抓可填 `2026-09-24` 等日期 |
| `full_catalog` | `false` | `true` 时分页刷新整个官方 API 目录，需个人 `CONGRESS_API_KEY` |

`full_catalog` 只扩大**官方链接目录**的刷新范围，不自动下载所有历史 PDF。扩大 `days` 才会扩大原文下载窗口；大规模回填建议按日期分批，以免超过单次工作流 90 分钟限制。

### 可选：配置免费的官方 API Key

当前零配置模式不要求先提交 key。公开 `DEMO_KEY` 配额有限，代码限制每次最多 20 个 API 请求，并记录限流后的降级状态。需要更稳定的官方 API 校验或全量官方目录时：

1. 在 <https://api.congress.gov/sign-up/> 申请个人免费 API key。
2. 仓库 **Settings → Secrets and variables → Actions → New repository secret**。
3. 名称填写 **`CONGRESS_API_KEY`**，值填写自己的 key，然后保存。

不要把 key 写进代码、README、Issue 或聊天记录。工作流只从 GitHub Secret 注入，且只向官方 API 主机发送 key。向仓库提交归档使用 GitHub 自动提供的 `GITHUB_TOKEN`，不需要另建个人 GitHub token。

## 如何确认备份是否完整

`data/status.json` 分开记录：发现的报告数、尝试版本数、成功版本数、新增 PDF 数、累积版本数、待重试报告/文件数以及每个来源是否可用。成功下载的 PDF 和索引在校验通过后提交；某些报告失败时仍保留已成功的文件和重试队列，并让本次 Actions **明确失败**，避免错误地报告全部成功。

仅 HTML 获取失败、PDF 已完整保存时，保留 PDF 和抽取文本，记录告警并安排 HTML 重试。主来源暂不可用但备用来源成功时同样记录降级告警。未来上游收录延迟或网站结构变化仍可能需要维护。

## 本地运行

```bash
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/sync_crs.py --days 7
# 已通过环境变量安全设置 CONGRESS_API_KEY 时：
python scripts/sync_crs.py --days 7 --full-catalog
```

## 保存边界与维护

原文直接提交到 Git，不依赖会到期的 Actions artifact。随着长期归档，仓库体积会增长；脚本对单个下载设置 80 MiB 上限，超大文件显式进入失败记录，不会悄悄省略。未来数据量显著增长时可按年份拆分归档，但当前不会自动删除历史。

第三方 action 固定 commit SHA，Python 依赖固定版本；更新依赖后先运行测试。GitHub 对长时间无活动的公开仓库可能停用定时任务；请留意 Actions 页面。自动提交只涉及归档目录，工作流的 push 过滤器也不会因报告提交而循环触发。

## 来源、权利与参考

本仓库是独立备份项目，不代表 CRS、美国国会或 EveryCRSReport。CRS 报告中的第三方图片或其他材料可能保留第三方权利；原始报告及来源声明应一并保留。仓库已有 `LICENSE` 未作修改，**不要据此认为第三方报告和图片自动改用本项目软件许可证**。

- Congress.gov API 文档：<https://github.com/LibraryOfCongress/api.congress.gov>
- CRS API 端点说明：<https://github.com/LibraryOfCongress/api.congress.gov/blob/main/Documentation/CRSReportEndpoint.md>
- EveryCRSReport 数据与使用说明：<https://www.everycrsreport.com/download.html>
- 全部目录：<https://www.everycrsreport.com/reports.csv>
- RSS：<https://www.everycrsreport.com/rss.xml>
- GitHub 定时事件说明：<https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule>
- 目录排布与版本保留参考：<https://github.com/ProfAmiot/crs-reports>。本仓库不是该仓库的副本，报告由上述公开数据源采集。
