# CRS refresh health

**UNHEALTHY**

Watchdog checked UTC: 2026-10-27T19:27:28.456398+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | MISSING |
| official-reconcile.yml | 2026-10-27T01:37:31.331205+00:00 |
| coverage-audit.yml | 2026-10-27T01:40:31.544739+00:00 |

## Findings

crs-backup.yml: no verified refresh within 26 hours
crs-backup.yml: latest run failure
Collector has unresolved required failures

## Recovery

Retry cooldown/cap active; failure remains visible

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
