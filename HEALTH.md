# CRS refresh health

**UNHEALTHY**

Watchdog checked UTC: 2026-11-03T01:38:13.837988+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-11-02T20:25:12.349729+00:00 |
| official-reconcile.yml | 2026-11-02T20:28:29.003374+00:00 |
| coverage-audit.yml | 2026-11-02T01:42:24.552405+00:00 |

## Findings

coverage-audit.yml: latest run failure

## Recovery

Retry cooldown/cap active; failure remains visible

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
