import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import date

spec = importlib.util.spec_from_file_location('audit',Path(__file__).with_name('verify_crs.py'))
audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)
sys.path.insert(0,str(audit.ROOT/'tests'))
from test_sync import make_pdf

class CoverageTests(unittest.TestCase):
    def receipt(self):
        return dict(sources={'official_api':{'ok':True},'mirror':{'ok':True}},missing=[],invalid_files=[],unverified=[])
    def test_failure_not_green_when_missing(self):
        r=self.receipt();r['missing']=[{'id':'R1'}];self.assertEqual(audit.result_state(r),'failed')
    def test_official_outage_is_not_complete(self):
        r=self.receipt();r['sources']['official_api']['ok']=False;self.assertEqual(audit.result_state(r),'unverified')
    def test_unverifiable_file_is_not_complete(self):
        r=self.receipt();r['unverified']=[{'id':'R1'}];self.assertEqual(audit.result_state(r),'unverified')
    def test_same_date_different_hash_is_missing(self):
        self.assertFalse(audit.hash_matches([{'date':'2026-10-22','pdf_sha1':'a'}],'b'))
    def test_unknown_hash_is_not_match(self):
        self.assertFalse(audit.hash_matches([{'pdf_sha1':''}],''))
    def test_boundary_date(self):
        self.assertTrue(audit.in_window('2026-10-22T04:00:00Z',date(2026,10,16),date(2026,10,23)))
        self.assertFalse(audit.in_window(None,date(2026,10,16),date(2026,10,23)))
    def test_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):audit.safe_local(Path(d),'../outside')
    def test_actual_pdf_corruption_detected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);body=make_pdf();(p/'x.pdf').write_bytes(body);(p/'x.md').write_text('text')
            v=dict(id='R10000',pdf='x.pdf',markdown='x.md',pdf_sha1=audit.s.digest(body,'sha1'),pdf_sha256=audit.s.digest(body))
            good,bad=audit.verify_manifest(p,[v]);self.assertIn('R10000',good);self.assertFalse(bad)
            (p/'x.pdf').write_bytes(body+b'changed')
            good,bad=audit.verify_manifest(p,[v]);self.assertFalse(good);self.assertEqual(len(bad),1)
    def test_duplicate_pagination_rejected(self):
        class HTTP:
            def json(self,url):
                return {'CRSReports':[{'id':'R10000'}], 'pagination':{'count':2,'next':'next'}}
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'repeated'):
                audit.official_list(HTTP(),date(2026,10,16),date(2026,10,23),Path(d))

if __name__=='__main__': unittest.main()
