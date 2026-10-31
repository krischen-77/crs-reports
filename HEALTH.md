# CRS refresh health

**UNHEALTHY**

Watchdog checked UTC: 2026-10-31T00:51:18.427065+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-10-30T16:44:55.199585+00:00 |
| official-reconcile.yml | 2026-10-30T16:50:23.035433+00:00 |
| coverage-audit.yml | 2026-10-30T02:09:44.268202+00:00 |

## Findings

coverage-audit.yml: latest run failure

## Recovery

Dispatched coverage-audit.yml; completion is NOT yet verified

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
