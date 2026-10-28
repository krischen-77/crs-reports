"""Regression coverage for the 2026-10-28 failure and noise policy."""
import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / '.github/ops')]
import current_scope as scope
import refresh_receipts as receipts
import alert_policy
import stage_gate


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.raw = b'%PDF-1.4\nfixture for byte-verification test'
        (self.root / 'a.pdf').write_bytes(self.raw)
        (self.root / 'a.md').write_text('text')
        self.old = dict(id='R45635', date='2019-03-26', metadata_source='EveryCRSReport', required_by_recent_update=True, formats={'PDF': {'urls': ['https://www.everycrsreport.com/old.pdf'], 'sha1': 'old-hash'}})
        url = 'https://www.congress.gov/crs_external_products/R/PDF/R45635.5.pdf'
        self.new = dict(id='R45635', date='2026-10-26', metadata_source='Congress.gov API', formats={'PDF': {'urls': [url]}})
        self.saved = dict(id='R45635', date='2026-10-26', pdf_source=url, pdf='a.pdf', markdown='a.md', pdf_sha256=hashlib.sha256(self.raw).hexdigest())
    def result(self, old=None, tasks=None, archives=None):
        return scope.superseded_history(self.root, self.old if old is None else old, [self.new] if tasks is None else tasks, [self.saved] if archives is None else archives, date(2026,9,17))
    def test_obsolete_mirror_requires_live_official_and_saved_bytes(self):
        before = copy.deepcopy(self.old)
        self.assertEqual(self.result()['historical_publication'], '2019-03-26')
        self.assertEqual(self.old, before)
    def test_recent_original_never_demoted(self):
        self.assertIsNone(self.result(old={**self.old, 'date':'2026-09-18'}))
    def test_unknown_date_never_demoted(self):
        self.assertIsNone(self.result(old={**self.old, 'date':''}))
    def test_active_old_current_not_demoted_without_newer_official(self):
        self.assertIsNone(self.result(tasks=[]))
    def test_newer_official_must_be_actually_saved(self):
        self.assertIsNone(self.result(archives=[]))
    def test_corrupt_local_file_blocks_demotion(self):
        (self.root / 'a.pdf').write_bytes(b'broken')
        self.assertIsNone(self.result())
    def test_mirror_not_authoritative_official(self):
        self.assertIsNone(self.result(tasks=[{**self.new, 'metadata_source':'mirror'}]))
    def test_old_official_task_never_demoted(self):
        self.assertIsNone(self.result(old={**self.old, 'metadata_source':'Congress.gov API'}))
    def test_same_publication_never_demoted(self):
        self.assertIsNone(self.result(tasks=[{**self.new, 'date':'2019-03-26'}]))
    def test_wrong_source_bytes_do_not_prove_official_coverage(self):
        self.assertIsNone(self.result(archives=[{**self.saved, 'pdf_source':'https://www.everycrsreport.com/new.pdf'}]))


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.good = {'result':'success_with_warnings','primary_pdf_complete':True,'errors':[], 'required_pdf_failures':0, 'sources':{'congress_api':{'ok':True}},'run_at':'2026-10-27T01:31:28+00:00'}
    def test_failed_attempt_preserves_real_prior_success(self):
        receipts.save(self.root/'data/runs/2026-10-27/1-1.json', self.good)
        bad = {**self.good, 'result':'failed', 'primary_pdf_complete':False, 'errors':['partial'], 'required_pdf_failures':1, 'run_at':'2026-10-28T01:00:00+00:00'}
        receipts.record_collection(self.root, bad)
        self.assertEqual(bad['last_successful_run_at'], self.good['run_at'])
        self.assertFalse((self.root/'data/last-successful-collection.json').exists())
    def test_success_writes_actual_completion_not_commit_time(self):
        receipts.record_collection(self.root,self.good)
        self.assertEqual(self.good['last_successful_run_at'],self.good['finished_at'])
        self.assertEqual(receipts.last_collection(self.root)['finished_at'],self.good['finished_at'])
    def test_empty_source_cannot_advance_success(self):
        r={**self.good,'sources':{}}
        receipts.record_collection(self.root,r)
        self.assertIsNone(r['last_successful_run_at'])


class AlertTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.now=datetime(2026,10,28,0,0,tzinfo=timezone.utc)
        receipts.save(self.root/'data/runs/2026-10-27/1-1.json',{'run_at':'2026-10-27T01:00:00Z','github_run_id':'1','primary_new_pdf_versions':2})
    def prepare(self,errors, state=None,audit=None):
        report={'result':'unhealthy' if errors else 'healthy','errors':errors,'checked_at':self.now.isoformat(),'monitor_result':'completed'}
        state={} if state is None else state
        notification=alert_policy.prepare_notification(self.root,report,state,self.now,audit or {})
        return report,notification,state
    def test_transient_partial_retained_but_not_notified(self):
        report,notice,_=self.prepare(['Collector has unresolved required failures'])
        self.assertEqual(report['result'],'unhealthy');self.assertEqual(report['notification_severity'],'warning');self.assertIsNone(notice)
    def test_stale_verification_is_critical(self):
        report,notice,_=self.prepare(['coverage-audit.yml: no verified refresh within 26 hours'])
        self.assertEqual(report['notification_severity'],'critical');self.assertIsNotNone(notice)
    def test_integrity_loss_always_alerts(self):
        _,notice,_=self.prepare(['incomplete'],audit={'invalid_files':['bad.pdf']})
        self.assertIsNotNone(notice)
    def test_persistent_partial_escalates(self):
        _,notice,_=self.prepare(['incomplete'],state={'first_degraded_at':(self.now-timedelta(hours=27)).isoformat()})
        self.assertIsNotNone(notice)
    def test_optional_history_does_not_count_as_daily_delivery(self):
        receipts.save(self.root/'data/runs/2026-10-27/1-1.json',{'run_at':'2026-10-27T01:00:00Z','primary_new_pdf_versions':0,'new_pdf_versions':10,'historical_new_pdf_versions':10})
        report,notice,_=self.prepare([])
        self.assertEqual(report['daily_delivery']['new_original_versions'],0)
        self.assertIn('zero_delivery_day',notice)
        _,second,_=self.prepare([],state={'zero_delivery_notified_day':notice['zero_delivery_day']})
        self.assertIsNone(second)
    def test_no_zero_update_alarm_before_day_is_closed(self):
        self.assertIsNone(alert_policy.previous_day_delivery(self.root,self.now-timedelta(hours=1)))
    def test_official_delivery_counted_once(self):
        r={'checked_at':'2026-10-27T01:30:00Z','github_run_id':'2','github_run_attempt':'1','new_pdf_versions':1}
        receipts.save(self.root/'data/official-runs/2-1.json',r)
        receipts.save(self.root/'data/official-status.json',r)
        self.assertEqual(alert_policy.previous_day_delivery(self.root,self.now)['new_original_versions'],3)


class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.env=patch.dict(os.environ,{'GITHUB_RUN_ID':'7','GITHUB_RUN_ATTEMPT':'1'});self.env.start();self.addCleanup(self.env.stop)
    def audit(self,**kwargs):
        r={'github_run_id':'7','github_run_attempt':'1','finished_at':'2026-10-28T01:00:00Z','missing':[],'unverified':[],'invalid_files':[],'result':'verified_for_observed_sources'}
        r.update(kwargs);receipts.save(self.root/'data/verification-status.json',r)
        return stage_gate.check('audit',self.root)
    def test_structured_missing_does_not_fail_transport(self):
        self.assertEqual(self.audit(missing=['R1'],result='incomplete')['missing'],['R1'])
    def test_corruption_still_fails(self):
        with self.assertRaises(AssertionError):self.audit(invalid_files=['broken'])
    def test_stale_receipt_still_fails(self):
        with self.assertRaises(AssertionError):self.audit(github_run_id='6')

if __name__=='__main__':unittest.main()
