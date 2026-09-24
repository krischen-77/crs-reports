"""Deterministic offline regression tests; network smoke test runs in the sync job."""
import csv
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import fitz
from scripts.sync_crs import (api_scan, archive_task, body_markdown, category, digest,
                              download_format, export_indexes, feed_records,
                              mirror_tasks, parse_catalog, report_id, safe_url, within)


def make_pdf():
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Synthetic test report. This is a fixture, not a real CRS report. " * 2)
    result = document.tobytes()
    document.close()
    return result


class FakeHTTP:
    def __init__(self, bodies):
        self.bodies = bodies
        self.calls = []

    def get(self, url):
        self.calls.append(url)
        result = self.bodies[url]
        if isinstance(result, Exception):
            raise result
        return result, url


class SyncTests(unittest.TestCase):
    def test_date_boundaries_and_missing_dates(self):
        start, end = date(2026, 9, 17), date(2026, 9, 24)
        self.assertTrue(within("2026-09-17T12:00:00Z", start, end))
        self.assertTrue(within("2026-09-24", start, end))
        self.assertFalse(within("2026-09-16", start, end))
        self.assertFalse(within("2026-09-25", start, end))
        self.assertFalse(within(None, start, end))

    def test_id_and_path_safety(self):
        self.assertEqual(report_id("if12345"), "IF12345")
        self.assertEqual(report_id("97-123"), "97-123")
        for bad in ["../secret", "/tmp/x", "R1\nscript", ""]:
            with self.assertRaises(ValueError):
                report_id(bad)

    def test_scoped_url_and_key_redaction(self):
        result = safe_url("https://api.congress.gov/v3/crsreport?api_key=SECRET&offset=5")
        self.assertNotIn("SECRET", result)
        self.assertIn("offset=5", result)
        for bad in ["http://www.congress.gov/x", "https://evil.example/x", "https://www.congress.gov.evil.example/x", "https://a:b@www.congress.gov/x", "https://127.0.0.1/x"]:
            with self.assertRaises(ValueError):
                safe_url(bad)

    def test_categories(self):
        expected = {"IF1": "in-focus", "IN1": "insights", "LSB1": "sidebars", "IG1": "infographics", "TE1": "testimony", "R1": "reports", "RL1": "reports"}
        for ident, folder in expected.items():
            self.assertEqual(category(ident), folder)

    def test_csv_catalog_quoted_title(self):
        raw = b'number,url,sha1,latestPubDate,title,latestPDF,latestHTML\nR10000,reports/R10000.json,x,2026-09-24,"A title, with comma",files/test.pdf,files/test.html\n'
        rows = parse_catalog(raw)
        self.assertEqual(rows["R10000"]["title"], "A title, with comma")
        self.assertEqual(rows["R10000"]["mirror_pdf"], "https://www.everycrsreport.com/files/test.pdf")
        with self.assertRaises(ValueError):
            parse_catalog(b"<html>Access denied</html>")

    def test_rss_is_only_supplemental(self):
        raw = b'<rss><channel><item><title>Example</title><link>https://www.EveryCRSReport.com/reports/R10000.html</link><pubDate>Thu, 24 Sep 2026 00:00:00 -0400</pubDate></item></channel></rss>'
        self.assertEqual(feed_records(raw)[0]["id"], "R10000")

    def test_all_versions_in_window_are_selected(self):
        def version(n, d):
            return {"id": str(n), "date": d, "title": "Example", "formats": [{"format": "PDF", "url": f"https://www.congress.gov/crs_external_products/R/PDF/R10000/R10000.{n}.pdf", "filename": f"files/{n}.pdf", "sha1": "a" * 40}]}
        obj = {"id": "R10000", "versions": [version(3, "2026-09-24"), version(2, "2026-09-20"), version(1, "2020-01-01")]}
        tasks = mirror_tasks(obj, date(2026, 9, 17), date(2026, 9, 24))
        self.assertEqual([t["version"] for t in tasks], ["3", "2"])
        self.assertEqual(len(tasks[0]["formats"]["PDF"]["urls"]), 2)

    def test_paginated_api_keeps_date_filters(self):
        class APIHTTP:
            def __init__(self):
                self.urls = []
            def json(self, url):
                self.urls.append(url)
                return {"CRSReports": [{"id": str(len(self.urls))}], "pagination": {"count": 2, **({"next": "https://api.congress.gov/v3/crsreport?offset=1"} if len(self.urls) == 1 else {})}}
        http = APIHTTP()
        rows, total = api_scan(http, date(2026, 9, 17), date(2026, 9, 24))
        self.assertEqual(total, len(rows))
        self.assertTrue(all("fromDateTime=" in u for u in http.urls))
        self.assertIn("offset=1", http.urls[1])

    def test_truncated_api_is_error_not_empty_success(self):
        class Truncated:
            def json(self, url):
                return {"CRSReports": [], "pagination": {"count": 10}}
        with self.assertRaises(ValueError):
            api_scan(Truncated(), date(2026, 9, 17), date(2026, 9, 24))

    def test_pdf_fallback_and_hash_validation(self):
        pdf = make_pdf()
        official, mirror = "https://www.congress.gov/a.pdf", "https://www.everycrsreport.com/files/a.pdf"
        http = FakeHTTP({official: b"<html>not pdf</html>", mirror: pdf})
        result, actual, notices = download_format(http, {"urls": [official, mirror], "sha1": digest(pdf, "sha1")}, "PDF")
        self.assertEqual(result, pdf)
        self.assertEqual(actual, mirror)
        self.assertTrue(notices)

    def test_pdf_extraction_without_ai_or_ocr(self):
        text, method, pages = body_markdown(None, "", make_pdf())
        self.assertIn("Synthetic test report", text)
        self.assertEqual(pages, 1)
        self.assertIn("pdf-text-extraction", method)

    def test_html_resolves_relative_links_and_removes_scripts(self):
        html = b'<body><h1>Report</h1><p>' + b'Public research text. ' * 15 + b'</p><a href="other.html">Source</a><script>execute_bad()</script></body>'
        text, method, pages = body_markdown(html, "https://www.congress.gov/content/report.html", make_pdf())
        self.assertIn("https://www.congress.gov/content/other.html", text)
        self.assertNotIn("execute_bad", text)
        self.assertIn("html-to-markdown", method)

    def test_archive_is_idempotent_and_keeps_changed_same_day_version(self):
        pdf = make_pdf()
        url = "https://www.everycrsreport.com/files/test.pdf"
        task = {"id": "R10000", "title": "Fixture", "date": "2026-09-24", "version": "1", "metadata_source": "fixture", "formats": {"PDF": {"urls": [url], "sha1": digest(pdf, "sha1")}}}
        http = FakeHTTP({url: pdf})
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            entry, is_new, _ = archive_task(http, root, task, [])
            self.assertTrue(is_new)
            self.assertEqual((root / entry["pdf"]).read_bytes(), pdf)
            entry2, is_new, _ = archive_task(http, root, task, [entry])
            self.assertFalse(is_new)
            self.assertEqual(len(http.calls), 1)
            second = make_pdf()
            self.assertNotEqual(digest(pdf), digest(second))
            task["formats"]["PDF"]["sha1"] = digest(second, "sha1")
            http.bodies[url] = second
            newer, _, _ = archive_task(http, root, task, [entry])
            self.assertNotEqual(entry["pdf"], newer["pdf"])
            self.assertTrue((root / entry["pdf"]).exists())
            self.assertTrue((root / newer["pdf"]).exists())

    def test_failed_html_keeps_pdf_and_is_queued_for_retry(self):
        pdf = make_pdf()
        p, h = "https://www.everycrsreport.com/files/a.pdf", "https://www.everycrsreport.com/files/a.html"
        task = {"id": "R10000", "title": "Fixture", "date": "2026-09-24", "version": "1", "metadata_source": "fixture", "formats": {"PDF": {"urls": [p]}, "HTML": {"urls": [h]}}}
        with tempfile.TemporaryDirectory() as folder:
            result, _, notices = archive_task(FakeHTTP({p: pdf, h: RuntimeError("offline")}), Path(folder), task, [])
            self.assertTrue(result["retry_html"])
            self.assertTrue((Path(folder) / result["pdf"]).is_file())
            self.assertTrue((Path(folder) / result["markdown"]).is_file())

    def test_catalog_does_not_claim_link_only_reports_are_archived(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            export_indexes(root, {"R10000": {"title": "Fixture"}}, [], date(2026, 9, 17), date(2026, 9, 24))
            rows = list(csv.DictReader(io.StringIO((root / "data/all-report-links.csv").read_text("utf-8-sig"))))
            self.assertEqual(rows[0]["archived_versions"], "0")
            self.assertEqual(rows[0]["official_page_verified_by_api"], "False")


if __name__ == "__main__":
    unittest.main()
