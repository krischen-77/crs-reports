"""Regressions for source-schema differences found in the first live run."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from datetime import date
from scripts.sync_crs import (access_scope, source_version, mirror_covers_publication,
                              mirror_tasks, download_format, archive_task)
from test_sync import FakeHTTP, make_pdf

class LiveSchemaTests(unittest.TestCase):
    def test_access_denial_scopes_are_separate_routes(self):
        self.assertNotEqual(access_scope('https://www.congress.gov/crs_external_products/R/HTML/R1.html'),
                            access_scope('https://www.congress.gov/crs_external_products/R/PDF/R1.pdf'))
        self.assertEqual(access_scope('https://api.congress.gov/v3/crsreport/R1'), 'api.congress.gov')

    def test_legacy_and_current_pdf_revisions(self):
        self.assertEqual(source_version('https://crsreports.congress.gov/product/pdf/IF/IF10045/104'), '104')
        self.assertEqual(source_version('https://www.congress.gov/IF11806.11.pdf'), '11')
        self.assertEqual(source_version('', 'IF11806_A11_2026-09-22'), '11')

    def test_pdf_revision_not_confused_with_api_metadata_version(self):
        tasks = [{'date': '2026-09-22', 'version': '11'}]
        self.assertTrue(mirror_covers_publication(tasks, {'publishDate': '2026-09-22T04:00:00Z', 'version': 10}))
        self.assertFalse(mirror_covers_publication(tasks, {'publishDate': '2026-09-23T04:00:00Z', 'version': 10}))
        self.assertFalse(mirror_covers_publication([], {'publishDate': '2026-09-22'}))

    def test_nonpublic_legacy_url_does_not_discard_public_mirror(self):
        obj = {'id': 'R46354', 'versions': [{'date': '2020-05-13', 'formats': [
            {'format': 'PDF', 'url': 'https://www.crs.gov/Reports/pdf/R46354',
             'filename': 'files/test.pdf'}]}]}
        result = mirror_tasks(obj, date(2020, 5, 1), date(2020, 5, 31))
        self.assertEqual(result[0]['formats']['PDF']['urls'], ['https://www.everycrsreport.com/files/test.pdf'])
        self.assertEqual(len(result[0]['ignored_nonpublic_source_urls']), 1)

    def test_transformed_html_requires_explicit_provenance_and_identity(self):
        url = 'https://www.everycrsreport.com/files/test.html'
        html = b'<div>IF11806 ' + b'Public research text. ' * 20 + b'</div>'
        spec = {'urls': [url], 'sha1': '0' * 40, 'report_id': 'IF11806', 'allow_transformed_html': True}
        body, _, warnings = download_format(FakeHTTP({url: html}), spec, 'HTML')
        self.assertEqual(body, html)
        self.assertIn('derivative', warnings[0])
        spec['report_id'] = 'IF99999'
        with self.assertRaises(RuntimeError):
            download_format(FakeHTTP({url: html}), spec, 'HTML')
        spec['report_id'] = 'IF11806'
        spec['allow_transformed_html'] = False
        with self.assertRaises(RuntimeError):
            download_format(FakeHTTP({url: html}), spec, 'HTML')

    def test_pdf_checksum_is_never_relaxed(self):
        url = 'https://www.everycrsreport.com/files/test.pdf'
        with self.assertRaises(RuntimeError):
            download_format(FakeHTTP({url: make_pdf()}), {'urls': [url], 'sha1': '0' * 40, 'allow_transformed_html': True}, 'PDF')

    def test_historical_backfill_does_not_fetch_future_latest(self):
        obj = {'id': 'R10000', 'versions': [{'date': '2026-09-25', 'formats': [
            {'format': 'PDF', 'filename': 'files/test.pdf'}]}]}
        self.assertEqual(mirror_tasks(obj, date(2026, 9, 17), date(2026, 9, 24), include_latest=True), [])

    def test_bad_mirror_pdf_uses_independent_official_same_date(self):
        mirror = 'https://www.everycrsreport.com/files/bad.pdf'
        official = 'https://www.congress.gov/crs_external_products/R/PDF/R10000/R10000.3.pdf'
        task = {'id': 'R10000', 'title': 'Fixture', 'date': '2020-05-13', 'version': 'unknown',
                'metadata_source': 'EveryCRSReport.com', 'formats': {'PDF': {'urls': [mirror], 'sha1': '0' * 40}}}
        alternative = {**task, 'version': '3', 'metadata_source': 'Congress.gov API', 'formats': {'PDF': {'urls': [official]}}}
        http = FakeHTTP({mirror: make_pdf(), official: make_pdf()})
        with tempfile.TemporaryDirectory() as folder, patch('scripts.sync_crs.official_task', return_value=alternative):
            entry, is_new, notices = archive_task(http, Path(folder), task, [])
            self.assertEqual(entry['pdf_source'], official)
            self.assertEqual(entry['version'], '3')
            self.assertIn('source_recovery', entry)
            self.assertTrue(is_new)

    def test_bad_historical_pdf_not_replaced_by_newer_publication(self):
        mirror = 'https://www.everycrsreport.com/files/bad.pdf'
        task = {'id': 'R10000', 'title': 'Fixture', 'date': '2020-05-13', 'version': 'unknown',
                'metadata_source': 'EveryCRSReport.com', 'formats': {'PDF': {'urls': [mirror], 'sha1': '0' * 40}}}
        with tempfile.TemporaryDirectory() as folder, patch('scripts.sync_crs.official_task', return_value={**task, 'date': '2026-09-24'}):
            with self.assertRaises(RuntimeError):
                archive_task(FakeHTTP({mirror: make_pdf()}), Path(folder), task, [])

if __name__ == '__main__':
    unittest.main()
