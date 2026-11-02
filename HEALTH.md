# CRS refresh health

**REFRESHING**

Watchdog checked UTC: 2026-11-02T18:37:32.155746+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-11-02T18:30:26.951350+00:00 |
| official-reconcile.yml | 2026-11-02T18:36:09.009812+00:00 |
| coverage-audit.yml | 2026-11-02T01:42:24.552405+00:00 |

## Findings

No unresolved freshness or completeness failures detected.

## Recovery

No recovery dispatch required.

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
