# CRS refresh health

**UNHEALTHY**

Watchdog checked UTC: 2026-11-14T16:46:49.591082+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-11-14T16:39:00.692492+00:00 |
| official-reconcile.yml | 2026-11-14T16:45:53.468514+00:00 |
| coverage-audit.yml | 2026-11-14T02:41:02.895007+00:00 |

## Findings

coverage-audit.yml: latest run failure

## Recovery

No recovery dispatch required.

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
