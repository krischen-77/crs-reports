"""Reviewed exact-match source migration. Abort on unexpected code; never edit data."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]


def patch(path, old, new):
    target = ROOT / path
    text = target.read_text('utf-8')
    if new in text:
        return
    if text.count(old) != 1:
        raise RuntimeError('Unexpected source, refusing replacement: ' + path + ' :: ' + old[:100])
    target.write_text(text.replace(old, new, 1), 'utf-8')


patch('scripts/sync_crs.py', 'ROOT = Path(__file__).resolve().parents[1]',
      'ROOT = Path(__file__).resolve().parents[1]\nsys.path.insert(0, str(ROOT / "scripts"))\nfrom current_scope import superseded_history\nfrom refresh_receipts import record_collection')
old = '''        print(f"[{n}/{len(tasks)}] {task['id']} v{task['version']} ({task['date']})", flush=True)
        try:'''
new = '''        evidence = superseded_history(root, task, list(tasks.values()), archives, archive_start)
        if evidence:
            historical_task = {**task, "required_by_recent_update": False,
                               "superseded_by_official_current": evidence}
            key = retry_identity(historical_task)
            if not any(retry_identity(x["task"]) == key for x in historical):
                historical.append({"task": historical_task, "attempts": 0,
                                   "next_retry": str(now.date() + timedelta(days=1)),
                                   "reason": evidence["reason"]})
            status.setdefault("superseded_historical_versions", []).append(evidence)
            continue
        print(f"[{n}/{len(tasks)}] {task['id']} v{task['version']} ({task['date']})", flush=True)
        try:'''
patch('scripts/sync_crs.py', old, new)
patch('scripts/sync_crs.py', 'attempted_versions=len(tasks), successful_versions=ok_count,',
      'planned_versions=len(tasks), attempted_versions=len(tasks) - len(status.get("superseded_historical_versions", [])), successful_versions=ok_count,')
patch('scripts/sync_crs.py', '    write_json(root / "data/status.json", status)',
      '    record_collection(root, status)\n    write_json(root / "data/status.json", status)')
patch('scripts/sync_crs.py', 'attempted versions: **{len(tasks)}**;',
      "attempted versions: **{status['attempted_versions']}**;")
patch('.github/ops/reliability.py', 'from freshness import parse_time, recovery_days, last_verification',
      'from freshness import parse_time, recovery_days, last_verification\nfrom alert_policy import prepare_notification\nsys.path.insert(0, str(ROOT / "scripts"))\nfrom refresh_receipts import last_collection')
patch('.github/ops/reliability.py', "times = [backup.get('run_at') if not backup.get('errors') and not backup.get('required_pdf_failures') else backup.get('last_successful_run_at'),",
      "times = [(backup.get('finished_at') or backup.get('run_at')) if not backup.get('errors') and not backup.get('required_pdf_failures') else backup.get('last_successful_run_at'),")
patch('.github/ops/reliability.py', "        report.update(evaluate(now, load(root / 'data/status.json', {}),",
      "        latest_backup = load(root / 'data/status.json', {})\n        previous_collection = last_collection(root)\n        latest_backup['last_successful_run_at'] = previous_collection.get('finished_at') or previous_collection.get('run_at')\n        report.update(evaluate(now, latest_backup,")
patch('.github/ops/reliability.py', '''        if notify:
            issue_update(api, report, state)''', '''        notification = prepare_notification(root, report, state, now, latest_audit)
        if notify and notification is not None:
            issue_update(api, notification, state)
            if notification.get('zero_delivery_day'):
                state['zero_delivery_notified_day'] = notification['zero_delivery_day']
            if notification.get('alert_issue'):
                report['alert_issue'] = notification['alert_issue']''')
print('Reviewed source migration applied; regression suites must pass before commit.')
