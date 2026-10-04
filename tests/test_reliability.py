"""Offline regressions for the 2026-10-02/03 API metadata/backlog incident."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from scripts import sync_crs as crs
from test_sync import FakeHTTP, make_pdf


START, END = date(2026, 9, 27), date(2026, 10, 4)


def task(ident='R10000', published='2026-10-01', pdf=None):
    pdf = pdf or make_pdf()
    return {'id': ident, 'date': published, 'title': 'Synthetic fixture', 'version': '1',
            'metadata_source': 'EveryCRSReport.com', 'formats': {'PDF': {
                'urls': [crs.MIRROR + 'files/' + ident + '.pdf'], 'sha1': crs.digest(pdf, 'sha1')}}}


class PlanningTests(unittest.TestCase):
    def test_mass_old_metadata_updates_do_not_become_current_pdf_jobs(self):
        rows = [{'id': 'R' + str(10000+i), 'publishDate': '2015-01-01',
                 'updateDate': '2026-10-02', 'status': 'Archived'} for i in range(400)]
        rows.append({'id': 'IF13324', 'publishDate': '2026-10-01', 'updateDate': '2026-10-02'})
        required, metadata = crs.publication_candidates(rows, {}, START, END)
        self.assertEqual(list(required), ['IF13324'])
        self.assertEqual(len(metadata), 400)
        self.assertEqual(metadata[0]['updateDate'], '2026-10-02')

    def test_mirror_revision_not_lost_when_api_publication_lags(self):
        row = {'id': 'R10000', 'publishDate': '2020-01-01', 'updateDate': '2026-10-02'}
        required, _ = crs.publication_candidates([row], {'R10000': {'published': '2026-10-01'}}, START, END)
        self.assertIn('R10000', required)

    def test_missing_publication_date_never_demoted(self):
        required, _ = crs.publication_candidates([{'id': 'R10000', 'updateDate': '2026-10-02'}], {}, START, END)
        self.assertIn('R10000', required)

    def test_future_publication_not_in_historical_window(self):
        required, _ = crs.publication_candidates([{'id': 'R10000', 'publishDate': '2026-10-10',
                                                   'updateDate': '2026-10-02'}], {}, START, END)
        self.assertFalse(required)

    def test_scope_migration_keeps_old_specs_and_true_missed_reports(self):
        old, missed, unknown = task(published='2015-01-01'), task('R10001', '2026-09-20'), task('R10002', '')
        required, background = crs.split_pending({'reports': [], 'tasks': [old, missed, unknown]}, [], date(2026, 9, 17))
        self.assertEqual([t['id'] for t in required['tasks']], ['R10001', 'R10002'])
        self.assertEqual(background[0]['task'], old)
        again, bg2 = crs.split_pending(required, background, date(2026, 9, 17))
        self.assertEqual(again, required)
        self.assertEqual(bg2, background)

    def test_manual_backfill_promotes_optional_task(self):
        old = task(published='2015-01-01')
        required, background = crs.split_pending({'reports': [], 'tasks': []}, [{'task': old, 'attempts': 4}], date(2014, 1, 1))
        self.assertEqual(required['tasks'], [old])
        self.assertEqual(background, [])

    def test_migration_uses_original_run_windows_not_pdf_dates(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            crs.write_json(root / 'data/runs/2026-09-24/1.json', {'window_start_inclusive': '2026-09-17'})
            crs.write_json(root / 'data/archive-manifest.json', [{'date': '2001-01-01'}])
            self.assertEqual(crs.archive_start_date(root, START), date(2026, 9, 17))
            self.assertEqual(crs.archive_start_date(root, date(2014, 1, 1)), date(2014, 1, 1))


class RecoveryCacheTests(unittest.TestCase):
    def setUp(self):
        self.pdf = make_pdf()
        self.original = task(published='2020-05-13')
        self.original['formats']['PDF']['sha1'] = '0'*40
        self.pdf_url = 'https://www.congress.gov/crs_external_products/R/PDF/R10000/R10000.3.pdf'
        self.alternative = {**self.original, 'metadata_source': 'Congress.gov API', 'version': '3',
                            'formats': {'PDF': {'urls': [self.pdf_url]}}}

    def recovered(self, root):
        http = FakeHTTP({self.original['formats']['PDF']['urls'][0]: self.pdf, self.pdf_url: self.pdf})
        with patch.object(crs, 'official_task', return_value=self.alternative):
            return crs.archive_task(http, root, self.original, [])[0]

    def test_independently_recovered_pdf_is_reused_without_any_network(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            saved = self.recovered(root)
            http = FakeHTTP({})
            with patch.object(crs, 'official_task', side_effect=AssertionError('must not call API')):
                again, is_new, _ = crs.archive_task(http, root, self.original, [saved])
            self.assertFalse(is_new)
            self.assertEqual(again['pdf'], saved['pdf'])
            self.assertEqual(http.calls, [])

    def test_corrupt_cached_pdf_never_trusted(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            saved = self.recovered(root)
            (root / saved['pdf']).write_bytes(b'corrupt')
            with patch.object(crs, 'official_task', side_effect=RuntimeError('offline')):
                with self.assertRaises(RuntimeError):
                    crs.archive_task(FakeHTTP({}), root, self.original, [saved])

    def test_different_date_cannot_reuse_old_recovery(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            saved = self.recovered(root)
            changed = {**self.original, 'date': '2026-10-01'}
            with patch.object(crs, 'official_task', side_effect=RuntimeError('offline')):
                with self.assertRaises(RuntimeError):
                    crs.archive_task(FakeHTTP({}), root, changed, [saved])

    def test_html_retry_keeps_recovery_and_canonical_pdf_path(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            saved = self.recovered(root)
            saved['retry_html'] = True
            retry = copy.deepcopy(self.original)
            html_url = crs.MIRROR + 'files/R10000.html'
            retry['formats']['HTML'] = {'urls': [html_url]}
            http = FakeHTTP({html_url: RuntimeError('temporary HTML outage')})
            with patch.object(crs, 'official_task', side_effect=AssertionError('must not call API')):
                again, _, _ = crs.archive_task(http, root, retry, [saved])
            self.assertEqual(again['pdf'], saved['pdf'])
            self.assertEqual(again['version'], '3')
            self.assertEqual(again['source_recovery'], saved['source_recovery'])
            self.assertTrue(again['retry_html'])
            self.assertEqual(http.calls, [html_url])


class BackgroundTests(unittest.TestCase):
    def test_history_is_bounded_fair_and_failed_specs_are_not_deleted(self):
        entries = [{'task': task('R'+str(10000+i), '2015-01-01'), 'attempts': 0, 'next_retry': ''} for i in range(5)]
        with patch.object(crs, 'archive_task', side_effect=RuntimeError('quota')) as archive:
            q, _, count, notices = crs.retry_historical(Mock(), Path('.'), entries, [], END, 2)
            self.assertEqual(archive.call_count, 2)
            self.assertEqual(count, 0)
            self.assertEqual(len(q), 5)
            self.assertEqual(len(notices), 2)
            self.assertEqual({crs.retry_identity(e['task']) for e in q}, {crs.retry_identity(e['task']) for e in entries})
            archive.reset_mock()
            q2, _, _, _ = crs.retry_historical(Mock(), Path('.'), q, [], END, 2)
            attempted = [c.args[2]['id'] for c in archive.call_args_list]
            self.assertEqual(attempted, ['R10002', 'R10003'])
            self.assertTrue(all(e['next_retry'] == '2026-10-06' for e in q2 if e.get('attempts')))

    def test_zero_background_limit_never_attempts_download(self):
        e = [{'task': task(published='2015-01-01')}]
        with patch.object(crs, 'archive_task') as archive:
            q, _, _, _ = crs.retry_historical(Mock(), Path('.'), e, [], END, 0)
            archive.assert_not_called()
            self.assertEqual(q, e)


class QuotaTests(unittest.TestCase):
    def test_each_wire_retry_counts_towards_demo_budget(self):
        http = crs.HTTP()
        http.api_calls = 19
        http.session.get = Mock(side_effect=requests.ConnectionError('network'))
        with patch.object(crs.time, 'sleep'), self.assertRaisesRegex(RuntimeError, 'budget'):
            http.get(crs.API)
        self.assertEqual(http.session.get.call_count, 1)
        self.assertEqual(http.api_calls, 20)

    def test_zero_remaining_quota_stops_before_wire_request(self):
        http = crs.HTTP()
        http.api_remaining = 0
        http.session.get = Mock()
        with self.assertRaisesRegex(RuntimeError, 'quota'):
            http.get(crs.API)
        http.session.get.assert_not_called()

    def test_literal_demo_key_is_not_treated_as_personal_key(self):
        self.assertFalse(crs.HTTP('DEMO_KEY').has_key)


class SyncOutcomeTests(unittest.TestCase):
    def run_fixture(self, root, pdf, missing=False, history=False):
        ident = 'R10000'
        pdf_url = crs.MIRROR + 'files/' + ident + '.pdf'
        obj = {'id': ident, 'versions': [{'id': 'R10000_A1_2026-10-01', 'date': '2026-10-01',
                                        'formats': [{'format': 'PDF', 'filename': 'files/R10000.pdf', 'sha1': crs.digest(pdf, 'sha1')}]}]}
        rows = {f'R{20000+i}': {'id': f'R{20000+i}', 'published': '2001-01-01', 'mirror_metadata': 'fixture'} for i in range(1000)}
        rows[ident] = {'id': ident, 'published': '2026-10-01'}
        if history:
            crs.write_json(root / 'data/runs/2026-09-24/1.json', {'window_start_inclusive': '2026-09-17'})
            crs.write_json(root / 'data/pending.json', {'reports': [], 'tasks': [task('R10001', '2015-01-01')]})
        class FixtureHTTP(FakeHTTP):
            def __init__(self, *args):
                super().__init__({crs.MIRROR + 'reports.csv': b'csv-fixture', crs.RSS: b'<rss><channel/></rss>',
                                  pdf_url: RuntimeError('PDF missing') if missing else pdf})
                self.has_key, self.api_calls, self.api_remaining = False, 0, None
            def json(self, url):
                if url == crs.MIRROR + 'reports/R10000.json':
                    return obj
                raise RuntimeError('API recovery unavailable')
        args = SimpleNamespace(root=str(root), until='2026-10-04', days=7, full_catalog=False, historical_limit=2)
        with patch.object(crs, 'HTTP', FixtureHTTP), patch.object(crs, 'api_scan', return_value=([], 0)), \
             patch.object(crs, 'parse_catalog', return_value=rows), contextlib.redirect_stdout(io.StringIO()):
            result = crs.sync(args)
        return result, crs.read_json(root / 'data/status.json', {})

    def test_missing_required_pdf_is_still_a_failed_run(self):
        with tempfile.TemporaryDirectory() as d:
            result, status = self.run_fixture(Path(d), make_pdf(), missing=True)
            self.assertEqual(result, 1)
            self.assertFalse(status['primary_pdf_complete'])
            self.assertEqual(status['pending_versions'], 1)
            self.assertEqual(status['total_archived_pdf_versions'], 0)

    def test_optional_history_failure_is_disclosed_without_failing_current_backup(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            result, status = self.run_fixture(root, make_pdf(), history=True)
            self.assertEqual(result, 0)
            self.assertTrue(status['primary_pdf_complete'])
            self.assertEqual(status['historical_pending_versions'], 1)
            self.assertEqual(status['total_archived_pdf_versions'], 1)
            self.assertEqual(status['result'], 'success_with_warnings')
            self.assertEqual(len(crs.read_json(root / 'data/historical-pending.json', {})['entries']), 1)
            self.assertTrue(status['warnings'])

    def test_missing_all_discovery_sources_cannot_return_success(self):
        with tempfile.TemporaryDirectory() as d:
            args = SimpleNamespace(root=d, until='2026-10-04', days=7, full_catalog=False, historical_limit=0)
            http = Mock(has_key=False, api_calls=0, api_remaining=None)
            http.get.side_effect = RuntimeError('offline')
            with patch.object(crs, 'HTTP', return_value=http), patch.object(crs, 'api_scan', side_effect=RuntimeError('offline')), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(crs.sync(args), 1)


if __name__ == '__main__':
    unittest.main()
