# CRS refresh health

**HEALTHY**

Watchdog checked UTC: 2026-11-02T00:54:19.187008+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-11-01T16:51:17.297369+00:00 |
| official-reconcile.yml | 2026-11-01T16:56:01.941617+00:00 |
| coverage-audit.yml | 2026-11-02T00:54:05.073824+00:00 |

## Findings

No unresolved freshness or completeness failures detected.

## Recovery

No recovery dispatch required.

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
