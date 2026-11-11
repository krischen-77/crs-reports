# CRS refresh health

**UNHEALTHY**

Watchdog checked UTC: 2026-11-11T01:17:20.343303+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-11-10T18:01:13.670833+00:00 |
| official-reconcile.yml | 2026-11-10T18:17:55.635324+00:00 |
| coverage-audit.yml | 2026-11-10T04:23:07.013856+00:00 |

## Findings

coverage-audit.yml: latest run failure

## Recovery

Dispatched coverage-audit.yml; completion is NOT yet verified

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
