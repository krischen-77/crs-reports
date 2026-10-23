#!/usr/bin/env python3
"""Resolve official-current CRS files independently of lagging mirror revisions.

Each API worker obeys provider quota headers. Partial results are retained;
unresolved entries are never silently dropped or claimed complete.
"""
from __future__ import annotations
import argparse
import copy
import csv
import json
import os
from pathlib import Path
import re
import sys
from datetime import date, datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import sync_crs as s


def signal(row):
    return {k:str(row.get(k,'')) for k in ('id','publishDate','updateDate')}


def task_from_item(item):
    ident=s.report_id(item['id'])
    fmt=next(f for f in item['formats'] if f['format'].upper()=='PDF')
    url=s.safe_url(fmt.get('url') or fmt['URL'])
    return dict(id=ident,title=item['title'],date=item['publishDate'][:10],version=s.source_version(url),
        api_version=str(item.get('currentVersion',item.get('version',''))),formats={'PDF':{'urls':[url],'sha1':''}},
        metadata_source='Congress.gov API',source_record=ident,required_by_recent_update=True,
        observed_update_date=item.get('updateDate',''))


def is_required(row,start,end):
    published=s.day(row.get('publishDate'))
    if published and published>end:return False
    return s.within(row.get('publishDate'),start,end) or (
        str(row.get('status','')).lower()=='active' and s.within(row.get('updateDate'),start,end))


def plan(root,out):
    out.mkdir(parents=True,exist_ok=True)
    now=datetime.now(timezone.utc);end=now.date();start=end-timedelta(days=7)
    http=s.HTTP(os.getenv('CONGRESS_API_KEY','').strip())
    rows,count=s.api_scan(http,start,end)
    if len(rows)!=count:raise ValueError('Official list incomplete')
    required={r['id']:r for r in rows if is_required(r,start,end)}
    for row in s.read_json(root/'data/official-pending.json',[]):required.setdefault(row['id'],row)
    cache=s.read_json(root/'data/official-current.json',{})
    for ident,value in s.read_json(root/'.github/repairs/official-seed.json',{}).items():cache.setdefault(ident,value)
    unresolved=[]
    for ident,row in required.items():
        item=cache.get(ident,{})
        fresh=str(item.get('detail_checked_at',''))[:10]==str(end)
        if item.get('signal')!=signal(row) or not item.get('task') or not fresh:unresolved.append(row)
    unresolved.sort(key=lambda r:(r.get('updateDate',''),r['id']),reverse=True)
    chunks=[unresolved[i:i+8] for i in range(0,len(unresolved),8)] or [[]]
    value=dict(created_at=now.isoformat(),start=str(start),end=str(end),official_rows=rows,
        required=required,cache=cache,chunks=chunks,source_count=count,
        coverage_note='Current public official API entries with recent publications or Active update signals; mirror-only discoveries remain separately archived.')
    s.write_json(out/'plan.json',value)
    if os.getenv('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('matrix='+json.dumps({'chunk':list(range(len(chunks)))})+'\n')
    print(json.dumps(dict(required=len(required),cached=len(required)-len(unresolved),api_queries_required=len(unresolved),batches=len(chunks)),indent=2))
    return 0


def resolve(root,out,plan_path,chunk):
    out.mkdir(parents=True,exist_ok=True)
    p=s.read_json(plan_path,None);http=s.HTTP(os.getenv('CONGRESS_API_KEY','').strip())
    resolved,errors={},[]
    for row in p['chunks'][chunk]:
        ident=row['id']
        try:
            obj=http.json(s.API+'/'+s.report_id(ident)+'?format=json')
            item=next(v for k,v in obj.items() if k.lower()=='crsreport')
            if s.report_id(item['id'])!=ident:raise ValueError('Official report ID mismatch')
            if item.get('updateDate','')<row.get('updateDate',''):raise ValueError('Official item is older than list signal')
            resolved[ident]=dict(signal=signal(row),task=task_from_item(item),
                detail_checked_at=datetime.now(timezone.utc).isoformat(),api_metadata=item)
            print('Resolved official current PDF:',ident,flush=True)
        except Exception as exc:
            errors.append(dict(id=ident,error=str(exc)));print('Unresolved:',ident,str(exc),flush=True)
    s.write_json(out/f'resolved-{chunk}.json',dict(resolved=resolved,errors=errors,api_calls=http.api_calls,
        quota_remaining=http.api_remaining,chunk=chunk))
    # Transport partial evidence; aggregate will fail if any current entry is unresolved.
    return 0


def cover_date(body,fallback):
    with s.fitz.open(stream=body,filetype='pdf') as doc:
        if not len(doc) or doc.needs_pass:raise ValueError('Official PDF is unreadable')
        text=doc[0].get_text()[:4000]
    month='January|February|March|April|May|June|July|August|September|October|November|December'
    found=re.search(rf'(?im)^\s*(?:Updated\s+)?((?:{month})\s+\d{{1,2}},\s+\d{{4}})\s*$',text)
    if found:
        d=datetime.strptime(re.sub(r'\s+',' ',found[1]),'%B %d, %Y').date()
        if d<=datetime.now(timezone.utc).date():return str(d)
    return fallback


def verify_local(root,entry):
    if not entry:return False
    path=(root/entry['pdf']).resolve()
    if not path.is_relative_to(root.resolve()):return False
    return path.is_file() and s.digest(path.read_bytes())==entry['pdf_sha256'] and (root/entry['markdown']).is_file()


def save_current(http,root,record,archives):
    task=copy.deepcopy(record['task']);expected=record.get('pdf_sha256')
    if task['id']!=record.get('signal',{}).get('id'):raise ValueError('Cached official task identity mismatch')
    old=next((v for v in archives if v['id']==task['id'] and expected and v['pdf_sha256']==expected),None)
    if verify_local(root,old):return old,False,[]
    url=task['formats']['PDF']['urls'][0]
    body,actual=http.get(url)
    if not body.lstrip().startswith(b'%PDF-'):raise ValueError('Official response is not a PDF')
    sha=s.digest(body)
    old=next((v for v in archives if v['id']==task['id'] and v['pdf_sha256']==sha),None)
    if verify_local(root,old):return old,False,[]
    task['api_publication_date']=task['date'];task['date']=cover_date(body,task['date'])
    class Buffered:
        def get(self,candidate):
            if candidate==url:return body,actual
            return http.get(candidate)
        def json(self,candidate):return http.json(candidate)
    entry,is_new,notices=s.archive_task(Buffered(),root,task,archives)
    entry['api_publication_date']=task['api_publication_date']
    return entry,is_new,notices


def aggregate(root,out,plan_path,parts):
    out.mkdir(parents=True,exist_ok=True)
    p=s.read_json(plan_path,None);http=s.HTTP(os.getenv('CONGRESS_API_KEY','').strip())
    cache=s.read_json(root/'data/official-current.json',{})
    for ident,item in p['cache'].items():cache.setdefault(ident,item)
    failures=[]
    for path in parts.glob('**/resolved-*.json'):
        part=s.read_json(path,{});failures.extend(part.get('errors',[]))
        for ident,item in part.get('resolved',{}).items():
            current=cache.get(ident,{})
            if current.get('signal',{}).get('updateDate','')<=item['signal']['updateDate']:cache[ident]=item
    archives=s.read_json(root/'data/archive-manifest.json',[]);before={(v['id'],v['pdf_sha256']) for v in archives}
    catalog=s.read_json(root/'data/catalog.json',{})
    for row in p['official_rows']:catalog.setdefault(row['id'],{'id':row['id']})['api']=row
    checks=[];pending=[]
    for ident,row in sorted(p['required'].items()):
        record=cache.get(ident,{})
        check=dict(id=ident,title=row.get('title',''),api_publication=row.get('publishDate','')[:10],api_update=row.get('updateDate',''))
        try:
            if (record.get('signal')!=signal(row) or not record.get('task') or str(record.get('detail_checked_at',''))[:10]!=p['end']):raise ValueError('Current official details not verified for this date; retry retained')
            entry,is_new,notices=save_current(http,root,record,archives)
            if not verify_local(root,entry):raise ValueError('Saved PDF failed actual hash verification')
            archives=[v for v in archives if not (v['id']==ident and v['pdf_sha256']==entry['pdf_sha256'])]+[entry]
            record.update(pdf_sha256=entry['pdf_sha256'],pdf=entry['pdf'],markdown=entry['markdown'],
                original_cover_date=entry['date'],pdf_verified_at=datetime.now(timezone.utc).isoformat())
            cache[ident]=record
            check.update(verified=True,official_pdf_url=record['task']['formats']['PDF']['urls'][0],
                official_pdf_revision=record['task']['version'],pdf_sha256=entry['pdf_sha256'],
                pdf=entry['pdf'],markdown=entry['markdown'],cover_date=entry['date'],new_pdf=is_new)
        except Exception as exc:check.update(verified=False,error=str(exc));pending.append(row)
        checks.append(check);print('Official-current',ident,'verified' if check['verified'] else check['error'],flush=True)
    for item in archives:
        if not verify_local(root,item):raise ValueError('Archive integrity failure: '+item['pdf'])
    archives.sort(key=lambda v:(v['id'],v['date'],v['pdf_sha256']))
    new=[v for v in archives if (v['id'],v['pdf_sha256']) not in before]
    now=datetime.now(timezone.utc).isoformat()
    receipt=dict(checked_at=now,window_start=p['start'],window_end=p['end'],
        official_list_records=p['source_count'],official_current_required=len(checks),
        official_current_verified=sum(c['verified'] for c in checks),official_current_pending=len(pending),
        new_pdf_versions=len(new),new_pdf_records=[{k:v[k] for k in ('id','version','date','pdf','markdown','pdf_sha256')} for v in new],
        total_archived_pdf_versions=len(archives),github_run_id=os.getenv('GITHUB_RUN_ID',''),
        github_run_attempt=os.getenv('GITHUB_RUN_ATTEMPT',''),resolution_errors=failures,
        result='verified_for_observed_official_entries' if not pending else 'incomplete',scope=p['coverage_note'])
    s.write_json(root/'data/official-current.json',cache);s.write_json(root/'data/official-pending.json',pending)
    s.write_json(root/'data/official-status.json',receipt);s.write_json(root/'data/archive-manifest.json',archives)
    s.write_json(root/'data/catalog.json',catalog)
    s.write_json(root/f'data/audits/{p["end"]}-official-current.json',receipt)
    s.write_json(root/'data/audits/latest-official-current-comparisons.json',checks)
    s.export_indexes(root,catalog,archives,date.fromisoformat(p['start']),date.fromisoformat(p['end']))
    lines=['# Official current CRS files','',f"Checked: {now}. Official current entries verified: **{receipt['official_current_verified']}/{len(checks)}**.",
        '', 'The original cover date is distinct from the API update date. Only verified rows link to a current official PDF.', '',
        '| API update | Cover date | Report | Title | Current PDF | Full text |','|---|---|---|---|---|---|']
    for c in sorted(checks,key=lambda c:(c['api_update'],c['id']),reverse=True):
        title=c['title'].replace('|','\\|')
        links=f"[PDF]({c['pdf']}) | [Markdown]({c['markdown']})" if c['verified'] else 'UNVERIFIED | Retry pending'
        lines.append(f"| {c['api_update'][:10]} | {c.get('cover_date',c['api_publication'])} | {c['id']} v{c.get('official_pdf_revision','?')} | {title} | {links} |")
    s.write(root/'CURRENT.md','\n'.join(lines)+'\n')
    latest=root/'LATEST.md'
    s.write(latest,f"**Official-current verification: {receipt['official_current_verified']}/{len(checks)}. [View current official files](CURRENT.md).**\n\n"+latest.read_text())
    with (root/'data/audits/latest-official-current.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,['id','title','api_publication','api_update','cover_date','official_pdf_revision','verified','official_pdf_url','pdf_sha256','pdf','markdown','error'],extrasaction='ignore')
        writer.writeheader();writer.writerows(checks)
    status=s.read_json(root/'data/status.json',{})
    status.update(official_current_required=len(checks),official_current_verified=receipt['official_current_verified'],
        official_current_pending=len(pending),official_reconciled_at=now,official_new_pdf_versions=len(new),
        total_archived_pdf_versions=len(archives),total_html_snapshots=sum(bool(v.get('html')) for v in archives),
        total_pdf_bytes=sum((root/v['pdf']).stat().st_size for v in archives))
    if pending:status.update(result='failed',primary_pdf_complete=False)
    s.write_json(root/'data/status.json',status)
    s.write_json(out/'receipt.json',receipt);s.write_json(out/'checks.json',checks)
    print(json.dumps(receipt,ensure_ascii=False,indent=2))
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:f.write('```json\n'+json.dumps(receipt,ensure_ascii=False,indent=2)+'\n```\n')
    return 1 if pending else 0


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['plan','resolve','aggregate'])
    parser.add_argument('--root',default=str(ROOT));parser.add_argument('--out',default='official-evidence')
    parser.add_argument('--plan',default='official-plan/plan.json');parser.add_argument('--parts',default='official-parts')
    parser.add_argument('--chunk',type=int,default=0)
    args=parser.parse_args();root=Path(args.root).resolve();out=Path(args.out)
    if args.command=='plan':result=plan(root,out)
    elif args.command=='resolve':result=resolve(root,out,Path(args.plan),args.chunk)
    else:result=aggregate(root,out,Path(args.plan),Path(args.parts))
    sys.exit(result)
