# CRS refresh health

**UNHEALTHY**

Watchdog checked UTC: 2026-10-24T07:00:13.950118+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-10-23T22:48:52.115083+00:00 |
| official-reconcile.yml | 2026-10-24T05:53:26.058769+00:00 |
| coverage-audit.yml | 2026-10-23T13:45:29.729954+00:00 |

## Findings

official-reconcile.yml: latest run failure
coverage-audit.yml: latest run failure
Official-current coverage is incomplete

## Recovery

Retry cooldown/cap active; failure remains visible

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
