# CRS refresh health

**UNHEALTHY**

Watchdog checked UTC: 2026-10-31T07:02:29.898964+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-10-30T16:44:55.199585+00:00 |
| official-reconcile.yml | 2026-10-31T01:45:05.903390+00:00 |
| coverage-audit.yml | 2026-10-31T01:48:03.837239+00:00 |

## Findings

Collector has unresolved required failures

## Recovery

Dispatched crs-backup.yml; completion is NOT yet verified

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
