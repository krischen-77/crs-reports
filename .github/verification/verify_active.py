#!/usr/bin/env python3
"""Independent coverage check: recent publications UNION active update signals."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import csv
import hashlib
import json
import os
import subprocess
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.github/audits'))
import verify_crs as a
s = a.s


def main():
    out = ROOT / 'coverage-evidence'
    out.mkdir(exist_ok=True)
    now = datetime.now(timezone.utc)
    end, start = now.date(), now.date() - timedelta(days=7)
    receipt = dict(checked_at=now.isoformat(), start=str(start), end=str(end),
        repository_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        github_run_id=os.getenv('GITHUB_RUN_ID',''), sources={},missing=[],unverified=[],invalid_files=[])
    http = s.HTTP(os.getenv('CONGRESS_API_KEY','').strip())
    rows, mirror = [], {}
    try:
        rows = a.official_list(http,start,end,out)
        receipt['sources']['official_api'] = dict(ok=True,records=len(rows))
    except Exception as exc:
        receipt['sources']['official_api'] = dict(ok=False,error=str(exc))
    s.write_json(out/'official-list.json',rows)
    try:
        body,_ = http.get(s.MIRROR+'reports.csv')
        s.write(out/'mirror.csv',body)
        mirror = s.parse_catalog(body)
        if len(mirror)<1000: raise ValueError('Unexpectedly small mirror catalog')
        receipt['sources']['mirror_catalog'] = dict(ok=True,records=len(mirror))
    except Exception as exc:
        receipt['sources']['mirror_catalog'] = dict(ok=False,error=str(exc))
    # Deliberately independent of sync_crs.publication_candidates. Do not copy
    # the collector's date-only exclusion into its verifier.
    recent = {r['id']:r for r in rows if a.in_window(r.get('publishDate'),start,end)}
    active = {r['id']:r for r in rows if str(r.get('status','')).lower()=='active'
              and a.in_window(r.get('updateDate'),start,end)
              and (not s.day(r.get('publishDate')) or s.day(r['publishDate'])<=end)}
    observed = {**recent,**active}
    ids = sorted(set(observed)|{i for i,r in mirror.items() if a.in_window(r.get('published'),start,end)})
    manifest = json.loads((ROOT/'data/archive-manifest.json').read_text())
    valid,receipt['invalid_files'] = a.verify_manifest(ROOT,manifest)
    checks=[]
    for n,ident in enumerate(ids,1):
        print(f'Active coverage [{n}/{len(ids)}] {ident}',flush=True)
        row=observed.get(ident,{})
        check=dict(id=ident,title=row.get('title') or mirror.get(ident,{}).get('title',ident),
            api_publication_date=row.get('publishDate','')[:10],api_update_date=row.get('updateDate',''),
            active_update=ident in active,files=[])
        local=valid.get(ident,[])
        tasks=[]
        try:
            obj=http.json(s.MIRROR+'reports/'+ident+'.json')
            if s.report_id(obj.get('id') or obj.get('number'))!=ident: raise ValueError('Metadata ID mismatch')
            s.write_json(out/'metadata'/f'{ident}.json',obj)
            tasks=s.mirror_tasks(obj,start,end,include_latest=ident in observed)
        except Exception as exc:
            check['mirror_metadata_error']=str(exc)
        if not tasks and row:
            try:
                tasks=[s.official_task(http,{**row,'required_by_recent_update':ident in active})]
            except Exception as exc:
                receipt['unverified'].append(dict(id=ident,error=str(exc),reason='No current PDF specification'))
        if not tasks:
            receipt['unverified'].append(dict(id=ident,reason='No PDF version selected'))
        seen=set()
        for task in tasks:
            spec=task['formats']['PDF']
            urls=[u for u in spec['urls'] if urlsplit(u).hostname in ('www.congress.gov','congress.gov','crsreports.congress.gov')]
            if not urls and row:
                try:
                    official=s.official_task(http,row)
                    if official['date']!=task['date']: raise ValueError('Official and mirror publication dates differ')
                    urls=official['formats']['PDF']['urls']
                except Exception as exc:
                    receipt['unverified'].append(dict(id=ident,reason='Cannot resolve independently public official PDF',error=str(exc)))
            if not urls:
                receipt['unverified'].append(dict(id=ident,reason='No official PDF URL to verify'))
                continue
            url=urls[0]
            if url in seen: continue
            seen.add(url)
            record=dict(date=task['date'],version=task['version'],official_pdf_url=url)
            try:
                body,actual=http.get(url)
                if not body.lstrip().startswith(b'%PDF-'): raise ValueError('Response is not a PDF')
                with s.fitz.open(stream=body,filetype='pdf') as doc:
                    if not len(doc) or doc.needs_pass: raise ValueError('Official PDF is unreadable')
                sha=hashlib.sha256(body).hexdigest()
                match=[v for v in local if v['pdf_sha256']==sha]
                record.update(official_pdf_url=actual,sha256=sha,exact_pdf_archived=bool(match),
                    local_pdf_paths=[v['pdf'] for v in match],local_markdown_paths=[v['markdown'] for v in match])
                if not match: receipt['missing'].append(dict(id=ident,reason='Current official PDF bytes not archived',**record))
            except Exception as exc:
                record['error']=str(exc)
                receipt['unverified'].append(dict(id=ident,url=url,error=str(exc)))
            check['files'].append(record)
        checks.append(check)
    receipt.update(official_recent_publication_ids=len(recent),official_active_update_ids=len(active),
        active_updates_with_older_publication=sum(not a.in_window(r.get('publishDate'),start,end) for r in active.values()),
        candidate_report_ids=len(ids),official_pdf_files_checked=sum(len(c['files']) for c in checks),
        official_pdf_exact_matches=sum(bool(f.get('exact_pdf_archived')) for c in checks for f in c['files']),
        total_archive_versions=len(manifest),api_requests=http.api_calls,
        finished_at=datetime.now(timezone.utc).isoformat(),
        scope='Observed current official API publications and all active update signals in the last seven days, plus current mirror revisions. Official PDFs are downloaded and compared with actual local hashes; cover dates are not rewritten. Unpublished material and frontend changes not exposed by these sources remain outside verifiable scope.')
    receipt['result']=a.result_state(receipt)
    s.write_json(out/'active-update-comparisons.json',checks)
    s.write_json(out/'active-update-receipt.json',receipt)
    with (out/'active-update-coverage.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f);writer.writerow(['report_id','title','API_publish_date','API_update_date','PDF_cover_date','PDF_version','official_PDF_URL','SHA256','exact_archived','local_PDF','local_Markdown'])
        for c in checks:
            for v in c['files']:
                writer.writerow([c['id'],c['title'],c['api_publication_date'],c['api_update_date'],v['date'],v['version'],v['official_pdf_url'],v.get('sha256',''),v.get('exact_pdf_archived',False),';'.join(v.get('local_pdf_paths',[])),';'.join(v.get('local_markdown_paths',[]))])
    text='# CRS publication and active-update coverage\n\n```json\n'+json.dumps(receipt,ensure_ascii=False,indent=2)+'\n```\n'
    s.write(out/'SUMMARY.md',text)
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:f.write(text)
    print(json.dumps(receipt,ensure_ascii=False,indent=2))
    return 0 if receipt['result']=='verified_for_observed_sources' else 1

if __name__=='__main__':sys.exit(main())
