# CRS refresh health

**UNHEALTHY**

Watchdog checked UTC: 2026-10-29T17:06:01.722273+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-10-29T17:00:18.512496+00:00 |
| official-reconcile.yml | 2026-10-29T17:04:35.162914+00:00 |
| coverage-audit.yml | 2026-10-29T02:01:14.426907+00:00 |

## Findings

coverage-audit.yml: latest run failure

## Recovery

No recovery dispatch required.

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
