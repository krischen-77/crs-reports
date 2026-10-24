import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'.github/ops'))
import reliability as h
import dispatch_next as d

class QuietMonitorTests(unittest.TestCase):
    def test_successfully_reported_incident_is_not_a_monitor_execution_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);api=Mock();api.runs.return_value=[];api.call.return_value={'state':'active'}
            result=dict(result='unhealthy',errors=['official original missing'],notices=[],recovery_stage=None,source_times={},active_stages=[])
            with patch.object(h,'GitHubAPI',return_value=api),patch.object(h,'evaluate',return_value=result),patch.object(h,'issue_update') as notify,patch('builtins.print'):
                self.assertEqual(h.watchdog(root,False,True),0);notify.assert_called_once()
            receipt=h.load(root/'data/health.json',{})
            self.assertEqual(receipt['result'],'unhealthy');self.assertEqual(receipt['monitor_result'],'completed')
    def test_monitor_transport_failure_still_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);api=Mock();api.runs.side_effect=RuntimeError('GitHub unavailable')
            with patch.object(h,'GitHubAPI',return_value=api),patch('builtins.print'):
                self.assertEqual(h.watchdog(root,False,False),1)
            self.assertEqual(h.load(root/'data/health.json',{})['monitor_result'],'failed')
    def test_html_and_pdf_counts_have_explicit_total(self):
        receipt=dict(result='verified_for_observed_sources',sources={'official_api':{'ok':True},'mirror_catalog':{'ok':True}},candidate_report_ids=2,verified_current_pdf_files=1,verified_current_html_files=1,verified_current_original_files=2)
        self.assertTrue(h.valid_audit(receipt))
        receipt['verified_current_original_files']=1;self.assertFalse(h.valid_audit(receipt))
    def test_failure_timestamp_not_counted_as_success(self):
        now=datetime.now(timezone.utc);old=(now-timedelta(hours=30)).isoformat();fresh=now.isoformat()
        backup={'run_at':fresh};official={'checked_at':fresh,'result':'incomplete','official_current_pending':1,'last_successful_checked_at':old}
        audit={'result':'failed','finished_at':fresh,'last_successful_finished_at':old}
        runs={x:{'status':'completed','conclusion':'success','updated_at':fresh} for x in h.STAGES}
        r=h.evaluate(now,backup,official,audit,runs,{x:{'state':'active'} for x in h.STAGES})
        self.assertEqual(r['source_times'][h.STAGES[1]],old);self.assertEqual(r['source_times'][h.STAGES[2]],old)
        self.assertEqual(r['result'],'unhealthy')
    def test_watchdog_reads_latest_failure_not_only_old_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);h.save(root/'data/verification-status.json',{'result':'failed','missing':[{'id':'R1'}]})
            h.save(root/'data/last-successful-verification.json',{'result':'verified_for_observed_sources','finished_at':'2026-10-23T13:45:29+00:00'})
            api=Mock();api.runs.return_value=[]
            r=dict(result='unhealthy',errors=[],notices=[],recovery_stage=None,source_times={},active_stages=[])
            with patch.object(h,'GitHubAPI',return_value=api),patch.object(h,'evaluate',return_value=r) as evaluate,patch('builtins.print'):
                h.watchdog(root,False,False)
            self.assertEqual(evaluate.call_args.args[3]['missing'],[{'id':'R1'}])
    def test_dispatch_skips_active_target(self):
        api=Mock();api.call.side_effect=[{'state':'active'},{'workflow_runs':[{'id':42,'status':'in_progress'}]}]
        with patch('builtins.print'):d.dispatch('audit',api)
        self.assertEqual(api.call.call_count,2)
    def test_dispatch_honors_disabled_workflow(self):
        api=Mock();api.call.return_value={'state':'disabled_manually'}
        with self.assertRaises(RuntimeError):d.dispatch('audit',api)
        self.assertEqual(api.call.call_count,1)
    def test_dispatch_uses_supported_explicit_event(self):
        api=Mock();api.call.side_effect=[{'state':'active'},{'workflow_runs':[]},None]
        with patch('builtins.print'):d.dispatch('audit',api)
        self.assertEqual(api.call.call_args.args,('/actions/workflows/coverage-audit.yml/dispatches','POST',{'ref':'main'}))
    def test_production_callbacks_do_not_use_recursive_workflow_run(self):
        for path in ['official-reconcile.yml','coverage-audit.yml','crs-watchdog.yml']:
            text=(ROOT/'.github/workflows'/path).read_text();self.assertNotIn('  workflow_run:',text)
        self.assertIn('dispatch_next.py reconcile',(ROOT/'.github/workflows/crs-backup.yml').read_text())
        self.assertIn("needs.archive.result == 'success'",(ROOT/'.github/workflows/official-reconcile.yml').read_text())
    def test_unchanged_incident_does_not_repeatedly_edit_issue(self):
        state={};now=datetime.now(timezone.utc).isoformat();api=Mock();api.repo='example/repo'
        issue={'number':1,'body':h.MARKER,'state':'open','html_url':'https://github.com/example/repo/issues/1'}
        api.call.side_effect=[[],issue]
        report={'result':'unhealthy','errors':['one incident'],'checked_at':now}
        h.issue_update(api,report,state)
        api.reset_mock();api.call.return_value=issue;api.call.side_effect=None
        h.issue_update(api,{**report,'checked_at':now},state)
        self.assertEqual(api.call.call_count,1)
        self.assertEqual(api.call.call_args.args,('/issues/1',))

if __name__=='__main__':unittest.main()
