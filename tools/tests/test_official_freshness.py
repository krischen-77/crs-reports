import contextlib,io,tempfile,unittest,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import official_pipeline as p
class FreshnessTests(unittest.TestCase):
    def test_old_cache_cannot_hide_failed_refresh(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'data').mkdir();parts=root/'parts';parts.mkdir()
            row={'id':'R10001','title':'Example','publishDate':'2026-07-31','updateDate':'2026-10-22'}
            task={'id':'R10001','title':'Example','date':'2026-07-31','version':'5','formats':{'PDF':{'urls':['https://www.congress.gov/example.pdf'],'sha1':''}}}
            cache={'R10001':{'signal':p.signal(row),'task':task,'detail_checked_at':'2026-10-22T23:00:00Z','pdf_sha256':'unused'}}
            plan={'start':'2026-10-16','end':'2026-10-23','cache':cache,'required':{'R10001':row},'official_rows':[row],'source_count':1,'coverage_note':'test'}
            p.s.write_json(root/'plan.json',plan)
            with patch.object(p,'save_current',side_effect=AssertionError('Stale cache must not reach archive reuse')) as save,contextlib.redirect_stdout(io.StringIO()):
                result=p.aggregate(root,root/'out',root/'plan.json',parts)
            self.assertEqual(result,1);save.assert_not_called()
            self.assertEqual(len(p.s.read_json(root/'data/official-pending.json',[])),1)
