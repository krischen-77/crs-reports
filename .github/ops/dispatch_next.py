#!/usr/bin/env python3
"""Explicit, bounded workflow handoff; no recursive workflow_run chain."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from reliability import GitHubAPI

STAGES = {'backup': 'crs-backup.yml', 'reconcile': 'official-reconcile.yml', 'audit': 'coverage-audit.yml', 'watchdog': 'crs-watchdog.yml'}


def dispatch(stage, api=None):
    api = api or GitHubAPI()
    workflow = STAGES[stage]
    info = api.call('/actions/workflows/'+workflow)
    if info.get('state') != 'active':
        raise RuntimeError('Required workflow is disabled; owner setting was not overridden: '+workflow)
    runs = api.call('/actions/workflows/'+workflow+'/runs?branch=main&per_page=10')['workflow_runs']
    active = [r for r in runs if r.get('status') != 'completed']
    if active:
        print(json.dumps({'handoff': 'already_running', 'workflow': workflow, 'run_id': active[0]['id']}))
        return
    api.call('/actions/workflows/'+workflow+'/dispatches', 'POST', {'ref': 'main'})
    print(json.dumps({'handoff': 'dispatched', 'workflow': workflow, 'completion_verified': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=STAGES)
    dispatch(parser.parse_args().stage)
