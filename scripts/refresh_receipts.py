"""Keep success watermarks separate from attempts; timestamps come only from receipts."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path


def load(path, default=None):
    return json.loads(path.read_text('utf-8')) if path.exists() else default


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    tmp.replace(path)


def collection_ok(r):
    return (r.get('result') in ('success', 'success_with_warnings')
            and r.get('primary_pdf_complete') is True
            and not r.get('errors') and not r.get('required_pdf_failures')
            and any(r.get('sources', {}).get(k, {}).get('ok') is True
                    for k in ('congress_api', 'everycrsreport')))


def last_collection(root):
    candidates = [load(root / 'data/last-successful-collection.json', {})]
    candidates += [load(p, {}) for p in sorted((root / 'data/runs').glob('*/*.json'))]
    valid = [r for r in candidates if collection_ok(r) and (r.get('finished_at') or r.get('run_at'))]
    return max(valid, key=lambda r: r.get('finished_at') or r['run_at'], default={})


def record_collection(root, status):
    previous = last_collection(root)
    status['finished_at'] = datetime.now(timezone.utc).isoformat()
    if collection_ok(status):
        status['last_successful_run_at'] = status['finished_at']
        save(root / 'data/last-successful-collection.json', status)
    else:
        status['last_successful_run_at'] = previous.get('finished_at') or previous.get('run_at')
    return status
