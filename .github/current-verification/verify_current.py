#!/usr/bin/env python3
"""Read-only verifier for live official update signals and canonical PDF bytes."""
from datetime import datetime,timedelta,timezone
import csv,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'.github/audits'))
import verify_crs as a
s=a.s
sys.path.insert(0,str(ROOT/'.github/ops'))
from freshness import recovery_days

def main():
    now=datetime.now(timezone.utc);end=now.date();start=end-timedelta(days=recovery_days(ROOT,end))
    out=ROOT/'coverage-evidence';out.mkdir(exist_ok=True)
    http=s.HTTP(os.getenv('CONGRESS_API_KEY','').strip())
    receipt=dict(checked_at=now.isoformat(),start=str(start),end=str(end),github_run_id=os.getenv('GITHUB_RUN_ID',''),github_run_attempt=os.getenv('GITHUB_RUN_ATTEMPT',''),sources={},missing=[],unverified=[],invalid_files=[])
    official,mirror=[],{}
    try:
        official=a.official_list(http,start,end,out)
        receipt['sources']['official_api']={'ok':True,'records':len(official)}
    except Exception as exc:receipt['sources']['official_api']={'ok':False,'error':str(exc)}
    try:
        raw,_=http.get(s.MIRROR+'reports.csv');mirror=s.parse_catalog(raw);s.write(out/'mirror.csv',raw)
        if len(mirror)<1000:raise ValueError('Unexpectedly small catalog')
        receipt['sources']['mirror_catalog']={'ok':True,'records':len(mirror)}
    except Exception as exc:receipt['sources']['mirror_catalog']={'ok':False,'error':str(exc)}
    required={r['id']:r for r in official if (not s.day(r.get('publishDate')) or s.day(r['publishDate'])<=end) and (s.within(r.get('publishDate'),start,end) or (str(r.get('status','')).lower()=='active' and s.within(r.get('updateDate'),start,end)))}
    ids=sorted(set(required)|{i for i,r in mirror.items() if s.within(r.get('published'),start,end)})
    manifest=s.read_json(ROOT/'data/archive-manifest.json',[])
    valid,receipt['invalid_files']=a.verify_manifest(ROOT,manifest)
    current=s.read_json(ROOT/'data/official-current.json',{})
    checks=[]
    for n,ident in enumerate(ids,1):
        row=required.get(ident,{})
        check=dict(id=ident,title=row.get('title') or mirror.get(ident,{}).get('title',ident),scope='official current' if row else 'mirror-only recent discovery')
        print(f'Canonical verification {n}/{len(ids)}: {ident}',flush=True)
        try:
            if row:
                record=current.get(ident,{})
                expected={k:str(row.get(k,'')) for k in ('id','publishDate','updateDate')}
                if record.get('signal')!=expected:raise ValueError('Canonical metadata does not match live official update signal')
                if record.get('detail_checked_at','')[:10]!=str(end):raise ValueError('Canonical detail evidence is not from today')
                task=record['task'];url=task['formats']['PDF']['urls'][0]
            else:
                obj=http.json(s.MIRROR+'reports/'+ident+'.json')
                tasks=s.mirror_tasks(obj,start,end)
                if not tasks:raise ValueError('Mirror-only report has no current PDF')
                task=max(tasks,key=lambda t:(t['date'],int(t['version']) if t['version'].isdigit() else -1))
                url=task['formats']['PDF']['urls'][0]
            raw,actual=http.get(url)
            if not raw.lstrip().startswith(b'%PDF-'):raise ValueError('Response is not a PDF')
            with s.fitz.open(stream=raw,filetype='pdf') as d:
                if not len(d) or d.needs_pass:raise ValueError('PDF unreadable')
            sha=s.digest(raw);matches=[v for v in valid.get(ident,[]) if v['pdf_sha256']==sha]
            check.update(official_pdf_url=actual,version=task['version'],sha256=sha,verified=bool(matches),pdf=[v['pdf'] for v in matches],markdown=[v['markdown'] for v in matches])
            if not matches:receipt['missing'].append(check)
        except Exception as exc:
            check.update(verified=False,error=str(exc));receipt['unverified'].append({'id':ident,'error':str(exc)})
        checks.append(check)
    receipt.update(official_current_ids=len(required),candidate_report_ids=len(ids),verified_current_pdf_files=sum(bool(c.get('verified')) for c in checks),total_archive_versions=len(manifest),finished_at=datetime.now(timezone.utc).isoformat(),scope='Live official recent publications and Active updates, plus recent mirror-only IDs; compares canonical official current-format PDF URLs against actual local bytes. Unpublished and not-yet-indexed material is outside this verification.')
    receipt['result']=a.result_state(receipt)
    s.write_json(out/'current-receipt.json',receipt);s.write_json(out/'current-comparisons.json',checks)
    with (out/'current-coverage.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,['id','title','scope','version','official_pdf_url','sha256','verified','pdf','markdown','error'],extrasaction='ignore');w.writeheader();w.writerows(checks)
    text='# Official-current independent verification\n\n```json\n'+json.dumps(receipt,ensure_ascii=False,indent=2)+'\n```\n'
    s.write(out/'SUMMARY.md',text)
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:f.write(text)
    print(json.dumps(receipt,ensure_ascii=False,indent=2))
    return 0 if receipt['result']=='verified_for_observed_sources' else 1

if __name__=='__main__':sys.exit(main())
