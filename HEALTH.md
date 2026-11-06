# CRS refresh health

**UNHEALTHY**

Watchdog checked UTC: 2026-11-06T21:33:42.066015+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-11-06T17:34:17.264370+00:00 |
| official-reconcile.yml | 2026-11-06T17:41:06.650861+00:00 |
| coverage-audit.yml | 2026-11-06T02:45:17.685859+00:00 |

## Findings

coverage-audit.yml: latest run failure

## Recovery

Retry cooldown/cap active; failure remains visible

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
