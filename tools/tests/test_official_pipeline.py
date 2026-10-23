import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import date
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import official_pipeline as p
s=p.s
class OfficialTests(unittest.TestCase):
    def row(self):
        return dict(id='R10001',title='Example',publishDate='2026-07-31T04:00:00Z',updateDate='2026-10-22T00:00:00Z',status='Active')
    def task(self):
        return p.task_from_item({**self.row(),'currentVersion':5,'formats':[{'format':'PDF','url':'https://www.congress.gov/crs_external_products/R/PDF/R10001/R10001.5.pdf'}]})
    def pdf(self):
        with s.fitz.open() as d:
            page=d.new_page();page.insert_text((72,72),'Example report\nUpdated October 20, 2026\nR10001\n'+('Full report. '*20))
            return d.tobytes()
    def test_active_older_date_required(self):
        self.assertTrue(p.is_required(self.row(),date(2026,10,16),date(2026,10,23)))
    def test_archived_old_status_not_required(self):
        self.assertFalse(p.is_required({**self.row(),'status':'Archived'},date(2026,10,16),date(2026,10,23)))
    def test_official_filename_wins_over_list_version(self):
        self.assertEqual(self.task()['version'],'5')
    def test_actual_cover_date_not_api_stale_date(self):
        self.assertEqual(p.cover_date(self.pdf(),'2026-07-31'),'2026-10-20')
    def test_wrong_cached_identity_rejected(self):
        with self.assertRaises(ValueError):p.save_current(None,Path('/tmp'),dict(task=self.task(),signal={'id':'R99999'}),[])
    def test_existing_pdf_preserves_real_cover_date(self):
        class H:
            def get(self,url):return body,url
        body=self.pdf()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);record=dict(task=self.task(),signal=p.signal(self.row()))
            old,_,_=s.archive_task(H(),root,{**self.task(),'date':'2026-10-20'},[])
            entry,new,_=p.save_current(H(),root,record,[old])
            self.assertEqual(entry['date'],'2026-10-20');self.assertFalse(new)
    def test_missing_resolution_is_incomplete_and_retained(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'data').mkdir();out=root/'out';parts=root/'parts';parts.mkdir()
            v=dict(start='2026-10-16',end='2026-10-23',cache={},required={'R10001':self.row()},official_rows=[self.row()],source_count=1,coverage_note='test')
            s.write_json(root/'plan.json',v)
            with contextlib.redirect_stdout(io.StringIO()):result=p.aggregate(root,out,root/'plan.json',parts)
            self.assertEqual(result,1);self.assertEqual(len(s.read_json(root/'data/official-pending.json',[])),1)
            self.assertIn('UNVERIFIED',(root/'CURRENT.md').read_text())
    def test_exact_official_file_saved(self):
        body=self.pdf()
        class H:
            def get(self,url):return body,url
        with tempfile.TemporaryDirectory() as d:
            entry,new,_=p.save_current(H(),Path(d),dict(task=self.task(),signal=p.signal(self.row())),[])
            self.assertTrue(new);self.assertEqual(entry['pdf_sha256'],s.digest(body));self.assertTrue(p.verify_local(Path(d),entry))
if __name__=='__main__':unittest.main()
