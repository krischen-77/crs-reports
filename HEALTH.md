# CRS refresh health

**UNHEALTHY**

Watchdog checked UTC: 2026-11-24T20:54:26.862846+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-11-16T02:15:21.477049+00:00 |
| official-reconcile.yml | 2026-11-24T20:52:32.204791+00:00 |
| coverage-audit.yml | 2026-11-24T06:37:36.640809+00:00 |

## Findings

crs-backup.yml: no verified refresh within 26 hours
coverage-audit.yml: latest run failure
Collector has unresolved required failures

## Recovery

Dispatched crs-backup.yml; completion is NOT yet verified

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
