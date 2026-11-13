# CRS refresh health

**UNHEALTHY**

Watchdog checked UTC: 2026-11-13T17:57:25.975475+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-11-13T17:51:33.315407+00:00 |
| official-reconcile.yml | 2026-11-13T17:56:27.443768+00:00 |
| coverage-audit.yml | 2026-11-10T04:23:07.013856+00:00 |

## Findings

coverage-audit.yml: no verified refresh within 26 hours
coverage-audit.yml: latest run failure
No valid independent byte-verification receipt

## Recovery

No recovery dispatch required.

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
