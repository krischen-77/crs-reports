#!/usr/bin/env python3
"""Independent refresh watchdog. A monitor commit is NEVER a source refresh."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.github/ops'))
from freshness import parse_time, recovery_days, last_verification

STAGES = ('crs-backup.yml', 'official-reconcile.yml', 'coverage-audit.yml')
MARKER = '<!-- crs-refresh-health:v1 -->'
TITLE = '[CRS refresh] Automatic freshness / completeness alert'


def load(path: Path, default):
    return json.loads(path.read_text('utf-8')) if path.exists() else default


def save(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    tmp.replace(path)


def age_hours(value, now):
    if not value:
        return float('inf')
    hours = (now - parse_time(str(value))).total_seconds() / 3600
    if hours < -0.1:
        raise ValueError('Evidence timestamp is in the future')
    return max(0.0, hours)


def valid_audit(receipt):
    return (receipt.get('result') == 'verified_for_observed_sources'
            and not any(receipt.get(k) for k in ('missing', 'unverified', 'invalid_files'))
            and receipt.get('sources', {}).get('official_api', {}).get('ok') is True
            and receipt.get('sources', {}).get('mirror_catalog', {}).get('ok') is True
            and isinstance(receipt.get('candidate_report_ids'), int)
            and receipt.get('verified_current_original_files', receipt.get('verified_current_pdf_files')) == receipt['candidate_report_ids'])


def evaluate(now, backup, official, audit, runs, workflows):
    """Pure decision logic, covered by offline failure-injection tests."""
    errors, notices, recovery = [], [], None
    # A new failed attempt must NEVER refresh the last-success timestamp.
    official_ok = (official.get('result') == 'verified_for_observed_official_entries'
                   and official.get('official_current_pending') == 0)
    times = [backup.get('run_at') if not backup.get('errors') and not backup.get('required_pdf_failures') else backup.get('last_successful_run_at'),
             official.get('checked_at') if official_ok else official.get('last_successful_checked_at'),
             audit.get('finished_at') if valid_audit(audit) else audit.get('last_successful_finished_at')]
    ages = []
    for stage, value in zip(STAGES, times):
        try:
            age = age_hours(value, now)
        except (ValueError, TypeError):
            age = float('inf')
            errors.append(stage + ': invalid receipt timestamp')
        ages.append(age)
        if age > 26:
            errors.append(stage + ': no verified refresh within 26 hours')
    running = []
    failures = []
    for stage in STAGES:
        info = workflows.get(stage, {})
        if info.get('state') != 'active':
            errors.append(stage + ': workflow is not active')
        run = runs.get(stage, {})
        if not run:
            errors.append(stage + ': no workflow run found')
            failures.append(stage)
            continue
        if run.get('status') != 'completed':
            running.append(stage)
            if age_hours(run.get('run_started_at') or run.get('created_at'), now) > 2:
                errors.append(stage + ': queued/running for over two hours')
        elif run.get('conclusion') != 'success':
            errors.append(stage + ': latest run ' + str(run.get('conclusion')))
            failures.append(stage)
    if backup.get('errors') or backup.get('required_pdf_failures'):
        errors.append('Collector has unresolved required failures')
        if STAGES[0] not in failures:
            failures.append(STAGES[0])
    if (official.get('result') != 'verified_for_observed_official_entries'
            or official.get('official_current_pending') != 0
            or official.get('official_current_verified') != official.get('official_current_required')):
        errors.append('Official-current coverage is incomplete')
        if STAGES[1] not in failures:
            failures.append(STAGES[1])
    if not valid_audit(audit):
        errors.append('No valid independent byte-verification receipt')
        if STAGES[2] not in failures:
            failures.append(STAGES[2])
    # Failed latest runs remain visible even when old successful receipts exist.
    if not running:
        for stage in STAGES:
            if stage not in failures:
                continue
            run = runs.get(stage, {})
            completed_age = age_hours(run.get('updated_at'), now)
            if completed_age >= 1/6 and workflows.get(stage, {}).get('state') == 'active':
                recovery = stage
                break
        if recovery is None and ages[0] > 14:
            recovery = STAGES[0]
        if recovery is None and times[0] and times[1] and parse_time(times[0]) > parse_time(times[1]):
            if ages[0] > 2:
                recovery = STAGES[1]
                errors.append('Collector finished, but official reconciliation did not follow')
            else:
                notices.append('Official reconciliation is due after the new collection')
        if recovery is None and times[1] and (not times[2] or parse_time(times[1]) > parse_time(times[2])):
            if ages[1] > 2:
                recovery = STAGES[2]
                errors.append('Official refresh finished, but independent verification did not follow')
            else:
                notices.append('Independent verification is due after the new reconciliation')
    if recovery and workflows.get(recovery, {}).get('state') != 'active':
        recovery = None  # Never override an owner's manual workflow disable.
    if running:
        notices.append('Pipeline is running; do not launch duplicate work')
        # Startup/recovery grace suppresses ONLY age warnings, never actual content failures.
        recent_running = any(age_hours(runs[k].get('run_started_at') or runs[k].get('created_at'), now) <= 2 for k in running)
        if recent_running:
            stale = [e for e in errors if 'no verified refresh within 26 hours' in e]
            errors = [e for e in errors if e not in stale]
            if stale:
                notices.append('Two-hour recovery grace for old success timestamps; completion is not yet verified')
    return dict(result='unhealthy' if errors else ('refreshing' if running or notices else 'healthy'),
                errors=errors, notices=notices, recovery_stage=recovery,
                source_times=dict(zip(STAGES, times)), active_stages=running)


def retry_allowed(state, stage, now):
    history = [x for x in state.get('dispatches', []) if age_hours(x['at'], now) < 24]
    return (len(history) < 4 and not any(x['stage'] == stage and age_hours(x['at'], now) < 6
                                      for x in history))


class GitHubAPI:
    def __init__(self):
        self.repo = os.environ['GITHUB_REPOSITORY']
        self.token = os.environ['GH_TOKEN']
        self.base = 'https://api.github.com/repos/' + self.repo

    def call(self, path, method='GET', body=None):
        if not path.startswith('/') or '://' in path:
            raise ValueError('Invalid API path')
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers={
            'Authorization': 'Bearer ' + self.token, 'Accept': 'application/vnd.github+json',
            'Content-Type': 'application/json', 'X-GitHub-Api-Version': '2026-03-10',
            'User-Agent': 'crs-reports-freshness-watchdog'})
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            # Never dump request headers, tokens, or response payloads into the repo.
            raise RuntimeError(f'GitHub {method} {path.split("?")[0]} returned HTTP {exc.code}') from None

    def runs(self, stage):
        rows = self.call('/actions/workflows/' + stage + '/runs?branch=main&per_page=10')['workflow_runs']
        return sorted(rows, key=lambda r: r.get('run_started_at') or r['created_at'], reverse=True)


def issue_update(api, report, state):
    issue = None
    if state.get('issue_number'):
        candidate = api.call('/issues/' + str(state['issue_number']))
        if MARKER in (candidate.get('body') or ''):
            issue = candidate
    if issue is None:
        for page in range(1, 11):
            rows = api.call(f'/issues?state=all&per_page=100&page={page}')
            issue = next((i for i in rows if MARKER in (i.get('body') or '')), None)
            if issue or len(rows) < 100:
                break
        else:
            raise RuntimeError('Issue scan exceeded safety bound; refusing duplicate alert')
    if report['result'] == 'unhealthy':
        fingerprint = hashlib.sha256(json.dumps(report['errors'], sort_keys=True).encode()).hexdigest()
        text = (MARKER + '\n@' + api.repo.split('/')[0]
                + '\n\nCRS refresh is not verified healthy.\n\n'
                + '\n'.join('- ' + e for e in report['errors'])
                + '\n\nChecked UTC: ' + report['checked_at']
                + '\n\nInspect [HEALTH.md](https://github.com/' + api.repo + '/blob/main/HEALTH.md), `data/health.json`, '
                  '`data/official-status.json`, and the three production workflows. '
                  'A new watchdog commit is not a successful source refresh.\n')
        if issue is None:
            issue = api.call('/issues', 'POST', dict(title=TITLE, body=text))
        elif issue.get('state') != 'open' or fingerprint != state.get('issue_fingerprint'):
            api.call('/issues/' + str(issue['number']), 'PATCH', dict(state='open', body=text))
        state.update(issue_number=issue['number'], issue_fingerprint=fingerprint)
    elif report['result'] == 'healthy' and issue and issue.get('state') == 'open':
        api.call('/issues/' + str(issue['number']) + '/comments', 'POST',
                 dict(body='Recovered: source refresh, official-current coverage, and independent verification are healthy at '
                           + report['checked_at'] + '. See `data/health.json`.'))
        api.call('/issues/' + str(issue['number']), 'PATCH', dict(state='closed'))
    if issue:
        report['alert_issue'] = issue['html_url']


def watchdog(root, repair, notify):
    now = datetime.now(timezone.utc)
    state = load(root / 'data/health-retry-state.json', {})
    api = GitHubAPI()
    report = dict(result='unhealthy', errors=[], checked_at=now.isoformat(), monitor_result='completed')
    try:
        all_runs = {stage: api.runs(stage) for stage in STAGES}
        runs = {stage: rows[0] if rows else {} for stage, rows in all_runs.items()}
        workflows = {stage: api.call('/actions/workflows/' + stage) for stage in STAGES}
        latest_audit = load(root / 'data/verification-status.json', {})
        latest_audit['last_successful_finished_at'] = last_verification(root).get('finished_at')
        latest_official = load(root / 'data/official-status.json', {})
        latest_official['last_successful_checked_at'] = load(root / 'data/last-successful-official.json', {}).get('checked_at') or latest_official.get('last_successful_checked_at')
        report.update(evaluate(now, load(root / 'data/status.json', {}),
                     latest_official, latest_audit, runs, workflows))
        report['latest_runs'] = {k: {f: v.get(f) for f in ('id', 'status', 'conclusion', 'html_url', 'run_started_at', 'updated_at')}
                                 for k, v in runs.items()}
        stage = report['recovery_stage']
        if repair and stage:
            recent_dispatch = any(r.get('event') == 'workflow_dispatch'
                                  and age_hours(r.get('run_started_at') or r.get('created_at'), now) < 6
                                  for r in all_runs[stage])
            if retry_allowed(state, stage, now) and not recent_dispatch:
                body = {'ref': 'main'}
                if stage == STAGES[0]:
                    body['inputs'] = {'days': str(recovery_days(root, now.date()))}
                api.call('/actions/workflows/' + stage + '/dispatches', 'POST', body)
                state['dispatches'] = [x for x in state.get('dispatches', []) if age_hours(x['at'], now) < 24]
                state['dispatches'].append(dict(stage=stage, at=now.isoformat()))
                report['recovery_action'] = 'Dispatched ' + stage + '; completion is NOT yet verified'
            else:
                report['recovery_action'] = 'Retry cooldown/cap active; failure remains visible'
        if notify:
            issue_update(api, report, state)
    except Exception as exc:
        report['result'] = 'unhealthy'
        report['errors'].append(type(exc).__name__ + ': ' + (str(exc) or repr(exc)))
        report['monitor_result'] = 'failed'
    report.update(github_run_id=os.getenv('GITHUB_RUN_ID', ''),
                  stale_after_hours=26, recovery_due_hours=14,
                  retry_cooldown_hours=6, retry_cap_per_24h=4,
                  interpretation='checked_at is monitor time, NOT the last successful CRS source refresh.')
    save(root / 'data/health.json', report)
    save(root / 'data/health-retry-state.json', state)
    lines = ['# CRS refresh health', '', '**' + report['result'].upper() + '**', '',
             'Watchdog checked UTC: ' + report['checked_at'], '',
             'Monitor commits are NOT source refreshes. No new reports can be normal; stale verification is not.', '',
             '| Production stage | Last source/verification receipt (UTC) |', '|---|---|']
    for stage, value in report.get('source_times', {}).items():
        lines.append(f'| {stage} | {value or "MISSING"} |')
    lines += ['', '## Findings', ''] + (report['errors'] or ['No unresolved freshness or completeness failures detected.'])
    lines += ['', '## Recovery', '', report.get('recovery_action', 'No recovery dispatch required.'), '',
              'Hourly checks; overdue after 26 hours; retry at most once per stage per six hours and four times total per 24 hours.',
              'A GitHub-wide outage can also stop this watchdog. External monitoring is a separate safety net.', '']
    (root / 'HEALTH.md').write_text('\n'.join(lines), 'utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as f:
            f.write('\n'.join(lines))
    # Health is carried in JSON + one deduplicated Issue. A correctly executed
    # monitor is not another failed production job for the same incident.
    # Transport, parsing, notification or persistence failures still fail this job.
    return 1 if report['monitor_result'] == 'failed' else 0


def publish_receipt(root):
    receipt = load(root / 'coverage-evidence/current-receipt.json', {})
    if receipt.get('github_run_id') != os.environ['GITHUB_RUN_ID']:
        raise ValueError('Refusing stale independent verification receipt')
    if str(receipt.get('github_run_attempt')) != os.environ['GITHUB_RUN_ATTEMPT']:
        raise ValueError('Refusing stale independent verification attempt')
    if not valid_audit(receipt):
        receipt['last_successful_finished_at'] = last_verification(root).get('finished_at')
    save(root / 'data/verification-status.json', receipt)
    save(root / f"data/audits/verification-{receipt['github_run_id']}-{receipt['github_run_attempt']}.json", receipt)
    if not valid_audit(receipt):
        print('Failed verification retained; successful watermark unchanged')
        return 1
    save(root / 'data/last-successful-verification.json', receipt)
    print('Persisted successful independent verification, not a synthetic heartbeat')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['watchdog', 'publish'])
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--repair', action='store_true')
    parser.add_argument('--notify', action='store_true')
    args = parser.parse_args()
    sys.exit(watchdog(args.root, args.repair, args.notify) if args.command == 'watchdog' else publish_receipt(args.root))
