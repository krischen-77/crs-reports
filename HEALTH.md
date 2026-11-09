# CRS refresh health

**UNHEALTHY**

Watchdog checked UTC: 2026-11-09T20:59:50.016783+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-11-09T20:52:17.451240+00:00 |
| official-reconcile.yml | 2026-11-09T20:58:37.125381+00:00 |
| coverage-audit.yml | 2026-11-09T01:55:14.642394+00:00 |

## Findings

coverage-audit.yml: latest run failure

## Recovery

No recovery dispatch required.

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
