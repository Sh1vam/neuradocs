# sandbox_check.py -- is the Docker sandbox usable? Used by run.py (preflight) and /api/sandbox/status.
import os
import shutil
import subprocess

IMAGE = 'agent-sandbox:latest'
BUILD = 'docker build -t agent-sandbox:latest -f docuteam/sandbox/Dockerfile docuteam/sandbox'


def status():
    if os.getenv('SANDBOX_URL'):                          # online deployment: ask the sandbox service
        import sandbox_client
        ok = sandbox_client.health()
        return {'ok': ok, 'reason': 'sandbox service ready' if ok else 'the sandbox service does not answer'}
    if not shutil.which('docker'):
        return {'ok': False, 'reason': 'Docker is not installed or not on PATH'}
    try:
        r = subprocess.run(['docker', 'image', 'inspect', IMAGE], capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired:
        return {'ok': False, 'reason': 'Docker did not answer: is Docker Desktop running?'}
    if r.returncode == 0:
        return {'ok': True, 'reason': 'ready'}
    err = (r.stderr or '').lower()
    if 'daemon' in err or 'pipe' in err or 'connect' in err:
        return {'ok': False, 'reason': 'Docker is installed but not running: start Docker Desktop'}
    return {'ok': False, 'reason': 'the sandbox image is missing, build it with: ' + BUILD}
