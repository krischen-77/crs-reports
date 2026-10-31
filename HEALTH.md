# CRS refresh health

**HEALTHY**

Watchdog checked UTC: 2026-10-31T22:32:13.422381+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-10-31T15:48:13.121878+00:00 |
| official-reconcile.yml | 2026-10-31T15:53:40.020176+00:00 |
| coverage-audit.yml | 2026-10-31T15:56:39.032298+00:00 |

## Findings

No unresolved freshness or completeness failures detected.

## Recovery

No recovery dispatch required.

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
