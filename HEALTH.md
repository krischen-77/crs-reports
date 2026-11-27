# CRS refresh health

**UNHEALTHY**

Watchdog checked UTC: 2026-11-27T02:54:44.576536+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-11-16T02:15:21.477049+00:00 |
| official-reconcile.yml | 2026-11-26T19:50:58.480046+00:00 |
| coverage-audit.yml | 2026-11-26T09:50:18.367803+00:00 |

## Findings

crs-backup.yml: no verified refresh within 26 hours
coverage-audit.yml: latest run failure
Collector has unresolved required failures

## Recovery

Dispatched crs-backup.yml; completion is NOT yet verified

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
