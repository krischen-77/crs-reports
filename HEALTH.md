# CRS refresh health

**UNHEALTHY**

Watchdog checked UTC: 2026-11-17T03:57:16.346264+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-11-16T02:15:21.477049+00:00 |
| official-reconcile.yml | 2026-11-16T20:43:37.291960+00:00 |
| coverage-audit.yml | 2026-11-16T02:25:03.894772+00:00 |

## Findings

coverage-audit.yml: latest run failure
Collector has unresolved required failures

## Recovery

Dispatched crs-backup.yml; completion is NOT yet verified

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
