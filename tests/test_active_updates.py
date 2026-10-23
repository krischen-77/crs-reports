"""Regressions: active updates must not disappear behind old publication dates."""
import contextlib
import io
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from scripts import sync_crs as s
from test_sync import FakeHTTP, make_pdf

START, END = date(2026,10,16), date(2026,10,23)
class ActiveUpdateTests(unittest.TestCase):
    def row(self,status="Active"):
        return dict(id="R49057",title="Synthetic report",publishDate="2026-07-31T04:00:00Z",updateDate="2026-10-22T13:38:13Z",status=status,version=1)
    def test_active_old_cover_date_still_checked(self):
        required,metadata=s.publication_candidates([self.row()],{},START,END)
        self.assertIn("R49057",required);self.assertTrue(required["R49057"]["required_by_recent_update"]);self.assertFalse(metadata)
    def test_archived_mass_history_still_not_downloaded(self):
        required,metadata=s.publication_candidates([self.row("Archived")],{},START,END)
        self.assertFalse(required);self.assertEqual(len(metadata),1)
    def test_active_future_publication_not_backfilled(self):
        required,_=s.publication_candidates([{**self.row(),"publishDate":"2026-10-24"}],{},START,END)
        self.assertFalse(required)
    def test_recent_update_retry_not_demoted_to_optional_history(self):
        t=dict(id="R49057",date="2026-07-31",required_by_recent_update=True,formats={"PDF":{"urls":["https://www.congress.gov/x.pdf"]}})
        pending,bg=s.split_pending({"reports":[],"tasks":[t]},[],START)
        self.assertEqual(pending["tasks"],[t]);self.assertFalse(bg)
    def test_recent_update_promoted_from_history(self):
        t=dict(id="R49057",date="2026-07-31",required_by_recent_update=True,formats={"PDF":{"urls":["https://www.congress.gov/x.pdf"]}})
        pending,bg=s.split_pending({"reports":[],"tasks":[]},[{"task":t}],START)
        self.assertEqual(pending["tasks"],[t]);self.assertFalse(bg)
    def test_active_old_publication_saved_and_visible_in_latest(self):
        pdf=make_pdf();ident="R49057";url=s.MIRROR+"files/R49057.pdf"
        obj={"id":ident,"versions":[{"id":"R49057_A5_2026-07-31","title":"Synthetic report","date":"2026-07-31","formats":[{"format":"PDF","filename":"files/R49057.pdf","sha1":s.digest(pdf,"sha1")}]}]}
        rows={f"R{20000+i}":{"id":f"R{20000+i}","published":"2001-01-01","mirror_metadata":"fixture"} for i in range(1000)}
        rows[ident]={"id":ident,"published":"2026-07-31"}
        class HTTP(FakeHTTP):
            def __init__(self,*args):
                super().__init__({s.MIRROR+"reports.csv":b"fixture",s.RSS:b"<rss><channel/></rss>",url:pdf})
                self.has_key,self.api_calls,self.api_remaining=False,0,None
            def json(self,url):return obj
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);args=SimpleNamespace(root=d,until="2026-10-23",days=7,full_catalog=False,historical_limit=0)
            with patch.object(s,"HTTP",HTTP),patch.object(s,"api_scan",return_value=([self.row()],1)),patch.object(s,"parse_catalog",return_value=rows),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(s.sync(args),0)
            m=s.read_json(root/"data/archive-manifest.json",[])
            self.assertEqual(len(m),1);self.assertEqual(m[0]["date"],"2026-07-31")
            latest=(root/"LATEST.md").read_text();self.assertIn("older publication dates",latest);self.assertIn("R49057",latest)
            self.assertTrue((root/"data/sources/congress-api-latest.json").is_file())

if __name__=="__main__":unittest.main()
