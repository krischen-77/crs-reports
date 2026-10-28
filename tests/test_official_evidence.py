import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import official_evidence as e

class OfficialEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026,10,28,4,tzinfo=timezone.utc)
        self.row = dict(id='IN12598',publishDate='2026-01-22T05:00:00Z',updateDate='2026-10-27T21:56:50Z')
        self.item = dict(self.row, currentVersion=6, title='Report title', summary='Exact official API text.\nSecond paragraph.', topics=[{'topic':'A'}])
        self.record = dict(signal=e.signal(self.row), task={'id':'IN12598'}, api_metadata=self.item, detail_checked_at=self.now.isoformat())
    def test_exact_signal_reused(self):
        self.assertEqual(e.choose_cached_record(self.row,[self.record],self.now),self.record)
    def test_changed_signal_not_reused(self):
        row={**self.row,'updateDate':'2026-10-28T03:00:00Z'}
        self.assertFalse(e.choose_cached_record(row,[self.record],self.now))
    def test_expired_evidence_not_reused(self):
        self.assertFalse(e.choose_cached_record(self.row,[self.record],self.now+timedelta(hours=27)))
    def test_future_evidence_not_reused(self):
        self.assertFalse(e.choose_cached_record(self.row,[self.record],self.now-timedelta(seconds=1)))
    def test_wrong_identity_not_reused(self):
        record=copy.deepcopy(self.record);record['task']['id']='IN99999'
        self.assertFalse(e.choose_cached_record(self.row,[record],self.now))
    def test_freshest_matching_record_wins(self):
        older={**self.record,'detail_checked_at':(self.now-timedelta(hours=1)).isoformat()}
        self.assertEqual(e.choose_cached_record(self.row,[older,self.record],self.now)['detail_checked_at'],self.now.isoformat())
    def test_selection_is_not_alias(self):
        selected=e.choose_cached_record(self.row,[self.record],self.now);selected['task']['id']='OTHER'
        self.assertEqual(self.record['task']['id'],'IN12598')
    def test_nonmatching_newer_cache_does_not_hide_match(self):
        other=copy.deepcopy(self.record);other['signal']['updateDate']='other'
        self.assertEqual(e.choose_cached_record(self.row,[other,self.record],self.now),self.record)
    def test_timestamp_must_have_timezone(self):
        with self.assertRaises(ValueError):e.stamp('2026-10-28T04:00:00')
    def test_api_summary_stored_without_clearing_original_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);e.save(root/'data/official-status.json',{'official_current_pending':1,'result':'incomplete'})
            before=(root/'data/official-status.json').read_bytes()
            entry=e.archive_api_summary(root,self.record,self.now)
            self.assertIn(self.item['summary'],(root/entry['markdown']).read_text())
            self.assertIn('NOT the PDF/HTML original',(root/entry['markdown']).read_text())
            self.assertFalse(entry['original_verified']);self.assertFalse(entry['counts_as_original'])
            self.assertEqual((root/'data/official-status.json').read_bytes(),before)
            self.assertFalse((root/'data/last-successful-verification.json').exists())
    def test_verification_calls_live_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);e.archive_api_summary(root,self.record,self.now)
            fetch=Mock(return_value={'CRSReport':self.item})
            proof=e.verify_api_summary(root,'IN12598',fetch,self.now)
            self.assertTrue(proof['verified']);self.assertFalse(proof['original_verified'])
            fetch.assert_called_once_with(e.API+'IN12598?format=json')
    def test_changed_text_not_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);e.archive_api_summary(root,self.record,self.now)
            proof=e.verify_api_summary(root,'IN12598',lambda _: {'CRSReport':{**self.item,'summary':'Changed'}},self.now)
            self.assertFalse(proof['verified'])
    def test_changed_version_not_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);e.archive_api_summary(root,self.record,self.now)
            proof=e.verify_api_summary(root,'IN12598',lambda _: {'CRSReport':{**self.item,'currentVersion':7}},self.now)
            self.assertFalse(proof['verified'])
    def test_wrong_live_id_not_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);e.archive_api_summary(root,self.record,self.now)
            proof=e.verify_api_summary(root,'IN12598',lambda _: {'CRSReport':{**self.item,'id':'IN99999'}},self.now)
            self.assertFalse(proof['verified'])
    def test_raw_record_corruption_not_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);entry=e.archive_api_summary(root,self.record,self.now)
            (root/entry['record']).write_text('{}');fetch=Mock()
            self.assertFalse(e.verify_api_summary(root,'IN12598',fetch,self.now)['verified']);fetch.assert_not_called()
    def test_markdown_corruption_not_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);entry=e.archive_api_summary(root,self.record,self.now)
            (root/entry['markdown']).write_text('corrupt');fetch=Mock()
            self.assertFalse(e.verify_api_summary(root,'IN12598',fetch,self.now)['verified']);fetch.assert_not_called()
    def test_rate_limit_not_swallowed_as_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);e.archive_api_summary(root,self.record,self.now)
            proof=e.verify_api_summary(root,'IN12598',Mock(side_effect=RuntimeError('quota exhausted')),self.now)
            self.assertFalse(proof['verified']);self.assertIn('quota',proof['error'])
    def test_no_stored_snapshot_no_network_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            fetch=Mock();self.assertIsNone(e.verify_api_summary(Path(tmp),'IN12598',fetch,self.now));fetch.assert_not_called()
    def test_topic_order_and_index_timestamp_not_content(self):
        changed={**self.item,'topics':[{'topic':'B'},{'topic':'A'}],'updateDate':'2026-10-28T01:00:00Z'}
        self.assertEqual(e.content_digest(self.item),e.content_digest(changed))
    def test_stale_record_not_archived_as_current_supplement(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):e.archive_api_summary(Path(tmp),self.record,self.now+timedelta(hours=27))
    def test_identity_mismatch_not_archived(self):
        with tempfile.TemporaryDirectory() as tmp:
            record=copy.deepcopy(self.record);record['api_metadata']['id']='IN99999'
            with self.assertRaises(ValueError):e.archive_api_summary(Path(tmp),record,self.now)
    def test_empty_summary_rejected(self):
        with self.assertRaises(ValueError):e.content_digest({**self.item,'summary':''})
    def test_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):e.safe_path(Path(tmp),'../outside')
    def test_multiple_retries_do_not_duplicate_same_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);e.archive_api_summary(root,self.record,self.now);e.archive_api_summary(root,self.record,self.now)
            self.assertEqual(len(e.load(root/e.MANIFEST,[])),1)


class EvidenceIntegrationTests(unittest.TestCase):
    def test_original_failure_remains_pending_after_supplement_saved(self):
        import contextlib
        import io
        from unittest.mock import patch
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
        import official_pipeline as p
        now=datetime.now(timezone.utc)
        row=dict(id='IN12598',title='Example',publishDate='2026-01-22T05:00:00Z',updateDate=now.isoformat(),status='Active')
        item=dict(row,currentVersion=6,summary='Official API summary',formats=[{'format':'HTML','url':'https://www.congress.gov/crs_external_products/IN/HTML/IN12598.html'}])
        record=dict(signal=e.signal(row),task=p.task_from_item(item),api_metadata=item,detail_checked_at=(now-timedelta(seconds=1)).isoformat())
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);parts=root/'parts';parts.mkdir()
            plan=dict(start='2026-10-21',end='2026-10-28',cache={row['id']:record},required={row['id']:row},official_rows=[row],source_count=1,coverage_note='test')
            e.save(root/'plan.json',plan)
            previous={'checked_at':'2026-10-27T01:37:31+00:00','result':'verified_for_observed_official_entries'}
            e.save(root/'data/last-successful-official.json',previous)
            with patch.object(p,'save_current',side_effect=RuntimeError('HTTP 403')), contextlib.redirect_stdout(io.StringIO()):
                result=p.aggregate(root,root/'out',root/'plan.json',parts)
            self.assertEqual(result,1)
            receipt=e.load(root/'data/official-status.json',{})
            self.assertEqual(receipt['official_current_pending'],1)
            self.assertEqual(receipt['official_current_verified'],0)
            self.assertEqual(receipt['supplementary_api_summaries'],1)
            self.assertEqual(e.load(root/'data/last-successful-official.json',{}),previous)
            self.assertIn('UNVERIFIED',(root/'CURRENT.md').read_text())
            self.assertIn('not original',(root/'CURRENT.md').read_text())
            proof=e.verify_api_summary(root,'IN12598',lambda _: {'CRSReport':item})
            self.assertTrue(proof['verified']);self.assertFalse(proof['counts_as_original'])

    def test_audit_metadata_is_reused_only_for_matching_live_signal(self):
        import importlib.util
        base=Path(__file__).resolve().parents[1]
        spec=importlib.util.spec_from_file_location('evidence_audit_test',base/'.github/current-verification/verify_current.py')
        verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
        now=datetime.now(timezone.utc)
        row=dict(id='IN12598',publishDate='2026-01-22T05:00:00Z',updateDate='2026-10-28T01:00:00Z')
        item=dict(row,title='Example',currentVersion=6,formats=[{'format':'HTML','url':'https://www.congress.gov/crs_external_products/IN/HTML/IN12598.html'}])
        record=dict(signal=e.signal(row),task=verifier.formats.task_from_item(item),api_metadata=item,detail_checked_at=now.isoformat())
        http=Mock();http.json.return_value={'CRSReport':item}
        cached,refreshed=verifier.live_record(http,row,[record],now)
        self.assertFalse(refreshed);http.json.assert_not_called()
        changed={**row,'updateDate':'2026-10-28T02:00:00Z'}
        cached,refreshed=verifier.live_record(http,changed,[record],now)
        self.assertTrue(refreshed);http.json.assert_called_once()
        self.assertEqual(cached['signal'],e.signal(changed))

if __name__=='__main__':unittest.main()
