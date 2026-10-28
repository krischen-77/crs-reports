# CRS refresh health

**UNHEALTHY**

Watchdog checked UTC: 2026-10-28T02:31:31.753737+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-10-28T02:24:33.861275+00:00 |
| official-reconcile.yml | 2026-10-27T01:37:31.331205+00:00 |
| coverage-audit.yml | 2026-10-27T01:40:31.544739+00:00 |

## Findings

Official-current coverage is incomplete
No valid independent byte-verification receipt

## Recovery

No recovery dispatch required.

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
