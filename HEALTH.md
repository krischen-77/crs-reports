# CRS refresh health

**UNHEALTHY**

Watchdog checked UTC: 2026-11-03T23:27:57.897801+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-11-03T03:30:43.891440+00:00 |
| official-reconcile.yml | 2026-11-03T03:35:55.856913+00:00 |
| coverage-audit.yml | 2026-11-03T03:38:37.100049+00:00 |

## Findings

coverage-audit.yml: latest run failure
Collector has unresolved required failures
Official-current coverage is incomplete

## Recovery

Retry cooldown/cap active; failure remains visible

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
