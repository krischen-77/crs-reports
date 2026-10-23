"""Regression: same URL/signal is NOT proof that live PDF bytes are unchanged."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools'))

class CurrentBytesTests(unittest.TestCase):
    def test_current_pdf_is_downloaded_even_when_cached_hash_is_valid(self):
        import official_pipeline as p
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'saved.pdf').write_bytes(b'old');(root/'saved.md').write_text('old')
            old={'id':'R10001','pdf':'saved.pdf','markdown':'saved.md','pdf_sha256':p.s.digest(b'old')}
            url='https://www.congress.gov/crs_external_products/R/PDF/R10001/R10001.1.pdf'
            record={'task':{'id':'R10001','formats':{'PDF':{'urls':[url]}}},'signal':{'id':'R10001'},'pdf_sha256':old['pdf_sha256']}
            http=Mock();http.get.side_effect=RuntimeError('network probe reached')
            with self.assertRaisesRegex(RuntimeError,'network probe reached'):
                p.save_current(http,root,record,[old])
            http.get.assert_called_once_with(url)

if __name__=='__main__':unittest.main()
