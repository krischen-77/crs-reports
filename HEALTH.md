# CRS refresh health

**UNHEALTHY**

Watchdog checked UTC: 2026-10-23T22:56:07.858713+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-10-23T22:48:52.115083+00:00 |
| official-reconcile.yml | 2026-10-23T22:55:47.855059+00:00 |
| coverage-audit.yml | 2026-10-23T13:45:29.729954+00:00 |

## Findings

official-reconcile.yml: latest run failure
Official-current coverage is incomplete

## Recovery

No recovery dispatch required.

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
