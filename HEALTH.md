# CRS refresh health

**UNHEALTHY**

Watchdog checked UTC: 2026-10-28T23:16:28.116137+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-10-28T16:46:51.619075+00:00 |
| official-reconcile.yml | 2026-10-28T16:52:21.659058+00:00 |
| coverage-audit.yml | 2026-10-27T01:40:31.544739+00:00 |

## Findings

coverage-audit.yml: no verified refresh within 26 hours
coverage-audit.yml: latest run failure
No valid independent byte-verification receipt

## Recovery

Dispatched coverage-audit.yml; completion is NOT yet verified

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
