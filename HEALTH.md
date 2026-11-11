# CRS refresh health

**UNHEALTHY**

Watchdog checked UTC: 2026-11-11T18:05:51.017026+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-11-11T17:57:20.453936+00:00 |
| official-reconcile.yml | 2026-11-10T18:17:55.635324+00:00 |
| coverage-audit.yml | 2026-11-10T04:23:07.013856+00:00 |

## Findings

Official-current coverage is incomplete
No valid independent byte-verification receipt

## Recovery

No recovery dispatch required.

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
