import copy
import importlib.util
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'.github/ops'))
from freshness import recovery_days, parse_time, last_verification
spec=importlib.util.spec_from_file_location('refresh_health',ROOT/'.github/ops/reliability.py')
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)

class HealthTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,23,20,tzinfo=timezone.utc)
        stamp=(self.now-timedelta(hours=1)).isoformat()
        self.backup={'run_at':stamp,'errors':[],'required_pdf_failures':0,'new_pdf_versions':0}
        self.official={'checked_at':stamp,'result':'verified_for_observed_official_entries','official_current_pending':0,'official_current_verified':67,'official_current_required':67}
        self.audit={'finished_at':stamp,'result':'verified_for_observed_sources','sources':{'official_api':{'ok':True},'mirror_catalog':{'ok':True}},'candidate_report_ids':68,'verified_current_pdf_files':68,'missing':[],'unverified':[],'invalid_files':[]}
        self.runs={k:{'status':'completed','conclusion':'success','updated_at':stamp,'run_started_at':stamp} for k in h.STAGES}
        self.workflows={k:{'state':'active'} for k in h.STAGES}
    def evaluate(self):
        return h.evaluate(self.now,self.backup,self.official,self.audit,self.runs,self.workflows)
    def test_no_new_report_is_not_a_failed_refresh(self):
        self.assertEqual(self.evaluate()['result'],'healthy')
    def test_monitor_commit_cannot_hide_stale_sources(self):
        old=(self.now-timedelta(hours=27)).isoformat()
        self.backup['run_at']=old;self.official['checked_at']=old;self.audit['finished_at']=old
        r=self.evaluate();self.assertEqual(r['result'],'unhealthy');self.assertEqual(r['recovery_stage'],h.STAGES[0])
    def test_latest_failure_overrides_old_green_receipt(self):
        self.runs[h.STAGES[2]]['conclusion']='failure'
        r=self.evaluate();self.assertEqual(r['result'],'unhealthy');self.assertEqual(r['recovery_stage'],h.STAGES[2])
    def test_old_diagnostic_failure_not_used_as_production_failure(self):
        self.runs['metadata-freshness.yml']={'status':'completed','conclusion':'failure'}
        self.assertEqual(self.evaluate()['result'],'healthy')
    def test_pending_official_entries_are_never_healthy(self):
        self.official['official_current_pending']=1
        self.assertEqual(self.evaluate()['result'],'unhealthy')
    def test_source_failure_does_not_become_empty_success(self):
        self.audit['sources']['official_api']['ok']=False
        self.assertEqual(self.evaluate()['result'],'unhealthy')
    def test_byte_mismatch_is_not_success(self):
        self.audit['missing']=[{'id':'R1'}]
        self.assertEqual(self.evaluate()['result'],'unhealthy')
    def test_unverified_is_not_success(self):
        self.audit['unverified']=[{'id':'R1'}]
        self.assertEqual(self.evaluate()['result'],'unhealthy')
    def test_count_mismatch_is_not_success(self):
        self.audit['verified_current_pdf_files']=67
        self.assertEqual(self.evaluate()['result'],'unhealthy')
    def test_in_progress_prevents_duplicate_dispatch(self):
        self.runs[h.STAGES[1]]['status']='in_progress'
        self.backup['errors']=['failed']
        self.assertIsNone(self.evaluate()['recovery_stage'])
    def test_manual_disable_not_automatically_reenabled(self):
        self.workflows[h.STAGES[0]]['state']='disabled_manually';self.backup['errors']=['failed']
        r=self.evaluate();self.assertEqual(r['result'],'unhealthy');self.assertIsNone(r['recovery_stage'])
    def test_missed_scheduled_run_triggers_early_recovery(self):
        self.backup['run_at']=(self.now-timedelta(hours=15)).isoformat()
        self.assertEqual(self.evaluate()['recovery_stage'],h.STAGES[0])
    def test_downstream_chain_not_started_detected(self):
        self.backup['run_at']=(self.now-timedelta(hours=3)).isoformat()
        self.official['checked_at']=(self.now-timedelta(hours=5)).isoformat()
        self.assertEqual(self.evaluate()['recovery_stage'],h.STAGES[1])
    def test_retry_cooldown_survives_new_watchdog_process(self):
        state={'dispatches':[{'stage':h.STAGES[0],'at':(self.now-timedelta(hours=2)).isoformat()}]}
        self.assertFalse(h.retry_allowed(state,h.STAGES[0],self.now))
        self.assertTrue(h.retry_allowed(state,h.STAGES[1],self.now))
    def test_global_retry_cap(self):
        state={'dispatches':[{'stage':'other','at':(self.now-timedelta(hours=8+i)).isoformat()} for i in range(4)]}
        self.assertFalse(h.retry_allowed(state,h.STAGES[0],self.now))
    def test_retry_cap_expires(self):
        state={'dispatches':[{'stage':h.STAGES[0],'at':(self.now-timedelta(hours=25)).isoformat()}]}
        self.assertTrue(h.retry_allowed(state,h.STAGES[0],self.now))
    def test_future_receipt_rejected(self):
        self.audit['finished_at']=(self.now+timedelta(days=1)).isoformat()
        self.assertEqual(self.evaluate()['result'],'unhealthy')
    def test_missing_receipts_unhealthy(self):
        self.audit={};self.assertEqual(self.evaluate()['result'],'unhealthy')
    def test_failed_publish_does_not_advance_watermark(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);h.save(root/'data/last-successful-verification.json',self.audit)
            failed={**self.audit,'result':'incomplete','github_run_id':'123','github_run_attempt':'1'}
            h.save(root/'coverage-evidence/current-receipt.json',failed)
            with patch.dict(os.environ,{'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1'}):
                self.assertEqual(h.publish_receipt(root),1)
            self.assertEqual(h.load(root/'data/last-successful-verification.json',{}),self.audit)
    def test_stale_attempt_receipt_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);h.save(root/'coverage-evidence/current-receipt.json',{**self.audit,'github_run_id':'123','github_run_attempt':'1'})
            with patch.dict(os.environ,{'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'2'}):
                with self.assertRaises(ValueError):h.publish_receipt(root)
    def test_successful_publish_preserves_actual_finished_time(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);r={**self.audit,'github_run_id':'123','github_run_attempt':'2'}
            h.save(root/'coverage-evidence/current-receipt.json',r)
            with patch.dict(os.environ,{'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'2'}):self.assertEqual(h.publish_receipt(root),0)
            self.assertEqual(h.load(root/'data/last-successful-verification.json',{})['finished_at'],self.audit['finished_at'])
    def test_outage_expands_lookback(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);r={**self.audit,'finished_at':(self.now-timedelta(days=15)).isoformat()}
            h.save(root/'data/last-successful-verification.json',r)
            self.assertEqual(recovery_days(root,self.now.date()),16)
    def test_explicit_historical_window_not_changed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);h.save(root/'data/last-successful-verification.json',self.audit)
            self.assertEqual(recovery_days(root,datetime(2025,1,1).date(),7,True),7)
    def test_invalid_watermark_stops_catchup(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);h.save(root/'data/last-successful-verification.json',{'result':'failed'})
            with self.assertRaises(ValueError):recovery_days(root,self.now.date())
    def test_timezone_required(self):
        with self.assertRaises(ValueError):parse_time('2026-10-23T10:00:00')
    def test_old_real_audit_receipt_migrated(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);h.save(root/'data/audits/2026-10-23-independent-current-verification.json',self.audit)
            self.assertEqual(last_verification(root),self.audit)
    def test_optional_historical_backlog_not_claimed_completed(self):
        self.backup['historical_pending_versions']=240
        self.assertEqual(self.evaluate()['result'],'healthy')

if __name__=='__main__':unittest.main()
