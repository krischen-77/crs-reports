"""Evidence-based separation of obsolete mirror history from current originals."""
from __future__ import annotations
import hashlib
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit


def superseded_history(root: Path, task: dict, tasks: list[dict], archives: list[dict], archive_start: date):
    """Demote only after a newer freshly resolved official original is saved.

    Never demote an in-window original, an unknown date, or a genuinely current
    old-cover-date update. The exact old mirror specification remains retryable.
    """
    try:
        published = date.fromisoformat(str(task.get('date', ''))[:10])
    except ValueError:
        return None
    if (published >= archive_start or not task.get('required_by_recent_update')
            or task.get('metadata_source') == 'Congress.gov API'):
        return None
    for current in tasks:
        if current.get('id') != task.get('id') or current.get('metadata_source') != 'Congress.gov API':
            continue
        try:
            current_date = date.fromisoformat(str(current.get('date', ''))[:10])
        except ValueError:
            continue
        if current_date <= published:
            continue
        urls = set(current.get('formats', {}).get('PDF', {}).get('urls', []))
        for saved in archives:
            if (saved.get('id') != task['id'] or str(saved.get('date', ''))[:10] != str(current_date)
                    or saved.get('pdf_source') not in urls
                    or urlsplit(saved.get('pdf_source', '')).hostname not in
                    {'www.congress.gov', 'congress.gov', 'crsreports.congress.gov'}):
                continue
            try:
                path = (root / saved['pdf']).resolve()
                markdown = (root / saved['markdown']).resolve()
                if not path.is_relative_to(root.resolve()) or not markdown.is_relative_to(root.resolve()):
                    continue
                raw = path.read_bytes()
                if (not raw.lstrip().startswith(b'%PDF-') or not markdown.is_file()
                        or hashlib.sha256(raw).hexdigest() != saved['pdf_sha256']):
                    continue
            except (OSError, KeyError):
                continue
            return {'id': task['id'], 'historical_publication': str(published),
                    'official_publication': str(current_date), 'official_pdf_source': saved['pdf_source'],
                    'official_pdf_sha256': saved['pdf_sha256'],
                    'reason': 'Newer freshly resolved official original is archived and hash-verified; obsolete mirror predates every requested archive window. Exact historical task retained, not claimed complete.'}
    return None
