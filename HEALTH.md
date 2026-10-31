# CRS refresh health

**UNHEALTHY**

Watchdog checked UTC: 2026-10-31T00:53:39.033573+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-10-30T16:44:55.199585+00:00 |
| official-reconcile.yml | 2026-10-30T16:50:23.035433+00:00 |
| coverage-audit.yml | 2026-10-30T02:09:44.268202+00:00 |

## Findings

No valid independent byte-verification receipt
Official refresh finished, but independent verification did not follow

## Recovery

Retry cooldown/cap active; failure remains visible

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
