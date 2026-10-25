# CRS refresh health

**HEALTHY**

Watchdog checked UTC: 2026-10-25T01:14:41.309837+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-10-24T22:45:25.882235+00:00 |
| official-reconcile.yml | 2026-10-24T22:51:02.180650+00:00 |
| coverage-audit.yml | 2026-10-24T22:53:47.928644+00:00 |

## Findings

No unresolved freshness or completeness failures detected.

## Recovery

No recovery dispatch required.

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
