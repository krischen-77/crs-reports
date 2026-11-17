# CRS refresh health

**UNHEALTHY**

Watchdog checked UTC: 2026-11-17T04:11:59.372542+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-11-16T02:15:21.477049+00:00 |
| official-reconcile.yml | 2026-11-17T04:07:42.643203+00:00 |
| coverage-audit.yml | 2026-11-17T04:11:46.210520+00:00 |

## Findings

Collector has unresolved required failures

## Recovery

Retry cooldown/cap active; failure remains visible

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
