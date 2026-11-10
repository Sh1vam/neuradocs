# runner/server.py -- the sandbox as a service. It runs in its own container (no internet, read-only root, non-root user,
# memory/CPU/process limits from docker-compose). The app sends files and a command; this returns the output.
import hmac
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TOKEN = os.environ.get('SANDBOX_TOKEN', '')
WORK = Path(os.environ.get('WORKDIR', '/work'))
ALLOWED = {'python', 'pytest'}
MAX_OUT, MAX_BODY = 20_000, 4_000_000
slots = threading.BoundedSemaphore(int(os.environ.get('SANDBOX_SLOTS', '2')))     # jobs at once (the memory limit is shared)


def run_job(files, argv, timeout):
    WORK.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(dir=WORK)).resolve()
    try:
        for rel, text in files.items():
            p = (root / rel).resolve()
            if rel.startswith(('/', '\\')) or not p.is_relative_to(root):
                return 2, 'rejected path: ' + rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding='utf-8')
        if not argv or argv[0] not in ALLOWED:
            return 2, 'command not allowed: ' + (argv[0] if argv else '(empty)')
        cmd = [sys.executable if argv[0] == 'python' else argv[0]] + list(argv[1:])
        env = {'PATH': os.environ.get('PATH', ''), 'HOME': str(root), 'PYTHONDONTWRITEBYTECODE': '1'}   # no secrets in here
        try:
            r = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=timeout, env=env)
            return r.returncode, (r.stdout + r.stderr)[-MAX_OUT:]
        except subprocess.TimeoutExpired:
            return 124, f'timed out after {timeout}s'
    finally:
        shutil.rmtree(root, ignore_errors=True)


class Handler(BaseHTTPRequestHandler):
    def reply(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.reply(200 if self.path == '/health' else 404, {'ok': self.path == '/health'})

    def do_POST(self):
        sent = self.headers.get('X-Token', '')
        if self.path != '/run' or not TOKEN or not hmac.compare_digest(sent, TOKEN):
            return self.reply(401, {'error': 'unauthorized'})
        n = int(self.headers.get('Content-Length', 0))
        if n > MAX_BODY:
            return self.reply(413, {'error': 'too large'})
        try:
            job = json.loads(self.rfile.read(n))
            files, argv, timeout = job['files'], job['argv'], min(int(job.get('timeout', 60)), 300)
        except Exception:
            return self.reply(400, {'error': 'bad request'})
        with slots:
            rc, out = run_job(files, argv, timeout)
        self.reply(200, {'rc': rc, 'output': out})

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    ThreadingHTTPServer((os.environ.get('HOST', '0.0.0.0'), int(os.environ.get('PORT', '9000'))), Handler).serve_forever()
