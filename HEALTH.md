# CRS refresh health

**UNHEALTHY**

Watchdog checked UTC: 2026-11-06T00:25:11.820746+00:00

Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.

| Production stage | Last source/verification receipt (UTC) |
|---|---|
| crs-backup.yml | 2026-11-05T18:06:57.584382+00:00 |
| official-reconcile.yml | 2026-11-05T18:13:33.454299+00:00 |
| coverage-audit.yml | 2026-11-05T02:44:59.062496+00:00 |

## Findings

No valid independent byte-verification receipt
Official refresh finished, but independent verification did not follow

## Recovery

Retry cooldown/cap active; failure remains visible

Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.
A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.
