"""Publication windows expand after outages; only verified source receipts advance them."""
from __future__ import annotations
import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path


def parse_time(value: str) -> datetime:
    value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise ValueError('Timestamp must include a timezone')
    return value.astimezone(timezone.utc)


def last_verification(root: Path) -> dict:
    path = root / 'data/last-successful-verification.json'
    if path.exists():
        return json.loads(path.read_text('utf-8'))
    # Migrate only real, previously committed independent receipts.
    candidates = []
    for path in (root / 'data/audits').glob('*independent-current-verification.json'):
        receipt = json.loads(path.read_text('utf-8'))
        if receipt.get('result') == 'verified_for_observed_sources':
            candidates.append(receipt)
    return max(candidates, key=lambda r: r.get('finished_at', ''), default={})


def recovery_days(root: Path, end: date, minimum: int = 7, historical: bool = False) -> int:
    if not 1 <= minimum <= 3650:
        raise ValueError('Lookback must be between 1 and 3650 days')
    if historical:
        return minimum  # Preserve the user's explicit historical window.
    receipt = last_verification(root)
    if not receipt:
        return minimum  # First deployment, not a claim of verified coverage.
    if receipt.get('result') != 'verified_for_observed_sources':
        raise ValueError('Recovery watermark is not a successful verification')
    if any(receipt.get(k) for k in ('missing', 'unverified', 'invalid_files')):
        raise ValueError('Recovery watermark contains unresolved findings')
    previous = parse_time(receipt['finished_at']).date()
    if previous > end:
        raise ValueError('Recovery watermark is in the future')
    days = max(minimum, (end - previous).days + 1)
    if days > 3650:
        raise ValueError('Recovery exceeds supported window; manual backfill required')
    return days


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--days', type=int, default=7)
    p.add_argument('--until', default='')
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    a = p.parse_args()
    end = date.fromisoformat(a.until) if a.until else datetime.now(timezone.utc).date()
    print(recovery_days(a.root, end, a.days, bool(a.until)))
