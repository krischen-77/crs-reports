# CRS refresh health

**UNHEALTHY**

Watchdog checked UTC: 2026-11-04T21:56:06.647423+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-11-04T18:05:57.261257+00:00 |
| official-reconcile.yml | 2026-11-04T18:12:26.959057+00:00 |
| coverage-audit.yml | 2026-11-04T15:40:41.694404+00:00 |

## Findings

coverage-audit.yml: latest run failure

## Recovery

Retry cooldown/cap active; failure remains visible

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
