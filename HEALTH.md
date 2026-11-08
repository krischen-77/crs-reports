# CRS refresh health

**UNHEALTHY**

Watchdog checked UTC: 2026-11-08T06:11:19.961478+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-11-08T01:44:05.997871+00:00 |
| official-reconcile.yml | 2026-11-07T16:38:03.042827+00:00 |
| coverage-audit.yml | 2026-11-07T02:11:10.037642+00:00 |

## Findings

coverage-audit.yml: no verified refresh within 26 hours
official-reconcile.yml: latest run failure
coverage-audit.yml: latest run failure

## Recovery

Retry cooldown/cap active; failure remains visible

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
