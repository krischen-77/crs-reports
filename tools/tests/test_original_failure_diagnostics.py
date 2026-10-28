"""Keep both original-source errors without extra routes or weaker validation."""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import crs_formats as f


class OriginalFailureTests(unittest.TestCase):
    def setUp(self):
        self.task={'id':'IN12598','primary_format':'PDF','official_pdf_format_missing':True,
                   'formats':{'PDF':{'urls':['https://www.congress.gov/declared.pdf']},
                              'HTML':{'urls':['https://www.congress.gov/declared.html']}}}

    def test_both_failure_causes_are_preserved(self):
        http=Mock();http.get.side_effect=[RuntimeError('PDF HTTP 404'),RuntimeError('HTML HTTP 403')]
        with self.assertRaises(RuntimeError) as caught:f.fetch_original(http,self.task)
        self.assertIn('PDF HTTP 404',str(caught.exception))
        self.assertIn('HTML HTTP 403',str(caught.exception))
        self.assertEqual(http.get.call_count,2)

    def test_explicit_pdf_failure_does_not_use_html(self):
        http=Mock();http.get.side_effect=ValueError('bad advertised PDF')
        self.task['official_pdf_format_missing']=False
        with self.assertRaisesRegex(ValueError,'bad advertised PDF'):f.fetch_original(http,self.task)
        http.get.assert_called_once()

    def test_valid_pdf_does_not_fetch_html(self):
        http=Mock();http.get.return_value=(b'%PDF-fixture','pdf-url')
        with patch.object(f,'validate_pdf') as validate:
            raw,url,kind,notes=f.fetch_original(http,self.task)
        self.assertEqual((raw,url,kind,notes),(b'%PDF-fixture','pdf-url','PDF',[]))
        validate.assert_called_once();http.get.assert_called_once()

    def test_declared_html_recovery_keeps_pdf_failure_notice(self):
        http=Mock();http.get.side_effect=[(b'%PDF-fixture','pdf-url'),(b'<html>fixture</html>','html-url')]
        with patch.object(f,'validate_pdf',side_effect=ValueError('wrong embedded revision')),patch.object(f,'validate_html') as validate:
            raw,url,kind,notes=f.fetch_original(http,self.task)
        self.assertEqual((url,kind),('html-url','HTML'))
        self.assertIn('wrong embedded revision',notes[0])
        validate.assert_called_once();self.assertEqual(http.get.call_count,2)


if __name__=='__main__':unittest.main()
