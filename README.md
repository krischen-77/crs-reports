# CRS Reports Archive | 美国国会研究局报告备份

[![Daily collection](https://github.com/krischen-77/crs-reports/actions/workflows/crs-backup.yml/badge.svg)](https://github.com/krischen-77/crs-reports/actions/workflows/crs-backup.yml)
[![Official current reconciliation](https://github.com/krischen-77/crs-reports/actions/workflows/official-reconcile.yml/badge.svg)](https://github.com/krischen-77/crs-reports/actions/workflows/official-reconcile.yml)
[![Independent verification](https://github.com/krischen-77/crs-reports/actions/workflows/coverage-audit.yml/badge.svg)](https://github.com/krischen-77/crs-reports/actions/workflows/coverage-audit.yml)

每天保存 CRS 原始 PDF、Markdown 全文、可取得的 HTML 阅读快照及报告链接目录。**抓取程序运行成功，不等于当前官方版本已经收齐。** 本仓库将收集、官方当前版本对账、独立文件核验分开执行和展示。

## 先从这里阅读

**[CURRENT.md：按官方当前下载地址核验的最新文件](CURRENT.md)**

[最近一周发布／修订及旧日期更新](LATEST.md) · [全部已发现报告链接 CSV](data/all-report-links.csv) · [纯文本链接](data/all-report-links.txt) · [实际已归档版本](data/archived-reports.csv)

**[官方当前版本验收状态](data/official-status.json)** · [逐份对账 CSV](data/audits/latest-official-current.csv) · [逐份对账 JSON](data/audits/latest-official-current-comparisons.json) · [基础抓取状态](data/status.json)

`CURRENT.md` 分开显示 API 更新日期、报告封面日期、官方 PDF 修订号及文件入口。较早的封面日期不代表这份报告本周没有更新；镜像文件名的修订号也不一定是官方当前修订号。

## 自动化链路

| 阶段 | 执行内容 | 验收依据 |
|---|---|---|
| CRS daily backup | 每日 10:23 UTC／北京时间 18:23；回看 7 天并纳入边界日，刷新镜像完整目录、官方更新列表、RSS，保存近期原文和重试任务 | `data/status.json` |
| CRS official-current reconciliation | 每次每日抓取结束后，解析近期发布及本周有更新的 Active 报告的官方详情接口 `formats`；按官方当前 PDF 地址保存文件，不用镜像修订号代替 | `data/official-status.json`、`CURRENT.md` |
| CRS independent coverage audit | 在官方对账后重新检查官方更新信号，取回当前 PDF，并比较仓库实际字节；另覆盖近期镜像发现但尚不在 API 列表中的报告 | Actions 独立核验结果及逐份证据 artifact |

GitHub 定时任务可能排队；这不是精确到秒的执行承诺。完整性判断必须结合三个阶段及它们的**实际检查时间**，不能只看第一个绿色徽章。

## 2026-10-23 漏抓修复

深入核对证实此前存在两类问题：

1. 旧代码把部分 Active 报告的本周更新，因 `publishDate` 较早误归为仅元数据更新，导致原文漏存。
2. 镜像的 PDF 修订号可能落后于官方详情接口，即使镜像中有同编号、同发布日期的 PDF，也不能据此证明官方当前文件已备份。

现已把近期 Active 更新纳入必需范围，修正旧日期重试分流；另增加官方当前版本对账层，以实际文件 SHA-256 验证，不只比较编号、日期或任务成功次数。同内容不重复计数，不同内容分别保留，原始发布日期不为满足窗口而改写。

[第一阶段修复与发现过程](docs/repair-2026-10-23.md) · [实时官方对账结果](data/official-status.json) · [最初 3 份明确漏项的前后证据](data/audits/2026-10-23-active-update-repair.json)

第一阶段记录的补入数量只是当时阶段性结果；后续官方详情对账发现的缺失修订版，以 `data/official-status.json` 和完整 manifest 为准。

## 可靠性与范围

**原文以 PDF 为准。** 保存时验证 PDF 文件头、可解析性；提交前复核实际 SHA-1、SHA-256、Markdown 文件存在性，以及已有 HTML 的 SHA-256。镜像提供的 PDF 校验值不匹配时不放宽要求，只能独立解析和保存可验证的官方文件。

**官方目录版本、官方当前 PDF 修订号、镜像修订号分别记录。** 官方 API 的列表 `version`、详情 `currentVersion`、文件名修订号不混用。当前文件以官方详情 `formats` 返回的 PDF URL 为依据，已有同字节文件保留真实封面日期和历史路径。

**HTML／Markdown 是阅读辅助。** 镜像 HTML 可能重新排版或来自 PDF 转换，必须记录衍生性质。Markdown 是全文转换，不是 AI 摘要或改写；复杂表格、公式、图片、布局以 PDF 为最终依据。无可用文本层时明确标记，不默认 OCR。

**API 失败不能被缓存掩盖。** 使用当天的官方详情证据并匹配最新更新信号；配额、网络或格式错误留下未解决任务。旧详情缓存不代替未完成的当日核查。部分成功的原文可以先保存，但对账不完整仍报错。

**历史待办不冒充完成。** `data/historical-pending.json` 保存较早窗口外的历史任务，逐条保留请求规格、错误、尝试次数和重试日；主窗口失败保存在 `data/pending.json`，官方当前版本未解决项另存 `data/official-pending.json`。超过一周不会删除已归档原文。

**全部链接不等于全部 PDF。** 链接目录覆盖所用公开来源已经发现的编号；不保证覆盖未公开或尚未进入 API／镜像的官网变化，也不保证恢复所有历史中间版本。对账成功的含义是：在明确时间和来源范围内，应核验的当前文件已经实际保存。

## 数据源与密钥

| 来源 | 用途 |
|---|---|
| Congress.gov `/v3/crsreport` | 官方更新列表、状态、发布日期及详情接口 |
| Congress.gov `/v3/crsreport/{id}` | 官方当前文件地址、`currentVersion`、作者等元数据 |
| EveryCRSReport `reports.csv` 与报告 JSON | 完整镜像链接目录、近期发现及版本历史，补充 API 尚未反映的日期变化 |
| EveryCRSReport `rss.xml` | 补充发现，不代替完整目录；这是第三方 RSS，不冒称 CRS 官方 RSS |

默认使用公开 `DEMO_KEY`，但其实际配额较低，不能当作生产稳定性保证。程序读取并遵守服务返回的剩余配额，按有限批次处理，遇到拒绝或限流不绕过。**建议配置个人免费 API Key**：

申请：<https://api.congress.gov/sign-up/>

仓库 **Settings → Secrets and variables → Actions → New repository secret**：名称 `CONGRESS_API_KEY`，值为个人 key。不要把 key 放入代码、README、Issue 或聊天。归档提交使用 GitHub 自动提供的 `GITHUB_TOKEN`，不需要个人 GitHub token。

## 文件结构

```text
CURRENT.md                         官方当前文件入口，包含日期、修订号与原文链接
LATEST.md                          按发布日期显示近期报告，并另列旧日期 Active 更新
pdf/{类型}/                        原始 PDF，不覆盖旧内容版本
markdown/{类型}/                   全文转换与来源说明
html/{类型}/                       可取得的 HTML 阅读快照
metadata/sources/                  来源版本元数据
data/archive-manifest.json         所有已归档文件的路径、哈希、页数、来源
data/all-report-links.csv          全部已发现报告的链接目录
data/archived-reports.csv          实际已归档版本清单
data/official-current.json         官方当前格式、更新信号、文件哈希与验证时间
data/official-status.json          官方当前版本对账结果
data/official-pending.json         官方对账尚未解决的报告
data/status.json                   基础抓取结果及官方对账汇总
data/pending.json                  主范围失败／辅助 HTML 重试
data/historical-pending.json       范围外历史待办
data/audits/                       可追溯对账证据
data/runs/                         每次基础抓取运行记录
scripts/sync_crs.py                 目录发现、下载、转换、版本与重试
tools/official_pipeline.py          官方当前格式解析与逐文件对账
.github/current-verification/       独立当前文件核验
```

类型包含 `in-focus`、`insights`、`reports`、`sidebars`、`infographics`、`testimony`。文件名包含报告编号、PDF 修订号、发布日期、SHA-256 前缀。统计以 manifest 中的编号与完整哈希去重，不按可能存在的历史路径别名重复计数。

## 手动补抓与维护

**Actions → CRS daily backup → Run workflow**：`days` 默认 `7`，可改为 `30`、`90`；`until` 为可选的 UTC 结束日期；`full_catalog=true` 刷新官方完整链接目录，需要个人 key，不等于下载全部历史 PDF。官方当前对账固定检查当前近一周更新；历史回填不会把今日当前文件冒充历史版本。

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m unittest discover -s tools/tests -v
python -m unittest discover -s .github/audits -p 'test_*.py' -v
python scripts/sync_crs.py --days 7
```

第三方 Actions 固定 commit SHA；依赖升级先测试。文件直接提交到 Git，不依赖临时 artifact 长期保存。较大规模历史回填应分批；单个下载上限 80 MiB，超限明确报错。长期归档会增大仓库，未来可按年份拆分或迁移存储，但当前不会自动删除旧文件。

## 历史记录与使用边界

[2026-10-04 限流与历史任务分流修复](docs/repair-2026-10-04.md) · [2026-10-23 漏抓核查过程](docs/repair-2026-10-23.md)

本项目不代表 CRS、美国国会或 EveryCRSReport。报告中的第三方图片等可能保留第三方权利；仓库已有 `LICENSE` 未修改，不能据此认为来源报告与图片自动采用软件许可证。

官方说明：<https://github.com/LibraryOfCongress/api.congress.gov/blob/main/Documentation/CRSReportEndpoint.md>

镜像数据说明：<https://www.everycrsreport.com/download.html>

API 配额说明：<https://api.data.gov/docs/developer-manual/>

最初目录布局参考：<https://github.com/ProfAmiot/crs-reports>。本项目不是其副本，文件由所列公开来源采集。
