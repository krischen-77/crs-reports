# CRS refresh health

**HEALTHY**

Watchdog checked UTC: 2026-10-25T22:37:02.747662+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-10-25T14:26:45.575945+00:00 |
| official-reconcile.yml | 2026-10-25T14:31:37.368449+00:00 |
| coverage-audit.yml | 2026-10-25T14:34:04.521053+00:00 |

## Findings

No unresolved freshness or completeness failures detected.

## Recovery

No recovery dispatch required.

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
