import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import official_pipeline as p
class SignalTests(unittest.TestCase):
    def test_indexing_timestamp_difference_is_not_publication_loss(self):
        p.validate_detail_signal({'id':'R10001','publishDate':'2026-10-22','updateDate':'2026-10-23T06:53:00Z'},{'id':'R10001','publishDate':'2026-10-22','updateDate':'2026-10-23T07:08:00Z'})
    def test_older_publication_is_not_accepted(self):
        with self.assertRaises(ValueError):p.validate_detail_signal({'id':'R10001','publishDate':'2026-10-21'},{'id':'R10001','publishDate':'2026-10-22'})
    def test_wrong_report_is_not_accepted(self):
        with self.assertRaises(ValueError):p.validate_detail_signal({'id':'R10002','publishDate':'2026-10-22'},{'id':'R10001','publishDate':'2026-10-22'})
