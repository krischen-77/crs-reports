# CRS refresh health

**UNHEALTHY**

Watchdog checked UTC: 2026-10-28T05:50:51.485235+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-10-28T03:51:44.244020+00:00 |
| official-reconcile.yml | 2026-10-27T01:37:31.331205+00:00 |
| coverage-audit.yml | 2026-10-27T01:40:31.544739+00:00 |

## Findings

official-reconcile.yml: no verified refresh within 26 hours
coverage-audit.yml: no verified refresh within 26 hours
Official-current coverage is incomplete
No valid independent byte-verification receipt

## Recovery

Retry cooldown/cap active; failure remains visible

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
