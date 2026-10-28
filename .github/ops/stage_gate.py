"""Fail execution/integrity errors, not structured recoverable source failures.

Receipts keep their true incomplete result. Notifications are the watchdog's job.
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from refresh_receipts import load, save


def check(stage, root=ROOT):
    filenames = {'backup': 'status.json', 'official': 'official-status.json', 'audit': 'verification-status.json'}
    r = load(root / 'data' / filenames[stage], {})
    assert str(r.get('github_run_id')) == os.environ['GITHUB_RUN_ID'], 'Missing or stale stage receipt'
    assert str(r.get('github_run_attempt')) == os.environ['GITHUB_RUN_ATTEMPT'], 'Stale stage attempt'
    if stage == 'backup':
        assert r.get('result') in ('success', 'success_with_warnings', 'failed'), 'Unrecognized collector result'
        assert isinstance(r.get('errors'), list) and isinstance(r.get('required_pdf_failures'), int)
        incomplete = bool(r['errors'] or r['required_pdf_failures'])
    elif stage == 'official':
        required, verified, pending = [r.get(k) for k in ('official_current_required', 'official_current_verified', 'official_current_pending')]
        assert all(isinstance(x, int) and x >= 0 for x in (required, verified, pending)), 'Invalid official counts'
        assert verified + pending == required, 'Official coverage accounting mismatch'
        save(root / 'data/official-runs' / (os.environ['GITHUB_RUN_ID'] + '-' + os.environ['GITHUB_RUN_ATTEMPT'] + '.json'), r)
        incomplete = pending > 0 or r.get('result') != 'verified_for_observed_official_entries'
        if not incomplete:
            save(root / 'data/last-successful-official.json', r)
    else:
        assert all(isinstance(r.get(k), list) for k in ('missing', 'unverified', 'invalid_files')), 'Invalid audit receipt'
        assert r.get('finished_at'), 'Audit did not finish'
        assert not r['invalid_files'], 'Archived file corruption: immediate failure, never suppressed'
        incomplete = bool(r['missing'] or r['unverified'] or r.get('result') != 'verified_for_observed_sources')
    if incomplete:
        print('::warning title=CRS partial refresh::Source failures retained in the receipt and retry queues. Continue independent stages; watchdog escalates persistent or daily-delivery failures without repeated Actions failure mail.')
    else:
        print('Stage evidence verified; no unresolved required source failures.')
    return r


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['backup', 'official', 'audit'])
    check(parser.parse_args().stage)
