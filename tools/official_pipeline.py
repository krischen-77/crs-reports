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
import crs_formats as formats
import official_evidence as evidence
sys.path.insert(0,str(ROOT/'.github/ops'))
from freshness import recovery_days, parse_time


def signal(row):
    return {k:str(row.get(k,'')) for k in ('id','publishDate','updateDate')}


def task_from_item(item):
    return formats.task_from_item(item)


def is_required(row,start,end):
    published=s.day(row.get('publishDate'))
    if published and published>end:return False
    return s.within(row.get('publishDate'),start,end) or (
        str(row.get('status','')).lower()=='active' and s.within(row.get('updateDate'),start,end))


def plan(root,out):
    out.mkdir(parents=True,exist_ok=True)
    now=datetime.now(timezone.utc);end=now.date();start=end-timedelta(days=recovery_days(root,end))
    http=s.HTTP(os.getenv('CONGRESS_API_KEY','').strip())
    rows,count=s.api_scan(http,start,end)
    if len(rows)!=count:raise ValueError('Official list incomplete')
    required={r['id']:r for r in rows if is_required(r,start,end)}
    for row in s.read_json(root/'data/official-pending.json',[]):required.setdefault(row['id'],row)
    for row in s.read_json(root/'data/deferred-official-formats.json',[]):required.setdefault(row['id'],row)
    cache=s.read_json(root/'data/official-current.json',{})
    audit_cache=s.read_json(root/'data/audit-detail-cache.json',{})
    for ident,row in required.items():
        candidate=evidence.choose_cached_record(row,[cache.get(ident,{}),audit_cache.get(ident,{})],now,max_age_hours=6)
        if candidate:cache[ident]=candidate
    for ident,value in s.read_json(root/'.github/repairs/official-seed.json',{}).items():cache.setdefault(ident,value)
    unresolved=[]
    for ident,row in required.items():
        item=cache.get(ident,{})
        try:
            fresh=0 <= (now-parse_time(item.get('detail_checked_at',''))).total_seconds() < 6*3600
        except (ValueError,TypeError):
            fresh=False
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


def validate_detail_signal(item,row):
    if s.report_id(item['id']) != s.report_id(row['id']):
        raise ValueError('Official report ID mismatch')
    expected,actual=s.day(row.get('publishDate')),s.day(item.get('publishDate'))
    if expected and (not actual or actual < expected):
        raise ValueError('Official detail publication predates the requested publication')
    # List indexing and detail update timestamps may differ. Preserve
    # the discrepancy and verify live formats/current PDF bytes rather
    # than pretending these timestamps have identical semantics.


def resolve(root,out,plan_path,chunk):
    out.mkdir(parents=True,exist_ok=True)
    p=s.read_json(plan_path,None);http=s.HTTP(os.getenv('CONGRESS_API_KEY','').strip())
    resolved,errors={},[]
    for row in p['chunks'][chunk]:
        ident=row['id']
        try:
            obj=http.json(s.API+'/'+s.report_id(ident)+'?format=json')
            item=formats.report_item(obj)
            if s.report_id(item['id'])!=ident:raise ValueError('Official report ID mismatch')
            validate_detail_signal(item,row)
            resolved[ident]=dict(signal=signal(row),task=task_from_item(item),
                detail_checked_at=datetime.now(timezone.utc).isoformat(),api_metadata=item)
            print('Resolved official current PDF:',ident,flush=True)
        except Exception as exc:
            errors.append(dict(id=ident,error=formats.error_text(exc)));print('Unresolved:',ident,formats.error_text(exc),flush=True)
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
    task=copy.deepcopy(record['task'])
    if task['id']!=record.get('signal',{}).get('id'):
        raise ValueError('Cached official task identity mismatch')
    body,actual,kind,notices=formats.fetch_original(http,task)
    if kind == 'HTML':
        entry,is_new=formats.save_html(root,task,body,actual)
        return entry,is_new,notices
    sha=s.digest(body)
    old=next((v for v in archives if v['id']==task['id'] and v['pdf_sha256']==sha),None)
    if verify_local(root,old):return old,False,notices
    task['api_publication_date']=task['date'];task['date']=cover_date(body,task['date'])
    # The original HTML URL is auxiliary when a verified current PDF is available.
    task['formats']={'PDF': task['formats']['PDF']}
    url=task['formats']['PDF']['urls'][0]
    class Buffered:
        def get(self,candidate):
            if candidate==url:return body,actual
            return http.get(candidate)
        def json(self,candidate):return http.json(candidate)
    entry,is_new,extra=s.archive_task(Buffered(),root,task,archives)
    entry['api_publication_date']=task['api_publication_date']
    if task.get('official_pdf_format_missing'):
        entry['current_format_recovery']={'method':'live currentVersion + official namespace + embedded ID/revision/title',
                                          'currentVersion':task['api_version'],'official_formats_omitted_pdf':True}
    return entry,is_new,notices+extra


def aggregate(root,out,plan_path,parts):
    out.mkdir(parents=True,exist_ok=True)
    p=s.read_json(plan_path,None);http=s.HTTP(os.getenv('CONGRESS_API_KEY','').strip())
    cache=s.read_json(root/'data/official-current.json',{})
    for ident,item in p['cache'].items():cache.setdefault(ident,item)
    for ident,row in p['required'].items():
        candidate=evidence.choose_cached_record(row,[cache.get(ident,{}),p['cache'].get(ident,{})],datetime.now(timezone.utc))
        if candidate:cache[ident]=candidate
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
    html_before={(v['id'],v['sha256']) for v in s.read_json(root/'data/html-original-manifest.json',[])}
    for ident,row in sorted(p['required'].items()):
        record=cache.get(ident,{})
        check=dict(id=ident,title=row.get('title',''),api_publication=row.get('publishDate','')[:10],api_update=row.get('updateDate',''))
        try:
            if record.get('signal')!=signal(row) or not record.get('task'):
                raise ValueError('Current official details do not match the requested signal; retry retained')
            checked=parse_time(record.get('detail_checked_at',''))
            if not 0 <= (datetime.now(timezone.utc)-checked).total_seconds() <= 26*3600:
                raise ValueError('Current official detail evidence expired; retry retained')
            entry,is_new,notices=save_current(http,root,record,archives)
            kind=entry.get('original_format','PDF')
            if kind=='HTML':
                if not formats.verify_html_entry(root,entry):raise ValueError('Saved HTML original failed byte verification')
                path,sha=entry['original'],entry['sha256']
                for key in ('pdf','pdf_sha256','pdf_verified_at'):
                    record.pop(key,None)
            else:
                if not verify_local(root,entry):raise ValueError('Saved PDF failed actual hash verification')
                archives=[v for v in archives if not (v['id']==ident and v['pdf_sha256']==entry['pdf_sha256'])]+[entry]
                path,sha=entry['pdf'],entry['pdf_sha256']
                record.update(pdf_sha256=sha,pdf=path,pdf_verified_at=datetime.now(timezone.utc).isoformat())
            record.update(original_format=kind,original_path=path,original_sha256=sha,
                          markdown=entry['markdown'],original_cover_date=entry['date'],
                          original_verified_at=datetime.now(timezone.utc).isoformat())
            cache[ident]=record
            check.update(verified=True,original_format=kind,original_url=record['task']['formats'][kind]['urls'][0],
                         original_path=path,original_sha256=sha,official_pdf_revision=record['task']['version'],
                         markdown=entry['markdown'],cover_date=entry['date'],new_original=is_new,
                         new_pdf=is_new if kind=='PDF' else False,notices=notices)
            if kind=='PDF':check.update(official_pdf_url=check['original_url'],pdf_sha256=sha,pdf=path)
        except Exception as exc:
            check.update(verified=False,error=formats.error_text(exc));pending.append(row)
            # Preserve useful official API text, but never count it as an original.
            try:
                matching=evidence.choose_cached_record(row,[record],datetime.now(timezone.utc))
                if matching:
                    check['api_summary_supplement']=evidence.archive_api_summary(root,matching)
            except Exception as snapshot_exc:
                check['api_summary_error']=formats.error_text(snapshot_exc)
        checks.append(check);print('Official-current',ident,'verified' if check['verified'] else check['error'],flush=True)
    for item in archives:
        if not verify_local(root,item):raise ValueError('Archive integrity failure: '+item['pdf'])
    archives.sort(key=lambda v:(v['id'],v['date'],v['pdf_sha256']))
    new=[v for v in archives if (v['id'],v['pdf_sha256']) not in before]
    html_entries=s.read_json(root/'data/html-original-manifest.json',[])
    for entry in html_entries:
        if not formats.verify_html_entry(root,entry):raise ValueError('HTML original archive integrity failure: '+entry['id'])
    new_html=[v for v in html_entries if (v['id'],v['sha256']) not in html_before]
    now=datetime.now(timezone.utc).isoformat()
    receipt=dict(checked_at=now,window_start=p['start'],window_end=p['end'],
        official_list_records=p['source_count'],official_current_required=len(checks),
        official_current_verified=sum(c['verified'] for c in checks),official_current_pending=len(pending),
        supplementary_api_summaries=sum(bool(c.get('api_summary_supplement')) for c in checks),
        new_html_original_versions=len(new_html),total_html_original_versions=len(html_entries),
        official_pdf_verified=sum(c.get('verified',False) and c.get('original_format')=='PDF' for c in checks),
        official_html_verified=sum(c.get('verified',False) and c.get('original_format')=='HTML' for c in checks),
        source_refreshed_at=p.get('created_at'),new_pdf_versions=len(new),new_pdf_records=[{k:v[k] for k in ('id','version','date','pdf','markdown','pdf_sha256')} for v in new],
        total_archived_pdf_versions=len(archives),github_run_id=os.getenv('GITHUB_RUN_ID',''),
        github_run_attempt=os.getenv('GITHUB_RUN_ATTEMPT',''),resolution_errors=[f for f in failures if f['id'] in {r['id'] for r in pending}],
        result='verified_for_observed_official_entries' if not pending else 'incomplete',scope=p['coverage_note'],
        metadata_notices=[{'id':i,'list_update_date':r.get('updateDate'),'detail_update_date':cache.get(i,{}).get('api_metadata',{}).get('updateDate') or cache.get(i,{}).get('task',{}).get('observed_update_date'),'note':'List/detail update timestamps differ; current formats were resolved live and PDF bytes verified'} for i,r in p['required'].items() if i not in {r['id'] for r in pending} and (cache.get(i,{}).get('api_metadata',{}).get('updateDate') or cache.get(i,{}).get('task',{}).get('observed_update_date')) != r.get('updateDate')])
    s.write_json(root/'data/official-current.json',cache);s.write_json(root/'data/official-pending.json',pending)
    previous_success=s.read_json(root/'data/last-successful-official.json',{})
    if pending:
        receipt['last_successful_checked_at']=previous_success.get('checked_at')
    else:
        s.write_json(root/'data/last-successful-official.json',receipt)
    s.write_json(root/'data/deferred-official-formats.json',[r for r in s.read_json(root/'data/deferred-official-formats.json',[]) if r['id'] in {v['id'] for v in pending}])
    s.write_json(root/'data/official-status.json',receipt);s.write_json(root/'data/archive-manifest.json',archives)
    s.write_json(root/'data/catalog.json',catalog)
    s.write_json(root/f'data/audits/{p["end"]}-official-current.json',receipt)
    s.write_json(root/'data/audits/latest-official-current-comparisons.json',checks)
    s.export_indexes(root,catalog,archives,date.fromisoformat(p['start']),date.fromisoformat(p['end']))
    lines=['# Official current CRS files','',f"Checked: {now}. Official current entries verified: **{receipt['official_current_verified']}/{len(checks)}**.",
        '', 'The original cover date is distinct from the API update date. Only verified rows link to a current official original (PDF preferred, HTML when supplied).', '',
        '| API update | Cover date | Report | Title | Current original | Full text |','|---|---|---|---|---|---|']
    for c in sorted(checks,key=lambda c:(c['api_update'],c['id']),reverse=True):
        title=c['title'].replace('|','\\|')
        links=f"[{c['original_format']}]({c['original_path']}) | [Markdown]({c['markdown']})" if c['verified'] else 'UNVERIFIED | Retry pending'
        if not c['verified'] and c.get('api_summary_supplement'):
            links="UNVERIFIED | [Supplementary API summary; not original]("+c['api_summary_supplement']['markdown']+")"
        lines.append(f"| {c['api_update'][:10]} | {c.get('cover_date',c['api_publication'])} | {c['id']} v{c.get('official_pdf_revision','?')} | {title} | {links} |")
    s.write(root/'CURRENT.md','\n'.join(lines)+'\n')
    latest=root/'LATEST.md'
    s.write(latest,f"**Official-current verification: {receipt['official_current_verified']}/{len(checks)}. [View current official files](CURRENT.md).**\n\n"+latest.read_text())
    with (root/'data/audits/latest-official-current.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,['id','title','api_publication','api_update','cover_date','official_pdf_revision','verified','official_pdf_url','pdf_sha256','pdf','markdown','error','original_format','original_url','original_path','original_sha256'],extrasaction='ignore')
        writer.writeheader();writer.writerows(checks)
    status=s.read_json(root/'data/status.json',{})
    status.update(official_current_required=len(checks),official_current_verified=receipt['official_current_verified'],
        official_current_pending=len(pending),official_reconciled_at=now,official_new_pdf_versions=len(new),
        total_html_original_versions=len(html_entries),
        total_archived_pdf_versions=len(archives),total_html_snapshots=sum(bool(v.get('html')) for v in archives),
        total_pdf_bytes=sum((root/v['pdf']).stat().st_size for v in archives))
    if pending:status.update(result='failed',primary_pdf_complete=False)
    elif not status.get('errors') and not status.get('required_pdf_failures'):
        status.update(result='success_with_warnings' if status.get('warnings') or status.get('historical_pending_versions') else 'success',primary_pdf_complete=True)
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