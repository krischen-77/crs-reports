#!/usr/bin/env python3
"""Apply the SHA-pinned, locally tested source diff; never touch archives or secrets."""
from pathlib import Path
import base64
import hashlib
import json
import lzma
import subprocess

root = Path(__file__).resolve().parents[2]
bits = ''.join((root / f'.github/repairs/refresh-patch-{i}.b64').read_text().strip() for i in range(4))
raw = lzma.decompress(base64.b64decode(bits, validate=True))
if hashlib.sha256(raw).hexdigest() != 'b5fd3bc08b3304df8dcde5ba93c98740ea6098fbcb7a7d606de93b52b824dab9':
    raise RuntimeError('Repair payload checksum mismatch')
payload = json.loads(raw)
allowed = {
    'scripts/crs_formats.py', 'scripts/sync_crs.py', 'tools/official_pipeline.py',
    'tools/tests/test_original_formats.py', '.github/current-verification/verify_current.py',
    '.github/ops/reliability.py', '.github/ops/dispatch_next.py',
    '.github/ops/tests/test_quiet_monitoring.py', 'docs/repair-2026-10-24.md',
}
if set(payload['checks']) != allowed:
    raise RuntimeError('Unexpected repair scope')
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
actual = {name: digest(root / name) for name in allowed}
if all(actual[n] == c['after_sha256'] for n, c in payload['checks'].items()):
    print('Reviewed source repair already applied')
else:
    for name, check in payload['checks'].items():
        if actual[name] != check['before_sha256']:
            raise RuntimeError('Source changed since review; refusing overwrite: ' + name)
    patch = payload['patch'].encode()
    subprocess.run(['git', 'apply', '--check', '--whitespace=nowarn', '-'], input=patch, cwd=root, check=True)
    subprocess.run(['git', 'apply', '--whitespace=nowarn', '-'], input=patch, cwd=root, check=True)
    for name, check in payload['checks'].items():
        if digest(root / name) != check['after_sha256']:
            raise RuntimeError('Applied source checksum mismatch: ' + name)
    print('Applied 9 reviewed source/test/document files; archives untouched')
