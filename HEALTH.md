# CRS refresh health

**HEALTHY**

Watchdog checked UTC: 2026-11-02T18:28:37.871177+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-11-02T01:35:04.734471+00:00 |
| official-reconcile.yml | 2026-11-02T01:39:49.565707+00:00 |
| coverage-audit.yml | 2026-11-02T01:42:24.552405+00:00 |

## Findings

No unresolved freshness or completeness failures detected.

## Recovery

Dispatched crs-backup.yml; completion is NOT yet verified

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
