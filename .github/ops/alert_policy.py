"""One operational alert, not an email per recoverable source error."""
from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

BEIJING = timezone(timedelta(hours=8))


def read(path, default):
    return json.loads(path.read_text('utf-8')) if path.exists() else default


def parse(value):
    return datetime.fromisoformat(str(value).replace('Z', '+00:00')).astimezone(timezone.utc)


def previous_day_delivery(root, now):
    """Count persisted new originals, not Git commits or optional old backfill."""
    local = now.astimezone(BEIJING)
    if local.hour < 8:
        return None
    target = local.date() - timedelta(days=1)
    rows = [read(p, {}) for p in (root / 'data/runs').glob('*/*.json')]
    official = [read(p, {}) for p in (root / 'data/official-runs').glob('*.json')]
    official.append(read(root / 'data/official-status.json', {}))
    total, attempts, seen = 0, 0, set()
    for stage, records in [('backup', rows), ('official', official)]:
        for r in records:
            value = r.get('finished_at') or r.get('checked_at') or r.get('run_at')
            if not value:
                continue
            stamp = parse(value)
            if stamp.astimezone(BEIJING).date() != target:
                continue
            key = (stage, r.get('github_run_id'), r.get('github_run_attempt'), value)
            if key in seen:
                continue
            seen.add(key)
            attempts += 1
            if stage == 'backup':
                count = r.get('primary_new_pdf_versions', max(0, r.get('new_pdf_versions', 0) - r.get('historical_new_pdf_versions', 0)))
            else:
                count = r.get('new_pdf_versions', 0) + r.get('new_html_original_versions', 0)
            total += max(0, int(count))
    return {'date_beijing': str(target), 'new_original_versions': total, 'persisted_attempts': attempts,
            'interpretation': 'No new originals is a delivery notice, not by itself proof of refresh failure.'}


def prepare_notification(root, report, state, now, audit):
    """Raw health/errors stay intact; only notification severity is reduced."""
    errors = list(report.get('errors', []))
    critical = [e for e in errors if any(text in e for text in (
        'no verified refresh within 26 hours', 'workflow is not active',
        'queued/running for over two hours', 'invalid receipt timestamp', 'no workflow run found'))]
    if audit.get('invalid_files'):
        critical.append('Archived file integrity verification failed; inspect invalid_files')
    if report.get('monitor_result') == 'failed':
        critical.append('Independent monitor could not verify repository health')
    if errors:
        first = state.setdefault('first_degraded_at', now.isoformat())
        if (now - parse(first)).total_seconds() > 26 * 3600:
            critical.append('Required source/coverage failures remain unresolved for over 26 hours')
    else:
        state.pop('first_degraded_at', None)
    delivery = previous_day_delivery(root, now)
    report['daily_delivery'] = delivery
    report['notification_severity'] = 'critical' if critical else ('warning' if errors else 'none')
    report['notification_required'] = bool(critical)
    report['notification_policy'] = 'Recoverable partial results remain visible and retryable, but do not fail Actions. Alert on integrity loss, disabled/stalled workflows, no successful refresh/verification for 26h, persistent required failures, or once per completed Beijing day with zero new originals.'
    if critical:
        return {**report, 'result': 'unhealthy', 'errors': sorted(set(critical))}
    if delivery and delivery['new_original_versions'] == 0:
        report['notification_severity'] = 'notice' if not errors else 'warning'
        day = delivery['date_beijing']
        if state.get('zero_delivery_notified_day') != day:
            report['notification_required'] = True
            return {**report, 'result': 'unhealthy', 'zero_delivery_day': day,
                    'errors': [day + '（北京时间）未记录任何新增报告原文。此项为每日交付提醒，不自动等同刷新失败；请结合源站刷新及独立核验记录判断。']}
        return None
    if report.get('result') == 'healthy':
        return report
    return None
