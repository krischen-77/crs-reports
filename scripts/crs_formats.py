"""Official-original handling. Missing PDF metadata is not proof of no original.

A derived PDF is accepted ONLY with a live currentVersion plus matching embedded
report ID/revision/title. Otherwise only an explicitly advertised original is used.
Old mirrored PDFs never establish the current version.
"""
from __future__ import annotations
import copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


def collector():
    import sync_crs
    return sync_crs


def error_text(exc: Exception) -> str:
    return f"{type(exc).__name__}: {str(exc) or repr(exc)}"


def report_item(obj: dict) -> dict:
    if isinstance(obj, dict):
        item = next((v for k, v in obj.items() if k.lower() == 'crsreport'), None)
        if isinstance(item, dict):
            return item
    raise ValueError('Official detail response has no CRSReport object')


def task_from_item(item: dict) -> dict:
    s = collector()
    ident = s.report_id(item['id'])
    formats = {}
    raw_formats = item.get('formats', [])
    if not isinstance(raw_formats, list):
        raise ValueError(f'{ident}: invalid official formats schema')
    for fmt in raw_formats:
        if not isinstance(fmt, dict):
            continue
        kind = str(fmt.get('format', '')).strip().upper()
        kind = {'APPLICATION/PDF': 'PDF', 'TEXT/HTML': 'HTML'}.get(kind, kind)
        if kind not in ('PDF', 'HTML'):
            continue
        url = fmt.get('url') or fmt.get('URL')
        if url:
            url = s.safe_url(url)
            if urlsplit(url).hostname not in ('www.congress.gov', 'congress.gov', 'crsreports.congress.gov'):
                raise ValueError(f'{ident}: official formats must point to an official host')
            formats[kind] = {'urls': [url], 'sha1': ''}
    # currentVersion belongs to the detail API; list-level `version` is NOT a substitute.
    current = str(item.get('currentVersion', '')).strip()
    derived = False
    if 'PDF' not in formats and 'HTML' in formats and re.fullmatch(r'[1-9]\d{0,5}', current):
        html_url = urlsplit(formats['HTML']['urls'][0])
        match = re.fullmatch(r'/crs_external_products/([A-Z]+)/HTML/' + re.escape(ident) + r'(?:\.web)?\.html', html_url.path)
        if html_url.hostname in ('www.congress.gov', 'congress.gov') and match:
            candidate = f'https://www.congress.gov/crs_external_products/{match[1]}/PDF/{ident}/{ident}.{current}.pdf'
            formats['PDF'] = {'urls': [candidate], 'sha1': '',
                              'require_embedded_revision': current,
                              'resolution': 'derived from live detail currentVersion and official HTML namespace'}
            derived = True
    if not formats:
        raise ValueError(f'{ident}: official detail advertises no supported original format')
    primary = 'PDF' if 'PDF' in formats else 'HTML'
    version = s.source_version(formats['PDF']['urls'][0]) if primary == 'PDF' else current or 'unknown'
    return dict(id=ident, title=item.get('title') or ident,
                date=str(item.get('publishDate') or '')[:10], version=version,
                api_version=current or str(item.get('version', '')), formats=formats,
                primary_format=primary, metadata_source='Congress.gov API', source_record=ident,
                required_by_recent_update=True, observed_update_date=item.get('updateDate', ''),
                official_pdf_format_missing=derived)


def validate_pdf(raw: bytes, task: dict) -> None:
    s = collector()
    if not raw.lstrip().startswith(b'%PDF-'):
        raise ValueError('Official response is not a PDF')
    with s.fitz.open(stream=raw, filetype='pdf') as doc:
        if not len(doc) or doc.needs_pass:
            raise ValueError('Official PDF is empty or encrypted')
        expected = task.get('formats', {}).get('PDF', {}).get('require_embedded_revision')
        if not expected:
            return
        first = doc[0].get_text()
        last = '\n'.join(doc[i].get_text() for i in range(max(0, len(doc)-2), len(doc)))
        ident = task['id']
        if not re.search(r'\b' + re.escape(ident) + r'\b', first):
            raise ValueError('Derived PDF report ID does not match official metadata')
        pattern = r'\b' + re.escape(ident) + r'\b[\s·•.\-]*VERSION\s+' + re.escape(str(expected)) + r'\b'
        if not re.search(pattern, last, re.I):
            raise ValueError('Derived PDF embedded revision does not match official currentVersion')
        normalize = lambda text: ' '.join(re.findall(r'\w+', text.casefold()))
        if normalize(task['title']) not in normalize(first):
            raise ValueError('Derived PDF cover title does not match official metadata')


def validate_html(raw: bytes, task: dict) -> None:
    s = collector()
    if raw.lstrip().startswith(b'%PDF-'):
        raise ValueError('HTML original endpoint returned a different format')
    soup = s.BeautifulSoup(raw, 'html.parser')
    for node in soup.select('script, style, noscript'):
        node.decompose()
    text = soup.get_text(' ', strip=True)
    prefix = text[:700].lower()
    if len(text) < 200 or any(x in prefix for x in ('just a moment', 'access denied', 'verify you are human', 'sign in to continue')):
        raise ValueError('HTML original is empty or an access-denial page')
    if not re.search(r'\b' + re.escape(task['id']) + r'\b', text):
        raise ValueError('HTML original report ID does not match')
    normalize = lambda x: ' '.join(re.findall(r'\w+', x.casefold()))
    if normalize(task['title']) not in normalize(text):
        raise ValueError('HTML original title does not match')


def original_kind(task: dict) -> str:
    return task.get('primary_format') or ('PDF' if 'PDF' in task.get('formats', {}) else 'HTML')


def fetch_original(http, task: dict) -> tuple[bytes, str, str, list[str]]:
    """Prefer PDF; a missing-metadata candidate may fall back to declared HTML.

    Never fall back from an explicitly advertised but invalid PDF to a stale mirror.
    """
    kind = original_kind(task)
    try:
        raw, url = http.get(task['formats'][kind]['urls'][0])
        (validate_pdf if kind == 'PDF' else validate_html)(raw, task)
        return raw, url, kind, []
    except Exception as exc:
        if kind != 'PDF' or not task.get('official_pdf_format_missing') or 'HTML' not in task['formats']:
            raise
        # This is an independently advertised original, not a guessed alternate route.
        raw, url = http.get(task['formats']['HTML']['urls'][0])
        validate_html(raw, task)
        return raw, url, 'HTML', ['Unlisted PDF could not be validated; saved advertised HTML original: ' + error_text(exc)]


def verify_html_entry(root: Path, entry: dict) -> bool:
    s = collector()
    try:
        root = root.resolve()
        path = (root / entry['original']).resolve()
        md = (root / entry['markdown']).resolve()
        return (path.is_relative_to(root) and md.is_relative_to(root) and path.is_file()
                and md.is_file() and s.digest(path.read_bytes()) == entry['sha256'])
    except (KeyError, OSError, ValueError):
        return False


def save_html(root: Path, task: dict, raw: bytes, actual_url: str) -> tuple[dict, bool]:
    s = collector()
    validate_html(raw, task)
    sha = s.digest(raw)
    entries = s.read_json(root/'data/html-original-manifest.json', [])
    old = next((v for v in entries if v['id'] == task['id'] and v['sha256'] == sha), None)
    if old and verify_html_entry(root, old):
        return old, False
    version = re.sub(r'[^A-Za-z0-9-]', '', str(task['version'])) or 'unknown'
    stem = f"{task['id']}v{version}-{s.day(task['date']) or 'undated'}-{sha[:16]}"
    original = f'html/originals/{stem}.html'
    md_path = f'markdown/originals/{stem}.md'
    s.write(root/original, raw)
    soup = s.BeautifulSoup(raw, 'html.parser')
    for node in soup.select('script, style, noscript'):
        node.decompose()
    # Raw HTML is authoritative; this Markdown is a clearly labelled derivative.
    header = {'report_id': task['id'], 'source_url': actual_url, 'original_format': 'HTML',
              'original_sha256': sha, 'api_version': task['api_version'],
              'conversion': 'html-to-markdown; original HTML bytes preserved separately'}
    text = '---\n' + '\n'.join(f'{k}: {json.dumps(v)}' for k, v in header.items()) + '\n---\n\n'
    text += s.markdownify(str(soup), heading_style='ATX')
    s.write(root/md_path, text+'\n')
    entry = dict(id=task['id'], title=task['title'], date=task['date'], version=version,
                 original_format='HTML', original=original, sha256=sha, source_url=actual_url,
                 markdown=md_path, archived_at=(old or {}).get('archived_at') or datetime.now(timezone.utc).isoformat())
    entries = [v for v in entries if not (v['id'] == task['id'] and v['sha256'] == sha)] + [entry]
    s.write_json(root/'data/html-original-manifest.json', entries)
    return entry, old is None
