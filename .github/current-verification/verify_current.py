#!/usr/bin/env python3
"""Independent live-original verifier. Reports without PDF metadata are supported."""
from datetime import datetime, timedelta, timezone
import csv
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'.github/audits'))
sys.path.insert(0, str(ROOT/'tools'))
import verify_crs as a
import official_pipeline as p
import crs_formats as formats
s = a.s
sys.path.insert(0, str(ROOT/'.github/ops'))
from freshness import recovery_days, parse_time


def live_task(http, row, record, now):
    """Re-resolve a changed signal instead of failing merely on timestamp drift.

    It is still necessary for the resulting CURRENT original bytes to be archived.
    Re-resolution does not turn a missing new revision into a successful check.
    """
    try:
        age = (now-parse_time(record.get('detail_checked_at', ''))).total_seconds()
    except (ValueError, TypeError):
        age = float('inf')
    if record.get('signal') == p.signal(row) and record.get('task') and 0 <= age <= 26*3600:
        return record['task'], False
    obj = http.json(s.API+'/'+s.report_id(row['id'])+'?format=json')
    item = formats.report_item(obj)
    p.validate_detail_signal(item, row)
    return formats.task_from_item(item), True


def main():
    now = datetime.now(timezone.utc)
    end = now.date()
    start = end-timedelta(days=recovery_days(ROOT, end))
    out = ROOT/'coverage-evidence'
    out.mkdir(exist_ok=True)
    http = s.HTTP(os.getenv('CONGRESS_API_KEY', '').strip())
    receipt = dict(checked_at=now.isoformat(), start=str(start), end=str(end),
                   github_run_id=os.getenv('GITHUB_RUN_ID', ''), github_run_attempt=os.getenv('GITHUB_RUN_ATTEMPT', ''),
                   sources={}, missing=[], unverified=[], invalid_files=[], notices=[])
    official, mirror = [], {}
    try:
        official = a.official_list(http, start, end, out)
        receipt['sources']['official_api'] = {'ok': True, 'records': len(official)}
    except Exception as exc:
        receipt['sources']['official_api'] = {'ok': False, 'error': formats.error_text(exc)}
    try:
        raw, _ = http.get(s.MIRROR+'reports.csv')
        mirror = s.parse_catalog(raw)
        s.write(out/'mirror.csv', raw)
        if len(mirror) < 1000:
            raise ValueError('Unexpectedly small mirror catalog')
        receipt['sources']['mirror_catalog'] = {'ok': True, 'records': len(mirror)}
    except Exception as exc:
        receipt['sources']['mirror_catalog'] = {'ok': False, 'error': formats.error_text(exc)}
    required = {r['id']: r for r in official if p.is_required(r, start, end)}
    ids = sorted(set(required) | {i for i, r in mirror.items() if s.within(r.get('published'), start, end)})
    manifest = s.read_json(ROOT/'data/archive-manifest.json', [])
    valid, receipt['invalid_files'] = a.verify_manifest(ROOT, manifest)
    html_entries = s.read_json(ROOT/'data/html-original-manifest.json', [])
    html_valid = {}
    for entry in html_entries:
        if formats.verify_html_entry(ROOT, entry):
            html_valid.setdefault(entry['id'], []).append(entry)
        else:
            receipt['invalid_files'].append({'id': entry.get('id'), 'error': 'HTML original byte/hash/path validation failed'})
    current = s.read_json(ROOT/'data/official-current.json', {})
    checks = []
    for n, ident in enumerate(ids, 1):
        row = required.get(ident, {})
        check = dict(id=ident, title=row.get('title') or mirror.get(ident, {}).get('title', ident),
                     scope='official current' if row else 'mirror-only recent discovery')
        print(f'Independent original verification {n}/{len(ids)}: {ident}', flush=True)
        try:
            if row:
                task, refreshed = live_task(http, row, current.get(ident, {}), now)
                if refreshed:
                    receipt['notices'].append({'id': ident, 'note': 'Live signal changed or cached detail expired; official formats re-resolved before byte comparison'})
            else:
                obj = http.json(s.MIRROR+'reports/'+ident+'.json')
                tasks = s.mirror_tasks(obj, start, end)
                if not tasks:
                    raise ValueError('Mirror-only discovery has no current original')
                task = max(tasks, key=lambda t: (t['date'], int(t['version']) if t['version'].isdigit() else -1))
            raw, actual, kind, notices = formats.fetch_original(http, task)
            sha = s.digest(raw)
            candidates = valid.get(ident, []) if kind == 'PDF' else html_valid.get(ident, [])
            hash_key, path_key = ('pdf_sha256', 'pdf') if kind == 'PDF' else ('sha256', 'original')
            matches = [v for v in candidates if v[hash_key] == sha]
            check.update(original_format=kind, original_url=actual, version=task['version'], sha256=sha,
                         verified=bool(matches), original_paths=[v[path_key] for v in matches],
                         markdown=[v['markdown'] for v in matches], notices=notices)
            if kind == 'PDF':
                check.update(official_pdf_url=actual, pdf=check['original_paths'])
            if not matches:
                receipt['missing'].append(check)
        except Exception as exc:
            check.update(verified=False, error=formats.error_text(exc))
            receipt['unverified'].append({'id': ident, 'error': formats.error_text(exc)})
        checks.append(check)
    receipt.update(official_current_ids=len(required), candidate_report_ids=len(ids),
                   verified_current_original_files=sum(bool(c.get('verified')) for c in checks),
                   verified_current_pdf_files=sum(bool(c.get('verified')) and c.get('original_format') == 'PDF' for c in checks),
                   verified_current_html_files=sum(bool(c.get('verified')) and c.get('original_format') == 'HTML' for c in checks),
                   total_archive_versions=len(manifest), total_html_original_versions=len(html_entries),
                   finished_at=datetime.now(timezone.utc).isoformat(),
                   scope='Live official current originals and recent mirror-only discoveries; PDF or advertised HTML bytes independently redownloaded and compared. Derived PDF paths require matching live currentVersion, embedded report ID/revision and title. Mirror-only metadata exceptions are not counted as official-current declarations.')
    receipt['result'] = a.result_state(receipt)
    s.write_json(out/'current-receipt.json', receipt)
    s.write_json(out/'current-comparisons.json', checks)
    with (out/'current-coverage.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, ['id', 'title', 'scope', 'version', 'original_format', 'original_url', 'sha256', 'verified', 'original_paths', 'markdown', 'error'], extrasaction='ignore')
        w.writeheader()
        w.writerows(checks)
    text = '# Independent current-original verification\n\n```json\n'+json.dumps(receipt, ensure_ascii=False, indent=2)+'\n```\n'
    s.write(out/'SUMMARY.md', text)
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as f:
            f.write(text)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt['result'] == 'verified_for_observed_sources' else 1


if __name__ == '__main__':
    sys.exit(main())
