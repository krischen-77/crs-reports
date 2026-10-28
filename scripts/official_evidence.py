"""Persist live metadata and supplementary API text without claiming original coverage.

An API summary is NOT a substitute for a PDF/HTML original. These helpers never
advance an original-verification success watermark or clear an original failure.
"""
from __future__ import annotations
import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

API = 'https://api.congress.gov/v3/crsreport/'
MANIFEST = 'data/official-api-summary-manifest.json'
CONTENT_FIELDS = ('id', 'title', 'currentVersion', 'publishDate', 'summary')


def stamp(value):
    result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Evidence must have an explicit timezone')
    return result.astimezone(timezone.utc)


def ident(value):
    value = str(value).upper()
    if not re.fullmatch(r'[A-Z][A-Z0-9-]{1,29}', value):
        raise ValueError('Invalid report identifier')
    return value


def signal(row):
    return {k: str(row.get(k, '')) for k in ('id', 'publishDate', 'updateDate')}


def choose_cached_record(row, records, now, max_age_hours=26):
    """Reuse only matching live-list signals, never a changed/expired task."""
    candidates = []
    for record in records:
        try:
            checked = stamp(record.get('detail_checked_at'))
            age = (now - checked).total_seconds()
            if (record.get('signal') == signal(row)
                    and record.get('task', {}).get('id') == row['id']
                    and 0 <= age <= max_age_hours * 3600):
                candidates.append((checked, record))
        except (TypeError, ValueError, KeyError, AttributeError):
            continue
    return copy.deepcopy(max(candidates, key=lambda pair: pair[0])[1]) if candidates else {}


def load(path, default):
    return json.loads(path.read_text('utf-8')) if path.exists() else default


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(text, encoding='utf-8')
    temporary.replace(path)


def save(path, value):
    write(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def content_digest(item):
    """Compare the exact published text/version; index timestamps/topics may vary."""
    if not isinstance(item, dict) or not isinstance(item.get('summary'), str) or not item['summary'].strip():
        raise ValueError('No official API summary text')
    ident(item['id'])
    if not item.get('title') or not item.get('currentVersion') or not item.get('publishDate'):
        raise ValueError('Incomplete API identity/version metadata')
    payload = {key: item.get(key) for key in CONTENT_FIELDS}
    return sha(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())


def safe_path(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Evidence path escapes repository')
    return path


def archive_api_summary(root, record, now=None):
    """Preserve an extracted API record plus a clearly labelled summary derivative."""
    root = Path(root)
    now = now or datetime.now(timezone.utc)
    checked = stamp(record.get('detail_checked_at'))
    if not 0 <= (now - checked).total_seconds() <= 26 * 3600:
        raise ValueError('API detail evidence is stale or in the future')
    item = record.get('api_metadata', {})
    report_id = ident(item.get('id', ''))
    if report_id != record.get('task', {}).get('id') or report_id != record.get('signal', {}).get('id'):
        raise ValueError('API record identity mismatch')
    digest = content_digest(item)
    # This is explicitly a reserialized CRSReport record, not a wire-byte capture.
    serialized = json.dumps(item, ensure_ascii=False, sort_keys=True, indent=2) + '\n'
    raw_hash = sha(serialized.encode())
    stem = report_id + '-' + raw_hash[:20]
    record_path = 'metadata/official-api-records/' + stem + '.json'
    text_path = 'metadata/official-api-text/' + stem + '.md'
    source_url = API + report_id + '?format=json'
    write(root / record_path, serialized)
    text = ('# ' + str(item['title']) + '\n\n'
            '> Supplementary official API text, NOT the PDF/HTML original.\n'
            '> This reproduces the Congress.gov API `summary` field verbatim; full-report completeness, original layout and hyperlinks are not established.\n'
            '> The original remains pending and this supplement does not clear that failure.\n\n'
            + 'Source: ' + source_url + '\n\n'
            + 'API version: ' + str(item['currentVersion']) + '\n\n'
            + 'API detail fetched: ' + checked.isoformat() + '\n\n'
            + item['summary'] + '\n')
    write(root / text_path, text)
    entry = dict(id=report_id, api_version=str(item['currentVersion']), source_url=source_url,
                 observed_at=checked.isoformat(), stored_at=now.isoformat(), record=record_path,
                 markdown=text_path, record_sha256=raw_hash, markdown_sha256=sha(text.encode()),
                 content_sha256=digest, comparison_fields=list(CONTENT_FIELDS),
                 representation='reserialized official CRSReport API record and verbatim summary field',
                 original_verified=False, counts_as_original=False)
    entries = load(root / MANIFEST, [])
    entries = [old for old in entries if not (old.get('id') == report_id and old.get('record_sha256') == raw_hash)]
    entries.append(entry)
    save(root / MANIFEST, entries)
    return entry


def verify_api_summary(root, report_id, fetch_json, now=None):
    """Independently refetch official API text; never convert this into original success."""
    root = Path(root)
    report_id = ident(report_id)
    entries = [entry for entry in load(root / MANIFEST, []) if entry.get('id') == report_id]
    if not entries:
        return None
    entry = max(entries, key=lambda value: stamp(value['observed_at']))
    now = now or datetime.now(timezone.utc)
    proof = dict(id=report_id, checked_at=now.isoformat(), verified=False,
                 original_verified=False, counts_as_original=False,
                 record=entry['record'], markdown=entry['markdown'],
                 source_url=API + report_id + '?format=json',
                 comparison='Exact API identity/version/publication/title/summary; NOT PDF/HTML equivalence')
    try:
        raw = safe_path(root, entry['record']).read_bytes()
        text = safe_path(root, entry['markdown']).read_bytes()
        if sha(raw) != entry['record_sha256'] or sha(text) != entry['markdown_sha256']:
            raise ValueError('Supplementary evidence checksum mismatch')
        saved = json.loads(raw)
        if saved.get('id') != report_id or content_digest(saved) != entry['content_sha256']:
            raise ValueError('Supplementary evidence identity/content mismatch')
        obj = fetch_json(proof['source_url'])
        live = next((value for key, value in obj.items() if key.lower() == 'crsreport'), None)
        if not isinstance(live, dict) or live.get('id') != report_id:
            raise ValueError('Live API report identity mismatch')
        live_digest = content_digest(live)
        if live_digest != entry['content_sha256']:
            raise ValueError('Live API text/version changed; supplement must be refreshed')
        proof.update(verified=True, content_sha256=live_digest,
                     live_update_date=live.get('updateDate'), api_version=str(live['currentVersion']))
    except Exception as exc:
        proof['error'] = type(exc).__name__ + ': ' + str(exc)
    return proof
