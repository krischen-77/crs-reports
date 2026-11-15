# CRS refresh health

**UNHEALTHY**

Watchdog checked UTC: 2026-11-15T17:23:36.326058+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-11-15T17:17:22.149999+00:00 |
| official-reconcile.yml | 2026-11-15T17:22:33.350907+00:00 |
| coverage-audit.yml | 2026-11-15T02:09:01.038462+00:00 |

## Findings

coverage-audit.yml: latest run failure

## Recovery

No recovery dispatch required.

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
