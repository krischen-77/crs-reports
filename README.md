# CRS Reports Archive | 美国国会研究局报告备份

**目标：每天自动保存最近一周新增或更新的 CRS 报告原文，并刷新全部已发现报告的链接目录。** 已归档版本永久保留，不会因超出一周窗口而删除。

**阅读入口：** [官方当前原文](CURRENT.md) · [最近一周报告](LATEST.md) · [全部链接 CSV](data/all-report-links.csv) · [纯文本链接](data/all-report-links.txt) · [健康状态](HEALTH.md) · [每日交付与降噪规则](docs/delivery-alert-policy.md)

[![Daily collection](https://github.com/krischen-77/crs-reports/actions/workflows/crs-backup.yml/badge.svg)](https://github.com/krischen-77/crs-reports/actions/workflows/crs-backup.yml)
[![Official reconciliation](https://github.com/krischen-77/crs-reports/actions/workflows/official-reconcile.yml/badge.svg)](https://github.com/krischen-77/crs-reports/actions/workflows/official-reconcile.yml)
[![Independent verification](https://github.com/krischen-77/crs-reports/actions/workflows/coverage-audit.yml/badge.svg)](https://github.com/krischen-77/crs-reports/actions/workflows/coverage-audit.yml)

## 每天怎样运行

每天北京时间 **06:23、18:23** 各有一次刷新机会。GitHub 可能排队，时间不是精确执行承诺。

**抓取和归档 → 官方当前版本对账 → 独立重新下载核验 → 健康检查。** 阶段之间使用明确的 `workflow_dispatch` 接续，不依赖多层 `workflow_run` 链。只要当前阶段正常执行、文件通过完整性检查且真实结果成功持久化，就继续下游；单份可恢复的来源失败不再阻断官方对账或独立核验。缺失和重试任务仍保留在状态文件中，不能把部分完成冒充覆盖完整。代码崩溃、损坏文件、旧运行凭据和持久化失败仍使任务失败。

默认回看 7 天并包含边界日，同时处理本周仍有更新的 Active 报告，即使它的封面日期很早。中断恢复时从最后成功核验日向前追赶。镜像用于历史版本和补充发现，不能把镜像旧版冒充官方当前版。只有更新的官方原文已经保存并核实，且旧镜像早于所有曾请求的存档窗口，才可将旧镜像任务转为保留的历史补抓；真正的当前旧封面版本和曾在请求范围内的漏抓不能降级。

修改普通文档不会启动整套抓取。代码变更由回归测试检查；需要立即验证源站时，在 Actions → **CRS daily backup** → **Run workflow** 执行，正常持久化后自动接续后续阶段。

## 原文与完整性

优先保存官方 PDF，按 `(报告编号, PDF SHA-256)` 去重，不覆盖不同内容的旧版。每个 PDF 有 Markdown 全文转换，图表和版式以原件为准。

官方详情接口有时漏列 PDF。仅当详情 `currentVersion` 和官方 HTML 路径明确时，程序才构造一个待核验的官方 PDF 地址；下载后必须同时匹配文内报告编号、修订号和标题，才可接受。**列表 `version` 不用于猜测最新版。** 如果官方只提供可验证的 HTML 原文，则保存其原始字节、SHA-256 及 Markdown，计入独立 HTML 原文清单，不伪造 PDF、也不混入 PDF 数量。访问拒绝页面、错误编号、错误版本均不接受。

独立核验重新读取实时更新信号并下载原文，比较实际仓库字节。仅时间戳变化时重新解析元数据；若确有新内容未保存、文件损坏或无法核实，必须如实保留失败。UTC 午夜翻页本身不使新鲜证据失效。

## 看什么才知道真的刷新成功

| 文件 | 含义 |
|---|---|
| `data/status.json` | 抓取来源、候选和实际归档结果；`run_at` 为开始时间，`finished_at` 为实际结束时间 |
| `data/last-successful-collection.json` | 上一次真正成功的源站采集；失败尝试不覆盖成功时间 |
| `data/official-status.json` | 官方当前版本对账；待核验数量必须为 0 才算覆盖完整 |
| `data/last-successful-official.json` | 上一次真正完成的官方对账，不被失败尝试覆盖 |
| `data/verification-status.json` | 最近一次独立核验，包括 `missing`、`unverified`、`invalid_files` |
| `data/last-successful-verification.json` | 最近一次真正成功的独立核验；失败时不推进成功时间 |
| `data/health.json` / `HEALTH.md` | 内容健康状态、三个阶段的实际成功时间，以及告警等级 |
| `data/runs/` / `data/official-runs/` | 按运行保留的采集与官方对账结果，供每日新增交付统计 |

**Git 提交时间、看门狗 `checked_at` 和 Actions 绿色都不能独自证明报告已完整刷新。** 没有新报告可以是正常情况，成功核验持续过期则不是。Actions 绿色表示阶段正常执行并持久化可信结果；部分覆盖仍在 JSON 中明确为失败或待核验。

## 少打扰，但不隐藏故障

每小时看门狗检查故障、26 小时过期及流程接续，按冷却时间和次数上限尝试恢复。`monitor_result=completed` 表示监控自身执行并报告成功；仓库是否健康看 `result=healthy/unhealthy/refreshing`，是否需要用户介入则看 `notification_severity` 与 `notification_required`。

可恢复的单份来源失败、辅助 HTML 和旧镜像问题保留 warning 与重试记录，不反复制造失败邮件。超过 26 小时没有成功源站刷新或独立核验、必需内容问题持续未恢复、损坏文件或禁用／卡住的工作流才集中升级到同一个去重 Issue。代码、执行、完整性或持久化错误仍会使 Actions 失败；无法执行监控或保存证据时也不会伪报健康。

按北京时间完整自然日统计新增原文，次日 **08:00 以后**检查：一整天没有任何新增报告时发一次交付提醒。可选历史补抓不充当当日新增；提示必须区分“源站无新报告”和“源站有更新但未保存”，前者不自动等同刷新失败。平台外独立监控继续作为 GitHub 定时调度停跑的兜底。

## 索引与保存范围

- `pdf/{类型}/`、`data/archive-manifest.json`：PDF 原文及哈希清单。
- `html/originals/`、`data/html-original-manifest.json`：官方 HTML 原文，单独计数。
- `html/{类型}/`：可获得的辅助阅读快照，可能经过镜像重新排版。
- `markdown/`：全文转换，不是 AI 摘要；复杂表格、图片、公式可能需要查阅原件。
- `data/all-report-links.csv`：所用公开来源发现的全部链接，不等于已下载所有历史原文。
- `data/official-pending.json`、`data/deferred-official-formats.json`：未完成的官方当前原文任务，不能默默删除。
- `data/historical-pending.json`：窗口外可选历史补抓，单独披露，不冒充近期任务失败或全部完成。

IF13330 的既有例外：官方 PDF 字节已核验，但详情 API 曾返回 404；它作为镜像补充发现保留，不能据此声称已由官方详情确认当前版本。未公开、尚未被任何来源索引的材料不在可证明完整的范围内。

## 数据源、免费 Key 和手动补抓

官方 API：<https://api.congress.gov/v3/crsreport>；公开镜像目录：<https://www.everycrsreport.com/reports.csv>；第三方 RSS：<https://www.everycrsreport.com/rss.xml>。RSS 只是补充，不代替完整目录。

默认使用 `DEMO_KEY` 并遵守实际剩余配额。可在 <https://api.congress.gov/sign-up/> 申请个人免费 key，在仓库 Actions Secret 中保存为 `CONGRESS_API_KEY`；不要写入代码、Issue 或聊天。提交使用 GitHub 自动注入的 token，无需个人 GitHub token。

手动补抓：Actions → CRS daily backup → Run workflow。`days` 调整回看天数，`until` 可指定 UTC 结束日；`full_catalog=true` 刷新完整官方链接目录，需要个人 key，不等于下载所有历史 PDF。

## 维护记录

[2026-10-28：历史版本范围、真实成功时间与分级交付告警](docs/delivery-alert-policy.md) · [2026-10-24：格式漏列、空错误、重复失败告警和流程接续修复](docs/repair-2026-10-24.md) · [2026-10-23：漏抓及旧版本修复](docs/repair-2026-10-23.md) · [每日可靠性规则](docs/daily-reliability.md)

本项目不代表 CRS、美国国会或 EveryCRSReport；报告中的第三方内容可能有独立版权。已有 LICENSE 不自动改变来源报告的权利状态。旧失败记录保留用于审计，不承诺外部网站或平台永远不故障。
