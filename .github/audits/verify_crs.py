#!/usr/bin/env python3
"""Read-only, live-source CRS coverage audit. Never equate a green sync with coverage."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import sync_crs as s


def in_window(value, start, end):
    try:
        return start <= date.fromisoformat(str(value)[:10]) <= end
    except (TypeError, ValueError):
        return False


def official_list(http, start, end, out):
    """Independent pagination; retain complete responses, not only filtered IDs."""
    result, seen, offset = [], set(), 0
    while True:
        query = dict(format='json', limit=250, offset=offset,
                     fromDateTime=f'{start}T00:00:00Z', toDateTime=f'{end}T23:59:59Z')
        obj = http.json(s.API + '?' + urlencode(query))
        s.write_json(out / f'official-page-{offset}.json', obj)
        batch = next((v for k, v in obj.items() if k.lower() == 'crsreports'), None)
        if not isinstance(batch, list):
            raise ValueError('Official list schema is not a list')
        for row in batch:
            ident = s.report_id(row['id'])
            if ident in seen:
                raise ValueError(f'Pagination repeated {ident}; completeness unverified')
            seen.add(ident)
        result.extend(batch)
        offset += len(batch)
        count = int(obj.get('pagination', {}).get('count', len(result)))
        if not obj.get('pagination', {}).get('next'):
            if offset != count:
                raise ValueError(f'Incomplete pagination: received {offset}, reported {count}')
            return result
        if not batch or offset > 200000:
            raise ValueError('Pagination failed to make bounded progress')


def safe_local(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Manifest path escapes repository')
    return path


def verify_manifest(root, manifest):
    """Rehash the real files, and reject missing Markdown / invalid PDF containers."""
    valid, invalid = {}, []
    for item in manifest:
        try:
            body = safe_local(root, item['pdf']).read_bytes()
            if not body.lstrip().startswith(b'%PDF-'):
                raise ValueError('Missing PDF header')
            sha1 = hashlib.sha1(body).hexdigest()
            sha256 = hashlib.sha256(body).hexdigest()
            if sha1 != item['pdf_sha1'] or sha256 != item['pdf_sha256']:
                raise ValueError('Actual file checksum does not match manifest')
            with s.fitz.open(stream=body, filetype='pdf') as doc:
                if not len(doc) or doc.needs_pass:
                    raise ValueError('Unreadable PDF')
            if not safe_local(root, item['markdown']).is_file():
                raise ValueError('Markdown is missing')
            if item.get('html'):
                html = safe_local(root, item['html']).read_bytes()
                if hashlib.sha256(html).hexdigest() != item['html_sha256']:
                    raise ValueError('HTML checksum mismatch')
            valid.setdefault(item['id'], []).append(item)
        except Exception as exc:
            invalid.append({'id': item.get('id'), 'pdf': item.get('pdf'), 'error': str(exc)})
    return valid, invalid


def hash_matches(local, expected):
    return bool(expected) and any(v['pdf_sha1'] == expected for v in local)


def result_state(receipt):
    if receipt['missing'] or receipt['invalid_files']:
        return 'failed'
    if receipt['unverified'] or not all(v.get('ok') for v in receipt['sources'].values()):
        return 'unverified'
    return 'verified_for_observed_sources'


def run(args):
    root, out = Path(args.root).resolve(), Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    end = date.fromisoformat(args.until) if args.until else now.date()
    start = end - timedelta(days=args.days)
    receipt = dict(checked_at=now.isoformat(), start=str(start), end=str(end),
                   repository_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
                   github_run_id=os.getenv('GITHUB_RUN_ID', ''), github_run_attempt=os.getenv('GITHUB_RUN_ATTEMPT', ''),
                   sources={}, missing=[], invalid_files=[], unverified=[])
    http = s.HTTP(os.getenv('CONGRESS_API_KEY', '').strip())
    rows, mirror = [], {}
    try:
        rows = official_list(http, start, end, out)
        receipt['sources']['official_api'] = dict(ok=True, records=len(rows))
    except Exception as exc:
        receipt['sources']['official_api'] = dict(ok=False, error=str(exc))
    s.write_json(out / 'official-list.json', rows)
    try:
        body, _ = http.get(s.MIRROR + 'reports.csv')
        s.write(out / 'mirror.csv', body)
        mirror = s.parse_catalog(body)
        if len(mirror) < 1000:
            raise ValueError('Unexpectedly small mirror catalog')
        receipt['sources']['mirror_catalog'] = dict(ok=True, records=len(mirror))
    except Exception as exc:
        receipt['sources']['mirror_catalog'] = dict(ok=False, error=str(exc))
    manifest = json.loads((root / 'data/archive-manifest.json').read_text())
    valid, receipt['invalid_files'] = verify_manifest(root, manifest)
    api = {r['id']: r for r in rows if in_window(r.get('publishDate'), start, end)}
    recent_mirror = {i: r for i, r in mirror.items() if in_window(r.get('published'), start, end)}
    ids = sorted(set(api) | set(recent_mirror))
    checks, download_cache = [], {}

    def check_official_pdf(ident, url, local):
        """Public official URLs only. A 403/429 is recorded, never bypassed."""
        try:
            url = s.safe_url(url)
            if url not in download_cache:
                body, actual = http.get(url)
                if not body.lstrip().startswith(b'%PDF-'):
                    raise ValueError('Official response is not a PDF')
                with s.fitz.open(stream=body, filetype='pdf') as doc:
                    if not len(doc) or doc.needs_pass:
                        raise ValueError('Official PDF unreadable')
                    text = doc[0].get_text() + doc[-1].get_text()
                sha = hashlib.sha256(body).hexdigest()
                download_cache[url] = dict(url=actual, sha256=sha, bytes=len(body),
                    report_id_in_text=bool(re.search(r'(?<![A-Z0-9])' + re.escape(ident) + r'(?![A-Z0-9])', text)))
                s.write(out / 'official-pdf-text' / f'{ident}.txt', text)
            info = dict(download_cache[url])
            info['archived_exact_bytes'] = any(v['pdf_sha256'] == info['sha256'] for v in local)
            if not info['archived_exact_bytes']:
                receipt['missing'].append(dict(id=ident, reason='Official PDF bytes absent from archive', **info))
            if not info['report_id_in_text']:
                receipt['unverified'].append(dict(id=ident, reason='Report ID not found in official PDF text', url=url))
            return info
        except Exception as exc:
            receipt['unverified'].append(dict(id=ident, reason='Official PDF could not be checked', url=url, error=str(exc)))
            return dict(url=url, error=str(exc))

    for n, ident in enumerate(ids, 1):
        print(f'Coverage [{n}/{len(ids)}] {ident}', flush=True)
        local = valid.get(ident, [])
        row = dict(id=ident, title=api.get(ident, {}).get('title') or recent_mirror.get(ident, {}).get('title', ident),
                   official_publish_date=api.get(ident, {}).get('publishDate', '')[:10],
                   mirror_publish_date=recent_mirror.get(ident, {}).get('published', ''),
                   local=[{k: v[k] for k in ('date', 'version', 'pdf', 'markdown', 'pdf_sha1', 'pdf_sha256')} for v in local],
                   mirror_versions=[], official_pdf_checks=[])
        published = row['official_publish_date']
        if published and not any(v['date'] >= published for v in local):
            receipt['missing'].append(dict(id=ident, reason='Official publication date not covered', date=published))
        try:
            metadata = http.json(s.MIRROR + 'reports/' + ident + '.json')
            if s.report_id(metadata.get('id') or metadata.get('number')) != ident:
                raise ValueError('Mirror metadata ID mismatch')
            s.write_json(out / 'metadata' / f'{ident}.json', metadata)
            for version in metadata.get('versions', []):
                if not in_window(version.get('date'), start, end):
                    continue
                spec = next((f for f in version.get('formats', []) if str(f.get('format', '')).upper() == 'PDF'), None)
                if spec is None:
                    receipt['unverified'].append(dict(id=ident, reason='Mirror version has no PDF specification'))
                    continue
                matched = hash_matches(local, spec.get('sha1'))
                row['mirror_versions'].append(dict(date=version['date'], source_record=version.get('id'),
                    sha1=spec.get('sha1'), pdf_url=spec.get('url'), archived_exact_hash=matched))
                if not matched:
                    receipt['missing'].append(dict(id=ident, reason='Mirror version checksum not archived', date=version['date'], sha1=spec.get('sha1')))
                if args.direct_pdfs and spec.get('url'):
                    row['official_pdf_checks'].append(check_official_pdf(ident, spec['url'], local))
        except Exception as exc:
            receipt['unverified'].append(dict(id=ident, reason='Live version metadata unavailable', error=str(exc)))
        checks.append(row)

    # Resolve newest official publications directly; list version numbers and
    # actual PDF filename revisions are not assumed to be interchangeable.
    detail_rows = sorted(api.values(), key=lambda r: (r['publishDate'], r['id']), reverse=True)[:args.detail_limit]
    for row in detail_rows:
        ident = row['id']
        try:
            obj = http.json(s.API + '/' + ident + '?format=json')
            s.write_json(out / 'official-detail' / f'{ident}.json', obj)
            item = next(v for k, v in obj.items() if k.lower() == 'crsreport')
            pdf = next(f for f in item['formats'] if f['format'].upper() == 'PDF')
            result = check_official_pdf(ident, pdf.get('url') or pdf['URL'], valid.get(ident, []))
            result['publish_date'] = item.get('publishDate')
            next(c for c in checks if c['id'] == ident)['official_latest_detail'] = result
        except Exception as exc:
            receipt['unverified'].append(dict(id=ident, reason='Official latest-detail check unavailable', error=str(exc)))
    recent_archives = [v for v in manifest if in_window(v['date'], start, end)]
    receipt.update(official_recent_ids=len(api), mirror_recent_ids=len(recent_mirror), union_ids=len(ids),
                   total_archived_pdf_versions=len(manifest), recent_archived_pdf_versions=len(recent_archives),
                   mirror_expected_pdf_versions=sum(len(c['mirror_versions']) for c in checks),
                   mirror_exact_hash_matches=sum(v['archived_exact_hash'] for c in checks for v in c['mirror_versions']),
                   official_pdf_urls_checked=len(download_cache), official_latest_details_requested=len(detail_rows),
                   official_latest_details_verified=sum(bool(c.get('official_latest_detail', {}).get('archived_exact_bytes')) for c in checks),
                   newest_observed_publication=max([c['official_publish_date'] for c in checks] + [c['mirror_publish_date'] for c in checks], default=''),
                   newest_archived_publication=max((v['date'] for v in manifest), default=''),
                   api_requests=http.api_calls, finished_at=datetime.now(timezone.utc).isoformat())
    receipt['result'] = result_state(receipt)
    receipt['scope_note'] = ('Coverage of live API publication dates and mirror versions observed during this run, not a claim about '
                            'unpublished reports, official front-end changes not yet exposed by these sources, or every historical intermediate version.')
    s.write_json(out / 'comparisons.json', checks)
    s.write_json(out / 'receipt.json', receipt)
    with (out / 'coverage.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['report_id','title','official_publish_date','mirror_publish_date','mirror_versions','exact_hash_matches','official_PDF_checks','official_PDF_exact_matches','local_PDF_paths'])
        for c in checks:
            writer.writerow([c['id'],c['title'],c['official_publish_date'],c['mirror_publish_date'],len(c['mirror_versions']),
                sum(v['archived_exact_hash'] for v in c['mirror_versions']),len(c['official_pdf_checks']),
                sum(bool(v.get('archived_exact_bytes')) for v in c['official_pdf_checks']),';'.join(v['pdf'] for v in c['local'])])
    summary = '# CRS independent coverage audit\n\n```json\n' + json.dumps(receipt,ensure_ascii=False,indent=2) + '\n```\n'
    s.write(out / 'SUMMARY.md', summary)
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as f: f.write(summary)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt['result'] == 'verified_for_observed_sources' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default=str(ROOT))
    parser.add_argument('--out', default='coverage-evidence')
    parser.add_argument('--until', default='')
    parser.add_argument('--days', type=int, default=7)
    parser.add_argument('--detail-limit', type=int, default=6)
    parser.add_argument('--direct-pdfs', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.days <= 3650 or not 0 <= args.detail_limit <= 12:
        parser.error('days must be 1..3650 and detail-limit 0..12')
    sys.exit(run(args))
