"""Regression for 2026-10-24: official detail omitted PDF while v2 existed."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone, timedelta
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import official_pipeline as p
import crs_formats as f
s=p.s
spec=importlib.util.spec_from_file_location('current_verifier',ROOT/'.github/current-verification/verify_current.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)


class FormatsTests(unittest.TestCase):
    def item(self):
        return dict(id='R49491',title='Federal Government Shutdowns and the Impact on Civil Aviation',
                    currentVersion=2,version=999,publishDate='2026-10-22T04:00:00Z',
                    updateDate='2026-10-24T02:09:40Z',status='Active',
                    formats=[dict(format='HTML',url='https://www.congress.gov/crs_external_products/R/HTML/R49491.html')])
    def pdf(self,ident='R49491',version='2',title=None):
        with s.fitz.open() as doc:
            pg=doc.new_page()
            pg.insert_textbox(s.fitz.Rect(40,40,550,700),(title or self.item()['title'])+'\nOctober 22, 2026\n'+ident+'\nCongressional Research Service\n'+('Content text. '*20))
            pg=doc.new_page();pg.insert_text((40,40),f'{ident} . VERSION {version} . UPDATED')
            return doc.tobytes()
    def html(self):
        return ('<html><head><title>'+self.item()['title']+'</title></head><body>R49491<h1>'+self.item()['title']+'</h1>'+('Original report text. '*30)+'</body></html>').encode()
    def test_current_version_not_list_version_builds_guarded_candidate(self):
        task=f.task_from_item(self.item())
        self.assertTrue(task['official_pdf_format_missing'])
        self.assertEqual(task['formats']['PDF']['require_embedded_revision'],'2')
        self.assertTrue(task['formats']['PDF']['urls'][0].endswith('R49491.2.pdf'))
    def test_explicit_pdf_always_preferred_and_mime_normalized(self):
        item=self.item();item['formats'].append(dict(format='application/pdf',URL='https://www.congress.gov/crs_external_products/R/PDF/R49491/R49491.3.pdf'))
        task=f.task_from_item(item);self.assertFalse(task['official_pdf_format_missing']);self.assertEqual(task['version'],'3')
    def test_no_current_version_does_not_guess_pdf_from_list_version(self):
        item=self.item();del item['currentVersion'];task=f.task_from_item(item)
        self.assertEqual(task['primary_format'],'HTML');self.assertNotIn('PDF',task['formats'])
    def test_valid_embedded_id_version_title_accepts_recovered_pdf(self):
        f.validate_pdf(self.pdf(),f.task_from_item(self.item()))
    def test_wrong_embedded_version_rejected(self):
        with self.assertRaisesRegex(ValueError,'revision'):f.validate_pdf(self.pdf(version='1'),f.task_from_item(self.item()))
    def test_wrong_embedded_identity_rejected(self):
        with self.assertRaisesRegex(ValueError,'ID'):f.validate_pdf(self.pdf(ident='R99999'),f.task_from_item(self.item()))
    def test_wrong_cover_title_rejected(self):
        with self.assertRaisesRegex(ValueError,'title'):f.validate_pdf(self.pdf(title='Wrong report'),f.task_from_item(self.item()))
    def test_corrupt_or_html_response_is_not_a_pdf(self):
        with self.assertRaises(ValueError):f.validate_pdf(b'<html>denied</html>',f.task_from_item(self.item()))
    def test_wrong_official_html_namespace_does_not_generate_pdf(self):
        item=self.item();item['formats'][0]['url']='https://www.congress.gov/crs_external_products/R/HTML/R11111.html'
        self.assertNotIn('PDF',f.task_from_item(item)['formats'])
    def test_nonofficial_host_is_rejected(self):
        item=self.item();item['formats'][0]['url']='https://www.everycrsreport.com/reports/R49491.html'
        with self.assertRaises(ValueError):f.task_from_item(item)
    def test_missing_formats_error_is_not_empty_stopiteration(self):
        item=self.item();item['formats']=[]
        with self.assertRaisesRegex(ValueError,'no supported original'):f.task_from_item(item)
        self.assertIn('StopIteration',f.error_text(StopIteration()))
    def test_missing_report_object_rejected(self):
        with self.assertRaisesRegex(ValueError,'CRSReport'):f.report_item({'request':{}})
    def test_fallback_pdf_failure_preserves_advertised_html_not_old_mirror(self):
        raw=self.html()
        class HTTP:
            def get(self,url):
                if '/PDF/' in url:raise RuntimeError('HTTP 404')
                return raw,url
        body,url,kind,notes=f.fetch_original(HTTP(),f.task_from_item(self.item()))
        self.assertEqual(kind,'HTML');self.assertTrue(notes);self.assertEqual(body,raw)
    def test_explicit_broken_pdf_is_not_silently_replaced(self):
        item=self.item();item['formats'].append(dict(format='PDF',url='https://www.congress.gov/crs_external_products/R/PDF/R49491/R49491.2.pdf'))
        class HTTP:
            def get(self,url):raise RuntimeError('upstream failed')
        with self.assertRaises(RuntimeError):f.fetch_original(HTTP(),f.task_from_item(item))
    def test_html_original_round_trip_and_dedup(self):
        task=f.task_from_item(self.item())
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            entry,new=f.save_html(root,task,self.html(),task['formats']['HTML']['urls'][0])
            self.assertTrue(new);self.assertTrue(f.verify_html_entry(root,entry));self.assertFalse('pdf' in entry)
            second,new=f.save_html(root,task,self.html(),task['formats']['HTML']['urls'][0]);self.assertFalse(new)
            (root/entry['original']).write_bytes(b'corrupt');self.assertFalse(f.verify_html_entry(root,entry))
    def test_html_access_denial_is_not_original(self):
        with self.assertRaises(ValueError):f.validate_html(b'<html>Access denied</html>',f.task_from_item(self.item()))
    def test_html_wrong_report_id_rejected(self):
        with self.assertRaises(ValueError):f.validate_html(self.html().replace(b'R49491',b'R99999'),f.task_from_item(self.item()))
    def test_html_manifest_path_traversal_rejected(self):
        self.assertFalse(f.verify_html_entry(Path('/tmp'),dict(original='../etc/passwd',markdown='../etc/passwd',sha256='x')))
    def test_collector_understands_missing_pdf_metadata(self):
        obj={'CRSReport':self.item()}
        class HTTP:
            def json(self,url):return obj
        task=s.official_task(HTTP(),self.item());self.assertEqual(task['version'],'2')
    def test_actual_candidate_saved_and_old_pdf_retained(self):
        body=self.pdf()
        class HTTP:
            def get(self,url):return body,url
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);task=f.task_from_item(self.item())
            entry,new,_=p.save_current(HTTP(),root,dict(task=task,signal=p.signal(self.item())),[])
            self.assertTrue(new);self.assertTrue(entry['current_format_recovery']['official_formats_omitted_pdf'])
            self.assertEqual(entry['pdf_sha256'],s.digest(body))
    def test_changed_signal_gets_live_detail_before_content_verification(self):
        now=datetime.now(timezone.utc);item=self.item()
        class HTTP:
            def json(self,url):return {'CRSReport':item}
        old=dict(signal={**p.signal(item),'updateDate':'2025-01-01'},detail_checked_at=now.isoformat(),task={'fake':True})
        task,resolved=v.live_task(HTTP(),item,old,now)
        self.assertTrue(resolved);self.assertEqual(task['version'],'2')
    def test_midnight_does_not_make_recent_detail_stale(self):
        now=datetime(2026,10,24,0,1,tzinfo=timezone.utc);item=self.item()
        old=dict(signal=p.signal(item),detail_checked_at=(now-timedelta(minutes=3)).isoformat(),task=f.task_from_item(item))
        task,resolved=v.live_task(None,item,old,now);self.assertFalse(resolved)
    def test_expired_detail_cannot_reuse_cache(self):
        now=datetime.now(timezone.utc);item=self.item()
        class HTTP:
            def json(self,url):raise RuntimeError('must fetch live')
        old=dict(signal=p.signal(item),detail_checked_at=(now-timedelta(hours=27)).isoformat(),task=f.task_from_item(item))
        with self.assertRaisesRegex(RuntimeError,'must fetch live'):v.live_task(HTTP(),item,old,now)
    def test_html_only_aggregate_counts_original_without_fake_pdf(self):
        item=self.item();item.pop('currentVersion');task=f.task_from_item(item);raw=self.html()
        class HTTP:
            def get(self,url):return raw,url
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'parts').mkdir()
            end=datetime.now(timezone.utc).date().isoformat()
            record=dict(signal=p.signal(item),task=task,detail_checked_at=end+'T00:00:00+00:00')
            s.write_json(root/'data/official-current.json',{'R49491':record})
            plan=dict(start='2026-10-17',end=end,cache={},required={'R49491':item},official_rows=[item],source_count=1,coverage_note='test')
            s.write_json(root/'plan.json',plan)
            with patch.object(s,'HTTP',return_value=HTTP()),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(p.aggregate(root,root/'out',root/'plan.json',root/'parts'),0)
            receipt=s.read_json(root/'data/official-status.json',{})
            self.assertEqual(receipt['official_html_verified'],1);self.assertEqual(receipt['total_archived_pdf_versions'],0)
            self.assertEqual(receipt['official_current_pending'],0);self.assertIn('[HTML]',(root/'CURRENT.md').read_text())

if __name__=='__main__':unittest.main()
