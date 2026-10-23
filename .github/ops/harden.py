"""Idempotent, exact-match migration; refuses to overwrite unexpected source changes."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def patch(path, old, new):
    target=ROOT/path; text=target.read_text('utf-8')
    if new in text:
        return
    if text.count(old)!=1:
        raise RuntimeError('Unexpected source; manual reconciliation required: '+path)
    target.write_text(text.replace(old,new,1),'utf-8')

patch('tools/official_pipeline.py','import sync_crs as s',
      "import sync_crs as s\nsys.path.insert(0,str(ROOT/'.github/ops'))\nfrom freshness import recovery_days, parse_time")
patch('tools/official_pipeline.py','start=end-timedelta(days=7)',
      'start=end-timedelta(days=recovery_days(root,end))')
patch('tools/official_pipeline.py',"fresh=str(item.get('detail_checked_at',''))[:10]==str(end)",
      "fresh=(str(item.get('detail_checked_at',''))[:10]==str(end) and (now-parse_time(item['detail_checked_at'])).total_seconds() < 6*3600)")
patch('tools/official_pipeline.py',"task=copy.deepcopy(record['task']);expected=record.get('pdf_sha256')",
      "task=copy.deepcopy(record['task']) # Live current bytes must be fetched on every reconciliation.")
patch('tools/official_pipeline.py',
      "    old=next((v for v in archives if v['id']==task['id'] and expected and v['pdf_sha256']==expected),None)\n    if verify_local(root,old):return old,False,[]",
      '    # A valid local hash does not prove that an unchanged URL still serves the same bytes.')
patch('.github/current-verification/verify_current.py','s=a.s',
      "s=a.s\nsys.path.insert(0,str(ROOT/'.github/ops'))\nfrom freshness import recovery_days")
patch('.github/current-verification/verify_current.py','start=end-timedelta(days=7)',
      'start=end-timedelta(days=recovery_days(ROOT,end))')
patch('.github/current-verification/verify_current.py',"github_run_id=os.getenv('GITHUB_RUN_ID',''),sources={}",
      "github_run_id=os.getenv('GITHUB_RUN_ID',''),github_run_attempt=os.getenv('GITHUB_RUN_ATTEMPT',''),sources={}")
readme=ROOT/'README.md';text=readme.read_text('utf-8')
notice='## 每日刷新可靠性\n\n每天北京时间 **06:23、18:23** 执行；随后自动官方当前版本对账和独立原文核验。每小时独立看门狗检查，超过 26 小时未成功刷新或流程失败时创建／更新告警 Issue，并进行有上限的自动重试。监控自身的提交不计作源站刷新。\n\n[刷新健康状态](HEALTH.md) · [可靠性规则与边界](docs/daily-reliability.md) · [官方当前版本](CURRENT.md)\n\n'
if '## 每日刷新可靠性' not in text:
    first=text.index('\n')+1;text=text[:first]+'\n'+notice+text[first:]
text=text.replace('**每天 10:23 UTC / 北京时间 18:23**，cron `23 10 * * *`',
                  '**每天 10:23、22:23 UTC / 北京时间 18:23、06:23**，cron `23 10,22 * * *`')
readme.write_text(text,'utf-8')
print('Exact-match reliability migration applied. Tests must pass before commit.')
