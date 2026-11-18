# CRS refresh health

**UNHEALTHY**

Watchdog checked UTC: 2026-11-18T22:14:43.758544+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-11-16T02:15:21.477049+00:00 |
| official-reconcile.yml | 2026-11-18T22:13:42.379201+00:00 |
| coverage-audit.yml | 2026-11-18T14:24:04.058939+00:00 |

## Findings

crs-backup.yml: no verified refresh within 26 hours
coverage-audit.yml: latest run failure
Collector has unresolved required failures

## Recovery

Retry cooldown/cap active; failure remains visible

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
