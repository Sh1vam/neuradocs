# sandbox.py -- Docker sandbox, run by YOUR code and never exposed as an agent tool (Chapter 07, Part H)
import os
import subprocess

from config import WORKSPACE

IMAGE = 'agent-sandbox:latest'
CODE_DIR = (WORKSPACE / 'code').resolve()
CODE_DIR.mkdir(exist_ok=True)
MOUNT = str(CODE_DIR).replace('\\', '/')          # Docker Desktop on Windows accepts C:/path form


def _docker(args, **kw):
    try:
        return subprocess.run(['docker'] + args, capture_output=True, text=True, **kw)
    except FileNotFoundError:
        raise RuntimeError('Docker is not installed or not on PATH (see SETUP.md)')


def create(name):
    return _docker(['run', '-d', '--name', name, '--network', os.environ.get('SANDBOX_NETWORK', 'none'), '--memory', '2g', '--cpus', '2',
                    '--pids-limit', '256', '--read-only', '--tmpfs', '/tmp',
                    '-v', MOUNT + ':/work', '--restart', 'unless-stopped', IMAGE])


def ensure_sandbox(name):
    r = _docker(['inspect', '-f', '{{.State.Running}}', name])
    if r.returncode != 0:
        c = create(name)                              # missing: rebuild; the work is in the mounted folder
        if c.returncode != 0:
            raise RuntimeError('could not create the sandbox: ' + c.stderr[-500:])
    elif r.stdout.strip() != 'true':
        _docker(['start', name])


def exec_in(name, argv, timeout=120):
    cmd = ['exec', '-w', '/work', name, 'timeout', str(timeout)] + argv
    r = _docker(cmd, timeout=timeout + 10)
    return r.returncode, (r.stdout + r.stderr)[-4000:]


def run_in_background(name, shell_line):
    # for long runs: output goes to the persistent folder, e.g.
    # run_in_background('docuteam-sb', 'pytest -q > logs/test.log 2>&1; echo finished > logs/test.done')
    _docker(['exec', '-d', '-w', '/work', name, 'sh', '-c', shell_line])
