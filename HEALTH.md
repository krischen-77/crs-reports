# CRS refresh health

**UNHEALTHY**

Watchdog checked UTC: 2026-11-08T22:56:49.997694+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-11-08T16:44:44.161091+00:00 |
| official-reconcile.yml | 2026-11-08T16:48:55.401562+00:00 |
| coverage-audit.yml | 2026-11-08T13:42:13.635046+00:00 |

## Findings

coverage-audit.yml: latest run failure
Official refresh finished, but independent verification did not follow

## Recovery

Retry cooldown/cap active; failure remains visible

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
