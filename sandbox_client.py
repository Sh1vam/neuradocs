# sandbox_client.py -- talks to the sandbox service (runner/server.py) when SANDBOX_URL is set (docker-compose does this).
import json
import os
import urllib.request
from pathlib import Path


def configured():
    return bool(os.getenv('SANDBOX_URL'))


def _call(path, payload=None, timeout=30):
    req = urllib.request.Request(os.environ['SANDBOX_URL'].rstrip('/') + path,
                                 data=None if payload is None else json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json', 'X-Token': os.getenv('SANDBOX_TOKEN', '')})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        raise RuntimeError(f'sandbox service unreachable or refused the job: {e}')


def run(files, argv, timeout=60, install=False):
    d = _call('/run', {'files': files, 'argv': argv, 'timeout': timeout, 'install': install}, timeout + 15 + (180 if install else 0))
    return d['rc'], d['output']


def run_folder(folder, argv, timeout=120, install=False):
    folder, files = Path(folder), {}
    for p in sorted(folder.rglob('*')):
        if p.is_file() and not {'__pycache__', '.pytest_cache'} & set(p.parts) and p.stat().st_size < 200_000:
            files[p.relative_to(folder).as_posix()] = p.read_text(encoding='utf-8', errors='replace')
    return run(files, argv, timeout, install)


def health():
    try:
        return bool(_call('/health', timeout=5).get('ok'))
    except RuntimeError:
        return False
