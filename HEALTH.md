# CRS refresh health

**HEALTHY**

Watchdog checked UTC: 2026-10-31T07:11:29.453240+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-10-31T07:04:12.484111+00:00 |
| official-reconcile.yml | 2026-10-31T07:08:24.403747+00:00 |
| coverage-audit.yml | 2026-10-31T07:11:16.940742+00:00 |

## Findings

No unresolved freshness or completeness failures detected.

## Recovery

No recovery dispatch required.

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
